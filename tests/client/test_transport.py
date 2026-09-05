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


def _client(transport: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=transport, timeout=None)


def _channel_client(transport: httpx.MockTransport) -> ChannelClient:
    return ChannelClient(SERVER, PAT, client=_client(transport))


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


async def test_close_closes_underlying_client():
    raw = httpx.AsyncClient(transport=_api_transport([]), timeout=None)
    client = ChannelClient(SERVER, PAT, client=raw)
    await client.close()
    assert raw.is_closed


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
