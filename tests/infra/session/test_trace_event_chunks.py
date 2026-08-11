from __future__ import annotations

import asyncio
from copy import deepcopy
from types import SimpleNamespace
from typing import Any

import pytest

from src.infra.session import trace_storage as trace_storage_module
from src.infra.session.trace_storage import TraceStorage


class _AsyncCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.docs = docs
        self.sort_args: tuple[str, int] | list[tuple[str, int]] | None = None

    def sort(self, key, direction: int | None = None):
        if isinstance(key, list):
            self.sort_args = key
            for sort_key, sort_direction in reversed(key):
                self.docs.sort(
                    key=lambda item: item.get(sort_key, 0),
                    reverse=sort_direction < 0,
                )
            return self

        assert direction is not None
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

    async def to_list(self, length: int | None = None):
        return deepcopy(self.docs if length is None else self.docs[:length])


class _FakeTraceCollection:
    def __init__(self, trace_doc: dict[str, Any] | None = None) -> None:
        self.trace_doc = trace_doc
        self.update_calls: list[tuple[dict[str, Any], dict[str, Any]]] = []
        self.find_one_and_update_calls: list[tuple[dict[str, Any], dict[str, Any]]] = []

    async def find_one(self, query: dict[str, Any], projection: dict[str, Any] | None = None):
        if self.trace_doc and _matches(self.trace_doc, query):
            return _project(self.trace_doc, projection)
        return None

    def find(self, query: dict[str, Any], projection: dict[str, Any] | None = None):
        documents = []
        if self.trace_doc and _matches(self.trace_doc, query):
            documents.append(_project(self.trace_doc, projection))
        return _AsyncCursor(documents)

    async def update_one(self, query: dict[str, Any], update: dict[str, Any]):
        self.update_calls.append((query, update))
        if not self.trace_doc or not _matches(self.trace_doc, query):
            return SimpleNamespace(matched_count=0, modified_count=0)
        before = deepcopy(self.trace_doc)
        _apply_update(self.trace_doc, update)
        return SimpleNamespace(
            matched_count=1,
            modified_count=int(before != self.trace_doc),
        )

    async def find_one_and_update(self, query: dict[str, Any], update: dict[str, Any], **kwargs):
        self.find_one_and_update_calls.append((query, update))
        if self.trace_doc and _matches(self.trace_doc, query):
            _apply_update(self.trace_doc, update)
            return _project(self.trace_doc, kwargs.get("projection"))
        return None


_MISSING = object()


def _nested_value(document: dict[str, Any], path: str) -> Any:
    value: Any = document
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return _MISSING
        value = value[part]
    return value


def _matches(document: dict[str, Any], query: dict[str, Any]) -> bool:
    for key, expected in query.items():
        if key == "$or":
            if not any(_matches(document, clause) for clause in expected):
                return False
            continue

        actual = _nested_value(document, key)
        if isinstance(expected, dict) and any(str(op).startswith("$") for op in expected):
            for operator, operand in expected.items():
                if operator == "$exists":
                    if (actual is not _MISSING) is not bool(operand):
                        return False
                elif operator == "$lte":
                    if actual is _MISSING or actual > operand:
                        return False
                elif operator == "$ne":
                    if actual is not _MISSING and actual == operand:
                        return False
                elif operator == "$in":
                    if actual is _MISSING or actual not in operand:
                        return False
                else:
                    raise AssertionError(f"unsupported fake query operator: {operator}")
            continue
        if actual is _MISSING or actual != expected:
            return False
    return True


def _set_nested(document: dict[str, Any], path: str, value: Any) -> None:
    target = document
    parts = path.split(".")
    for part in parts[:-1]:
        target = target.setdefault(part, {})
    target[parts[-1]] = deepcopy(value)


def _unset_nested(document: dict[str, Any], path: str) -> None:
    target: Any = document
    parts = path.split(".")
    for part in parts[:-1]:
        if not isinstance(target, dict) or part not in target:
            return
        target = target[part]
    if isinstance(target, dict):
        target.pop(parts[-1], None)


def _apply_update(document: dict[str, Any], update: dict[str, Any]) -> None:
    for path, value in update.get("$set", {}).items():
        _set_nested(document, path, value)
    for path in update.get("$unset", {}):
        _unset_nested(document, path)
    for path, increment in update.get("$inc", {}).items():
        current = _nested_value(document, path)
        _set_nested(document, path, (0 if current is _MISSING else current) + increment)
    for path, candidate in update.get("$max", {}).items():
        current = _nested_value(document, path)
        if current is _MISSING or current < candidate:
            _set_nested(document, path, candidate)
    for path, value in update.get("$push", {}).items():
        current = _nested_value(document, path)
        items = [] if current is _MISSING else list(current)
        items.append(deepcopy(value))
        _set_nested(document, path, items)


def _project(document: dict[str, Any], projection: dict[str, Any] | None) -> dict[str, Any]:
    result = deepcopy(document)
    if not projection:
        return result
    included = [key for key, enabled in projection.items() if enabled and key != "_id"]
    if included:
        projected: dict[str, Any] = {}
        if projection.get("_id", 1) and "_id" in result:
            projected["_id"] = result["_id"]
        for path in included:
            value = _nested_value(result, path)
            if value is not _MISSING:
                _set_nested(projected, path, value)
        return projected
    for path, enabled in projection.items():
        if not enabled:
            _unset_nested(result, path)
    return result


class _FakeChunkCollection:
    def __init__(self, chunks: list[dict[str, Any]] | None = None) -> None:
        self.chunks = chunks or []
        self.deleted_queries: list[dict[str, Any]] = []
        self.inserted_docs: list[dict[str, Any]] = []
        self.update_calls: list[tuple[dict[str, Any], dict[str, Any], bool]] = []
        self.update_many_calls: list[tuple[dict[str, Any], dict[str, Any]]] = []
        self.find_count = 0

    async def find_one(self, query: dict[str, Any], projection: dict[str, Any] | None = None):
        for chunk in self.chunks:
            if _matches(chunk, query):
                return _project(chunk, projection)
        return None

    def find(self, query: dict[str, Any], projection: dict[str, Any] | None = None):
        self.find_count += 1
        docs = [_project(chunk, projection) for chunk in self.chunks if _matches(chunk, query)]
        return _AsyncCursor(docs)

    async def delete_many(self, query: dict[str, Any]):
        self.deleted_queries.append(query)
        before = len(self.chunks)
        self.chunks = [chunk for chunk in self.chunks if not _matches(chunk, query)]
        return SimpleNamespace(deleted_count=before - len(self.chunks))

    async def insert_many(self, docs: list[dict[str, Any]]):
        self.inserted_docs.extend(docs)
        self.chunks.extend(docs)

    async def replace_one(
        self,
        query: dict[str, Any],
        document: dict[str, Any],
        upsert: bool = False,
    ):
        for index, chunk in enumerate(self.chunks):
            if _matches(chunk, query):
                self.chunks[index] = deepcopy(document)
                self.inserted_docs.append(deepcopy(document))
                return SimpleNamespace(matched_count=1, modified_count=1, upserted_id=None)
        if upsert:
            self.chunks.append(deepcopy(document))
            self.inserted_docs.append(deepcopy(document))
            return SimpleNamespace(matched_count=0, modified_count=0, upserted_id="upserted")
        return SimpleNamespace(matched_count=0, modified_count=0, upserted_id=None)

    async def update_one(self, query: dict[str, Any], update: dict[str, Any], upsert: bool = False):
        self.update_calls.append((query, update, upsert))

    async def update_many(self, query: dict[str, Any], update: dict[str, Any]):
        self.update_many_calls.append((query, update))
        modified = 0
        for chunk in self.chunks:
            if _matches(chunk, query):
                _apply_update(chunk, update)
                modified += 1
        return SimpleNamespace(matched_count=modified, modified_count=modified)


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
        docs = []
        for trace in self.traces:
            if trace.get("session_id") != query.get("session_id"):
                continue
            matches = True
            for key in ("run_id", "status"):
                if key not in query:
                    continue
                selector = query[key]
                value = trace.get(key)
                if isinstance(selector, dict) and "$in" in selector:
                    matches = value in selector["$in"]
                elif isinstance(selector, dict) and "$ne" in selector:
                    matches = value != selector["$ne"]
                else:
                    matches = value == selector
                if not matches:
                    break
            if matches:
                docs.append(trace)
        self.cursor = _SessionTraceCursor(docs)
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


def _trace_document(**overrides: Any) -> dict[str, Any]:
    document = {
        "_id": "parent-1",
        "trace_id": "trace-1",
        "session_id": "session-1",
        "run_id": "run-1",
        "started_at": "started",
        "updated_at": "version-1",
        "event_count": 0,
    }
    document.update(overrides)
    return document


def test_get_event_chunk_size_clamps_to_positive_int(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(trace_storage_module.settings, "SESSION_EVENT_CHUNK_SIZE", 0, raising=False)

    assert trace_storage_module._get_event_chunk_size() == 1


@pytest.mark.asyncio
async def test_replace_trace_events_with_chunks_splits_events_and_updates_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(trace_storage_module.settings, "SESSION_EVENT_CHUNK_SIZE", 2, raising=False)
    storage = TraceStorage()
    trace_collection = _FakeTraceCollection(_trace_document())
    chunk_collection = _FakeChunkCollection()
    storage._collection = trace_collection
    storage._chunks_collection = chunk_collection

    trace_doc = _trace_document()
    events = [
        _event("system", "a"),
        _event("user:message", "hello"),
        _event("done", "z"),
    ]

    assert (
        await storage.replace_trace_events_with_chunks(
            trace_doc,
            events,
            parent_updates={"metadata.merged": True},
        )
        is True
    )

    assert chunk_collection.deleted_queries == [{"trace_id": "trace-1"}]
    assert [doc["chunk_index"] for doc in chunk_collection.inserted_docs] == [0, 1]
    assert [event["seq"] for doc in chunk_collection.inserted_docs for event in doc["events"]] == [
        1,
        2,
        3,
    ]
    claim_query, claim_update = trace_collection.find_one_and_update_calls[0]
    assert claim_query == {
        "_id": "parent-1",
        "trace_id": "trace-1",
        "session_id": "session-1",
        "updated_at": "version-1",
        "attachment_chunk_write_operation": {"$exists": False},
        "event_revision": {"$exists": False},
    }
    claimed_marker = claim_update["$set"]["attachment_chunk_write_operation"]
    assert claimed_marker["kind"] == "replace"
    assert claim_update["$inc"] == {"event_revision": 1}

    final_query, final_update = trace_collection.update_calls[0]
    assert final_query == {
        "trace_id": "trace-1",
        "attachment_chunk_write_operation.id": claimed_marker["id"],
        "attachment_chunk_write_operation.phase": "installed",
        "attachment_chunk_write_operation.revision": claimed_marker["revision"],
        "event_revision": claimed_marker["revision"],
    }
    update = final_update["$set"]
    assert update["metadata.merged"] is True
    assert update["event_count"] == 3
    assert update["chunk_count"] == 2
    assert update["first_event_preview"]["event_type"] == "system"
    assert update["first_user_message_preview"]["data"] == {"content": "hello"}
    assert update["last_event_preview"]["event_type"] == "done"
    assert update["metadata.event_storage"] == "chunked"
    assert final_update["$unset"]["events"] == ""
    assert final_update["$unset"]["attachment_chunk_write_operation"] == ""


@pytest.mark.asyncio
async def test_replace_trace_events_with_chunks_can_preserve_legacy_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(trace_storage_module.settings, "SESSION_EVENT_CHUNK_SIZE", 2, raising=False)
    storage = TraceStorage()
    trace_collection = _FakeTraceCollection(_trace_document())
    chunk_collection = _FakeChunkCollection()
    storage._collection = trace_collection
    storage._chunks_collection = chunk_collection

    await storage.replace_trace_events_with_chunks(
        _trace_document(),
        [_event("message", "a")],
        remove_legacy_events=False,
    )

    assert "events" not in trace_collection.update_calls[0][1]["$unset"]
    assert trace_collection.update_calls[0][1]["$unset"]["attachment_chunk_write_operation"] == ""


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
async def test_read_trace_events_batch_compat_reads_all_traces_with_one_chunk_query() -> None:
    storage = TraceStorage()
    chunk_collection = _FakeChunkCollection(
        [
            {
                "trace_id": "chunked",
                "chunk_index": 0,
                "start_seq": 1,
                "events": [_event("message", "new", 1)],
            }
        ]
    )
    storage._chunks_collection = chunk_collection

    events_by_trace = await storage.read_trace_events_batch_compat(
        [
            {"trace_id": "legacy", "events": [_event("message", "old", 1)]},
            {"trace_id": "chunked", "events": []},
        ]
    )

    assert [event["data"]["content"] for event in events_by_trace["legacy"]] == ["old"]
    assert [event["data"]["content"] for event in events_by_trace["chunked"]] == ["new"]
    assert chunk_collection.find_count == 1


@pytest.mark.asyncio
async def test_read_trace_events_batch_compat_preserves_mixed_legacy_prefix_once() -> None:
    storage = TraceStorage()
    storage._chunks_collection = _FakeChunkCollection(
        [
            {
                "trace_id": "mixed",
                "chunk_index": 0,
                "start_seq": 3,
                "events": [_event("message", "three", 3)],
            }
        ]
    )

    events_by_trace = await storage.read_trace_events_batch_compat(
        [
            {
                "trace_id": "mixed",
                "events": [
                    _event("user:message", "one", 1),
                    _event("message", "two", 2),
                    _event("message", "duplicate-three", 3),
                ],
            }
        ]
    )

    assert [event["data"]["content"] for event in events_by_trace["mixed"]] == [
        "one",
        "two",
        "three",
    ]


@pytest.mark.asyncio
async def test_read_trace_events_batch_compat_filters_each_trace_without_reordering() -> None:
    storage = TraceStorage()
    storage._chunks_collection = _FakeChunkCollection(
        [
            {
                "trace_id": "trace-a",
                "chunk_index": 0,
                "start_seq": 1,
                "events": [
                    _event("message", "a-one", 1),
                    _event("thinking", "a-two", 2),
                    _event("message", "a-three", 3),
                ],
            },
            {
                "trace_id": "trace-b",
                "chunk_index": 0,
                "start_seq": 1,
                "events": [_event("message", "b-one", 1)],
            },
        ]
    )

    events_by_trace = await storage.read_trace_events_batch_compat(
        [{"trace_id": "trace-a"}, {"trace_id": "trace-b"}],
        event_types=["message"],
    )

    assert [event["data"]["content"] for event in events_by_trace["trace-a"]] == [
        "a-one",
        "a-three",
    ]
    assert [event["data"]["content"] for event in events_by_trace["trace-b"]] == ["b-one"]


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
    storage._collection = _TraceCollection(_trace_document())
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
    collection = _FakeTraceCollection(_trace_document(event_count=3))
    storage._collection = collection

    trace_doc = await storage.reserve_event_sequence_range("trace-1", 2)

    assert trace_doc is not None
    assert trace_doc["event_count"] == 5
    marker = trace_doc["attachment_chunk_write_operation"]
    assert marker["kind"] == "append"
    assert marker["phase"] == "reserved"
    assert marker["start_seq"] == 4
    assert marker["event_count"] == 2
    assert marker["reserved_event_count"] == 5
    assert marker["recovery_after"] is not None
    assert collection.find_one_and_update_calls[0][0] == {
        "trace_id": "trace-1",
        "updated_at": "version-1",
        "attachment_chunk_write_operation": {"$exists": False},
        "event_revision": {"$exists": False},
    }
    assert collection.find_one_and_update_calls[0][1]["$inc"] == {
        "event_count": 2,
        "event_revision": 1,
    }
    assert (
        collection.find_one_and_update_calls[0][1]["$set"]["attachment_chunk_write_operation"][
            "kind"
        ]
        == "append"
    )


@pytest.mark.asyncio
async def test_reserve_event_sequence_range_refuses_an_existing_chunk_write_marker() -> None:
    marker = {"id": "replace-in-progress", "kind": "replace"}
    storage = TraceStorage()
    collection = _FakeTraceCollection(
        _trace_document(
            event_count=3,
            attachment_chunk_write_operation=marker,
        )
    )
    storage._collection = collection

    trace_doc = await storage.reserve_event_sequence_range("trace-1", 2)

    assert trace_doc is None
    assert collection.trace_doc is not None
    assert collection.trace_doc["event_count"] == 3
    assert collection.trace_doc["attachment_chunk_write_operation"] == marker


@pytest.mark.asyncio
async def test_append_events_to_chunks_uses_reserved_sequence_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(trace_storage_module.settings, "SESSION_EVENT_CHUNK_SIZE", 2, raising=False)
    storage = TraceStorage()
    trace_collection = _FakeTraceCollection(_trace_document())
    chunk_collection = _FakeChunkCollection()
    storage._collection = trace_collection
    storage._chunks_collection = chunk_collection

    reserved = await storage.reserve_event_sequence_range("trace-1", 3)
    assert reserved is not None

    assert (
        await storage.append_events_to_chunks(
            reserved,
            [_event("message", "a"), _event("message", "b"), _event("done", "z")],
            start_seq=1,
        )
        is True
    )

    assert [call[0]["chunk_index"] for call in chunk_collection.update_calls] == [0, 1]
    assert [
        event["seq"]
        for _query, update, _upsert in chunk_collection.update_calls
        for event in update[0]["$set"]["events"]["$concatArrays"][1]
    ] == [1, 2, 3]
    assert len(trace_collection.update_calls) == 1
    trace_update_query, trace_update_doc = trace_collection.update_calls[0]
    operation_id = reserved["attachment_chunk_write_operation"]["id"]
    append_digest = trace_update_query["attachment_chunk_write_operation.digest"]
    assert isinstance(append_digest, str)
    assert trace_update_query == {
        "trace_id": "trace-1",
        "attachment_chunk_write_operation.id": operation_id,
        "attachment_chunk_write_operation.revision": reserved["event_revision"],
        "attachment_chunk_write_operation.phase": "writing",
        "attachment_chunk_write_operation.digest": append_digest,
        "event_revision": reserved["event_revision"],
    }
    trace_update = trace_update_doc["$set"]
    assert trace_update_doc["$max"] == {"chunk_count": 2}
    assert trace_update["last_event_preview"]["event_type"] == "done"
    assert trace_update_doc["$unset"] == {"attachment_chunk_write_operation": ""}


@pytest.mark.asyncio
async def test_append_events_to_chunks_does_not_upsert_when_parent_version_is_stale() -> None:
    storage = TraceStorage()
    trace_collection = _FakeTraceCollection(_trace_document(updated_at="version-2"))
    chunk_collection = _FakeChunkCollection()
    storage._collection = trace_collection
    storage._chunks_collection = chunk_collection

    appended = await storage.append_events_to_chunks(
        _trace_document(updated_at="version-1"),
        [_event("message", "must-survive")],
        start_seq=1,
    )

    assert appended is False
    assert chunk_collection.update_calls == []
    assert chunk_collection.deleted_queries == []
    assert chunk_collection.inserted_docs == []


@pytest.mark.asyncio
async def test_append_events_to_chunks_replaces_existing_reserved_sequence_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(trace_storage_module.settings, "SESSION_EVENT_CHUNK_SIZE", 4, raising=False)
    storage = TraceStorage()
    trace_collection = _FakeTraceCollection(_trace_document(event_count=3))
    chunk_collection = _FakeChunkCollection()
    storage._collection = trace_collection
    storage._chunks_collection = chunk_collection

    assert (
        await storage.append_events_to_chunks(
            _trace_document(event_count=3),
            [_event("message", "retry-a"), _event("message", "retry-b")],
            start_seq=2,
        )
        is True
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
    trace_collection = _FakeTraceCollection(_trace_document(event_count=4))
    chunk_collection = _FakeChunkCollection()
    storage._collection = trace_collection
    storage._chunks_collection = chunk_collection

    assert (
        await storage.append_events_to_chunks(
            _trace_document(event_count=4),
            [_event("message", "old-a"), _event("message", "old-b")],
            start_seq=1,
        )
        is True
    )

    summary_query, summary_update = trace_collection.update_calls[0]

    assert summary_query["trace_id"] == "trace-1"
    assert "attachment_chunk_write_operation.id" in summary_query
    assert summary_update["$max"] == {"chunk_count": 1}
    assert "last_event_preview" not in summary_update["$set"]
    assert len(trace_collection.update_calls) == 1


@pytest.mark.asyncio
async def test_append_events_to_chunks_only_sets_first_user_preview_for_prefix_batch() -> None:
    storage = TraceStorage()
    trace_collection = _FakeTraceCollection(_trace_document(event_count=4))
    chunk_collection = _FakeChunkCollection()
    storage._collection = trace_collection
    storage._chunks_collection = chunk_collection

    assert (
        await storage.append_events_to_chunks(
            _trace_document(event_count=4),
            [_event("user:message", "later-user")],
            start_seq=4,
        )
        is True
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
        assert trace_query == {
            "trace_id": "trace-1",
            "event_count": 7,
            "attachment_chunk_write_operation": {"$exists": False},
        }
        assert trace_update["$inc"] == {"event_count": -4, "event_revision": 1}
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
    assert trace_query == {
        "trace_id": "trace-1",
        "event_count": 7,
        "attachment_chunk_write_operation": {"$exists": False},
    }
    assert trace_update["$inc"] == {"event_count": -2, "event_revision": 1}


class _CancelAfterPersistingAppendChunk(_FakeChunkCollection):
    def __init__(self, chunks: list[dict[str, Any]]) -> None:
        super().__init__(chunks)
        self.cancel_next_append = True

    async def update_one(
        self,
        query: dict[str, Any],
        update: dict[str, Any] | list[dict[str, Any]],
        upsert: bool = False,
    ):
        self.update_calls.append((query, update, upsert))
        if isinstance(update, list) and "$concatArrays" in str(update):
            new_events = deepcopy(update[0]["$set"]["events"]["$concatArrays"][1])
            range_start = int(new_events[0]["seq"])
            range_end = int(new_events[-1]["seq"])
            chunk = next(
                (
                    item
                    for item in self.chunks
                    if item.get("trace_id") == query.get("trace_id")
                    and item.get("chunk_index") == query.get("chunk_index")
                ),
                None,
            )
            if chunk is None:
                chunk = {
                    "trace_id": query["trace_id"],
                    "chunk_index": query["chunk_index"],
                    "events": [],
                }
                self.chunks.append(chunk)
            chunk["events"] = [
                event
                for event in chunk.get("events", [])
                if not range_start <= int(event.get("seq", 0)) <= range_end
            ] + new_events
            chunk["events"].sort(key=lambda event: int(event.get("seq", 0)))
            chunk["event_count"] = len(chunk["events"])
            chunk["start_seq"] = min(event["seq"] for event in chunk["events"])
            chunk["end_seq"] = max(event["seq"] for event in chunk["events"])
            if self.cancel_next_append:
                self.cancel_next_append = False
                raise asyncio.CancelledError
            return SimpleNamespace(matched_count=1, modified_count=1)

        if isinstance(update, list) and "$filter" in str(update):
            seq_range = query["events"]["$elemMatch"]["seq"]
            range_start = int(seq_range["$gte"])
            range_end = int(seq_range["$lte"])
            chunk = next(
                (
                    item
                    for item in self.chunks
                    if item.get("trace_id") == query.get("trace_id")
                    and item.get("chunk_index") == query.get("chunk_index")
                ),
                None,
            )
            if chunk is None:
                return SimpleNamespace(matched_count=0, modified_count=0)
            chunk["events"] = [
                event
                for event in chunk.get("events", [])
                if not range_start <= int(event.get("seq", 0)) <= range_end
            ]
            chunk["event_count"] = len(chunk["events"])
            chunk["start_seq"] = min(
                (event["seq"] for event in chunk["events"]),
                default=None,
            )
            chunk["end_seq"] = max(
                (event["seq"] for event in chunk["events"]),
                default=None,
            )
            return SimpleNamespace(matched_count=1, modified_count=1)

        return await super().update_one(query, update, upsert=upsert)


@pytest.mark.asyncio
async def test_expired_append_reservation_rolls_back_before_future_reserve() -> None:
    storage = TraceStorage()
    trace_collection = _FakeTraceCollection(_trace_document(event_count=3))
    storage._collection = trace_collection
    storage._chunks_collection = _FakeChunkCollection()

    abandoned = await storage.reserve_event_sequence_range("trace-1", 2)
    assert abandoned is not None
    trace_collection.trace_doc["attachment_chunk_write_operation"]["recovery_after"] = "past"

    assert await storage.recover_incomplete_chunk_appends() == 1
    assert trace_collection.trace_doc["event_count"] == 3
    assert "attachment_chunk_write_operation" not in trace_collection.trace_doc

    next_reservation = await storage.reserve_event_sequence_range("trace-1", 1)
    assert next_reservation is not None
    next_marker = next_reservation["attachment_chunk_write_operation"]
    assert next_marker["start_seq"] == 4
    assert next_reservation["event_count"] == 4


@pytest.mark.asyncio
async def test_reserved_sequence_retry_recovers_its_expired_marker_without_merger() -> None:
    storage = TraceStorage()
    trace_collection = _FakeTraceCollection(_trace_document(event_count=3))
    storage._collection = trace_collection
    storage._chunks_collection = _FakeChunkCollection()

    abandoned = await storage.reserve_event_sequence_range("trace-1", 2)
    assert abandoned is not None
    trace_collection.trace_doc["attachment_chunk_write_operation"]["recovery_after"] = "past"

    appended = await storage.append_events_to_chunks(
        {"trace_id": "trace-1", "session_id": "session-1", "run_id": "run-1"},
        [_event("message", "retry-a"), _event("message", "retry-b")],
        start_seq=4,
    )

    assert appended is True
    assert trace_collection.trace_doc["event_count"] == 5
    assert "attachment_chunk_write_operation" not in trace_collection.trace_doc


@pytest.mark.asyncio
async def test_cancelled_partial_append_is_recovered_idempotently_by_exact_sequence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(trace_storage_module.settings, "SESSION_EVENT_CHUNK_SIZE", 4, raising=False)
    storage = TraceStorage()
    trace_collection = _FakeTraceCollection(_trace_document(event_count=1))
    chunk_collection = _CancelAfterPersistingAppendChunk(
        [
            {
                "trace_id": "trace-1",
                "chunk_index": 0,
                "start_seq": 1,
                "end_seq": 1,
                "event_count": 1,
                "events": [_event("message", "before", 1)],
            }
        ]
    )
    storage._collection = trace_collection
    storage._chunks_collection = chunk_collection

    reserved = await storage.reserve_event_sequence_range("trace-1", 2)
    assert reserved is not None
    with pytest.raises(asyncio.CancelledError):
        await storage.append_events_to_chunks(
            reserved,
            [_event("message", "partial-a"), _event("message", "partial-b")],
            start_seq=2,
        )

    marker = trace_collection.trace_doc["attachment_chunk_write_operation"]
    assert marker["phase"] == "writing"
    assert isinstance(marker["digest"], str)
    marker["recovery_after"] = "past"

    assert await storage.recover_incomplete_chunk_appends() == 1
    assert await storage.recover_incomplete_chunk_appends() == 0
    assert trace_collection.trace_doc["event_count"] == 1
    assert "attachment_chunk_write_operation" not in trace_collection.trace_doc
    assert [event["data"]["content"] for event in chunk_collection.chunks[0]["events"]] == [
        "before"
    ]
    assert chunk_collection.chunks[0]["event_count"] == 1
    assert chunk_collection.chunks[0]["start_seq"] == 1
    assert chunk_collection.chunks[0]["end_seq"] == 1


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
                "status": 1,
                "started_at": 1,
                "events": 1,
                "recommend_questions": 1,
                "recommend_questions_updated_at": 1,
            },
        )
    ]


@pytest.mark.asyncio
async def test_get_session_events_snapshot_returns_active_user_and_requires_stream_replay() -> None:
    storage = TraceStorage()
    trace_collection = _FakeSessionTraceCollection(
        [
            {
                "trace_id": "trace-old",
                "session_id": "session-1",
                "run_id": "run-old",
                "status": "completed",
                "started_at": "2026-04-25T00:01:00Z",
            },
            {
                "trace_id": "trace-active",
                "session_id": "session-1",
                "run_id": "run-active",
                "status": "running",
                "started_at": "2026-04-25T00:02:00Z",
            },
        ]
    )
    chunk_collection = _FakeChunkCollection(
        [
            {
                "trace_id": "trace-old",
                "chunk_index": 0,
                "start_seq": 1,
                "events": [
                    _event("user:message", "old-user", 1),
                    _event("message:chunk", "old-assistant", 2),
                ],
            },
            {
                "trace_id": "trace-active",
                "chunk_index": 0,
                "start_seq": 1,
                "events": [
                    _event("user:message", "active-user", 1),
                    _event("message:chunk", "active-assistant", 2),
                ],
            },
        ]
    )
    storage._collection = trace_collection
    storage._chunks_collection = chunk_collection

    snapshot = await storage.get_session_events_snapshot(
        "session-1",
        active_run_id="run-active",
    )

    assert snapshot.history_mode == "active_user_only"
    assert snapshot.stream_run_id == "run-active"
    assert [(event["run_id"], event["event_type"]) for event in snapshot.events] == [
        ("run-old", "user:message"),
        ("run-old", "message:chunk"),
        ("run-active", "user:message"),
    ]
    assert len(trace_collection.find_calls) == 1
    assert chunk_collection.find_count == 1


@pytest.mark.asyncio
async def test_get_session_events_snapshot_returns_complete_trace_after_terminal_transition() -> (
    None
):
    storage = TraceStorage()
    storage._collection = _FakeSessionTraceCollection(
        [
            {
                "trace_id": "trace-active",
                "session_id": "session-1",
                "run_id": "run-active",
                "status": "completed",
                "started_at": "2026-04-25T00:02:00Z",
                "events": [
                    _event("user:message", "active-user", 1),
                    _event("message:chunk", "active-assistant", 2),
                    _event("done", "done", 3),
                ],
            }
        ]
    )
    storage._chunks_collection = _FakeChunkCollection()

    snapshot = await storage.get_session_events_snapshot(
        "session-1",
        active_run_id="run-active",
    )

    assert snapshot.history_mode == "complete"
    assert snapshot.stream_run_id is None
    assert [event["event_type"] for event in snapshot.events] == [
        "user:message",
        "message:chunk",
        "done",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("kwargs", "expected_selector", "expected_runs"),
    [
        ({"run_id": "run-b"}, "run-b", ["run-b"]),
        ({"run_ids": ["run-a"]}, {"$in": ["run-a"]}, ["run-a"]),
        ({"exclude_run_id": "run-a"}, {"$ne": "run-a"}, ["run-b"]),
    ],
)
async def test_get_session_events_snapshot_preserves_run_selectors(
    kwargs: dict[str, Any],
    expected_selector: Any,
    expected_runs: list[str],
) -> None:
    storage = TraceStorage()
    trace_collection = _FakeSessionTraceCollection(
        [
            {
                "trace_id": "trace-a",
                "session_id": "session-1",
                "run_id": "run-a",
                "status": "completed",
                "started_at": "2026-04-25T00:01:00Z",
                "events": [_event("message", "a", 1)],
            },
            {
                "trace_id": "trace-b",
                "session_id": "session-1",
                "run_id": "run-b",
                "status": "completed",
                "started_at": "2026-04-25T00:02:00Z",
                "events": [_event("message", "b", 1)],
            },
        ]
    )
    storage._collection = trace_collection
    storage._chunks_collection = _FakeChunkCollection()

    snapshot = await storage.get_session_events_snapshot("session-1", **kwargs)

    assert [event["run_id"] for event in snapshot.events] == expected_runs
    assert trace_collection.find_calls[0][0]["run_id"] == expected_selector


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
async def test_get_session_events_uses_one_batch_read_and_applies_limit() -> None:
    class _TraceStorage(TraceStorage):
        def __init__(self) -> None:
            super().__init__()
            self.batch_reads: list[list[str]] = []

        async def read_trace_events_batch_compat(
            self,
            trace_docs: list[dict[str, Any]],
            event_types: list[str] | None = None,
        ) -> dict[str, list[dict[str, Any]]]:
            del event_types
            trace_ids = [str(trace["trace_id"]) for trace in trace_docs]
            self.batch_reads.append(trace_ids)
            return {
                "trace-1": [
                    _event("message", "a", 1),
                    _event("message", "b", 2),
                ]
            }

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

    assert storage.batch_reads == [["trace-1"]]
    assert [event["data"]["content"] for event in events] == ["a"]


@pytest.mark.asyncio
async def test_parent_append_is_fenced_during_chunk_replacement_and_can_retry() -> None:
    storage = TraceStorage()
    trace_collection = _FakeTraceCollection(
        _trace_document(
            events=[_event("message", "before")],
            event_count=1,
            metadata={"merged": True},
        )
    )
    storage._collection = trace_collection
    storage._chunks_collection = _FakeChunkCollection()

    claim = await storage._claim_chunk_write(trace_collection.trace_doc, kind="replace")

    assert claim is not None
    assert await storage.append_event("trace-1", "message", {"content": "during"}) is False
    assert [event["data"]["content"] for event in trace_collection.trace_doc["events"]] == [
        "before"
    ]

    operation_id, claimed = claim
    marker = claimed["attachment_chunk_write_operation"]
    result = await trace_collection.update_one(
        {
            "trace_id": "trace-1",
            "attachment_chunk_write_operation.id": operation_id,
        },
        {"$unset": {"attachment_chunk_write_operation": ""}},
    )
    assert result.modified_count == 1
    assert marker["revision"] == claimed["event_revision"]

    assert await storage.append_event("trace-1", "message", {"content": "after"}) is True
    assert [event["data"]["content"] for event in trace_collection.trace_doc["events"]] == [
        "before",
        "after",
    ]
    assert trace_collection.trace_doc["metadata"]["merged"] is False


class _FailOnceReplacementChunks(_FakeChunkCollection):
    def __init__(self, failure: str) -> None:
        super().__init__([{"trace_id": "trace-1", "chunk_index": 0, "events": []}])
        self.failure = failure
        self.failed = False

    async def delete_many(self, query: dict[str, Any]):
        if self.failure == "delete" and not self.failed:
            self.failed = True
            raise RuntimeError("transient replacement delete")
        return await super().delete_many(query)

    async def replace_one(
        self,
        query: dict[str, Any],
        document: dict[str, Any],
        upsert: bool = False,
    ):
        if self.failure in {"insert", "cancel"} and not self.failed:
            self.failed = True
            self.chunks.append(deepcopy(document))
            if self.failure == "cancel":
                raise asyncio.CancelledError
            raise RuntimeError("transient replacement insert")
        return await super().replace_one(query, document, upsert=upsert)


class _FailOnceReplacementFinal(_FakeTraceCollection):
    def __init__(self) -> None:
        super().__init__(_trace_document())
        self.failed = False

    async def update_one(self, query: dict[str, Any], update: dict[str, Any]):
        if query.get("attachment_chunk_write_operation.phase") == "installed" and not self.failed:
            self.failed = True
            raise RuntimeError("transient replacement final")
        return await super().update_one(query, update)

    def find(self, query: dict[str, Any], projection: dict[str, Any] | None = None):
        documents = []
        if self.trace_doc and _matches(self.trace_doc, query):
            documents.append(_project(self.trace_doc, projection))
        return _AsyncCursor(documents)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["delete", "insert", "final", "cancel"])
async def test_chunk_replacement_recovers_after_partial_failure_or_cancellation(
    failure: str,
) -> None:
    storage = TraceStorage()
    trace_collection = (
        _FailOnceReplacementFinal()
        if failure == "final"
        else _FakeTraceCollection(_trace_document())
    )
    chunk_collection = _FailOnceReplacementChunks(failure)
    storage._collection = trace_collection
    storage._chunks_collection = chunk_collection
    events = [_event("message", "replacement")]

    expected_error = asyncio.CancelledError if failure == "cancel" else RuntimeError
    with pytest.raises(expected_error):
        await storage.replace_trace_events_with_chunks(_trace_document(), events)

    assert trace_collection.trace_doc is not None
    assert "attachment_chunk_write_operation" in trace_collection.trace_doc

    assert await storage.replace_trace_events_with_chunks(_trace_document(), events) is True
    assert "attachment_chunk_write_operation" not in trace_collection.trace_doc
    assert [
        event["data"]["content"]
        for chunk in chunk_collection.chunks
        if chunk.get("trace_id") == "trace-1"
        for event in chunk.get("events", [])
    ] == ["replacement"]


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["insert", "final"])
async def test_stale_chunk_replacement_is_automatically_recovered(failure: str) -> None:
    storage = TraceStorage()
    trace_collection = _FailOnceReplacementFinal()
    if failure != "final":
        trace_collection.failed = True
    chunk_collection = _FailOnceReplacementChunks(failure)
    storage._collection = trace_collection
    storage._chunks_collection = chunk_collection
    events = [_event("message", "replacement")]

    with pytest.raises(RuntimeError):
        await storage.replace_trace_events_with_chunks(_trace_document(), events)
    assert trace_collection.trace_doc is not None
    trace_collection.trace_doc["attachment_chunk_write_operation"]["recovery_after"] = "past"

    assert await storage.recover_incomplete_chunk_replacements() == 1
    assert "attachment_chunk_write_operation" not in trace_collection.trace_doc
    contents = [
        event["data"]["content"]
        for chunk in chunk_collection.chunks
        if chunk.get("trace_id") == "trace-1"
        for event in chunk.get("events", [])
    ]
    assert contents == ([] if failure == "insert" else ["replacement"])
