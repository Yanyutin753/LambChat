"""SSE 通道传输：连接 / 帧解析 / 结果回传 / offline / 退避计算。

- 服务端契约（M1 真机实测）：``GET /api/sandbox/channel`` 返回 SSE，
  帧 ``event: hello|tool_call`` + ``data: <单行 JSON>``，注释行 ``: heartbeat`` 作心跳；
  ``POST /api/sandbox/results/{call_id}`` body ``{"stage","status","stdout","stderr","exit_code","error"}``；
  ``POST /api/sandbox/offline`` 优雅下线（服务端 T7 补）。
- 401/403 抛 :class:`TransportAuthError`（不重连，需重新 login）；网络异常原样上抛，
  由调用方（daemon）捕获后按 :func:`backoff_delay` 重连——transport 只保证单连接语义。
"""

from __future__ import annotations

import contextlib
import json
import random
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx

BACKOFF_MAX_S = 60.0
BACKOFF_JITTER = 0.2  # ±20%

AUTH_STATUSES = frozenset({401, 403})

_StreamCM = contextlib.AbstractAsyncContextManager[httpx.Response]


class TransportError(Exception):
    """通道传输失败（非认证）。"""


class TransportAuthError(TransportError):
    """PAT 失效或无权限（401/403）；调用方不应重连，应提示重新 login。"""


@dataclass
class ToolCall:
    """一条 tool_call 帧（data 单行 JSON 的结构化形态）。"""

    call_id: str
    op: str
    payload: dict[str, Any]
    timeout: float


def backoff_delay(attempt: int, *, rand: random.Random | None = None) -> float:
    """第 attempt 次重试（1-based）的退避秒数：基线 1,2,4,... 封顶 60，±20% 抖动。

    rand 供测试注入随机源/seed；默认每次新建系统熵种子。
    """
    exponent = min(max(1, attempt) - 1, 6)  # 2^6=64 已越过 60 封顶，同时避免大指数溢出
    base = min(BACKOFF_MAX_S, 2.0**exponent)
    r = rand if rand is not None else random.Random()
    return base * (1.0 + r.uniform(-BACKOFF_JITTER, BACKOFF_JITTER))


@dataclass
class _Frame:
    event: str
    data: str


class _FrameParser:
    """SSE 行级解析状态机：喂数据一行，帧完成（空行）时产出一帧。

    - 注释行（``: heartbeat``）与未知字段（id:/retry: 等）忽略；
    - ``data:`` 多行按 SSE 规范以 ``\\n`` 拼接（M1 服务端实发单行）；
    - 只有 event 与 data 齐备的帧才会产出，残缺帧在空行处静默丢弃。
    """

    def __init__(self) -> None:
        self._event: str | None = None
        self._data: list[str] = []

    def feed(self, line: str) -> _Frame | None:
        if line == "":
            frame = None
            if self._event is not None and self._data:
                frame = _Frame(event=self._event, data="\n".join(self._data))
            self._event = None
            self._data = []
            return frame
        if line.startswith(":"):
            return None
        field, sep, value = line.partition(":")
        if sep and value.startswith(" "):
            value = value[1:]
        if field == "event" and value:
            self._event = value
        elif field == "data":
            self._data.append(value)
        return None


class ChannelClient:
    """单连接 SSE 通道客户端 + 结果回传。

    ``connect()`` 返回 ``(hello_data, async_iterator)``：hello 帧先读到并直接回传，
    之后迭代器只产出 :class:`ToolCall`。连接生命周期绑定在该迭代器上——
    迭代完毕或提前 ``aclose()`` 时关闭底层流。
    """

    def __init__(
        self, server_url: str, pat: str, *, client: httpx.AsyncClient | None = None
    ) -> None:
        self._base = server_url.rstrip("/")
        self._pat = pat
        self._client = client if client is not None else httpx.AsyncClient(timeout=None)

    async def connect(self) -> tuple[dict[str, Any], AsyncIterator[ToolCall]]:
        """建立 SSE 通道，读到 hello 帧后返回 (hello 数据, tool_call 迭代器)。"""
        cm = self._client.stream(
            "GET",
            f"{self._base}/api/sandbox/channel",
            headers={"Authorization": f"Bearer {self._pat}", "Accept": "text/event-stream"},
        )
        response = await cm.__aenter__()
        parser = _FrameParser()
        try:
            _raise_for_status(response, "channel")
            hello: dict[str, Any] | None = None
            async for line in response.aiter_lines():
                frame = parser.feed(line)
                if frame is None or frame.event != "hello":
                    continue
                data = _parse_json_object(frame.data)
                if data is not None:
                    hello = data
                    break
            if hello is None:
                raise TransportError("SSE 通道在 hello 帧前关闭")
        except BaseException:
            await cm.__aexit__(None, None, None)
            raise
        return hello, self._iter_tool_calls(response, cm, parser)

    async def _iter_tool_calls(
        self,
        response: httpx.Response,
        cm: _StreamCM,
        parser: _FrameParser,
    ) -> AsyncIterator[ToolCall]:
        try:
            async for line in response.aiter_lines():
                frame = parser.feed(line)
                if frame is None or frame.event != "tool_call":
                    continue
                call = _parse_tool_call(frame.data)
                if call is not None:
                    yield call
        finally:
            await cm.__aexit__(None, None, None)

    async def post_result(self, call_id: str, body: dict[str, Any]) -> None:
        """回传执行结果；body 中值为 None 的字段按契约剔除（exclude_none）。"""
        response = await self._client.post(
            f"{self._base}/api/sandbox/results/{call_id}",
            json={k: v for k, v in body.items() if v is not None},
            headers=self._auth_headers(),
        )
        _raise_for_status(response, "post_result")

    async def post_offline(self) -> None:
        """优雅退出通知（服务端 offline 端点）。"""
        response = await self._client.post(
            f"{self._base}/api/sandbox/offline", headers=self._auth_headers()
        )
        _raise_for_status(response, "post_offline")

    async def close(self) -> None:
        await self._client.aclose()

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._pat}"}


def _raise_for_status(response: httpx.Response, context: str) -> None:
    if response.is_success:
        return
    if response.status_code in AUTH_STATUSES:
        raise TransportAuthError(
            f"{context}: HTTP {response.status_code}（PAT 失效或无权限，请重新 login）"
        )
    raise TransportError(f"{context}: HTTP {response.status_code}")


def _parse_json_object(data: str) -> dict[str, Any] | None:
    try:
        obj = json.loads(data)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _parse_tool_call(data: str) -> ToolCall | None:
    """data JSON 解析失败或缺关键字段时返回 None（调用方跳过该帧，不抛异常）。"""
    obj = _parse_json_object(data)
    if obj is None:
        return None
    call_id = obj.get("call_id")
    op = obj.get("op")
    if not isinstance(call_id, str) or not call_id or not isinstance(op, str) or not op:
        return None
    payload = obj.get("payload", {})
    if not isinstance(payload, dict):
        return None
    try:
        timeout = float(obj.get("timeout", 0.0))
    except (TypeError, ValueError):
        return None
    return ToolCall(call_id=call_id, op=op, payload=payload, timeout=timeout)
