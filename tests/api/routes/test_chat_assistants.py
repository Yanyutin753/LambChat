"""The ordinary chat endpoint must enforce assistant configuration too."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api.routes import chat
from src.infra.assistant.service import AssistantService
from src.infra.assistant.store import AssistantStore
from src.infra.utils.datetime import utc_now
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.agent import AgentRequest
from src.kernel.schemas.assistant import Assistant
from src.kernel.schemas.user import TokenPayload


@pytest.mark.parametrize("team_id", [None, "owned-team"])
@pytest.mark.parametrize("status", ["active", "paused", "archived"])
async def test_submit_loads_authoritative_identity_even_if_metadata_marker_was_removed(
    monkeypatch, status, team_id
):
    now = utc_now()
    assistant = Assistant(
        id="a",
        session_id="session",
        user_id="owner",
        name="Researcher",
        instructions="Cite primary sources.",
        model_id="configured",
        status=status,
        team_id=team_id,
        revision=1,
        created_at=now,
        updated_at=now,
    )
    monkeypatch.setattr(
        AssistantStore, "for_session", AsyncMock(return_value=assistant), raising=False
    )
    monkeypatch.setattr(
        chat.SessionManager,
        "get_session",
        AsyncMock(return_value=SimpleNamespace(user_id="owner", metadata={})),
    )
    monkeypatch.setattr(AssistantService, "validate_configuration", AsyncMock())
    monkeypatch.setattr(chat, "validate_user_agent_access", AsyncMock())
    validate_model = AsyncMock()
    monkeypatch.setattr(chat, "validate_agent_model_access", validate_model)

    async def persona(request, _user):
        request.persona_system_prompt = None
        request.persona_snapshot = None

    monkeypatch.setattr(chat, "resolve_persona_request", persona)

    class PreparedError(Exception):
        pass

    async def bind(request, *_args):
        assert request.persona_system_prompt == "Cite primary sources."
        assert request.agent_options == {"model_id": "configured", "sandbox": None}
        assert request.team_id == team_id
        raise PreparedError

    monkeypatch.setattr(chat, "bind_submission_goal", bind)
    request = AgentRequest(
        message="hello",
        session_id="session",
        persona_system_prompt="forged",
        agent_options={"model_id": "other"},
    )
    user = TokenPayload(sub="owner", username="owner", roles=[], permissions=["chat:write"])
    with pytest.raises(PreparedError if status == "active" else AppError) as caught:
        await chat._submit_chat(request, SimpleNamespace(), "search", user)
    if status != "active":
        assert caught.value.error_code == ErrorCode.CONFLICT
        validate_model.assert_not_awaited()
