from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api.routes import desktop_control


@pytest.mark.parametrize(
    ("current_run", "status", "expected"),
    [
        ("run-1", "running", True),
        ("run-2", "running", False),
        ("run-1", "completed", False),
        ("run-1", "cancelling", False),
        ("run-1", "waiting_human", False),
        ("run-1", "recovering", False),
    ],
)
async def test_control_authority_matches_live_execution(monkeypatch, current_run, status, expected):
    owned = AsyncMock(
        return_value=SimpleNamespace(
            metadata={
                "current_run_id": current_run,
                "task_status": status,
            }
        )
    )
    monkeypatch.setattr(desktop_control, "_owned_session_or_404", owned)
    user = SimpleNamespace(sub="owner")
    result = await desktop_control.desktop_control_lifecycle("session-1", "run-1", user)
    owned.assert_awaited_once_with(user, "session-1")
    assert result == {"active": expected}
