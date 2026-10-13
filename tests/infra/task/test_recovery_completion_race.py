"""Completed runs must win over stale orphan scans and delayed recovery claims."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.task import recovery as recovery_module
from src.infra.task.startup_cleanup import TaskStartupCleanupService


class _FakeStorage:
    def __init__(self, session):
        self.session = session
        self.updates = []

    async def get_by_session_id(self, session_id):
        return self.session

    async def update(self, session_id, update):
        self.updates.append((session_id, update))


class _FakeRedis:
    async def set(self, *args, **kwargs):
        return True

    async def eval(self, *args):
        return 1


def _session(status="running"):
    return SimpleNamespace(
        id="session-1",
        user_id="user-1",
        agent_id="fast",
        metadata={"current_run_id": "run-old", "task_status": status},
    )


@pytest.mark.asyncio
async def test_running_scan_does_not_resume_when_completed_during_heartbeat_read(monkeypatch):
    session = _session()
    storage = _FakeStorage(session)
    resume = AsyncMock(return_value={"success": True, "run_id": "run-old"})

    async def heartbeat_read(_run_id):
        # The worker finishes after the cursor and normalized model were read.
        storage.session = _session("completed")
        return True

    service = TaskStartupCleanupService(
        storage=storage,
        heartbeat=SimpleNamespace(is_stale=heartbeat_read),
        ensure_executor=lambda: None,
        load_session_record=AsyncMock(return_value=session),
        resume_interrupted_run=resume,
    )
    monkeypatch.setattr(service, "_is_user_cancelled_run", AsyncMock(return_value=False))
    raw = {"_id": "mongo-1", "session_id": session.id, "metadata": dict(session.metadata)}

    await service._process_running_sessions([raw])

    resume.assert_not_awaited()
    assert storage.updates == []
    assert storage.session.metadata["task_status"] == "completed"


@pytest.mark.asyncio
@pytest.mark.parametrize("completion_boundary", ["before_fresh_read", "at_atomic_claim"])
async def test_recovery_claim_does_not_reopen_completed_run(monkeypatch, completion_boundary):
    stale = _session()
    completed = _session("completed")
    storage = _FakeStorage(completed if completion_boundary == "before_fresh_read" else _session())

    async def claim_run_recovery(session_id, run_id, metadata):
        # Even a fresh read can become stale before the Mongo conditional update.
        assert (session_id, run_id) == ("session-1", "run-old")
        storage.session = completed
        return False

    storage.claim_run_recovery = AsyncMock(side_effect=claim_run_recovery)
    submit = AsyncMock(return_value={"success": True, "run_id": "run-old"})
    reopen = AsyncMock()
    strip_terminal = AsyncMock()
    monkeypatch.setattr(recovery_module, "get_redis_client", lambda: _FakeRedis())
    monkeypatch.setattr(
        recovery_module, "_lookup_trace_id_for_run", AsyncMock(return_value="trace-1")
    )
    monkeypatch.setattr(
        recovery_module,
        "get_trace_storage",
        lambda: SimpleNamespace(reopen_interrupted_trace=reopen),
    )
    service = recovery_module.TaskRecoveryService(
        storage=storage,
        run_info={},
        heartbeat=SimpleNamespace(is_stale=AsyncMock(return_value=True)),
        ensure_executor=lambda: None,
        submit_task=AsyncMock(),
        mark_run_failed=AsyncMock(),
    )
    monkeypatch.setattr(service, "submit_seamless_resume", submit)
    monkeypatch.setattr(service, "_strip_terminal_stream_events", strip_terminal)

    result = await service.resume_interrupted_run(stale, "run-old", "server_restart")

    assert result["success"] is False
    assert result["code"] == "task_recovery_not_available"
    assert result["message"] == "Task recovery is no longer available"
    reopen.assert_not_awaited()
    strip_terminal.assert_not_awaited()
    submit.assert_not_awaited()
    assert storage.updates == []
    assert storage.session.metadata["task_status"] == "completed"
    if completion_boundary == "at_atomic_claim":
        storage.claim_run_recovery.assert_awaited_once()


@pytest.mark.asyncio
async def test_recovery_failure_writeback_cannot_override_completion():
    storage = _FakeStorage(_session("completed"))

    async def guarded_update(session_id, run_id, metadata, *, expected_statuses):
        if (
            storage.session.metadata.get("current_run_id") != run_id
            or storage.session.metadata.get("task_status") not in expected_statuses
        ):
            return False
        await storage.update(session_id, SimpleNamespace(metadata=metadata))
        return True

    storage.update_metadata_for_run = AsyncMock(side_effect=guarded_update)
    service = recovery_module.TaskRecoveryService(
        storage=storage,
        run_info={},
        heartbeat=None,
        ensure_executor=lambda: None,
        submit_task=AsyncMock(),
        mark_run_failed=AsyncMock(),
    )

    await service._restore_recoverable_failure("session-1", "run-old", "submission failed")

    assert storage.updates == []
    assert storage.session.metadata["task_status"] == "completed"
