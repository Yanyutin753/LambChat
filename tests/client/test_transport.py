"""SSE 通道客户端：连接解析 / 结果回传 / offline / 退避序列。

服务端契约（M1 真机实测）：GET /api/sandbox/channel 返回 SSE，帧形如
``event: hello\\ndata: {...}\\n\\n`` / ``event: tool_call\\ndata: {...}\\n\\n``，
注释行 ``: heartbeat`` 作心跳；结果 POST /api/sandbox/results/{call_id}；
退出 POST /api/sandbox/offline。
"""

import json
import random

import httpx
import pytest

from lambchat_sandbox.transport import (
    ChannelClient,
    ToolCall,
    TransportAuthError,
    TransportError,
    _FrameParser,
    backoff_delay,
)

SERVER = "https://lc.example"
PAT = "pat-secret-1"

HEARTBEAT = ": heartbeat\n\n"


def _frame(event: str, data: str) -> str:
    return f"event: {event}\ndata: {data}\n\n"


GOOD_STREAM = (
    HEARTBEAT
    + _frame("hello", '{"sandbox_id": "sbx-1", "heartbeat_s": 15}')
    + HEARTBEAT
    + _frame(
        "tool_call",
        '{"call_id": "c1", "user_id": "u1", "op": "exec",'
        ' "payload": {"command": "echo hi"}, "timeout": 5.0, "ts": 1}',
    )
    + _frame(
        "tool_call",
        '{"call_id": "c2", "user_id": "u1", "op": "download",'
        ' "payload": {"path": "a.txt"}, "timeout": 10.0, "ts": 2}',
    )
)


def _sse_transport(
    log: list[httpx.Request], content: bytes, *, status: int = 200
) -> httpx.MockTransport:
    """假造 SSE 服务端；记录收到的请求供断言。"""

    def handler(request: httpx.Request) -> httpx.Response:
        log.append(request)
        return httpx.Response(
            status,
            content=content,
            headers={"content-type": "text/event-stream"},
        )

    return httpx.MockTransport(handler)


def _api_transport(log: list[httpx.Request], *, status: int = 200) -> httpx.MockTransport:
    """假造结果回传服务端（任意路径返回同一 JSON）。"""

    def handler(request: httpx.Request) -> httpx.Response:
        log.append(request)
        return httpx.Response(status, json={"ok": True})

    return httpx.MockTransport(handler)


def _client(transport: httpx.AsyncBaseTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=transport, timeout=None)


def _channel_client(transport: httpx.AsyncBaseTransport) -> ChannelClient:
    return ChannelClient(SERVER, PAT, client=_client(transport))


class _OneShotStream(httpx.AsyncByteStream):
    """一次性异步字节流：模拟真实网络响应——消费即尽，绝不可重放。"""

    def __init__(self, payload: bytes, chunk_size: int = 8) -> None:
        self._chunks = [payload[i : i + chunk_size] for i in range(0, len(payload), chunk_size)]
        self._iterated = False

    async def __aiter__(self):
        if self._iterated:
            raise RuntimeError("one-shot stream iterated twice")
        self._iterated = True
        for chunk in self._chunks:  # 8 字节分块：顺带压测跨块行重组
            yield chunk


class _RealStreamTransport(httpx.AsyncBaseTransport):
    """真实流服务端：``Response(200, stream=...)``，无 ``_content`` 缓存、不可重放。

    ``httpx.Response(status, content=...)`` 会预读出可重放的 ``_content``，
    二次 ``aiter_lines()`` 从字节 0 整体重放——这正是掩盖 ``StreamConsumed``
    假绿的根源；本 transport 堵死该路径。
    """

    def __init__(self, log: list[httpx.Request], payload: bytes) -> None:
        self._log = log
        self._payload = payload

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self._log.append(request)
        return httpx.Response(
            200,
            headers={"content-type": "text/event-stream; charset=utf-8"},
            stream=_OneShotStream(self._payload),
        )


# ---------- connect：hello + tool_call 迭代 ----------


async def test_connect_returns_hello_and_iterates_tool_calls():
    log: list[httpx.Request] = []
    client = _channel_client(_sse_transport(log, GOOD_STREAM.encode("utf-8")))
    hello, calls = await client.connect()

    assert hello == {"sandbox_id": "sbx-1", "heartbeat_s": 15}
    assert [c async for c in calls] == [
        ToolCall(call_id="c1", op="exec", payload={"command": "echo hi"}, timeout=5.0),
        ToolCall(call_id="c2", op="download", payload={"path": "a.txt"}, timeout=10.0),
    ]

    assert len(log) == 1  # 单连接语义：一次 connect 只发一个 GET
    req = log[0]
    assert req.method == "GET"
    assert req.url.path == "/api/sandbox/channel"
    assert req.headers["Authorization"] == f"Bearer {PAT}"
    assert req.headers["Accept"] == "text/event-stream"
    await client.close()


async def test_real_one_shot_stream_yields_hello_and_all_tool_calls():
    """真实流（不可重放）上 hello + 多条 tool_call 全部正常收到。

    修复前的假绿：``Response(content=...)`` 带 ``_content`` 缓存，connect() 与
    迭代器各自 ``aiter_lines()`` 时第二个从字节 0 重放；真实流上第二次调用必抛
    ``StreamConsumed``——本测试即为其回归防线。
    """
    log: list[httpx.Request] = []
    client = _channel_client(_RealStreamTransport(log, GOOD_STREAM.encode("utf-8")))
    hello, calls = await client.connect()

    assert hello == {"sandbox_id": "sbx-1", "heartbeat_s": 15}
    assert [c async for c in calls] == [
        ToolCall(call_id="c1", op="exec", payload={"command": "echo hi"}, timeout=5.0),
        ToolCall(call_id="c2", op="download", payload={"path": "a.txt"}, timeout=10.0),
    ]
    await client.close()


async def test_connect_drops_tool_call_arriving_before_hello():
    stream = (
        HEARTBEAT
        + _frame("tool_call", '{"call_id": "early", "op": "exec", "payload": {}, "timeout": 1.0}')
        + _frame("hello", '{"sandbox_id": "sbx-3"}')
        + _frame("tool_call", '{"call_id": "late", "op": "exec", "payload": {}, "timeout": 2.0}')
    )
    log: list[httpx.Request] = []
    client = _channel_client(_sse_transport(log, stream.encode("utf-8")))
    hello, calls = await client.connect()

    assert hello == {"sandbox_id": "sbx-3"}
    # 计划既定简化：hello 前的 tool_call 不缓存不回放，hello 后的正常收到
    assert [c async for c in calls] == [
        ToolCall(call_id="late", op="exec", payload={}, timeout=2.0)
    ]
    await client.close()


async def test_connect_skips_bad_json_missing_fields_and_unknown_events():
    stream = (
        HEARTBEAT
        + _frame("hello", '{"sandbox_id": "sbx-2"}')
        + _frame("tool_call", "{not valid json")
        + _frame("tool_call", '{"op": "exec", "payload": {}}')  # 缺 call_id
        + _frame("ping", '{"call_id": "cx", "op": "x", "payload": {}, "timeout": 1}')  # 未知事件
        + _frame("tool_call", '{"call_id": "c3", "op": "exec", "payload": {}, "timeout": 1.5}')
    )
    log: list[httpx.Request] = []
    client = _channel_client(_sse_transport(log, stream.encode("utf-8")))
    hello, calls = await client.connect()

    assert hello == {"sandbox_id": "sbx-2"}
    assert [c async for c in calls] == [ToolCall(call_id="c3", op="exec", payload={}, timeout=1.5)]
    await client.close()


async def test_connect_stream_closed_before_hello_raises_transport_error():
    log: list[httpx.Request] = []
    client = _channel_client(_sse_transport(log, (HEARTBEAT * 3).encode("utf-8")))
    with pytest.raises(TransportError) as excinfo:
        await client.connect()
    assert not isinstance(excinfo.value, TransportAuthError)
    await client.close()


@pytest.mark.parametrize("status", [401, 403])
async def test_connect_auth_failure_raises_transport_auth_error(status):
    log: list[httpx.Request] = []
    client = _channel_client(_sse_transport(log, b"", status=status))
    with pytest.raises(TransportAuthError):
        await client.connect()
    assert len(log) == 1  # 不重连：只发一次请求
    await client.close()


async def test_connect_non_2xx_raises_transport_error():
    log: list[httpx.Request] = []
    client = _channel_client(_sse_transport(log, b"oops", status=500))
    with pytest.raises(TransportError) as excinfo:
        await client.connect()
    assert not isinstance(excinfo.value, TransportAuthError)
    assert "500" in str(excinfo.value)
    await client.close()


async def test_connect_network_error_propagates_unwrapped():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    client = _channel_client(httpx.MockTransport(handler))
    # 网络异常原样上抛（由 daemon 外层按 backoff 重连），不包装不吞掉
    with pytest.raises(httpx.ConnectError):
        await client.connect()
    await client.close()


# ---------- post_result / post_offline ----------


async def test_post_result_sends_body_without_none_fields():
    log: list[httpx.Request] = []
    client = _channel_client(_api_transport(log))
    await client.post_result(
        "call-9",
        {
            "stage": "done",
            "status": "ok",
            "stdout": "out",
            "stderr": None,
            "exit_code": 0,
            "error": None,
        },
    )

    assert len(log) == 1
    req = log[0]
    assert req.method == "POST"
    assert req.url.path == "/api/sandbox/results/call-9"
    assert json.loads(req.content) == {
        "stage": "done",
        "status": "ok",
        "stdout": "out",
        "exit_code": 0,
    }
    assert req.headers["Authorization"] == f"Bearer {PAT}"
    await client.close()


async def test_post_result_quotes_call_id_in_path():
    log: list[httpx.Request] = []
    client = _channel_client(_api_transport(log))
    await client.post_result("call/9?x=1", {"stage": "done", "status": "ok"})

    req = log[0]
    # raw_path 才是编码后的真实路径（path 属性会解码且 ? 会被重切成 query）
    assert req.url.raw_path == b"/api/sandbox/results/call%2F9%3Fx%3D1"
    await client.close()


async def test_post_result_auth_failure_raises_transport_auth_error():
    log: list[httpx.Request] = []
    client = _channel_client(_api_transport(log, status=401))
    with pytest.raises(TransportAuthError):
        await client.post_result("call-9", {"stage": "done", "status": "ok"})
    await client.close()


async def test_post_offline_posts_to_offline_endpoint():
    log: list[httpx.Request] = []
    client = _channel_client(_api_transport(log))
    await client.post_offline()

    assert len(log) == 1
    req = log[0]
    assert req.method == "POST"
    assert req.url.path == "/api/sandbox/offline"
    assert req.headers["Authorization"] == f"Bearer {PAT}"
    await client.close()


async def test_post_offline_auth_failure_raises_transport_auth_error():
    log: list[httpx.Request] = []
    client = _channel_client(_api_transport(log, status=401))
    with pytest.raises(TransportAuthError):
        await client.post_offline()
    await client.close()


async def test_close_closes_underlying_client():
    raw = httpx.AsyncClient(transport=_api_transport([]), timeout=None)
    client = ChannelClient(SERVER, PAT, client=raw)
    await client.close()
    assert raw.is_closed


# ---------- _FrameParser 解析路径（直接单测） ----------


def test_frame_parser_joins_multi_line_data_with_newline():
    parser = _FrameParser()
    assert parser.feed("event: tool_call") is None
    assert parser.feed('data: {"call_id": "m1",') is None
    assert parser.feed('data: "op": "exec"}') is None
    frame = parser.feed("")  # 空行触发帧产出，多 data 行以 \n 拼接
    assert frame is not None
    assert frame.event == "tool_call"
    assert frame.data == '{"call_id": "m1",\n"op": "exec"}'


def test_frame_parser_ignores_frame_without_event_line():
    parser = _FrameParser()
    assert parser.feed('data: {"call_id": "x"}') is None
    assert parser.feed("") is None  # 只有 data、缺 event 行：整帧静默丢弃
    assert parser.feed("event: hello") is None
    assert parser.feed('data: {"a": 1}') is None
    frame = parser.feed("")  # 丢弃不影响后续正常帧
    assert frame is not None
    assert (frame.event, frame.data) == ("hello", '{"a": 1}')


# ---------- backoff_delay ----------


class _MidRand(random.Random):
    """uniform 恒返回区间中点 → 抖动乘数恰为 1.0，可精确断言基线序列。"""

    def uniform(self, a: float, b: float) -> float:
        return (a + b) / 2


def test_backoff_delay_doubles_and_caps_at_60():
    rand = _MidRand()
    assert [backoff_delay(n, rand=rand) for n in range(1, 9)] == [1, 2, 4, 8, 16, 32, 60, 60]


def test_backoff_delay_attempt_floored_at_one():
    assert backoff_delay(0, rand=_MidRand()) == 1.0
    assert backoff_delay(-3, rand=_MidRand()) == 1.0


def test_backoff_delay_jitter_stays_within_20_percent():
    rand = random.Random(1234)
    for attempt in range(1, 10):
        base = min(60.0, 2.0 ** (attempt - 1))
        delay = backoff_delay(attempt, rand=rand)
        assert 0.8 * base <= delay <= 1.2 * base, (attempt, delay, base)


def test_backoff_delay_is_deterministic_per_seed():
    first = [backoff_delay(n, rand=random.Random(7)) for n in range(1, 6)]
    second = [backoff_delay(n, rand=random.Random(7)) for n in range(1, 6)]
    assert first == second
    bases = [1, 2, 4, 8, 16]
    assert any(d != b for d, b in zip(first, bases))  # 确实带抖动，不是恒等基线
