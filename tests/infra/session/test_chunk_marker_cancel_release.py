from __future__ import annotations

"""Regression tests for chunk markers leaked by task cancellation.

Production symptom (2026-08-31, pod lambchat-b): a user cancelled a running
generation; the inline Mongo flush was suspended inside
``reserve_event_sequence_range``'s ``find_one_and_update`` when the
CancelledError landed. The server had already installed the append marker,
but the client never learned the claim, so no emergency release ran. The
marker then fenced ``complete_trace`` for its whole 5-minute lease and the
cancelled trace's non-user events stayed unreadable until recovery.
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

ATTACHMENT_MARKER = "attachment_chunk_write_operation"
EVENT_REVISION = "event_revision"


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
                else:
                    raise AssertionError(f"unsupported op {op}")
        elif value != expected:
            return False
    return True


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
        elif key == "$max":
            for path, item in value.items():
                current = _nested(document, path)
                if current is _MISSING or item > current:
                    _set_nested(document, path, item)
        else:
            raise AssertionError(f"unsupported update {key}")


class _CancellingCollection:
    """Applies find_one_and_update server-side, then raises CancelledError.

    Models the production interleaving: the MongoDB server installed the
    write while the client task was being cancelled, so the coroutine sees
    CancelledError even though the marker is durable.
    """

    def __init__(self, doc: dict[str, Any]) -> None:
        self.doc = doc
        self.update_one_queries: list[dict[str, Any]] = []

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
        raise asyncio.CancelledError()

    async def update_one(self, query, update, upsert=False):
        self.update_one_queries.append(deepcopy(query))
        if not self.doc or not _matches(self.doc, query):
            return SimpleNamespace(matched_count=0, modified_count=0)
        _apply_update(self.doc, update)
        return SimpleNamespace(matched_count=1, modified_count=1)


class _CasMissingCollection:
    """Rejects the fenced parent update (revision moved) but keeps our marker."""

    def __init__(self, doc: dict[str, Any]) -> None:
        self.doc = doc
        self.final_updates = 0

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
        if query.get(EVENT_REVISION) is not None:
            self.final_updates += 1
            return SimpleNamespace(matched_count=0, modified_count=0)
        if not self.doc or not _matches(self.doc, query):
            return SimpleNamespace(matched_count=0, modified_count=0)
        _apply_update(self.doc, update)
        return SimpleNamespace(matched_count=1, modified_count=1)


class _FakeChunks:
    def __init__(self) -> None:
        self.docs: dict[tuple[str, int], dict[str, Any]] = {}

    async def update_one(self, query, update, upsert=False):
        key = (query.get("trace_id"), query.get("chunk_index"))
        doc = self.docs.get(key)
        if doc is None:
            doc = {"trace_id": key[0], "chunk_index": key[1], "events": []}
            self.docs[key] = doc
        # append_events_to_chunks writes via an aggregation pipeline; the
        # exact events do not matter for these tests, only that the write
        # succeeded so the fenced parent update is reached.
        if isinstance(update, list):
            doc["written_via_pipeline"] = True
        else:
            doc["events"] = list(update.get("$set", {}).get("events", []) or [])
        return SimpleNamespace(matched_count=1, modified_count=1)


def _make_storage(monkeypatch, collection, chunks=None):
    storage = object.__new__(TraceStorage)
    monkeypatch.setattr(
        trace_storage_module.TraceStorage, "collection", property(lambda self: collection)
    )
    monkeypatch.setattr(
        trace_storage_module.TraceStorage,
        "chunks_collection",
        property(lambda self: chunks or _FakeChunks()),
    )
    storage._merger = None
    storage._indexes_ensured = True
    return storage


@pytest.mark.asyncio
async def test_reserve_cancelled_after_claim_releases_marker(monkeypatch):
    """A cancel landing after the server installed the append marker must
    still release it, scoped to the operation id we generated."""
    trace_doc = {
        "trace_id": "trace-cancel-reserve",
        "session_id": "session-1",
        "run_id": "run-1",
        "status": "running",
        "event_count": 2,
        "event_revision": 4,
    }
    collection = _CancellingCollection(trace_doc)
    storage = _make_storage(monkeypatch, collection)

    with pytest.raises(asyncio.CancelledError):
        await storage.reserve_event_sequence_range("trace-cancel-reserve", 3)

    assert ATTACHMENT_MARKER not in collection.doc
    # The release must be scoped to this operation only.
    release_queries = [q for q in collection.update_one_queries if f"{ATTACHMENT_MARKER}.id" in q]
    assert len(release_queries) == 1


@pytest.mark.asyncio
async def test_claim_chunk_write_cancelled_after_claim_releases_marker(monkeypatch):
    """Same cancellation window for the replace-kind claim used by chunk
    replacement (token usage event, compaction)."""
    trace_doc = {
        "trace_id": "trace-cancel-claim",
        "session_id": "session-2",
        "run_id": "run-2",
        "status": "running",
        "event_count": 2,
        "event_revision": 7,
    }
    collection = _CancellingCollection(trace_doc)
    storage = _make_storage(monkeypatch, collection)

    with pytest.raises(asyncio.CancelledError):
        await storage._claim_chunk_write(deepcopy(trace_doc), kind="replace")

    assert ATTACHMENT_MARKER not in collection.doc
    release_queries = [q for q in collection.update_one_queries if f"{ATTACHMENT_MARKER}.id" in q]
    assert len(release_queries) == 1


@pytest.mark.asyncio
async def test_append_final_cas_miss_retry_recovers_marker(monkeypatch):
    """When the revision-fenced parent update misses but the marker is still
    ours, the marker-identity retry must reclaim and release it — the
    cancel-release path above only covers claims whose caller never saw the
    claim result."""
    marker = {
        "id": "op-cas",
        "kind": "append",
        "revision": 5,
        "recovery_after": utc_now() + timedelta(minutes=5),
    }
    # event_revision moved after the claim, so the fenced parent update
    # misses, but the marker identity still matches the retry.
    collection = _CasMissingCollection(
        {
            "trace_id": "trace-cas",
            "session_id": "session-3",
            "run_id": "run-3",
            "status": "running",
            "event_count": 6,
            "event_revision": 6,
            ATTACHMENT_MARKER: marker,
        }
    )
    chunks = _FakeChunks()
    storage = _make_storage(monkeypatch, collection, chunks)

    trace_doc = {
        "trace_id": "trace-cas",
        "session_id": "session-3",
        "run_id": "run-3",
        "event_count": 6,
        ATTACHMENT_MARKER: marker,
    }
    appended = await storage.append_events_to_chunks(
        trace_doc,
        [{"event_type": "text", "data": {"text": "hi"}}],
        6,
    )

    assert appended is True
    assert collection.final_updates >= 1  # revision-fenced update missed
    assert ATTACHMENT_MARKER not in collection.doc
