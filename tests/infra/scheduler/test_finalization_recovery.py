"""Recover interrupted completion work without re-executing the agent."""

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.scheduler.conversation import _finish


async def test_completion_after_stats_outage_is_recoverable_without_changing_result(monkeypatch):
    record = {
        "_id": "r",
        "task_id": "t",
        "session_id": "s",
        "owner_id": "u",
        "conversation_state": "submitted",
        "trigger_type": "interval",
    }
    durable = deepcopy(record)

    async def write(query, update):
        matched = all(durable.get(key) == value for key, value in query.items())
        if matched:
            durable.update(update["$set"])
        return SimpleNamespace(modified_count=int(matched))

    async def update_run(run_id, updates):
        durable.update(updates)

    storage = SimpleNamespace(
        _get_collection=lambda name: SimpleNamespace(update_one=write),
        update_run=update_run,
        get_task=AsyncMock(return_value=None),
        update_task_run_stats=AsyncMock(side_effect=[ConnectionError("stats unavailable"), None]),
    )
    finished = datetime(2026, 10, 17, tzinfo=timezone.utc)
    monkeypatch.setattr(
        "src.infra.session.trace_storage.get_trace_storage",
        lambda: SimpleNamespace(
            collection=SimpleNamespace(find_one=AsyncMock(return_value={"completed_at": finished}))
        ),
    )
    with pytest.raises(ConnectionError):
        await _finish(storage, record, "success")
    assert durable["status"] == "success"
    assert durable["finalization_pending"] is True
    await _finish(storage, deepcopy(durable), "success")
    assert durable["status"] == "success"
    assert durable["finished_at"] == finished
    assert durable["finalization_pending"] is False


async def test_finished_record_without_pending_work_cannot_finalize_again():
    storage = SimpleNamespace(update_task_run_stats=AsyncMock())
    await _finish(storage, {"conversation_state": "finished"}, "success")
    storage.update_task_run_stats.assert_not_awaited()
