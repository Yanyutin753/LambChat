"""A queued coordinator must recheck authority before invoking its model."""

from unittest.mock import AsyncMock, Mock

import pytest

from src.infra.utils.datetime import utc_now
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.agent import AgentRequest
from src.kernel.schemas.assistant import Assistant
from src.kernel.schemas.user import TokenPayload


def assistant(**changes):
    return Assistant(
        id="assistant",
        session_id="123456789012345678901234",
        user_id="owner",
        name="Helper",
        revision=1,
        status="active",
        created_at=utc_now(),
        updated_at=utc_now(),
        **changes,
    )


def user():
    return TokenPayload(sub="owner", username="owner", roles=["user"], permissions=["chat:write"])


@pytest.mark.parametrize("status", ["paused", "archived"])
async def test_inactive_coordinator_never_executes(monkeypatch, status):
    from src.infra.assistant.execution import execute_assistant_stream
    from src.infra.assistant.store import AssistantStore
    from src.infra.task import background_tasks

    monkeypatch.setattr(
        AssistantStore,
        "for_session",
        AsyncMock(return_value=assistant().model_copy(update={"status": status})),
    )
    validate = AsyncMock()
    monkeypatch.setattr(background_tasks, "validate_background_execution", validate)
    with pytest.raises(AppError) as caught:
        async for _ in execute_assistant_stream(assistant().session_id, "search", "go", "owner"):
            pass
    assert caught.value.error_code == ErrorCode.CONFLICT
    validate.assert_not_awaited()


@pytest.mark.parametrize("team_id", [None, "owned-team"])
async def test_resume_restores_instructions_and_keeps_admitted_workspace(monkeypatch, team_id):
    from src.api import deps
    from src.api.routes import chat_agent_execution
    from src.infra.assistant.execution import execute_assistant_stream
    from src.infra.assistant.service import AssistantService
    from src.infra.assistant.store import AssistantStore
    from src.infra.task import background_tasks

    value = assistant(instructions="Keep a daily research log", team_id=team_id)
    agent_id = "team" if team_id else "search"
    options = {
        "sandbox": "local",
        "sandbox_machine_id": "original-machine",
        "model_id": "original-model",
    }
    monkeypatch.setattr(AssistantStore, "for_session", AsyncMock(return_value=value))
    monkeypatch.setattr(deps, "_load_user_payload", AsyncMock(return_value=user()))
    monkeypatch.setattr(AssistantService, "validate_configuration", AsyncMock())
    request = AgentRequest(
        message="",
        agent_options=options,
        persona_system_prompt="Role",
        disabled_tools=["unsafe"],
        team_id=team_id,
    )
    validate = AsyncMock(return_value=request)
    monkeypatch.setattr(background_tasks, "validate_background_execution", validate)
    invalidate = Mock()
    monkeypatch.setattr("src.infra.session.memory_scope.invalidate_memory_scope_caches", invalidate)
    seen = []

    async def execute(*args, **kwargs):
        seen.append(kwargs)
        yield {"event": "done"}

    monkeypatch.setattr(chat_agent_execution, "_execute_agent_stream", execute)
    events = [
        event
        async for event in execute_assistant_stream(
            value.session_id,
            agent_id,
            "go",
            "owner",
            agent_options=options,
            interrupted_resume=True,
        )
    ]
    assert events == [{"event": "done"}]
    assert seen[0]["persona_system_prompt"] == "Role\n\nKeep a daily research log"
    assert seen[0]["agent_options"] == options
    assert seen[0]["disabled_tools"] == ["unsafe"]
    assert seen[0]["interrupted_resume"] is True
    invalidate.assert_called_once_with(user_id="owner", session_id=value.session_id)
    validate.assert_awaited_once_with(value.session_id, agent_id, "owner", options)
    assert seen[0]["team_id"] == team_id


async def test_missing_identity_cannot_resume_as_an_ordinary_chat(monkeypatch):
    from src.infra.assistant.execution import execute_assistant_stream
    from src.infra.assistant.store import AssistantStore

    monkeypatch.setattr(AssistantStore, "for_session", AsyncMock(return_value=None))
    with pytest.raises(AppError) as caught:
        async for _ in execute_assistant_stream("missing", "search", "go", "owner"):
            pass
    assert caught.value.error_code == ErrorCode.FORBIDDEN


async def test_scheduled_coordinator_obeys_pause_after_queueing(monkeypatch):
    from types import SimpleNamespace

    from src.infra.assistant.store import AssistantStore
    from src.infra.scheduler import conversation
    from src.infra.task import background_tasks

    admission = AsyncMock()
    monkeypatch.setattr(conversation, "validate_scheduled_run_admission", admission)
    monkeypatch.setattr(
        AssistantStore,
        "for_session",
        AsyncMock(return_value=assistant().model_copy(update={"status": "paused"})),
    )
    validate = AsyncMock(side_effect=AssertionError("Paused coordinator reached execution"))
    monkeypatch.setattr(background_tasks, "validate_background_execution", validate)
    with pytest.raises(AppError) as caught:
        async for _ in conversation.execute_conversation_schedule(
            assistant().session_id,
            "search",
            "go",
            "owner",
            presenter=SimpleNamespace(run_id="scheduled-run"),
        ):
            pass
    assert caught.value.error_code == ErrorCode.CONFLICT
    admission.assert_awaited_once()
    validate.assert_not_awaited()
