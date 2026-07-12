from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from src.infra.session import trace_storage as trace_storage_module
from src.infra.session.trace_storage import TraceStorage


class _AsyncCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.docs = docs
        self.sort_args: tuple[str, int] | None = None

    def sort(self, key: str, direction: int):
        self.sort_args = (key, direction)
        self.docs.sort(key=lambda item: item.get(key, 0), reverse=direction < 0)
        return self

    def limit(self, limit: int):
        self.docs = self.docs[:limit]
        return self

    def __aiter__(self):
        self._iter = iter(self.docs)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _FakeTraceCollection:
    def __init__(self, trace_doc: dict[str, Any] | None = None) -> None:
        self.trace_doc = trace_doc
        self.update_calls: list[tuple[dict[str, Any], dict[str, Any]]] = []
        self.find_one_and_update_calls: list[tuple[dict[str, Any], dict[str, Any]]] = []

    async def find_one(self, query: dict[str, Any], projection: dict[str, Any] | None = None):
        del projection
        if self.trace_doc and self.trace_doc.get("trace_id") == query.get("trace_id"):
            return self.trace_doc
        return None

    async def update_one(self, query: dict[str, Any], update: dict[str, Any]):
        self.update_calls.append((query, update))

    async def find_one_and_update(self, query: dict[str, Any], update: dict[str, Any], **kwargs):
        del kwargs
        self.find_one_and_update_calls.append((query, update))
        if self.trace_doc and self.trace_doc.get("trace_id") == query.get("trace_id"):
            self.trace_doc["event_count"] = (
                self.trace_doc.get("event_count", 0) + update["$inc"]["event_count"]
            )
            return self.trace_doc
        return None


class _FakeChunkCollection:
    def __init__(self, chunks: list[dict[str, Any]] | None = None) -> None:
        self.chunks = chunks or []
        self.deleted_queries: list[dict[str, Any]] = []
        self.inserted_docs: list[dict[str, Any]] = []
        self.update_calls: list[tuple[dict[str, Any], dict[str, Any], bool]] = []
        self.update_many_calls: list[tuple[dict[str, Any], dict[str, Any]]] = []

    async def find_one(self, query: dict[str, Any], projection: dict[str, Any] | None = None):
        del projection
        for chunk in self.chunks:
            if chunk.get("trace_id") == query.get("trace_id"):
                return chunk
        return None

    def find(self, query: dict[str, Any], projection: dict[str, Any] | None = None):
        del projection
        docs = [chunk for chunk in self.chunks if chunk.get("trace_id") == query.get("trace_id")]
        return _AsyncCursor(docs)

    async def delete_many(self, query: dict[str, Any]):
        self.deleted_queries.append(query)
        self.chunks = [
            chunk for chunk in self.chunks if chunk.get("trace_id") != query.get("trace_id")
        ]

    async def insert_many(self, docs: list[dict[str, Any]]):
        self.inserted_docs.extend(docs)
        self.chunks.extend(docs)

    async def update_one(self, query: dict[str, Any], update: dict[str, Any], upsert: bool = False):
        self.update_calls.append((query, update, upsert))

    async def update_many(self, query: dict[str, Any], update: dict[str, Any]):
        self.update_many_calls.append((query, update))


class _SessionTraceCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.docs = docs
        self.sort_args: tuple[str, int] | None = None

    def sort(self, key: str, direction: int):
        self.sort_args = (key, direction)
        self.docs.sort(key=lambda item: item.get(key, ""), reverse=direction < 0)
        return self

    def __aiter__(self):
        self._iter_index = 0
        return self

    async def __anext__(self):
        if self._iter_index >= len(self.docs):
            raise StopAsyncIteration
        item = self.docs[self._iter_index]
        self._iter_index += 1
        return item

    async def to_list(self, length=None):
        if length is None:
            return self.docs
        return self.docs[:length]


class _FakeSessionTraceCollection(_FakeTraceCollection):
    def __init__(self, traces: list[dict[str, Any]]) -> None:
        super().__init__()
        self.traces = traces
        self.find_calls: list[tuple[dict[str, Any], dict[str, Any]]] = []
        self.cursor = _SessionTraceCursor(list(traces))

    def find(self, query: dict[str, Any], projection: dict[str, Any]):
        self.find_calls.append((query, projection))
        return self.cursor

    async def find_one(self, query: dict[str, Any], projection: dict[str, Any] | None = None):
        del projection
        for trace in self.traces:
            if trace.get("trace_id") == query.get("trace_id"):
                return trace
        return None


def _event(event_type: str, content: str, seq: int | None = None) -> dict[str, Any]:
    event = {
        "event_type": event_type,
        "data": {"content": content},
        "timestamp": f"t-{content}",
    }
    if seq is not None:
        event["seq"] = seq
    return event


def test_get_event_chunk_size_clamps_to_positive_int(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(trace_storage_module.settings, "SESSION_EVENT_CHUNK_SIZE", 0, raising=False)

    assert trace_storage_module._get_event_chunk_size() == 1


@pytest.mark.asyncio
async def test_replace_trace_events_with_chunks_splits_events_and_updates_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(trace_storage_module.settings, "SESSION_EVENT_CHUNK_SIZE", 2, raising=False)
    storage = TraceStorage()
    trace_collection = _FakeTraceCollection()
    chunk_collection = _FakeChunkCollection()
    storage._collection = trace_collection
    storage._chunks_collection = chunk_collection

    trace_doc = {
        "trace_id": "trace-1",
        "session_id": "session-1",
        "run_id": "run-1",
        "started_at": "started",
    }
    events = [
        _event("system", "a"),
        _event("user:message", "hello"),
        _event("done", "z"),
    ]

    await storage.replace_trace_events_with_chunks(trace_doc, events)

    assert chunk_collection.deleted_queries == [{"trace_id": "trace-1"}]
    assert [doc["chunk_index"] for doc in chunk_collection.inserted_docs] == [0, 1]
    assert [event["seq"] for doc in chunk_collection.inserted_docs for event in doc["events"]] == [
        1,
        2,
        3,
    ]
    update = trace_collection.update_calls[0][1]["$set"]
    assert update["event_count"] == 3
    assert update["chunk_count"] == 2
    assert update["first_event_preview"]["event_type"] == "system"
    assert update["first_user_message_preview"]["data"] == {"content": "hello"}
    assert update["last_event_preview"]["event_type"] == "done"
    assert update["metadata.event_storage"] == "chunked"
    assert trace_collection.update_calls[0][1]["$unset"] == {"events": ""}


@pytest.mark.asyncio
async def test_replace_trace_events_with_chunks_can_preserve_legacy_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(trace_storage_module.settings, "SESSION_EVENT_CHUNK_SIZE", 2, raising=False)
    storage = TraceStorage()
    trace_collection = _FakeTraceCollection()
    chunk_collection = _FakeChunkCollection()
    storage._collection = trace_collection
    storage._chunks_collection = chunk_collection

    await storage.replace_trace_events_with_chunks(
        {
            "trace_id": "trace-1",
            "session_id": "session-1",
            "run_id": "run-1",
            "started_at": "started",
        },
        [_event("message", "a")],
        remove_legacy_events=False,
    )

    assert "$unset" not in trace_collection.update_calls[0][1]


@pytest.mark.asyncio
async def test_read_trace_events_compat_prefers_chunks_over_legacy() -> None:
    storage = TraceStorage()
    storage._collection = _FakeTraceCollection(
        {"trace_id": "trace-1", "events": [_event("legacy", "old")]}
    )
    storage._chunks_collection = _FakeChunkCollection(
        [
            {"trace_id": "trace-1", "chunk_index": 1, "events": [_event("done", "z", 2)]},
            {"trace_id": "trace-1", "chunk_index": 0, "events": [_event("message", "a", 1)]},
        ]
    )

    events = await storage.read_trace_events_compat("trace-1")

    assert [event["event_type"] for event in events] == ["message", "done"]


@pytest.mark.asyncio
async def test_read_trace_events_compat_preserves_legacy_prefix_when_chunks_start_later() -> None:
    storage = TraceStorage()
    storage._collection = _FakeTraceCollection(
        {
            "trace_id": "trace-1",
            "events": [
                _event("user:message", "old-user", 1),
                _event("message", "old-assistant", 2),
            ],
        }
    )
    storage._chunks_collection = _FakeChunkCollection(
        [
            {
                "trace_id": "trace-1",
                "chunk_index": 0,
                "start_seq": 3,
                "events": [
                    _event("message", "new-a", 3),
                    _event("done", "done", 4),
                ],
            },
        ]
    )

    events = await storage.read_trace_events_compat("trace-1")

    assert [event["data"]["content"] for event in events] == [
        "old-user",
        "old-assistant",
        "new-a",
        "done",
    ]


@pytest.mark.asyncio
async def test_read_trace_events_compat_sorts_events_inside_chunks_by_seq() -> None:
    storage = TraceStorage()
    storage._collection = _FakeTraceCollection()
    storage._chunks_collection = _FakeChunkCollection(
        [
            {
                "trace_id": "trace-1",
                "chunk_index": 0,
                "events": [
                    _event("message", "b", 2),
                    _event("message", "a", 1),
                ],
            }
        ]
    )

    events = await storage.read_trace_events_compat("trace-1")

    assert [event["data"]["content"] for event in events] == ["a", "b"]


@pytest.mark.asyncio
async def test_read_trace_events_compat_tolerates_string_seq_values() -> None:
    storage = TraceStorage()
    storage._collection = _FakeTraceCollection()
    storage._chunks_collection = _FakeChunkCollection(
        [
            {
                "trace_id": "trace-1",
                "chunk_index": 0,
                "events": [
                    _event("message", "b", 2),
                    {**_event("message", "a"), "seq": "1"},
                ],
            },
        ]
    )

    events = await storage.read_trace_events_compat("trace-1")

    assert [event["data"]["content"] for event in events] == ["a", "b"]


@pytest.mark.asyncio
async def test_read_trace_events_compat_falls_back_to_legacy_events() -> None:
    storage = TraceStorage()
    storage._collection = _FakeTraceCollection(
        {"trace_id": "trace-1", "events": [_event("legacy", "old")]}
    )
    storage._chunks_collection = _FakeChunkCollection()

    events = await storage.read_trace_events_compat("trace-1")

    assert [event["event_type"] for event in events] == ["legacy"]


@pytest.mark.asyncio
async def test_read_trace_events_compat_filters_and_only_limits_when_requested() -> None:
    storage = TraceStorage()
    storage._collection = _FakeTraceCollection()
    storage._chunks_collection = _FakeChunkCollection(
        [
            {
                "trace_id": "trace-1",
                "chunk_index": 0,
                "events": [
                    _event("message", "a", 1),
                    _event("thinking", "b", 2),
                    _event("message", "c", 3),
                ],
            }
        ]
    )

    all_events = await storage.read_trace_events_compat("trace-1", event_types=["message"])
    limited_events = await storage.read_trace_events_compat(
        "trace-1",
        event_types=["message"],
        max_events=1,
    )

    assert [event["data"]["content"] for event in all_events] == ["a", "c"]
    assert [event["data"]["content"] for event in limited_events] == ["a"]


@pytest.mark.asyncio
async def test_get_trace_include_events_reads_chunk_events() -> None:
    storage = TraceStorage()
    storage._collection = _FakeTraceCollection({"trace_id": "trace-1", "events": []})
    storage._chunks_collection = _FakeChunkCollection(
        [{"trace_id": "trace-1", "chunk_index": 0, "events": [_event("message", "a", 1)]}]
    )

    trace = await storage.get_trace("trace-1", include_events=True)

    assert trace is not None
    assert [event["event_type"] for event in trace["events"]] == ["message"]


@pytest.mark.asyncio
async def test_get_trace_events_defaults_to_unlimited_chunk_read() -> None:
    storage = TraceStorage()
    storage._collection = _FakeTraceCollection()
    storage._chunks_collection = _FakeChunkCollection(
        [
            {
                "trace_id": "trace-1",
                "chunk_index": 0,
                "events": [_event("message", "a", 1), _event("message", "b", 2)],
            }
        ]
    )

    events = await storage.get_trace_events("trace-1")

    assert [event["data"]["content"] for event in events] == ["a", "b"]


@pytest.mark.asyncio
async def test_get_first_and_last_trace_event_read_chunks() -> None:
    storage = TraceStorage()
    storage._collection = _FakeTraceCollection()
    storage._chunks_collection = _FakeChunkCollection(
        [
            {
                "trace_id": "trace-1",
                "chunk_index": 0,
                "events": [_event("message", "a", 1), _event("token:usage", "old", 2)],
            },
            {
                "trace_id": "trace-1",
                "chunk_index": 1,
                "events": [_event("message", "b", 3), _event("token:usage", "new", 4)],
            },
        ]
    )

    first = await storage.get_first_trace_event("trace-1", event_types=["message"])
    last = await storage.get_last_trace_event("trace-1", event_types=["token:usage"])

    assert first is not None
    assert first["data"]["content"] == "a"
    assert last is not None
    assert last["data"]["content"] == "new"


@pytest.mark.asyncio
async def test_get_last_trace_event_scans_chunks_without_full_trace_read() -> None:
    class _TraceStorage(TraceStorage):
        async def read_trace_events_compat(self, *args, **kwargs):
            raise AssertionError("last event lookup should not read the full chunk trace")

    storage = _TraceStorage()
    storage._collection = _FakeTraceCollection()
    storage._chunks_collection = _FakeChunkCollection(
        [
            {
                "trace_id": "trace-1",
                "chunk_index": 0,
                "events": [_event("token:usage", "old", 1)],
            },
            {
                "trace_id": "trace-1",
                "chunk_index": 1,
                "events": [
                    _event("message", "later-message", 2),
                    _event("token:usage", "new", 3),
                ],
            },
        ]
    )

    last = await storage.get_last_trace_event("trace-1", event_types=["token:usage"])

    assert last is not None
    assert last["data"]["content"] == "new"


@pytest.mark.asyncio
async def test_complete_trace_adds_zero_token_usage_to_chunk_trace() -> None:
    class _TraceCollection(_FakeTraceCollection):
        async def update_one(self, query: dict[str, Any], update: dict[str, Any]):
            self.update_calls.append((query, update))
            return SimpleNamespace(modified_count=1)

    storage = TraceStorage()
    storage._collection = _TraceCollection(
        {
            "trace_id": "trace-1",
            "session_id": "session-1",
            "run_id": "run-1",
            "started_at": "started",
        }
    )
    storage._chunks_collection = _FakeChunkCollection(
        [
            {
                "trace_id": "trace-1",
                "chunk_index": 0,
                "events": [_event("done", "done", 1)],
            }
        ]
    )

    assert await storage.complete_trace("trace-1", ensure_token_usage=True) is True

    rewritten_events = storage.chunks_collection.inserted_docs[0]["events"]
    assert [event["event_type"] for event in rewritten_events] == ["token:usage", "done"]


@pytest.mark.asyncio
async def test_reserve_event_sequence_range_atomically_increments_event_count() -> None:
    storage = TraceStorage()
    collection = _FakeTraceCollection({"trace_id": "trace-1", "event_count": 3})
    storage._collection = collection

    trace_doc = await storage.reserve_event_sequence_range("trace-1", 2)

    assert trace_doc is not None
    assert trace_doc["event_count"] == 5
    assert collection.find_one_and_update_calls[0][0] == {"trace_id": "trace-1"}
    assert collection.find_one_and_update_calls[0][1]["$inc"] == {"event_count": 2}


@pytest.mark.asyncio
async def test_append_events_to_chunks_uses_reserved_sequence_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(trace_storage_module.settings, "SESSION_EVENT_CHUNK_SIZE", 2, raising=False)
    storage = TraceStorage()
    trace_collection = _FakeTraceCollection()
    chunk_collection = _FakeChunkCollection()
    storage._collection = trace_collection
    storage._chunks_collection = chunk_collection

    await storage.append_events_to_chunks(
        {
            "trace_id": "trace-1",
            "session_id": "session-1",
            "run_id": "run-1",
            "started_at": "started",
        },
        [_event("message", "a"), _event("message", "b"), _event("done", "z")],
        start_seq=1,
    )

    assert [call[0]["chunk_index"] for call in chunk_collection.update_calls] == [0, 1]
    assert [
        event["seq"]
        for _query, update, _upsert in chunk_collection.update_calls
        for event in update[0]["$set"]["events"]["$concatArrays"][1]
    ] == [1, 2, 3]
    trace_update_doc = trace_collection.update_calls[0][1]
    trace_update = trace_update_doc["$set"]
    assert trace_update_doc["$max"] == {"chunk_count": 2}
    last_preview_query, last_preview_update = trace_collection.update_calls[1]
    assert last_preview_query == {
        "trace_id": "trace-1",
        "$or": [
            {"event_count": {"$lte": 3}},
            {"event_count": {"$exists": False}},
        ],
    }
    assert last_preview_update["$set"]["last_event_preview"]["event_type"] == "done"


@pytest.mark.asyncio
async def test_append_events_to_chunks_replaces_existing_reserved_sequence_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(trace_storage_module.settings, "SESSION_EVENT_CHUNK_SIZE", 4, raising=False)
    storage = TraceStorage()
    trace_collection = _FakeTraceCollection()
    chunk_collection = _FakeChunkCollection()
    storage._collection = trace_collection
    storage._chunks_collection = chunk_collection

    await storage.append_events_to_chunks(
        {"trace_id": "trace-1", "session_id": "session-1", "run_id": "run-1"},
        [_event("message", "retry-a"), _event("message", "retry-b")],
        start_seq=2,
    )

    update = chunk_collection.update_calls[0][1]
    event_filter = update[0]["$set"]["events"]["$concatArrays"][0]["$filter"]

    assert event_filter["cond"]["$not"][0]["$and"] == [
        {"$gte": [{"$ifNull": ["$$event.seq", 0]}, 2]},
        {"$lte": [{"$ifNull": ["$$event.seq", 0]}, 3]},
    ]
    assert [event["seq"] for event in update[0]["$set"]["events"]["$concatArrays"][1]] == [2, 3]
    assert update[1]["$set"]["event_count"] == {"$size": "$events"}


@pytest.mark.asyncio
async def test_append_events_to_chunks_does_not_move_trace_summary_backwards(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(trace_storage_module.settings, "SESSION_EVENT_CHUNK_SIZE", 2, raising=False)
    storage = TraceStorage()
    trace_collection = _FakeTraceCollection()
    chunk_collection = _FakeChunkCollection()
    storage._collection = trace_collection
    storage._chunks_collection = chunk_collection

    await storage.append_events_to_chunks(
        {
            "trace_id": "trace-1",
            "session_id": "session-1",
            "run_id": "run-1",
            "event_count": 4,
        },
        [_event("message", "old-a"), _event("message", "old-b")],
        start_seq=1,
    )

    summary_query, summary_update = trace_collection.update_calls[0]

    assert summary_query == {"trace_id": "trace-1"}
    assert summary_update["$max"] == {"chunk_count": 1}
    assert "last_event_preview" not in summary_update["$set"]
    last_preview_query = trace_collection.update_calls[1][0]
    assert last_preview_query == {
        "trace_id": "trace-1",
        "$or": [
            {"event_count": {"$lte": 2}},
            {"event_count": {"$exists": False}},
        ],
    }


@pytest.mark.asyncio
async def test_append_events_to_chunks_only_sets_first_user_preview_for_prefix_batch() -> None:
    storage = TraceStorage()
    trace_collection = _FakeTraceCollection()
    chunk_collection = _FakeChunkCollection()
    storage._collection = trace_collection
    storage._chunks_collection = chunk_collection

    await storage.append_events_to_chunks(
        {
            "trace_id": "trace-1",
            "session_id": "session-1",
            "run_id": "run-1",
            "event_count": 4,
        },
        [_event("user:message", "later-user")],
        start_seq=4,
    )

    summary_update = trace_collection.update_calls[0][1]["$set"]

    assert "first_user_message_preview" not in summary_update


@pytest.mark.asyncio
async def test_rollback_event_sequence_range_removes_reserved_chunk_events() -> None:
    from src.infra.session import trace_storage as trace_storage_module

    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(trace_storage_module.settings, "SESSION_EVENT_CHUNK_SIZE", 2, raising=False)
    storage = TraceStorage()
    trace_collection = _FakeTraceCollection()
    chunk_collection = _FakeChunkCollection()
    storage._collection = trace_collection
    storage._chunks_collection = chunk_collection

    try:
        await storage.rollback_event_sequence_range(
            {"trace_id": "trace-1", "event_count": 7},
            start_seq=2,
            event_count=4,
        )

        assert [call[0] for call in chunk_collection.update_calls] == [
            {"trace_id": "trace-1", "chunk_index": 0, "events.seq": {"$gte": 2, "$lte": 2}},
            {"trace_id": "trace-1", "chunk_index": 1, "events.seq": {"$gte": 3, "$lte": 4}},
            {"trace_id": "trace-1", "chunk_index": 2, "events.seq": {"$gte": 5, "$lte": 5}},
        ]
        assert [call[1]["$pull"] for call in chunk_collection.update_calls] == [
            {"events": {"seq": {"$gte": 2, "$lte": 2}}},
            {"events": {"seq": {"$gte": 3, "$lte": 4}}},
            {"events": {"seq": {"$gte": 5, "$lte": 5}}},
        ]
        assert [call[1]["$inc"] for call in chunk_collection.update_calls] == [
            {"event_count": -1},
            {"event_count": -2},
            {"event_count": -1},
        ]
        trace_query, trace_update = trace_collection.update_calls[0]
        assert trace_query == {"trace_id": "trace-1", "event_count": 7}
        assert trace_update["$inc"] == {"event_count": -4}
    finally:
        monkeypatch.undo()


@pytest.mark.asyncio
async def test_rollback_event_sequence_range_only_decrements_latest_reservation() -> None:
    storage = TraceStorage()
    trace_collection = _FakeTraceCollection()
    chunk_collection = _FakeChunkCollection()
    storage._collection = trace_collection
    storage._chunks_collection = chunk_collection

    await storage.rollback_event_sequence_range(
        {"trace_id": "trace-1", "event_count": 7},
        start_seq=6,
        event_count=2,
    )

    trace_query, trace_update = trace_collection.update_calls[0]
    assert trace_query == {"trace_id": "trace-1", "event_count": 7}
    assert trace_update["$inc"] == {"event_count": -2}


@pytest.mark.asyncio
async def test_get_session_events_reads_chunks_across_traces_in_started_order() -> None:
    storage = TraceStorage()
    storage._collection = _FakeSessionTraceCollection(
        [
            {
                "trace_id": "trace-late",
                "session_id": "session-1",
                "run_id": "run-late",
                "status": "completed",
                "started_at": "2026-04-25T00:02:00Z",
            },
            {
                "trace_id": "trace-early",
                "session_id": "session-1",
                "run_id": "run-early",
                "status": "completed",
                "started_at": "2026-04-25T00:01:00Z",
            },
        ]
    )
    storage._chunks_collection = _FakeChunkCollection(
        [
            {
                "trace_id": "trace-late",
                "chunk_index": 0,
                "events": [_event("message", "late", 1)],
            },
            {
                "trace_id": "trace-early",
                "chunk_index": 0,
                "events": [_event("message", "early", 1), _event("done", "done", 2)],
            },
        ]
    )

    events = await storage.get_session_events("session-1", event_types=["message"])

    assert [(event["trace_id"], event["run_id"], event["data"]["content"]) for event in events] == [
        ("trace-early", "run-early", "early"),
        ("trace-late", "run-late", "late"),
    ]
    assert storage.collection.find_calls == [
        (
            {"session_id": "session-1", "status": {"$ne": "running"}},
            {
                "_id": 0,
                "trace_id": 1,
                "run_id": 1,
                "started_at": 1,
            },
        )
    ]


@pytest.mark.asyncio
async def test_get_session_events_applies_explicit_limit_across_chunks() -> None:
    storage = TraceStorage()
    storage._collection = _FakeSessionTraceCollection(
        [
            {
                "trace_id": "trace-1",
                "session_id": "session-1",
                "run_id": "run-1",
                "status": "completed",
                "started_at": "2026-04-25T00:01:00Z",
            }
        ]
    )
    storage._chunks_collection = _FakeChunkCollection(
        [
            {
                "trace_id": "trace-1",
                "chunk_index": 0,
                "events": [_event("message", "a", 1), _event("message", "b", 2)],
            }
        ]
    )

    events = await storage.get_session_events("session-1", max_events=1)

    assert [event["data"]["content"] for event in events] == ["a"]


@pytest.mark.asyncio
async def test_get_session_events_passes_remaining_limit_to_trace_reads() -> None:
    class _TraceStorage(TraceStorage):
        def __init__(self) -> None:
            super().__init__()
            self.read_limits: list[int | None] = []

        async def read_trace_events_compat(
            self,
            trace_id: str,
            event_types: list[str] | None = None,
            max_events: int | None = None,
        ) -> list[dict[str, Any]]:
            del trace_id, event_types
            self.read_limits.append(max_events)
            return [
                _event("message", "a", 1),
                _event("message", "b", 2),
            ]

    storage = _TraceStorage()
    storage._collection = _FakeSessionTraceCollection(
        [
            {
                "trace_id": "trace-1",
                "session_id": "session-1",
                "run_id": "run-1",
                "status": "completed",
                "started_at": "2026-04-25T00:01:00Z",
            }
        ]
    )
    storage._chunks_collection = _FakeChunkCollection()

    events = await storage.get_session_events("session-1", max_events=1)

    assert storage.read_limits == [1]
    assert [event["data"]["content"] for event in events] == ["a"]
