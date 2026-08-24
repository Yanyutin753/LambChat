from __future__ import annotations

"""Regression tests: complete_trace must not overwrite a terminal trace status.

Production symptom: traces whose run had already emitted done(status=
"completed") were later flipped to status="error" (with metadata.
cancel_reason="Task cancelled via pub/sub") when a stale task:cancel
message arrived for the finished run. The session's current_run_id stays
set after completion, so a late cancel resolves to the old run and the
pubsub fallback called complete_trace(status="error") unconditionally,
downgrading the finalized trace.
"""

from copy import deepcopy
from types import SimpleNamespace
from typing import Any

import pytest

from src.infra.session import trace_storage as trace_storage_module
from src.infra.session import trace_storage_writes as writes_module
from src.infra.session.trace_storage import TraceStorage


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
                    # MongoDB 语义：null 匹配缺失字段
                    if value is _MISSING:
                        if None not in operand:
                            return False
                    elif value not in operand:
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


class _FakeCollection:
    def __init__(self, doc: dict[str, Any] | None = None) -> None:
        self.doc = doc

    def find(self, query, projection=None):
        docs = [self.doc] if self.doc and _matches(self.doc, query) else []
        return _AsyncCursor(docs)

    async def find_one(self, query, projection=None):
        if self.doc and _matches(self.doc, query):
            return deepcopy(self.doc)
        return None

    async def update_one(self, query, update, upsert=False):
        if not self.doc or not _matches(self.doc, query):
            return SimpleNamespace(matched_count=0, modified_count=0)
        _apply_update(self.doc, update)
        return SimpleNamespace(matched_count=1, modified_count=1)


def _apply_update(document: dict[str, Any], update: dict[str, Any]) -> None:
    for key, value in update.items():
        if key == "$set":
            for path, item in value.items():
                _set_nested(document, path, deepcopy(item))
        elif key == "$inc":
            for path, item in value.items():
                current = _nested(document, path)
                _set_nested(document, path, (0 if current is _MISSING else current) + item)
        else:
            raise AssertionError(f"unsupported update {key}")


def _make_storage(monkeypatch, trace_doc):
    storage = object.__new__(TraceStorage)
    collection = _FakeCollection(trace_doc)
    monkeypatch.setattr(
        trace_storage_module.TraceStorage, "collection", property(lambda self: collection)
    )
    monkeypatch.setattr(
        trace_storage_module.TraceStorage,
        "chunks_collection",
        property(lambda self: _FakeCollection(None)),
    )
    monkeypatch.setattr(writes_module, "_USAGE_LOGS_ENABLED", False)
    storage._merger = None
    storage._indexes_ensured = True
    return storage, collection


@pytest.mark.asyncio
async def test_complete_trace_does_not_overwrite_completed_with_error(monkeypatch):
    """A late cancel must not downgrade a completed trace to error."""
    trace_doc = {"trace_id": "trace-1", "status": "completed"}
    storage, collection = _make_storage(monkeypatch, trace_doc)

    updated = await storage.complete_trace(
        "trace-1",
        status="error",
        metadata={"cancel_reason": "Task cancelled via pub/sub"},
        ensure_token_usage=False,
    )

    assert updated is False
    assert collection.doc["status"] == "completed"
    assert "cancel_reason" not in (collection.doc.get("metadata") or {})


@pytest.mark.asyncio
async def test_complete_trace_does_not_overwrite_error_with_completed(monkeypatch):
    """First finalization wins: error must not be silently upgraded either."""
    trace_doc = {"trace_id": "trace-1", "status": "error"}
    storage, collection = _make_storage(monkeypatch, trace_doc)

    updated = await storage.complete_trace("trace-1", status="completed", ensure_token_usage=False)

    assert updated is False
    assert collection.doc["status"] == "error"


@pytest.mark.asyncio
async def test_complete_trace_still_finalizes_running_trace(monkeypatch):
    trace_doc = {"trace_id": "trace-1", "status": "running"}
    storage, collection = _make_storage(monkeypatch, trace_doc)

    updated = await storage.complete_trace(
        "trace-1", status="error", metadata={"error": "boom"}, ensure_token_usage=False
    )

    assert updated is True
    assert collection.doc["status"] == "error"
    assert collection.doc["metadata"]["error"] == "boom"


@pytest.mark.asyncio
async def test_complete_trace_finalizes_trace_without_status(monkeypatch):
    """Legacy docs missing the status field can still be finalized."""
    trace_doc = {"trace_id": "trace-1"}
    storage, collection = _make_storage(monkeypatch, trace_doc)

    updated = await storage.complete_trace("trace-1", status="completed", ensure_token_usage=False)

    assert updated is True
    assert collection.doc["status"] == "completed"
