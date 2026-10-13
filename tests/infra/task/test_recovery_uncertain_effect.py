"""Unknown external outcomes remain terminal for their owning run."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.task.executor import TaskExecutor
from src.infra.task.recovery import TaskRecoveryService
from src.infra.task.state_machine import TaskStateMachine
from src.infra.task.status import TaskStatus
from src.kernel.errors import AppError, ErrorCode


@pytest.mark.parametrize("current", ["old", "new"])
async def test_uncertain_effect_is_persisted_only_for_owning_run(monkeypatch, current):
    metadata = {"current_run_id": current, "task_status": "running"}

    async def conditional(_session, run_id, update):
        if run_id != metadata["current_run_id"]:
            return False
        metadata.update(update)
        return True

    storage = SimpleNamespace(update_metadata_for_run=AsyncMock(side_effect=conditional))
    executor = TaskExecutor(storage, {}, SimpleNamespace())
    executor._update_session_status = AsyncMock()
    executor._send_task_notification = AsyncMock()
    executor._expire_terminal_stream = AsyncMock()
    monkeypatch.setattr("src.infra.task.executor.emit_undelivered_steer_events", AsyncMock())
    writer = SimpleNamespace(
        _flush_redis_buffer=AsyncMock(), flush_mongo_buffer=AsyncMock(), write_event=AsyncMock()
    )
    error = AppError(
        ErrorCode.TASK_RECOVERY_UNCERTAIN_EFFECT,
        args={"tool_calls": [{"id": "write", "name": "external_write"}]},
    )
    await executor._handle_generic_error("session", "old", "user", error, writer, None)
    executor._update_session_status.assert_not_awaited()
    if current == "old":
        assert metadata["task_status"] == "failed"
        assert metadata["task_recoverable"] is False
        assert metadata["verification_required"] is True
        assert metadata["task_error_code"] == "task_recovery_uncertain_effect"
        assert metadata["verification_tool_calls"] == error.args_data["tool_calls"]
    else:
        assert metadata == {"current_run_id": "new", "task_status": "running"}


@pytest.mark.parametrize("status", [TaskStatus.QUEUED, TaskStatus.PENDING, TaskStatus.STARTING])
def test_new_run_clears_old_verification_marker(status):
    metadata = {"verification_required": True, "verification_tool_calls": [{"id": "old"}]}
    metadata.update(TaskStateMachine().build_metadata(status, run_id="new"))
    assert metadata["verification_required"] is False
    assert metadata["verification_tool_calls"] == []
    assert metadata["task_error_code"] is None


@pytest.mark.parametrize(
    "entry", ["resume_session", "resume_interrupted_run", "submit_seamless_resume"]
)
async def test_recovery_entry_refuses_verification_required_run_before_dispatch(entry):
    session = SimpleNamespace(
        id="session",
        metadata={
            "current_run_id": "run",
            "task_error_code": "task_recovery_uncertain_effect",
            "task_recoverable": False,
        },
    )
    storage = SimpleNamespace(get_by_session_id=AsyncMock(return_value=session))
    submit = AsyncMock()
    service = TaskRecoveryService(
        storage=storage,
        run_info={},
        heartbeat=SimpleNamespace(),
        ensure_executor=lambda: None,
        submit_task=submit,
        mark_run_failed=AsyncMock(),
    )
    with pytest.raises(AppError) as caught:
        if entry == "resume_session":
            await service.resume_session("session")
        elif entry == "resume_interrupted_run":
            await service.resume_interrupted_run(session, "run", "manual_resume")
        else:
            await service.submit_seamless_resume(session, "run", None, "server_restart")
    assert caught.value.error_code is ErrorCode.TASK_RECOVERY_UNCERTAIN_EFFECT
    submit.assert_not_awaited()
