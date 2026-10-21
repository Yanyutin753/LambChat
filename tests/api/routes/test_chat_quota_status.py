"""Status polling preserves quota errors and clears them after recovery."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api.routes.chat import get_session_status
from src.infra.task.status import TaskStatus


@pytest.mark.parametrize(
    ("status", "run_id", "expected"),
    [
        (TaskStatus.FAILED, "run-1", "usage_quota_exceeded"),
        (TaskStatus.COMPLETED, "run-1", None),
        (TaskStatus.RUNNING, "run-1", None),
        (TaskStatus.RECOVERING, "run-1", None),
        (TaskStatus.FAILED, "older-run", "internal_error"),
    ],
)
async def test_status_uses_only_current_run_quota_code(monkeypatch, status, run_id, expected):
    session = SimpleNamespace(
        metadata={"current_run_id": "run-1", "task_error_code": "usage_quota_exceeded"},
    )
    manager = SimpleNamespace(
        get_run_status=AsyncMock(return_value=status),
        get_run_error=AsyncMock(return_value="Old quota error"),
    )
    monkeypatch.setattr(
        "src.api.routes.chat.SessionManager",
        lambda: SimpleNamespace(get_session=AsyncMock(return_value=session)),
    )
    monkeypatch.setattr("src.api.routes.chat.get_task_manager", lambda: manager)
    monkeypatch.setattr("src.api.routes.chat.verify_session_ownership", lambda *args: None)
    result = await get_session_status(
        "session-1", run_id=run_id, user=SimpleNamespace(sub="user-1")
    )
    assert result.get("code") == expected
    assert result["error"] == ("Old quota error" if expected else None)
