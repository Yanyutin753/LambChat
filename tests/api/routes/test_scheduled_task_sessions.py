"""Scheduled execution cards must distinguish approvals from active execution."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.api.routes.scheduled_task import list_task_sessions
from src.infra.task.status import TaskStatus
from src.kernel.schemas.scheduled_task import RunStatus


@pytest.mark.parametrize(
    ("record_status", "live_status", "display_status"),
    [
        (RunStatus.RUNNING, TaskStatus.WAITING_HUMAN, "waiting_human"),
        (RunStatus.RUNNING, TaskStatus.RUNNING, "running"),
        (RunStatus.SUCCESS, TaskStatus.WAITING_HUMAN, "success"),
    ],
)
async def test_conversation_session_card_shows_exact_run_approval_state(
    record_status, live_status, display_status
):
    task = SimpleNamespace(
        owner_id="owner",
        execution_mode="conversation",
        target_session_id="child",
        name="Scheduled task",
        agent_id="search",
    )
    record = SimpleNamespace(
        id="run",
        session_id="child",
        status=record_status,
        created_at=None,
        finished_at=None,
        started_at=None,
    )
    service = SimpleNamespace(
        get_task=AsyncMock(return_value=task),
        get_task_runs=AsyncMock(return_value=([record], 1)),
    )
    manager = SimpleNamespace(get_run_status=AsyncMock(return_value=live_status))
    with patch("src.infra.task.manager.get_task_manager", return_value=manager):
        result = await list_task_sessions(
            "task", skip=0, limit=20, user=SimpleNamespace(sub="owner"), service=service
        )
    assert result.items[0].metadata == {"run_id": "run", "run_status": display_status}
    if record_status == RunStatus.RUNNING:
        manager.get_run_status.assert_awaited_once_with("child", "run")
    else:
        manager.get_run_status.assert_not_awaited()
