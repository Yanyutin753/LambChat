import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api.routes import chat
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.agent import AgentRequest
from src.kernel.schemas.project import ProjectWorkspace
from src.kernel.schemas.user import TokenPayload


@pytest.mark.parametrize("exists", [False, True])
async def test_chat_resolves_workspace_before_dispatch_and_keeps_existing_scope(
    monkeypatch, exists
):
    from src.api.routes.chat_request_config import build_conversation_config
    from src.infra.backend.workspace_selection import selected_workspace_id

    workspace = ProjectWorkspace(id="local-" + "a" * 32, machineId="mac", path="/repo")
    projects = SimpleNamespace(
        get_by_id=AsyncMock(return_value=SimpleNamespace(workspace=workspace))
    )
    monkeypatch.setattr("src.infra.folder.storage.get_project_storage", lambda: projects)
    monkeypatch.setattr(chat, "validate_user_agent_access", AsyncMock())
    monkeypatch.setattr(chat, "validate_agent_model_access", AsyncMock())
    monkeypatch.setattr(chat, "resolve_persona_request", AsyncMock())
    monkeypatch.setattr(
        chat.SessionManager,
        "get_session",
        AsyncMock(return_value=SimpleNamespace(user_id="owner", metadata={}) if exists else None),
    )

    class PreparedError(Exception):
        pass

    async def prepared(request, metadata, *_args):
        if exists:
            assert selected_workspace_id(request.agent_options) is None
            projects.get_by_id.assert_not_awaited()
        else:
            assert selected_workspace_id(request.agent_options) == workspace.id
            projects.get_by_id.assert_awaited_once_with("project", "owner")
        snapshot = build_conversation_config("run", "search", request, "en")
        assert snapshot["agent_options"] == request.agent_options
        assert metadata == {}
        raise PreparedError

    monkeypatch.setattr(chat, "bind_submission_goal", prepared)
    request = AgentRequest(message="hello", session_id="custom-id", project_id="project")
    user = TokenPayload(sub="owner", username="test", roles=[], permissions=[])
    with pytest.raises(PreparedError):
        await chat._submit_chat(request, SimpleNamespace(), "search", user)


@pytest.mark.parametrize("status", ["active", "waiting_human"])
@pytest.mark.parametrize("changed", [False, True])
async def test_goal_submission_keeps_its_workspace_before_binding_run(monkeypatch, status, changed):
    workspace = {"id": "local-" + "a" * 32, "machineId": "mac", "path": "/repo"}
    options = {
        "sandbox": "local",
        "sandbox_machine_id": "mac",
        "sandbox_workspace": json.dumps(workspace),
    }
    metadata = {"agent_options": options, "persistent_goal_status": status}
    for name in [
        "validate_user_agent_access",
        "validate_agent_model_access",
        "resolve_persona_request",
    ]:
        monkeypatch.setattr(chat, name, AsyncMock())
    monkeypatch.setattr(
        chat.SessionManager,
        "get_session",
        AsyncMock(return_value=SimpleNamespace(user_id="owner", metadata=metadata)),
    )

    class PreparedError(Exception):
        pass

    bind = AsyncMock(side_effect=PreparedError)
    monkeypatch.setattr(chat, "bind_submission_goal", bind)
    requested = (
        {"sandbox": "cloud"}
        if changed
        else {**options, "sandbox_workspace": json.dumps(workspace, separators=(",", ":"))}
    )
    request = AgentRequest(message="continue", session_id="existing", agent_options=requested)
    user = TokenPayload(sub="owner", username="test", roles=[], permissions=[])
    with pytest.raises(AppError if changed else PreparedError) as error:
        await chat._submit_chat(request, SimpleNamespace(), "search", user)
    if changed:
        assert error.value.error_code == ErrorCode.CONFLICT
        bind.assert_not_awaited()
    else:
        bind.assert_awaited_once()
