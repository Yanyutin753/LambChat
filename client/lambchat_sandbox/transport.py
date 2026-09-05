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
from urllib.parse import quote

import httpx

from lambchat_sandbox import __version__
from lambchat_sandbox.platform import daemon_platform

BACKOFF_MAX_S = 60.0
BACKOFF_JITTER = 0.2  # ±20%

# 通道 SSE 的读超时（秒）：服务端每 15s 发 `: heartbeat`，45s = 3 次心跳
# 容错。后端重启/中间代理吞掉断开时连接会静默僵死——读超时把它判定为
# TransportError 进入退避重连，而不是永远挂在 read 上。
_CHANNEL_READ_TIMEOUT_S = 45.0
_CHANNEL_CONNECT_TIMEOUT_S = 10.0

# 结果回传/offline 通知的 per-request 超时（秒）。client 全局 timeout=None 是给
# SSE 长连接用的（心跳流不能被读超时切断），POST 沿用同一默认时服务端半死会让
# 回传永久挂起，拖垮 daemon 主循环。
POST_TIMEOUT_S = 10.0

AUTH_STATUSES = frozenset({401, 403})

_StreamCM = contextlib.AbstractAsyncContextManager[httpx.Response]


class TransportError(Exception):
    """通道传输失败（非认证）。"""


class TransportAuthError(TransportError):
    """PAT 失效或无权限（401/403）；调用方不应重连，应提示重新 login。"""


class UpdateRequiredError(TransportError):
    """服务端 426 版本门拒连（body 错误码 ``daemon_version_unsupported``）。

    daemon 版本低于 ``SANDBOX_MIN_DAEMON_VERSION``：调用方应提示升级
    （``lambchat_sandbox update``）并停机退出——退避重连没有意义，版本
    不会自己变新。异常串携带服务端 message。
    """


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
        self,
        server_url: str,
        pat: str,
        *,
        confirm_policy: str = "",
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._base = server_url.rstrip("/")
        self._pat = pat
        self._confirm_policy = confirm_policy
        self._client = (
            client
            if client is not None
            else httpx.AsyncClient(
                timeout=httpx.Timeout(
                    connect=_CHANNEL_CONNECT_TIMEOUT_S,
                    read=_CHANNEL_READ_TIMEOUT_S,
                    write=30.0,
                    pool=30.0,
                )
            )
        )

    async def connect(self) -> tuple[dict[str, Any], AsyncIterator[ToolCall]]:
        """建立 SSE 通道，读到 hello 帧后返回 (hello 数据, tool_call 迭代器)。

        URL 携带 ``?version={__version__}&platform={归一平台}``：客户端版本与
        平台随每次建连上报（服务端访问日志与注册表均可见）——平台是服务端
        文件命令生成分支（M4 T3）的依据，与版本同链路扩展；``confirm_policy``
        （all/commands/none）是服务端统一确认门的策略来源，随连接上报进
        注册表第四段（空值省略参数，服务端按未上报归 all 保守确认）。
        """
        policy_param = (
            f"&confirm_policy={quote(self._confirm_policy)}" if self._confirm_policy else ""
        )
        cm = self._client.stream(
            "GET",
            f"{self._base}/api/sandbox/channel"
            f"?version={quote(__version__)}&platform={quote(daemon_platform())}{policy_param}",
            headers={"Authorization": f"Bearer {self._pat}", "Accept": "text/event-stream"},
        )
        response = await cm.__aenter__()
        parser = _FrameParser()
        # 关键：整个连接生命周期只用这一个行生成器。hello 阶段推进它，
        # 之后把同一生成器交给 _iter_tool_calls 续读——对同一 Response 二次调用
        # aiter_lines() 在真实（不可重放）流上会抛 StreamConsumed。
        lines = response.aiter_lines()
        try:
            await _raise_for_status(response, "channel")
            hello: dict[str, Any] | None = None
            async for line in lines:
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
        return hello, self._iter_tool_calls(lines, cm, parser)

    async def _iter_tool_calls(
        self,
        lines: AsyncIterator[str],
        cm: _StreamCM,
        parser: _FrameParser,
    ) -> AsyncIterator[ToolCall]:
        try:
            async for line in lines:
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
            f"{self._base}/api/sandbox/results/{quote(call_id, safe='')}",
            json={k: v for k, v in body.items() if v is not None},
            headers=self._auth_headers(),
            timeout=POST_TIMEOUT_S,
        )
        await _raise_for_status(response, "post_result")

    async def post_offline(self) -> None:
        """优雅退出通知（服务端 offline 端点）。"""
        response = await self._client.post(
            f"{self._base}/api/sandbox/offline",
            headers=self._auth_headers(),
            timeout=POST_TIMEOUT_S,
        )
        await _raise_for_status(response, "post_offline")

    async def close(self) -> None:
        await self._client.aclose()

    def _auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._pat}"}


async def _version_gate_message(response: httpx.Response) -> str | None:
    """426 响应体解析服务端错误码：``daemon_version_unsupported`` 时返回 message。

    非 JSON / code 不匹配 / detail 形态不符 → None（宁缺毋滥：升级停机是重
    决策，只认明确的服务端契约，普通 426 走 TransportError 退避路径）。真实
    流响应先 ``aread()`` 落缓冲再解析；已缓冲响应 ``aread()`` 是 no-op。
    message 缺失/空白时兜底通用文案。
    """
    try:
        await response.aread()
        payload = response.json()
    except Exception:  # noqa: BLE001 - 解析尽力而为，失败按普通 426 处理
        return None
    detail = payload.get("detail") if isinstance(payload, dict) else None
    if not isinstance(detail, dict) or detail.get("code") != "daemon_version_unsupported":
        return None
    message = detail.get("message")
    if isinstance(message, str) and message.strip():
        return message
    return "daemon version unsupported"


async def _raise_for_status(response: httpx.Response, context: str) -> None:
    if response.is_success:
        return
    if response.status_code == 426:
        message = await _version_gate_message(response)
        if message is not None:
            raise UpdateRequiredError(f"{context}: {message}")
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
