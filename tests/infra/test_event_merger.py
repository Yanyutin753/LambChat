from __future__ import annotations

import asyncio

import pytest

from src.infra.session import event_merger as event_merger_module
from src.infra.session.event_merger import EventMerger


class _DedicatedRedis:
    def __init__(self) -> None:
        self.set_calls: list[tuple[tuple, dict]] = []
        self.eval_calls: list[tuple[tuple, dict]] = []
        self.closed = False

    async def set(self, *args, **kwargs):
        self.set_calls.append((args, kwargs))
        return True

    async def eval(self, *args, **kwargs):
        self.eval_calls.append((args, kwargs))
        return 1

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_event_merger_uses_dedicated_redis_for_locking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    dedicated = _DedicatedRedis()
    isolated_pool_flags: list[bool] = []

    monkeypatch.setattr(
        "src.infra.session.event_merger.create_redis_client",
        lambda isolated_pool=False: isolated_pool_flags.append(isolated_pool) or dedicated,
    )

    merger = EventMerger(trace_storage=None)

    assert await merger._acquire_lock() is True
    assert dedicated.set_calls
    assert isolated_pool_flags == [True]

    await merger._release_lock()
    assert dedicated.eval_calls

    await merger.stop()
    assert dedicated.closed is True


@pytest.mark.asyncio
async def test_close_event_merger_stops_and_releases_singleton() -> None:
    class _FakeMerger:
        def __init__(self) -> None:
            self.stop_calls = 0

        async def stop(self) -> None:
            self.stop_calls += 1

    merger = _FakeMerger()
    event_merger_module._event_merger = merger

    await event_merger_module.close_event_merger()

    assert merger.stop_calls == 1
    assert event_merger_module._event_merger is None


@pytest.mark.asyncio
async def test_close_event_merger_does_not_create_singleton_when_unused() -> None:
    event_merger_module._event_merger = None

    await event_merger_module.close_event_merger()

    assert event_merger_module._event_merger is None


def test_event_merger_lock_timeout_has_floor_for_short_intervals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """短间隔提速时批次仍可能耗时数分钟：锁 TTL 保底，避免批次进行中
    锁过期导致双实例并发合并。"""
    import src.infra.session.event_merger as event_merger

    monkeypatch.setattr(event_merger.settings, "EVENT_MERGE_INTERVAL", 30.0, raising=False)
    assert event_merger._get_lock_timeout() >= 600

    monkeypatch.setattr(event_merger.settings, "EVENT_MERGE_INTERVAL", 600.0, raising=False)
    assert event_merger._get_lock_timeout() == 1200


@pytest.mark.asyncio
async def test_event_merger_scans_largest_traces_first(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """存量自愈按 event_count 降序扫描：交错增量堆积的重型 trace
    （存储大头、用户感知最强的会话）最先被治，小 trace 慢慢补标记。"""
    import src.infra.session.event_merger as event_merger

    monkeypatch.setattr(event_merger.settings, "EVENT_MERGE_BATCH_SIZE", 4, raising=False)
    monkeypatch.setattr(
        event_merger.settings, "SESSION_EVENT_CHUNK_STORAGE_ENABLED", False, raising=False
    )
    captured: dict = {}

    class _Cursor:
        def sort(self, key, direction):
            captured["sort"] = (key, direction)
            return self

        def limit(self, _limit):
            return self

        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    class _Collection:
        def find(self, _filter, _projection):
            return _Cursor()

        async def bulk_write(self, operations, ordered: bool = False):
            return type("_Result", (), {"modified_count": 0})()

    class _TraceStorage:
        collection = _Collection()

        async def recover_incomplete_chunk_replacements(self):
            return None

    merger = EventMerger(trace_storage=_TraceStorage())
    await merger._merge_completed_traces()

    assert captured["sort"] == ("event_count", -1)


def test_event_merger_limits_follow_runtime_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.infra.session.event_merger as event_merger

    monkeypatch.setattr(event_merger.settings, "EVENT_MERGE_BATCH_SIZE", 17, raising=False)
    monkeypatch.setattr(event_merger.settings, "EVENT_MERGE_CONCURRENCY", 3, raising=False)
    monkeypatch.setattr(event_merger.settings, "EVENT_MERGE_TIMEOUT_SECONDS", 11, raising=False)
    monkeypatch.setattr(
        event_merger.settings,
        "EVENT_MERGE_IMMEDIATE_DEBOUNCE_SECONDS",
        0.25,
        raising=False,
    )
    monkeypatch.setattr(
        event_merger.settings,
        "EVENT_MERGE_MAX_EVENTS_PER_TRACE",
        222,
        raising=False,
    )

    assert event_merger._get_merge_batch_size() == 17
    assert event_merger._get_merge_concurrency() == 3
    assert event_merger._get_merge_timeout() == 11
    assert event_merger._get_immediate_merge_debounce_seconds() == 0.25
    assert event_merger._get_merge_max_events_per_trace() == 222


def test_event_merger_handles_fifty_thousand_events_per_trace_by_default() -> None:
    assert event_merger_module._get_merge_max_events_per_trace() == 50_000


@pytest.mark.asyncio
async def test_event_merger_schedule_merge_once_runs_background_merge(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.infra.session.event_merger as event_merger

    monkeypatch.setattr(
        event_merger,
        "_get_immediate_merge_debounce_seconds",
        lambda: 0.01,
    )
    merge_calls = 0

    async def fake_merge_once(self) -> None:
        nonlocal merge_calls
        merge_calls += 1

    monkeypatch.setattr(EventMerger, "merge_once", fake_merge_once)

    merger = EventMerger(trace_storage=None)
    merger.schedule_merge_once()
    merger.schedule_merge_once()

    await asyncio.wait_for(merger._merge_once_task, timeout=1)

    assert merge_calls == 1


@pytest.mark.asyncio
async def test_event_merger_debounces_many_immediate_merge_requests(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.infra.session.event_merger as event_merger

    monkeypatch.setattr(
        event_merger,
        "_get_immediate_merge_debounce_seconds",
        lambda: 0.05,
    )
    merge_calls = 0

    async def fake_merge_once(self) -> None:
        nonlocal merge_calls
        merge_calls += 1

    monkeypatch.setattr(EventMerger, "merge_once", fake_merge_once)

    merger = EventMerger(trace_storage=None)
    for _ in range(100):
        merger.schedule_merge_once()

    await asyncio.wait_for(merger._merge_once_task, timeout=1)

    assert merge_calls == 1


@pytest.mark.asyncio
async def test_event_merger_processes_traces_with_bounded_coroutines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.infra.session.event_merger as event_merger

    batch_size = 9
    concurrency = 3
    monkeypatch.setattr(event_merger.settings, "EVENT_MERGE_BATCH_SIZE", batch_size, raising=False)
    monkeypatch.setattr(
        event_merger.settings,
        "EVENT_MERGE_CONCURRENCY",
        concurrency,
        raising=False,
    )
    monkeypatch.setattr(
        event_merger.settings,
        "SESSION_EVENT_CHUNK_STORAGE_ENABLED",
        False,
        raising=False,
    )

    class _Cursor:
        def __init__(self) -> None:
            self._index = 0
            self._docs = [
                {
                    "_id": f"parent-{index}",
                    "trace_id": f"trace-{index}",
                    "session_id": "session-1",
                    "status": "completed",
                    "updated_at": f"version-{index}",
                    "events": [{"event_type": "message:chunk", "data": {"text": "x"}}],
                }
                for index in range(batch_size)
            ]

        def sort(self, *_args):
            return self

        def limit(self, _limit: int):
            return self

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self._index >= len(self._docs):
                raise StopAsyncIteration
            item = self._docs[self._index]
            self._index += 1
            return dict(item)

        async def to_list(self, length: int):
            return [dict(doc) for doc in self._docs[:length]]

    class _Collection:
        def __init__(self) -> None:
            self.operations = []

        def find(self, *args, **kwargs):
            return _Cursor()

        async def bulk_write(self, operations, ordered: bool = False):
            del ordered
            self.operations.extend(operations)
            return type("_Result", (), {"modified_count": len(operations)})()

    class _TraceStorage:
        def __init__(self) -> None:
            self.collection = _Collection()

    merger = EventMerger(_TraceStorage())
    real_gather = event_merger.asyncio.gather
    gather_sizes: list[int] = []

    async def tracking_gather(*aws, **kwargs):
        gather_sizes.append(len(aws))
        return await real_gather(*aws, **kwargs)

    monkeypatch.setattr(event_merger.asyncio, "gather", tracking_gather)

    await merger._merge_completed_traces()

    assert gather_sizes
    assert max(gather_sizes) <= concurrency
    for operation in merger.trace_storage.collection.operations:
        index = int(operation._filter["trace_id"].removeprefix("trace-"))
        assert operation._filter == {
            "_id": f"parent-{index}",
            "trace_id": f"trace-{index}",
            "status": {"$in": ["completed", "error", "cancelled"]},
            "updated_at": f"version-{index}",
            "attachment_chunk_write_operation": {"$exists": False},
        }
        assert operation._doc["$inc"] == {"event_revision": 1}


@pytest.mark.asyncio
async def test_event_merger_streams_cursor_without_materializing_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.infra.session.event_merger as event_merger

    monkeypatch.setattr(event_merger.settings, "EVENT_MERGE_BATCH_SIZE", 3, raising=False)
    monkeypatch.setattr(event_merger.settings, "EVENT_MERGE_CONCURRENCY", 1, raising=False)

    class _Cursor:
        def __init__(self) -> None:
            self._docs = [
                {
                    "trace_id": f"trace-{index}",
                    "events": [{"event_type": "message:chunk", "data": {"content": "x"}}],
                }
                for index in range(3)
            ]
            self._index = 0

        def sort(self, *_args):
            return self

        def limit(self, _limit: int):
            return self

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self._index >= len(self._docs):
                raise StopAsyncIteration
            item = self._docs[self._index]
            self._index += 1
            return dict(item)

        async def to_list(self, length: int):
            raise AssertionError("event merger should stream cursor instead of to_list")

    class _Collection:
        def __init__(self) -> None:
            self.operations = []

        def find(self, *args, **kwargs):
            return _Cursor()

        async def bulk_write(self, operations, ordered: bool = False):
            del ordered
            self.operations.extend(operations)
            return type("_Result", (), {"modified_count": len(operations)})()

    class _TraceStorage:
        def __init__(self) -> None:
            self.collection = _Collection()

    storage = _TraceStorage()
    merger = EventMerger(storage)

    await merger._merge_completed_traces()

    assert len(storage.collection.operations) == 3


@pytest.mark.asyncio
async def test_event_merger_offloads_cpu_merge_work(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.infra.session.event_merger as event_merger

    offloaded: list[str] = []

    async def fake_run_long_blocking_io(func, /, *args, **kwargs):
        del kwargs
        offloaded.append(func.__name__)
        return func(*args)

    monkeypatch.setattr(
        event_merger, "run_long_blocking_io", fake_run_long_blocking_io, raising=False
    )

    merger = EventMerger(trace_storage=None)
    traces = [
        {
            "trace_id": "trace-1",
            "events": [
                {"event_type": "message:chunk", "data": {"content": "a"}},
                {"event_type": "message:chunk", "data": {"content": "b"}},
            ],
        }
    ]

    results = await merger._process_trace_merges_bounded(traces, concurrency=1)

    assert offloaded == ["_merge_events"]
    assert results[0][0] == "trace-1"
    assert results[0][2][0]["data"]["content"] == "ab"


def test_event_merger_only_merges_contiguous_events_to_preserve_timeline() -> None:
    merger = EventMerger(trace_storage=None)

    events = [
        {"event_type": "message:chunk", "data": {"content": "a", "text_id": "t1"}},
        {"event_type": "tool:start", "data": {"name": "search"}},
        {"event_type": "message:chunk", "data": {"content": "b", "text_id": "t1"}},
        {"event_type": "message:chunk", "data": {"content": "c", "text_id": "t1"}},
    ]

    merged = merger._merge_events(events)

    assert [event["event_type"] for event in merged] == [
        "message:chunk",
        "tool:start",
        "message:chunk",
    ]
    assert [event["data"].get("content") for event in merged] == ["a", None, "bc"]


def test_event_merger_merges_interleaved_thinking_streams_by_thinking_id() -> None:
    """并行子代理的 thinking 增量交错落库（生产 34K 事件的根源）：
    按块标识分组归并到首现位置，连续合并不生效。"""
    merger = EventMerger(trace_storage=None)

    events = [
        {
            "event_type": "thinking",
            "data": {"content": "A1", "thinking_id": "ta"},
            "timestamp": "t1",
        },
        {
            "event_type": "thinking",
            "data": {"content": "B1", "thinking_id": "tb"},
            "timestamp": "t2",
        },
        {"event_type": "tool:start", "data": {"tool": "read_file"}, "timestamp": "t3"},
        {
            "event_type": "thinking",
            "data": {"content": "A2", "thinking_id": "ta"},
            "timestamp": "t4",
        },
        {
            "event_type": "thinking",
            "data": {"content": "B2", "thinking_id": "tb"},
            "timestamp": "t5",
        },
    ]

    merged = merger._merge_events(events)

    assert [event["event_type"] for event in merged] == [
        "thinking",
        "thinking",
        "tool:start",
    ]
    assert merged[0]["data"]["content"] == "A1A2"
    assert merged[1]["data"]["content"] == "B1B2"
    assert merged[0]["timestamp"] == "t1"


def test_event_merger_merges_tool_args_chunks_by_call_id() -> None:
    merger = EventMerger(trace_storage=None)

    events = [
        {
            "event_type": "tool:args:chunk",
            "data": {"content": '{"a"', "tool": "read_file", "tool_call_id": "c1"},
            "timestamp": "t1",
        },
        {
            "event_type": "tool:args:chunk",
            "data": {"content": '{"b"', "tool": "read_file", "tool_call_id": "c2"},
            "timestamp": "t2",
        },
        {
            "event_type": "tool:args:chunk",
            "data": {"content": ": 1}", "tool": "read_file", "tool_call_id": "c1"},
            "timestamp": "t3",
        },
        {
            "event_type": "tool:args:chunk",
            "data": {"content": ": 2}", "tool": "read_file", "tool_call_id": "c2"},
            "timestamp": "t4",
        },
    ]

    merged = merger._merge_events(events)

    assert len(merged) == 2
    assert merged[0]["data"]["content"] == '{"a": 1}'
    assert merged[1]["data"]["content"] == '{"b": 2}'


def test_event_merger_marks_merged_events_with_counts_and_times() -> None:
    merger = EventMerger(trace_storage=None)

    events = [
        {
            "event_type": "thinking",
            "data": {"content": "a", "thinking_id": "t1"},
            "timestamp": "t1",
        },
        {"event_type": "tool:start", "data": {"tool": "x"}, "timestamp": "t2"},
        {
            "event_type": "thinking",
            "data": {"content": "b", "thinking_id": "t1"},
            "timestamp": "t3",
        },
        {
            "event_type": "thinking",
            "data": {"content": "c", "thinking_id": "t1"},
            "timestamp": "t4",
        },
    ]

    merged = merger._merge_events(events)

    thinking = merged[0]
    assert thinking["data"]["merged"] is True
    assert thinking["data"]["merged_count"] == 3
    assert thinking["data"]["started_at"] == "t1"
    assert thinking["data"]["ended_at"] == "t4"


def test_event_merger_does_not_merge_thinking_across_agent_at_depth() -> None:
    merger = EventMerger(trace_storage=None)

    events = [
        {
            "event_type": "thinking",
            "data": {"content": "a", "thinking_id": "t1", "depth": 1, "agent_id": "w1"},
            "timestamp": "t1",
        },
        {
            "event_type": "thinking",
            "data": {"content": "b", "thinking_id": "t1", "depth": 1, "agent_id": "w2"},
            "timestamp": "t2",
        },
    ]

    merged = merger._merge_events(events)

    assert [event["data"]["content"] for event in merged] == ["a", "b"]


@pytest.mark.asyncio
async def test_event_merger_reenqueues_traces_merged_by_old_strategy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """旧版连续合并器收缩失败也会标记 metadata.merged=True，交错的 thinking
    trace 从未被真正合掉——按合并策略版本重新入队自愈。"""
    import src.infra.session.event_merger as event_merger

    monkeypatch.setattr(event_merger.settings, "EVENT_MERGE_BATCH_SIZE", 4, raising=False)
    monkeypatch.setattr(
        event_merger.settings, "SESSION_EVENT_CHUNK_STORAGE_ENABLED", False, raising=False
    )
    captured: dict = {}

    class _Cursor:
        def sort(self, *_args):
            return self

        def limit(self, _limit):
            return self

        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    class _Collection:
        def find(self, filter, *args, **kwargs):
            captured["filter"] = filter
            return _Cursor()

        async def bulk_write(self, operations, ordered: bool = False):
            return type("_Result", (), {"modified_count": 0})()

    class _TraceStorage:
        collection = _Collection()

        async def recover_incomplete_chunk_replacements(self):
            return None

    merger = EventMerger(trace_storage=_TraceStorage())
    await merger._merge_completed_traces()

    or_conditions = captured["filter"]["$and"][0]["$or"]
    assert {"metadata.merged": {"$ne": True}} in or_conditions
    assert {"metadata.merge_strategy": {"$ne": "grouped"}} in or_conditions
    event_count_conditions = captured["filter"]["$and"][1]["$or"]
    assert {"event_count": {"$exists": False}} in event_count_conditions


@pytest.mark.asyncio
async def test_event_merger_marks_merge_strategy_on_completion(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.infra.session.event_merger as event_merger

    monkeypatch.setattr(event_merger.settings, "EVENT_MERGE_BATCH_SIZE", 4, raising=False)
    monkeypatch.setattr(
        event_merger.settings, "SESSION_EVENT_CHUNK_STORAGE_ENABLED", False, raising=False
    )
    operations: list = []

    class _Cursor:
        def __init__(self) -> None:
            self._docs = [
                {
                    "_id": "parent-0",
                    "trace_id": "trace-0",
                    "session_id": "session-1",
                    "run_id": "run-1",
                    "status": "completed",
                    "updated_at": "v0",
                    "events": [
                        {"event_type": "thinking", "data": {"content": "a", "thinking_id": "t1"}},
                        {"event_type": "thinking", "data": {"content": "b", "thinking_id": "t1"}},
                    ],
                }
            ]
            self._index = 0

        def sort(self, *_args):
            return self

        def limit(self, _limit):
            return self

        def __aiter__(self):
            return self

        async def __anext__(self):
            if self._index >= len(self._docs):
                raise StopAsyncIteration
            item = self._docs[self._index]
            self._index += 1
            return dict(item)

    class _Collection:
        def find(self, *args, **kwargs):
            return _Cursor()

        async def bulk_write(self, ops, ordered: bool = False):
            operations.extend(ops)
            return type("_Result", (), {"modified_count": len(ops)})()

    class _TraceStorage:
        collection = _Collection()

        async def recover_incomplete_chunk_replacements(self):
            return None

    merger = EventMerger(trace_storage=_TraceStorage())
    await merger._merge_completed_traces()

    assert operations, "shrinkable trace should produce an update"
    update = operations[0]
    set_fields = update._doc["$set"] if hasattr(update, "_doc") else update.doc["$set"]
    assert set_fields["metadata.merged"] is True
    assert set_fields["metadata.merge_strategy"] == "grouped"


@pytest.mark.asyncio
async def test_event_merger_filters_out_giant_traces_before_loading_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.infra.session.event_merger as event_merger

    monkeypatch.setattr(
        event_merger.settings,
        "EVENT_MERGE_MAX_EVENTS_PER_TRACE",
        5,
        raising=False,
    )

    class _Cursor:
        def sort(self, *_args):
            return self

        def limit(self, _limit: int):
            return self

        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    class _Collection:
        def __init__(self) -> None:
            self.query = None
            self.projection = None

        def find(self, query, projection):
            self.query = query
            self.projection = projection
            return _Cursor()

    class _TraceStorage:
        def __init__(self) -> None:
            self.collection = _Collection()

    storage = _TraceStorage()
    merger = EventMerger(storage)

    await merger._merge_completed_traces()

    assert storage.collection.query == {
        "status": {"$in": ["completed", "error", "cancelled"]},
        "attachment_chunk_write_operation": {"$exists": False},
        "$and": [
            {
                "$or": [
                    {"metadata.merged": {"$ne": True}},
                    {"metadata.merge_strategy": {"$ne": "grouped"}},
                ]
            },
            {
                "$or": [
                    {"event_count": {"$lte": 5}},
                    {"event_count": {"$exists": False}},
                ]
            },
        ],
    }
    assert storage.collection.projection == {
        "_id": 1,
        "trace_id": 1,
        "session_id": 1,
        "run_id": 1,
        "started_at": 1,
        "status": 1,
        "updated_at": 1,
        "event_count": 1,
        "event_revision": 1,
        "metadata": 1,
    }


@pytest.mark.asyncio
async def test_event_merger_reads_events_through_trace_storage_compat() -> None:
    class _TraceStorage:
        async def read_trace_events_compat(self, trace_id: str):
            assert trace_id == "trace-1"
            return [
                {"event_type": "message:chunk", "data": {"content": "a"}},
                {"event_type": "message:chunk", "data": {"content": "b"}},
            ]

    merger = EventMerger(_TraceStorage())

    results = await merger._process_trace_merges_bounded(
        [{"trace_id": "trace-1"}],
        concurrency=1,
    )

    assert results[0][0] == "trace-1"
    assert results[0][1][0]["data"]["content"] == "a"
    assert results[0][2][0]["data"]["content"] == "ab"


@pytest.mark.asyncio
async def test_event_merger_rebuilds_chunks_when_chunk_storage_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        event_merger_module.settings,
        "SESSION_EVENT_CHUNK_STORAGE_ENABLED",
        True,
        raising=False,
    )

    class _Collection:
        def __init__(self) -> None:
            self.operations = []

        async def bulk_write(self, operations, ordered: bool = False):
            del ordered
            self.operations.extend(operations)
            return type("_Result", (), {"modified_count": len(operations)})()

    class _TraceStorage:
        def __init__(self) -> None:
            self.collection = _Collection()
            self.replacements = []

        async def replace_trace_events_with_chunks(self, trace_doc, events, **kwargs):
            self.replacements.append((trace_doc, events, kwargs))
            return True

    storage = _TraceStorage()
    merger = EventMerger(storage)

    modified, merged, skipped, errors = await merger._merge_trace_batch(
        storage.collection,
        [
            {
                "trace_id": "trace-1",
                "session_id": "session-1",
                "run_id": "run-1",
                "started_at": "started",
                "events": [
                    {"event_type": "message:chunk", "data": {"content": "a"}},
                    {"event_type": "message:chunk", "data": {"content": "b"}},
                ],
            }
        ],
        concurrency=1,
    )

    assert (modified, merged, skipped, errors) == (1, 1, 0, 0)
    assert storage.replacements[0][0]["trace_id"] == "trace-1"
    assert storage.replacements[0][1][0]["data"]["content"] == "ab"
    assert storage.replacements[0][2]["parent_updates"]["metadata.merged"] is True
    assert "metadata.merged_at" in storage.replacements[0][2]["parent_updates"]
    assert storage.collection.operations == []


@pytest.mark.asyncio
async def test_event_merger_does_not_mark_or_count_merge_when_chunk_replace_cas_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        event_merger_module.settings,
        "SESSION_EVENT_CHUNK_STORAGE_ENABLED",
        True,
        raising=False,
    )

    class _Collection:
        def __init__(self) -> None:
            self.operations = []

        async def bulk_write(self, operations, ordered: bool = False):
            del ordered
            self.operations.extend(operations)
            return type("_Result", (), {"modified_count": len(operations)})()

    class _TraceStorage:
        def __init__(self) -> None:
            self.collection = _Collection()

        async def replace_trace_events_with_chunks(self, trace_doc, events):
            del trace_doc, events
            return False

    storage = _TraceStorage()
    merger = EventMerger(storage)

    modified, merged, _skipped, _errors = await merger._merge_trace_batch(
        storage.collection,
        [
            {
                "_id": "parent-1",
                "trace_id": "trace-1",
                "session_id": "session-1",
                "run_id": "run-1",
                "started_at": "started",
                "updated_at": "version-1",
                "events": [
                    {"event_type": "message:chunk", "data": {"content": "a"}},
                    {"event_type": "message:chunk", "data": {"content": "b"}},
                ],
            }
        ],
        concurrency=1,
    )

    assert (modified, merged) == (0, 0)
    assert storage.collection.operations == []
