from __future__ import annotations

"""reopen_interrupted_trace：无缝续跑前重开被旧关停路径终结为 error 的 trace。

约束：只允许 error → running（旧代码在关停时会把 trace 终结为 error）；completed
trace 永不重开（终态保护，与 complete_trace 的 finalizable 过滤同一原则）。
"""

from types import SimpleNamespace
from typing import Any

import pytest

from src.infra.session import trace_storage as trace_storage_module
from src.infra.session.trace_storage import TraceStorage


class _FakeCollection:
    def __init__(self, doc: dict[str, Any] | None = None) -> None:
        self.doc = doc

    async def update_one(self, query, update, upsert=False):
        for key, expected in query.items():
            if self.doc.get(key) != expected:
                return SimpleNamespace(matched_count=0, modified_count=0)
        for operator, fields in update.items():
            if operator == "$set":
                self.doc.update(fields)
            elif operator == "$unset":
                for field in fields:
                    self.doc.pop(field, None)
            else:
                raise AssertionError(f"unsupported update {operator}")
        return SimpleNamespace(matched_count=1, modified_count=1)


def _make_storage(monkeypatch: pytest.MonkeyPatch, trace_doc: dict[str, Any]):
    storage = object.__new__(TraceStorage)
    collection = _FakeCollection(trace_doc)
    monkeypatch.setattr(
        trace_storage_module.TraceStorage, "collection", property(lambda self: collection)
    )
    storage._indexes_ensured = True
    return storage, collection


@pytest.mark.asyncio
async def test_reopen_resets_error_trace_to_running(monkeypatch):
    trace_doc = {
        "trace_id": "trace-1",
        "status": "error",
        "completed_at": "2026-09-01T00:00:00",
    }
    storage, collection = _make_storage(monkeypatch, trace_doc)

    reopened = await storage.reopen_interrupted_trace("trace-1")

    assert reopened is True
    assert collection.doc["status"] == "running"
    assert "completed_at" not in collection.doc
    assert "updated_at" in collection.doc


@pytest.mark.asyncio
async def test_reopen_never_touches_completed_trace(monkeypatch):
    trace_doc = {
        "trace_id": "trace-1",
        "status": "completed",
        "completed_at": "2026-09-01T00:00:00",
    }
    storage, collection = _make_storage(monkeypatch, trace_doc)

    reopened = await storage.reopen_interrupted_trace("trace-1")

    assert reopened is False
    assert collection.doc["status"] == "completed"
    assert "completed_at" in collection.doc


@pytest.mark.asyncio
async def test_reopen_running_trace_is_noop(monkeypatch):
    trace_doc = {"trace_id": "trace-1", "status": "running"}
    storage, collection = _make_storage(monkeypatch, trace_doc)

    reopened = await storage.reopen_interrupted_trace("trace-1")

    assert reopened is False
    assert collection.doc["status"] == "running"
