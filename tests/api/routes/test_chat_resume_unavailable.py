"""Manual recovery exposes unavailable races through the translated error contract."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api.routes import chat
from src.kernel.errors import AppError, ErrorCode


@pytest.mark.asyncio
async def test_manual_resume_exposes_recovery_unavailable_as_app_error(monkeypatch):
    monkeypatch.setattr(
        chat,
        "SessionManager",
        lambda: SimpleNamespace(
            get_session=AsyncMock(return_value=SimpleNamespace(user_id="user-1"))
        ),
    )
    monkeypatch.setattr(chat, "verify_session_ownership", lambda *_args: None)
    monkeypatch.setattr(
        chat,
        "get_task_manager",
        lambda: SimpleNamespace(
            resume_session=AsyncMock(
                return_value={
                    "success": False,
                    "code": "task_recovery_not_available",
                    "message": "Task recovery is no longer available",
                }
            )
        ),
    )

    with pytest.raises(AppError) as raised:
        await chat.resume_session("session-1", SimpleNamespace(sub="user-1"))

    assert raised.value.error_code is ErrorCode.TASK_RECOVERY_NOT_AVAILABLE
    assert raised.value.http_status == 409
