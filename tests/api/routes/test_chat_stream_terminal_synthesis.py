"""session_stream 对「终态 run + 已过期 stream」的合成终态测试。

生产孤儿工具卡根因：run 到终态后 Redis stream 60s TTL 过期，客户端（断线
自动重连/刷新重连）再连 /stream 时重放 0 条事件、端点又不查任务状态，
挂着发 24h 心跳——前端在途工具卡永远转圈。修复：stream 为空且 run 已
终态时立即合成 done/error 终态事件返回。
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.api.routes.chat import session_stream


def _user(sub="u1"):
    return SimpleNamespace(sub=sub)


def _session(metadata, user_id="u1"):
    return SimpleNamespace(user_id=user_id, session_id="s1", metadata=metadata)


class _FakeTraceCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    async def to_list(self, length=None):
        return self._docs[: length if length else len(self._docs)]


class _FakeTraceCollection:
    def __init__(self, docs):
        self._docs = docs
        self.find_calls = 0

    def find(self, query, *a, **k):
        self.find_calls += 1
        assert query.get("run_id")
        return _FakeTraceCursor(list(self._docs))


def _install(monkeypatch, *, stream_len, metadata, trace_docs=(), replay=()):
    read_calls: list[tuple] = []

    def _read(*args, **kwargs):
        read_calls.append((args, kwargs))
        return _aiter(list(replay))

    dual = SimpleNamespace(
        get_stream_length=AsyncMock(return_value=stream_len),
        read_from_redis=_read,
    )
    monkeypatch.setattr(
        "src.api.routes.chat.SessionManager",
        lambda: SimpleNamespace(get_session=AsyncMock(return_value=_session(metadata))),
    )
    monkeypatch.setattr(
        "src.infra.session.dual_writer.get_dual_writer",
        lambda: dual,
    )

    collection = _FakeTraceCollection(list(trace_docs))
    monkeypatch.setattr(
        "src.infra.session.trace_storage.get_trace_storage",
        lambda: SimpleNamespace(collection=collection),
    )
    return dual, collection, read_calls


async def _aiter(items):
    for item in items:
        yield item


async def _collect(response):
    return "".join([chunk async for chunk in response.body_iterator])


async def test_expired_stream_with_completed_run_synthesizes_done(monkeypatch):
    _install(
        monkeypatch,
        stream_len=0,
        metadata={"current_run_id": "r1", "task_status": "completed"},
        trace_docs=[{"status": "completed"}],
    )
    response = await session_stream("s1", run_id="r1", user=_user())
    body = await _collect(response)
    assert "event: done" in body
    assert '"status":"completed"' in body.replace(" ", "")


async def test_expired_stream_with_failed_run_synthesizes_terminal_error(monkeypatch):
    _install(
        monkeypatch,
        stream_len=0,
        metadata={
            "current_run_id": "r1",
            "task_status": "error",
            "task_error": "Worker crashed",
        },
        trace_docs=[{"status": "error"}],
    )
    response = await session_stream("s1", run_id="r1", user=_user())
    body = await _collect(response)
    assert "event: error" in body
    # 前端 isTerminalErrorPayload 需要 type/run_id/trace_id 之一在场
    assert '"run_id":"r1"' in body.replace(" ", "")
    assert "Worker crashed" in body


async def test_expired_stream_with_running_run_keeps_waiting(monkeypatch):
    """stream 空但 run 还在跑（孤儿接管窗口期）：维持现状挂流等待，
    不合成终态。"""
    dual, _, read_calls = _install(
        monkeypatch,
        stream_len=0,
        metadata={"current_run_id": "r1", "task_status": "running"},
        trace_docs=[{"status": "running"}],
        replay=[{"event_type": "heartbeat"}],
    )
    response = await session_stream("s1", run_id="r1", user=_user())
    body = await _collect(response)
    assert ": heartbeat" in body
    assert "event: done" not in body
    assert "event: error" not in body
    assert len(read_calls) == 1


async def test_alive_stream_replays_without_status_lookup(monkeypatch):
    """stream 还有事件（终态事件在缓冲里可重放）：走原重放路径，不查状态。"""
    dual, collection, read_calls = _install(
        monkeypatch,
        stream_len=2,
        metadata={},
        replay=[
            {
                "event_type": "done",
                "data": {"status": "completed"},
                "id": "e2",
                "timestamp": "2026-09-09T00:00:00Z",
            }
        ],
    )
    response = await session_stream("s1", run_id="r1", user=_user())
    body = await _collect(response)
    assert "event: done" in body
    assert collection.find_calls == 0
    assert len(read_calls) == 1


async def test_terminal_status_from_other_run_not_trusted(monkeypatch):
    """session metadata 是会话级：task_status 属于别的 run（current_run_id
    不匹配）且本 run 无 trace 终态 → 不合成终态（避免误杀活 run）。"""
    _install(
        monkeypatch,
        stream_len=0,
        metadata={"current_run_id": "r2", "task_status": "completed"},
        trace_docs=[],
        replay=[{"event_type": "heartbeat"}],
    )
    response = await session_stream("s1", run_id="r1", user=_user())
    body = await _collect(response)
    assert "event: done" not in body
    assert "event: error" not in body
