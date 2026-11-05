"""Human follow-ups keep task identity, scope and a separately authorized execution."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.kernel.errors import AppError
from src.kernel.schemas.agent import AgentRequest


def record(**changes):
    return {
        "_id": "task",
        "user_id": "owner",
        "session_id": "child",
        "assistant_id": "helper",
        "run_id": "initial",
        "state": "submitted",
        "agent_id": "search",
        "agent_options": {"sandbox": "cloud", "model_id": "original"},
        "config": {"persona_preset_id": "role", "project_id": None, "disabled_tools": ["unsafe"]},
        "assistant_instructions": "Verify every result",
        "timeout_seconds": 300,
        **changes,
    }


async def test_followup_restores_original_scope_and_keeps_additional_restrictions(monkeypatch):
    from src.infra.assistant.store import AssistantStore
    from src.infra.assistant.task_turns import prepare_task_turn
    from src.infra.task.background_task_store import BackgroundTaskStore
    from tests.infra.test_assistant_tasks import helper

    monkeypatch.setattr(AssistantStore, "get", AsyncMock(return_value=helper()))
    collection = SimpleNamespace(find_one=AsyncMock(return_value=record()))
    monkeypatch.setattr(BackgroundTaskStore, "collection", property(lambda self: collection))
    request = AgentRequest(
        message="Check the answer",
        session_id="child",
        persona_preset_id="different",
        project_id="different",
        agent_options={"model_id": "different"},
        disabled_tools=["write"],
    )
    result = await prepare_task_turn(
        request, SimpleNamespace(sub="owner"), {"background_task_id": "task"}
    )
    assert result["assistant_instructions"] == "Verify every result"
    assert request.persona_preset_id == "role" and request.project_id is None
    assert request.agent_options == {"sandbox": "cloud", "model_id": "original"}
    assert request.disabled_tools == ["write", "unsafe"]
    collection.find_one.assert_awaited_once_with(
        {"_id": "task", "user_id": "owner", "session_id": "child"}
    )


async def test_unregistered_task_identity_fails_closed(monkeypatch):
    from src.infra.assistant.task_turns import prepare_task_turn
    from src.infra.task.background_task_store import BackgroundTaskStore

    monkeypatch.setattr(
        BackgroundTaskStore,
        "collection",
        property(lambda self: SimpleNamespace(find_one=AsyncMock(return_value=None))),
    )
    with pytest.raises(AppError):
        await prepare_task_turn(
            AgentRequest(message="go", session_id="child"),
            SimpleNamespace(sub="owner"),
            {"background_task_id": "foreign"},
        )


async def test_followup_authorization_preserves_original_run_and_fences_concurrent_changes(
    monkeypatch,
):
    from src.infra.assistant.task_turns import authorize_task_turn
    from src.infra.task.background_task_store import BackgroundTaskStore

    collection = SimpleNamespace(
        update_one=AsyncMock(return_value=SimpleNamespace(modified_count=1))
    )
    monkeypatch.setattr(BackgroundTaskStore, "collection", property(lambda self: collection))
    await authorize_task_turn(record(authorized_run_id="previous"), "next")
    query, update = collection.update_one.call_args.args
    assert query == {
        "_id": "task",
        "user_id": "owner",
        "session_id": "child",
        "state": "submitted",
        "authorized_run_id": "previous",
    }
    assert update["$set"]["authorized_run_id"] == "next"
    assert "run_id" not in update["$set"]
    assert update["$set"]["authorized_run_started_at"] is not None
    collection.update_one.return_value.modified_count = 0
    with pytest.raises(AppError):
        await authorize_task_turn(record(authorized_run_id="previous"), "next")


async def test_uncertain_submission_cannot_be_replayed_as_a_followup(monkeypatch):
    from src.infra.assistant.task_turns import authorize_task_turn
    from src.infra.task.background_task_store import BackgroundTaskStore

    collection = SimpleNamespace(update_one=AsyncMock())
    monkeypatch.setattr(BackgroundTaskStore, "collection", property(lambda self: collection))
    with pytest.raises(AppError):
        await authorize_task_turn(record(state="uncertain"), "next")
    collection.update_one.assert_not_awaited()
