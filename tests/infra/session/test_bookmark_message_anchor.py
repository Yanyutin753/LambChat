"""message_anchor_exists：书签锚点校验的纯逻辑测试。

锚点合法性（与前端历史重建的 id 派生规则一致）：
- run 派生：{run_id}、{run_id}#t{N}、{run_id}:user
- user:message 事件里显式记录的 message_id（客户端自带 id 的场景）
"""

from types import SimpleNamespace

import pytest

from src.infra.session.manager import SessionManager


class _FakeTraceCollection:
    def __init__(self, traces):
        self.traces = traces

    def find(self, query, projection):
        # 按 run_id $in 过滤，模拟 Mongo 行为；无该条件时返回全量（兜底扫描）
        run_filter = query.get("run_id")
        run_ids = run_filter.get("$in") if isinstance(run_filter, dict) else None
        docs = [t for t in self.traces if run_ids is None or t.get("run_id") in run_ids]
        return _FakeCursor(docs)


class _FakeCursor:
    def __init__(self, docs):
        self.docs = docs

    def sort(self, *args):
        return self

    def __aiter__(self):
        return self._iter()

    async def _iter(self):
        for doc in self.docs:
            yield doc


def _make_manager(traces, user_message_events_by_trace=None) -> SessionManager:
    manager = SessionManager()

    async def fake_compat_reader(trace_id, event_types=None, max_events=None):
        return (user_message_events_by_trace or {}).get(trace_id, [])

    manager._trace_storage = SimpleNamespace(
        collection=_FakeTraceCollection(traces),
        read_trace_events_compat=fake_compat_reader,
    )
    return manager


@pytest.mark.asyncio
async def test_run_id_anchor_exists():
    manager = _make_manager([{"run_id": "run-1", "trace_id": "t1"}])
    assert await manager.message_anchor_exists("session-1", "run-1") is True


@pytest.mark.asyncio
async def test_run_derived_user_anchor_exists():
    manager = _make_manager([{"run_id": "run-1", "trace_id": "t1"}])
    assert await manager.message_anchor_exists("session-1", "run-1:user") is True


@pytest.mark.asyncio
async def test_run_derived_turn_anchor_exists():
    manager = _make_manager([{"run_id": "run-1", "trace_id": "t1"}])
    assert await manager.message_anchor_exists("session-1", "run-1#t2") is True


@pytest.mark.asyncio
@pytest.mark.parametrize("anchor", ["run-1", "run-1:user", "run-1#t0"])
async def test_run_anchor_matches_only_its_own_session(anchor: str) -> None:
    manager = _make_manager([{"run_id": "run-2", "trace_id": "t1"}])
    assert await manager.message_anchor_exists("session-1", anchor) is False


@pytest.mark.asyncio
async def test_explicit_user_message_id_exists():
    traces = [{"run_id": "run-1", "trace_id": "t1"}]
    events = {
        "t1": [
            {
                "event_type": "user:message",
                "data": {"message_id": "msg-client-1", "content": "hi"},
            }
        ]
    }
    manager = _make_manager(traces, events)
    assert await manager.message_anchor_exists("session-1", "msg-client-1") is True


@pytest.mark.asyncio
async def test_unknown_anchor_does_not_exist():
    traces = [{"run_id": "run-1", "trace_id": "t1"}]
    events = {
        "t1": [
            {
                "event_type": "user:message",
                "data": {"message_id": "msg-client-1"},
            }
        ]
    }
    manager = _make_manager(traces, events)
    assert await manager.message_anchor_exists("session-1", "random-uuid") is False


@pytest.mark.asyncio
async def test_empty_anchor_does_not_exist():
    manager = _make_manager([{"run_id": "run-1", "trace_id": "t1"}])
    assert await manager.message_anchor_exists("session-1", "") is False


@pytest.mark.asyncio
async def test_explicit_anchor_reads_traces_in_bounded_batches():
    traces = [{"run_id": f"run-{i}", "trace_id": f"t{i}"} for i in range(205)]
    event = {"event_type": "user:message", "data": {"message_id": "target"}}
    manager = _make_manager(traces, {"t204": [event]})
    calls = []

    async def batch_reader(docs, event_types=None, active_user_only_trace_ids=None):
        ids = [doc["trace_id"] for doc in docs]
        calls.append(ids)
        assert event_types == ["user:message"]
        assert active_user_only_trace_ids == set(ids)
        return {"t204": [event]} if "t204" in ids else {}

    async def unexpected_single(*args, **kwargs):
        raise AssertionError("normal reads must use the batch reader")

    manager._trace_storage.read_trace_events_batch_compat = batch_reader
    manager._trace_storage.read_trace_events_compat = unexpected_single
    assert await manager.message_anchor_exists("session-1", "target") is True
    assert [len(batch) for batch in calls] == [100, 100, 5]


@pytest.mark.asyncio
async def test_anchor_batch_failure_falls_back_and_skips_unreadable_trace():
    event = {"event_type": "user:message", "data": {"message_id": "target"}}
    manager = _make_manager(
        [
            {"run_id": "run-1", "trace_id": "bad"},
            {"run_id": "run-2", "trace_id": "good"},
        ]
    )
    calls = []

    async def batch_reader(*args, **kwargs):
        raise RuntimeError("batch failure")

    async def single_reader(trace_id, **kwargs):
        calls.append(trace_id)
        if trace_id == "bad":
            raise RuntimeError("unreadable")
        return [event]

    manager._trace_storage.read_trace_events_batch_compat = batch_reader
    manager._trace_storage.read_trace_events_compat = single_reader
    assert await manager.message_anchor_exists("session-1", "target") is True
    assert calls == ["bad", "good"]


@pytest.mark.asyncio
async def test_anchor_batch_reader_preserves_mixed_legacy_chunk_boundary():
    from src.infra.session.trace_event_read import TraceEventReadCompatMixin

    traces = [
        {
            "run_id": "run-1",
            "trace_id": "t1",
            "events": [
                {"event_type": "user:message", "data": {"message_id": "legacy-prefix"}},
                {"event_type": "message:chunk", "data": {"content": "text"}},
                {"event_type": "user:message", "data": {"message_id": "stale-tail"}},
            ],
        }
    ]

    class Chunks:
        def find(self, query, projection):
            assert query == {"trace_id": {"$in": ["t1"]}}
            assert "start_seq" in projection
            assert "$cond" in projection["events"]
            return _FakeCursor(
                [
                    {
                        "trace_id": "t1",
                        "chunk_index": 0,
                        "start_seq": 3,
                        "events": [
                            {
                                "seq": 3,
                                "event_type": "user:message",
                                "data": {"message_id": "chunk-message"},
                            }
                        ],
                    }
                ]
            )

    class Storage(TraceEventReadCompatMixin):
        collection = _FakeTraceCollection(traces)
        chunks_collection = Chunks()

    manager = SessionManager()
    manager._trace_storage = Storage()
    assert await manager.message_anchor_exists("session-1", "legacy-prefix") is True
    assert await manager.message_anchor_exists("session-1", "chunk-message") is True
    assert await manager.message_anchor_exists("session-1", "stale-tail") is False
    target = await manager._resolve_fork_target("session-1", "chunk-message")
    assert target["target_type"] == "user"
    assert target["completed_run_count"] == 0
