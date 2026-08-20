from __future__ import annotations

"""Regression tests for chunk-marker deadlocks around trace completion.

Production symptom (SESSION_EVENT_CHUNK_STORAGE_ENABLED=true): after a run
finished (SSE delivered done), refreshing GET /api/sessions/{id}/events
returned only the user:message and recommend:questions events, with
history_mode="active_user_only". Root cause: a chunk-write marker stuck on
the trace fenced complete_trace (its query requires the marker to be
absent), so the trace stayed status="running" and the read path hid every
non-user event behind an SSE replay that already ended.
"""

import asyncio
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
from typing import Any

import pytest

from src.infra.session import trace_storage as trace_storage_module
from src.infra.session.trace_storage import TraceStorage
from src.infra.utils.datetime import utc_now


class _AsyncCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.docs = docs

    def sort(self, key, direction=None):
        return self

    def limit(self, limit):
        return self

    def __aiter__(self):
        self._iter = iter(self.docs)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc

    async def to_list(self, length=None):
        return deepcopy(self.docs)


class _FakeCollection:
    """Minimal in-memory mongo collection covering the operators used here."""

    def __init__(self, doc: dict[str, Any] | None = None) -> None:
        self.doc = doc

    def find(self, query, projection=None):
        docs = [self.doc] if self.doc and _matches(self.doc, query) else []
        return _AsyncCursor(docs)

    async def find_one(self, query, projection=None):
        if self.doc and _matches(self.doc, query):
            return deepcopy(self.doc)
        return None

    async def find_one_and_update(self, query, update, **kwargs):
        if not self.doc or not _matches(self.doc, query):
            return None
        _apply_update(self.doc, update)
        return deepcopy(self.doc)

    async def update_one(self, query, update, upsert=False):
        if not self.doc or not _matches(self.doc, query):
            if upsert and self.doc is None and query.get("trace_id"):
                self.doc = deepcopy(query)
                _apply_update(self.doc, update)
                return SimpleNamespace(matched_count=0, modified_count=1)
            return SimpleNamespace(matched_count=0, modified_count=0)
        before = deepcopy(self.doc)
        _apply_update(self.doc, update)
        return SimpleNamespace(
            matched_count=1,
            modified_count=int(before != self.doc),
        )


_MISSING = object()


def _nested(document: dict[str, Any], path: str) -> Any:
    value: Any = document
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return _MISSING
        value = value[part]
    return value


def _matches(document: dict[str, Any], query: dict[str, Any]) -> bool:
    for key, expected in query.items():
        value = _nested(document, key)
        if isinstance(expected, dict):
            for op, operand in expected.items():
                if op == "$exists":
                    if (value is not _MISSING) != bool(operand):
                        return False
                elif op == "$in":
                    if value not in operand:
                        return False
                elif op == "$eq":
                    if value != operand:
                        return False
                elif op == "$ne":
                    if value == operand:
                        return False
                else:
                    raise AssertionError(f"unsupported op {op}")
        elif value != expected:
            return False
    return True


def _apply_update(document: dict[str, Any], update: dict[str, Any]) -> None:
    for key, value in update.items():
        if key == "$set":
            for path, item in value.items():
                _set_nested(document, path, deepcopy(item))
        elif key == "$inc":
            for path, item in value.items():
                current = _nested(document, path)
                _set_nested(document, path, (0 if current is _MISSING else current) + item)
        elif key == "$unset":
            for path in value:
                _unset_nested(document, path)
        else:
            raise AssertionError(f"unsupported update {key}")


def _set_nested(document: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    node = document
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def _unset_nested(document: dict[str, Any], path: str) -> None:
    parts = path.split(".")
    node = document
    for part in parts[:-1]:
        if not isinstance(node, dict) or part not in node:
            return
        node = node[part]
    if isinstance(node, dict):
        node.pop(parts[-1], None)


class _FakeChunks:
    def __init__(self) -> None:
        self.docs: dict[tuple[str, int], dict[str, Any]] = {}
        self.fail_next = False

    async def update_one(self, query, update, upsert=False):
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("simulated chunk write failure")
        key = (query.get("trace_id"), query.get("chunk_index"))
        doc = self.docs.get(key)
        if doc is None:
            if not upsert:
                return SimpleNamespace(matched_count=0, modified_count=0)
            doc = {"trace_id": key[0], "chunk_index": key[1], "events": []}
            self.docs[key] = doc
        events = list(doc.get("events", []))
        for event in update.get("$set", {}).get("events", []) or []:
            events.append(event)
        doc["events"] = events
        return SimpleNamespace(matched_count=1, modified_count=1)


def _make_storage(monkeypatch, trace_doc, chunks=None):
    storage = object.__new__(TraceStorage)
    collection = _FakeCollection(trace_doc)
    chunks_collection = chunks or _FakeChunks()
    monkeypatch.setattr(
        trace_storage_module.TraceStorage, "collection", property(lambda self: collection)
    )
    monkeypatch.setattr(
        trace_storage_module.TraceStorage,
        "chunks_collection",
        property(lambda self: chunks_collection),
    )
    storage._merger = None
    storage._indexes_ensured = True
    return storage, collection, chunks_collection


@pytest.mark.asyncio
async def test_complete_trace_releases_stuck_append_marker(monkeypatch):
    """A stuck append marker must not block the running→completed transition."""
    marker = {
        "id": "op-stuck",
        "kind": "append",
        "revision": 3,
        # expired long ago; writer is gone
        "recovery_after": utc_now() - timedelta(minutes=10),
    }
    trace_doc = {
        "trace_id": "trace-1",
        "session_id": "session-1",
        "run_id": "run-1",
        "status": "running",
        "event_count": 5,
        "event_revision": 3,
        "attachment_chunk_write_operation": marker,
    }
    storage, collection, _ = _make_storage(monkeypatch, trace_doc)

    ok = await storage.complete_trace("trace-1", "completed", ensure_token_usage=False)
    assert ok is True
    assert collection.doc["status"] == "completed"
    assert "attachment_chunk_write_operation" not in collection.doc


@pytest.mark.asyncio
async def test_complete_trace_defers_to_in_flight_marker(monkeypatch):
    """An unexpired marker belongs to a live writer and must not be force-released.

    Force-releasing it would break the append mutual exclusion; completion
    defers instead, and the recovery job finishes the trace once the lease
    lapses.
    """
    marker = {
        "id": "op-live",
        "kind": "append",
        "revision": 2,
        "recovery_after": utc_now() + timedelta(minutes=5),
    }
    trace_doc = {
        "trace_id": "trace-2",
        "session_id": "session-2",
        "run_id": "run-2",
        "status": "running",
        "event_count": 2,
        "event_revision": 2,
        "attachment_chunk_write_operation": marker,
    }
    storage, collection, _ = _make_storage(monkeypatch, trace_doc)

    ok = await storage.complete_trace("trace-2", "completed", ensure_token_usage=False)
    assert ok is False
    assert collection.doc["status"] == "running"
    assert collection.doc["attachment_chunk_write_operation"]["id"] == "op-live"


@pytest.mark.asyncio
async def test_recover_skips_unexpired_append_marker(monkeypatch):
    """The recovery job must not release a marker whose lease is still valid."""
    marker = {
        "id": "op-live",
        "kind": "append",
        "revision": 2,
        "recovery_after": utc_now() + timedelta(minutes=5),
    }
    trace_doc = {
        "trace_id": "trace-5",
        "session_id": "session-5",
        "run_id": "run-5",
        "status": "running",
        "event_count": 2,
        "event_revision": 2,
        "attachment_chunk_write_operation": marker,
    }
    storage, collection, _ = _make_storage(monkeypatch, trace_doc)

    recovered = await storage.recover_incomplete_chunk_replacements()
    assert recovered == 0
    assert collection.doc["attachment_chunk_write_operation"]["id"] == "op-live"
    assert collection.doc["status"] == "running"


@pytest.mark.asyncio
async def test_recover_releases_expired_append_marker_and_completes_trace(monkeypatch):
    """An expired append marker means the writer is gone: release it and finish
    a lingering running status so the read path stops hiding non-user events."""
    marker = {
        "id": "op-dead",
        "kind": "append",
        "revision": 2,
        "recovery_after": utc_now() - timedelta(minutes=1),
    }
    trace_doc = {
        "trace_id": "trace-6",
        "session_id": "session-6",
        "run_id": "run-6",
        "status": "running",
        "event_count": 2,
        "event_revision": 2,
        "attachment_chunk_write_operation": marker,
    }
    storage, collection, _ = _make_storage(monkeypatch, trace_doc)

    recovered = await storage.recover_incomplete_chunk_replacements()
    assert recovered == 1
    assert "attachment_chunk_write_operation" not in collection.doc
    assert collection.doc["status"] == "completed"


@pytest.mark.asyncio
async def test_append_exception_releases_marker_despite_revision_bump(monkeypatch):
    """The emergency unset must not be fenced by event_revision.

    Previously the exception-path unset required event_revision == marker
    revision; any concurrent revision bump (complete_trace, recommend
    questions) left the marker stuck forever, fencing later chunk writes and
    blocking completion.
    """
    trace_doc = {
        "trace_id": "trace-3",
        "session_id": "session-3",
        "run_id": "run-3",
        "status": "running",
        "event_count": 3,
        "event_revision": 4,
        "attachment_chunk_write_operation": {
            "id": "op-append",
            "kind": "append",
            "revision": 4,
            "recovery_after": utc_now() + timedelta(minutes=5),
        },
    }
    chunks = _FakeChunks()
    chunks.fail_next = True
    storage, collection, _ = _make_storage(monkeypatch, trace_doc, chunks)

    events = [{"event_type": "metadata", "data": {}, "timestamp": utc_now()}]
    with pytest.raises(RuntimeError):
        await storage.append_events_to_chunks(trace_doc, events, start_seq=4)

    # Marker must be released even though event_revision no longer matches.
    assert "attachment_chunk_write_operation" not in collection.doc


@pytest.mark.asyncio
async def test_recommend_questions_retry_on_marker(monkeypatch):
    """set_run_recommend_questions retries briefly while a marker is held."""
    trace_doc = {
        "trace_id": "trace-4",
        "session_id": "session-4",
        "run_id": "run-4",
        "status": "completed",
        "event_revision": 1,
        "attachment_chunk_write_operation": {
            "id": "op-held",
            "kind": "append",
            "revision": 1,
            "recovery_after": utc_now() + timedelta(minutes=5),
        },
    }
    storage, collection, _ = _make_storage(monkeypatch, trace_doc)

    async def _release_marker_later():
        await asyncio.sleep(0.05)
        collection.doc.pop("attachment_chunk_write_operation", None)

    release_task = asyncio.create_task(_release_marker_later())
    ok = await storage.set_run_recommend_questions("session-4", "run-4", ["q1", "q2"])
    await release_task
    assert ok is True
    assert collection.doc["recommend_questions"] == ["q1", "q2"]
