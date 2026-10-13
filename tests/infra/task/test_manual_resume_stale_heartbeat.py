from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.task.recovery import TaskRecoveryService
from src.infra.task.state_machine import TaskStateMachine
from src.infra.task.status import TaskStatus


@pytest.mark.parametrize("stale,expected", [(True, True), (False, False)])
async def test_manual_resume_uses_heartbeat_age_before_key_ttl_expires(stale, expected):
    session = SimpleNamespace(
        id="session-1",
        metadata=TaskStateMachine().build_metadata(TaskStatus.RUNNING, run_id="run-1"),
    )
    heartbeat = SimpleNamespace(
        check_exists=AsyncMock(return_value=True),
        is_stale=AsyncMock(return_value=stale),
    )
    service = TaskRecoveryService(
        storage=SimpleNamespace(get_by_session_id=AsyncMock(return_value=session)),
        run_info={},
        heartbeat=heartbeat,
        ensure_executor=lambda: None,
        submit_task=AsyncMock(),
        mark_run_failed=AsyncMock(),
    )
    service.resume_interrupted_run = AsyncMock(return_value={"success": True, "run_id": "run-1"})

    result = await service.resume_session("session-1")

    assert result["success"] is expected
    if expected:
        service.resume_interrupted_run.assert_awaited_once_with(session, "run-1", "manual_resume")
    else:
        service.resume_interrupted_run.assert_not_awaited()
