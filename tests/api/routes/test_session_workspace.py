import json
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api.routes.session import update_session
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.session import Session, SessionUpdate
from src.kernel.schemas.user import TokenPayload

SELECTION = json.dumps({"id": "local-" + "a" * 32, "machineId": "m1", "path": "/repo"})
OPTIONS = {"sandbox": "local", "sandbox_machine_id": "m1", "sandbox_workspace": SELECTION}


@pytest.fixture
def setup(monkeypatch):
    session = Session(id="s1", user_id="u1", metadata={"agent_options": OPTIONS.copy()})
    manager = SimpleNamespace(
        get_session=AsyncMock(return_value=session), update_session=AsyncMock(return_value=session)
    )
    monkeypatch.setattr("src.api.routes.session.SessionManager", lambda: manager)
    monkeypatch.setattr(
        "src.api.routes.session._get_favorites_project_id", AsyncMock(return_value=None)
    )
    locked = []

    @asynccontextmanager
    async def lease(session_id, user_id, **_kwargs):
        locked.append((session_id, user_id))
        if session.metadata.get("task_status") == "running":
            raise AppError(ErrorCode.CONFLICT)
        yield

    monkeypatch.setattr("src.infra.scheduler.conversation.conversation_submission", lease)
    user = TokenPayload(sub="u1", username="test", roles=[], permissions=[])
    return session, manager, locked, user


@pytest.mark.parametrize(
    "metadata",
    [
        {"agent_options.sandbox_workspace": ""},
        {"agent_options": {"sandbox": "cloud"}},
        {"agent_options": None},
    ],
)
async def test_running_chat_cannot_change_or_remove_workspace(setup, metadata):
    session, manager, locked, user = setup
    session.metadata["task_status"] = "running"
    with pytest.raises(AppError):
        await update_session("s1", SessionUpdate(metadata=metadata), user)
    manager.update_session.assert_not_awaited()
    assert locked == [("s1", "u1")]


async def test_machine_change_clears_old_directory_in_same_write(setup):
    _, manager, locked, user = setup
    await update_session(
        "s1", SessionUpdate(metadata={"agent_options.sandbox_machine_id": "m2"}), user
    )
    saved = manager.update_session.call_args.args[1].metadata
    assert saved["agent_options.sandbox_machine_id"] == "m2"
    assert saved["agent_options.sandbox_workspace"] == ""
    assert locked == [("s1", "u1")]


async def test_mismatched_explicit_binding_is_rejected_without_writing(setup):
    _, manager, _, user = setup
    with pytest.raises(AppError):
        await update_session(
            "s1",
            SessionUpdate(
                metadata={
                    "agent_options.sandbox_machine_id": "m2",
                    "agent_options.sandbox_workspace": SELECTION,
                }
            ),
            user,
        )
    manager.update_session.assert_not_awaited()


@pytest.mark.parametrize("status", ["active", "waiting_human"])
async def test_goal_cannot_change_working_directory_between_turns(setup, status):
    session, manager, _, user = setup
    session.metadata["persistent_goal_status"] = status
    with pytest.raises(AppError) as error:
        await update_session("s1", SessionUpdate(metadata={"agent_options.sandbox": "cloud"}), user)
    assert error.value.error_code == ErrorCode.CONFLICT
    manager.update_session.assert_not_awaited()


@pytest.mark.parametrize(
    "metadata",
    [
        {"agent_options": OPTIONS, "agent_options.sandbox": "cloud"},
        {"agent_options.sandbox_workspace.id": "forged"},
        {"agent_options.$unset": "sandbox_workspace"},
    ],
)
async def test_ambiguous_or_nested_option_patch_is_rejected(setup, metadata):
    _, manager, _, user = setup
    with pytest.raises(AppError) as error:
        await update_session("s1", SessionUpdate(metadata=metadata), user)
    assert error.value.error_code == ErrorCode.BAD_REQUEST
    manager.update_session.assert_not_awaited()


async def test_renaming_running_chat_does_not_take_workspace_lock(setup):
    session, manager, locked, user = setup
    session.metadata["task_status"] = "running"
    await update_session("s1", SessionUpdate(name="renamed"), user)
    manager.update_session.assert_awaited_once()
    assert locked == []


async def test_workspace_history_checks_ownership_before_reading_locations(setup, monkeypatch):
    from src.api.routes import session_workspace
    from src.api.routes.session import get_workspace_locations

    monkeypatch.setattr(session_workspace, "SessionManager", lambda: setup[1])
    from src.infra.session import workspace_locations

    session, _, _, user = setup
    session.user_id = "other-owner"
    lookup = AsyncMock()
    monkeypatch.setattr(workspace_locations, "list_workspace_locations", lookup)
    with pytest.raises(AppError):
        await get_workspace_locations("s1", user)
    lookup.assert_not_awaited()


async def test_workspace_history_does_not_start_or_move_sandbox(setup, monkeypatch):
    from src.api.routes import session_workspace
    from src.api.routes.session import get_workspace_locations

    monkeypatch.setattr(session_workspace, "SessionManager", lambda: setup[1])
    from src.infra.session import workspace_locations

    _, manager, locked, user = setup
    locations = [{"id": "old", "options": OPTIONS}]
    lookup = AsyncMock(return_value=locations)
    monkeypatch.setattr(workspace_locations, "list_workspace_locations", lookup)
    assert await get_workspace_locations("s1", user) == {"locations": locations}
    lookup.assert_awaited_once_with("u1", "s1")
    manager.update_session.assert_not_awaited()
    assert locked == []
