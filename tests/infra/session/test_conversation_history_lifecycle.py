from __future__ import annotations

import asyncio

import pytest

from src.infra.session import conversation_history as history
from src.infra.session import trace_storage_writes
from src.infra.session.trace_storage_writes import TraceStorageWriteMixin


class _Result:
    modified_count = 1


class _Collection:
    async def update_one(self, *args, **kwargs):
        return _Result()


class _WriteStorage(TraceStorageWriteMixin):
    def __init__(self) -> None:
        self.collection = _Collection()
        self._merger = None

    async def ensure_indexes_if_needed(self) -> None:
        return None


@pytest.mark.asyncio
async def test_complete_trace_schedules_index_after_success(monkeypatch) -> None:
    scheduled = []
    storage = _WriteStorage()
    monkeypatch.setattr(trace_storage_writes, "_USAGE_LOGS_ENABLED", False)
    monkeypatch.setattr(
        history,
        "schedule_conversation_trace_index",
        lambda trace_storage, trace_id: scheduled.append((trace_storage, trace_id)),
    )

    completed = await storage.complete_trace(
        "trace-1",
        "completed",
        ensure_token_usage=False,
    )

    assert completed is True
    assert scheduled == [(storage, "trace-1")]


@pytest.mark.asyncio
async def test_index_task_failure_is_observed_without_raising(monkeypatch, caplog) -> None:
    class _Service:
        def __init__(self, *, trace_storage):
            self.trace_storage = trace_storage

        async def index_trace(self, trace_id):
            raise RuntimeError("database body must not leak")

    monkeypatch.setattr(history, "ConversationHistoryService", _Service)

    history.schedule_conversation_trace_index(object(), "trace-1")
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert not history._conversation_index_tasks
    assert "RuntimeError" in caplog.text
    assert "database body" not in caplog.text
