"""POST /chat/sessions/{id}/steer 端点测试。"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import HTTPException

from src.api.routes.chat import SteerRequest, steer_running_agent
from src.infra.task.status import TaskStatus


def _user(sub="user-1"):
    return SimpleNamespace(sub=sub)


def _session(user_id="user-1"):
    return SimpleNamespace(user_id=user_id, session_id="session-1")


@pytest.fixture
def queue():
    from src.infra.task.steer import get_steer_queue

    q = get_steer_queue()
    yield q
    # 清理
    import asyncio

    asyncio.get_event_loop().run_until_complete(q.drain("session-1"))


async def test_steer_enqueues_message_for_running_session(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.api.routes.chat.SessionManager",
        lambda: SimpleNamespace(get_session=AsyncMock(return_value=_session())),
    )
    monkeypatch.setattr(
        "src.api.routes.chat.get_task_manager",
        lambda: SimpleNamespace(get_status=AsyncMock(return_value=TaskStatus.RUNNING)),
    )

    from src.infra.task.steer import get_steer_queue

    result = await steer_running_agent(
        "session-1", SteerRequest(message="中途插话"), user=_user()
    )

    assert result["status"] == "queued"
    assert await get_steer_queue().drain("session-1") == ["中途插话"]


async def test_steer_rejects_when_task_not_running(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.api.routes.chat.SessionManager",
        lambda: SimpleNamespace(get_session=AsyncMock(return_value=_session())),
    )
    monkeypatch.setattr(
        "src.api.routes.chat.get_task_manager",
        lambda: SimpleNamespace(
            get_status=AsyncMock(return_value=TaskStatus.WAITING_HUMAN)
        ),
    )

    with pytest.raises(HTTPException) as exc_info:
        await steer_running_agent(
            "session-1", SteerRequest(message="hi"), user=_user()
        )
    assert exc_info.value.status_code == 409


async def test_steer_rejects_missing_session(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.api.routes.chat.SessionManager",
        lambda: SimpleNamespace(get_session=AsyncMock(return_value=None)),
    )

    with pytest.raises(HTTPException) as exc_info:
        await steer_running_agent(
            "session-1", SteerRequest(message="hi"), user=_user()
        )
    assert exc_info.value.status_code == 404


async def test_steer_rejects_other_users_session(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.api.routes.chat.SessionManager",
        lambda: SimpleNamespace(get_session=AsyncMock(return_value=_session(user_id="user-2"))),
    )

    with pytest.raises(HTTPException) as exc_info:
        await steer_running_agent(
            "session-1", SteerRequest(message="hi"), user=_user("user-1")
        )
    assert exc_info.value.status_code == 403


async def test_steer_rejects_empty_message(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.api.routes.chat.SessionManager",
        lambda: SimpleNamespace(get_session=AsyncMock(return_value=_session())),
    )
    monkeypatch.setattr(
        "src.api.routes.chat.get_task_manager",
        lambda: SimpleNamespace(get_status=AsyncMock(return_value=TaskStatus.RUNNING)),
    )

    with pytest.raises(HTTPException) as exc_info:
        await steer_running_agent("session-1", SteerRequest(message="   "), user=_user())
    assert exc_info.value.status_code == 422
