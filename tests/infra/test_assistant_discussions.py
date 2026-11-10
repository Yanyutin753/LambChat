"""A channel audience gets its own assistant conversation, never the private coordinator."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.kernel.errors import AppError, ErrorCode


def test_discussion_identity_is_stable_but_separates_assistants_owners_and_sources():
    from src.infra.assistant.discussions import discussion_session_id

    first = discussion_session_id("owner", "helper", "channel-source")
    assert first == discussion_session_id("owner", "helper", "channel-source")
    assert (
        len(
            {
                first,
                discussion_session_id("other", "helper", "channel-source"),
                discussion_session_id("owner", "other-helper", "channel-source"),
                discussion_session_id("owner", "helper", "other-source"),
            }
        )
        == 4
    )


async def test_discussion_authority_rechecks_current_binding_and_pause(monkeypatch):
    from src.infra.assistant.discussions import validate_discussion
    from src.infra.assistant.store import AssistantStore
    from src.infra.channel.channel_storage import ChannelStorage

    assistant = SimpleNamespace(id="helper", status="active")
    lookup = AsyncMock(return_value=assistant)
    monkeypatch.setattr(AssistantStore, "get", lookup)
    config = {"enabled": True, "runtime_config": {"assistant_id": "helper"}}
    monkeypatch.setattr(ChannelStorage, "get_config", AsyncMock(return_value=config))
    discussion = {
        "user_id": "owner",
        "assistant_id": "helper",
        "channel_type": "telegram",
        "channel_instance_id": "instance",
        "session_id": "discussion",
    }
    assert await validate_discussion(discussion, "owner") is assistant
    config["runtime_config"]["assistant_id"] = "replacement"
    with pytest.raises(AppError):
        await validate_discussion(discussion, "owner")
    config["runtime_config"]["assistant_id"] = "helper"
    assistant.status = "paused"
    with pytest.raises(AppError):
        await validate_discussion(discussion, "owner")
    lookup.reset_mock()
    with pytest.raises(AppError):
        await validate_discussion(discussion, "foreign")
    lookup.assert_not_awaited()


async def test_discussion_memory_does_not_read_private_assistant_or_personal_bank(monkeypatch):
    from src.infra.assistant import discussions
    from src.infra.assistant.memory import session_assistant_partition

    session_id = discussions.discussion_session_id("owner", "helper", "source")
    row = {
        "_id": session_id,
        "session_id": session_id,
        "user_id": "owner",
        "assistant_id": "helper",
    }
    monkeypatch.setattr(discussions.DiscussionStore, "get", AsyncMock(return_value=row))
    validate = AsyncMock(return_value=SimpleNamespace(id="helper", memory_mode="private"))
    monkeypatch.setattr(discussions, "validate_discussion", validate)
    assert (
        await session_assistant_partition(session_id, "owner", {})
        == f"assistant-discussion-memory:{session_id}"
    )
    validate.assert_awaited_once()


def test_cloned_discussion_does_not_inherit_delivery_or_task_authority():
    from src.kernel.schemas.session import clone_session_metadata

    metadata = {
        "assistant_id": "helper",
        "assistant_discussion_id": "discussion",
        "background_task_id": "task",
        "background_parent_session_id": "parent",
        "channel_delivery": {"chat_id": "group"},
        "project_id": "project",
    }
    assert clone_session_metadata(metadata) == {"project_id": "project"}
    assert metadata["channel_delivery"]["chat_id"] == "group"


async def test_web_followup_keeps_discussion_identity_and_closes_private_history_tools(monkeypatch):
    from src.infra.assistant import discussions
    from src.infra.assistant.service import AssistantService, prepare_assistant_request
    from src.infra.utils.datetime import utc_now
    from src.kernel.schemas.agent import AgentRequest
    from src.kernel.schemas.assistant import Assistant
    from src.kernel.schemas.user import TokenPayload

    session_id = discussions.discussion_session_id("owner", "helper", "source")
    assistant = Assistant(
        id="helper",
        session_id="private",
        user_id="owner",
        name="Researcher",
        status="active",
        revision=1,
        model_id="approved-model",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    monkeypatch.setattr(
        discussions.DiscussionStore, "get", AsyncMock(return_value={"session_id": session_id})
    )
    monkeypatch.setattr(discussions, "validate_discussion", AsyncMock(return_value=assistant))
    monkeypatch.setattr(AssistantService, "validate_configuration", AsyncMock())
    monkeypatch.setattr(
        "src.infra.backend.workspace_selection.resolve_workspace_options",
        AsyncMock(return_value={"model_id": "approved-model"}),
    )
    request = AgentRequest(
        session_id=session_id, message="Continue", agent_options={"model_id": "unapproved"}
    )
    user = TokenPayload(sub="owner", username="tester")
    assert await prepare_assistant_request(request, user, {"assistant_id": "helper"}) is assistant
    assert request.session_id == session_id
    assert request.agent_options["model_id"] == "approved-model"
    assert {"search_conversation_history", "get_conversation_detail"}.issubset(
        request.disabled_tools
    )


async def test_replayed_channel_message_cannot_switch_assistant_or_conversation():
    from src.infra.assistant.channel_binding import channel_discussion_session
    from src.infra.channel.inbox_worker import current_delivery

    context = SimpleNamespace(
        checkpoint={"run_id": "run", "session_id": "original-discussion", "assistant_id": "helper"}
    )
    token = current_delivery.set(context)
    try:
        assert (
            channel_discussion_session(
                "source", {"runtime_config": {"assistant_id": "helper"}}, "owner"
            )
            == "original-discussion"
        )
        with pytest.raises(AppError):
            channel_discussion_session(
                "source", {"runtime_config": {"assistant_id": "replacement"}}, "owner"
            )
        with pytest.raises(AppError):
            channel_discussion_session("source", {}, "owner")
    finally:
        current_delivery.reset(token)


async def test_channel_dispatch_uses_assistant_executor_in_arq(monkeypatch):
    from src.infra.assistant import channel_binding
    from src.infra.channel.recovery import submit_channel_task
    from src.kernel.config import settings

    values = {
        "session_id": "discussion",
        "user_id": "owner",
        "session_metadata": {"executor_key": "assistant_stream"},
    }
    prepare = AsyncMock(return_value=values)
    monkeypatch.setattr(channel_binding, "prepare_channel_assistant", prepare)
    monkeypatch.setattr(settings, "TASK_BACKEND", "arq")
    manager = SimpleNamespace(submit_arq=AsyncMock(return_value=("run", "trace")))
    delivery = {"channel_type": "telegram", "channel_instance_id": "instance", "chat_id": "group"}
    assert await submit_channel_task(
        manager, channel_delivery=delivery, session_id="discussion", user_id="owner"
    ) == ("run", "trace")
    prepare.assert_awaited_once()
    assert manager.submit_arq.call_args.kwargs["executor_key"] == "assistant_stream"


async def test_bound_channel_admission_resolves_real_assistant_config_and_persists_scope(
    monkeypatch,
):
    from src.infra.assistant import discussions
    from src.infra.assistant.channel_binding import prepare_channel_assistant
    from src.infra.assistant.execution import execute_assistant_stream
    from src.infra.assistant.service import AssistantService
    from src.infra.assistant.store import AssistantStore
    from src.infra.channel.channel_storage import ChannelStorage
    from src.infra.utils.datetime import utc_now
    from src.kernel.schemas.assistant import Assistant
    from src.kernel.schemas.user import TokenPayload

    session_id = discussions.discussion_session_id("owner", "helper", "source")
    assistant = Assistant(
        id="helper",
        session_id="private",
        user_id="owner",
        name="Researcher",
        instructions="Verify findings",
        status="active",
        revision=1,
        model_id="approved",
        created_at=utc_now(),
        updated_at=utc_now(),
    )
    config = {"enabled": True, "runtime_config": {"assistant_id": "helper"}}
    discussion = {
        "user_id": "owner",
        "assistant_id": "helper",
        "session_id": session_id,
        "channel_type": "telegram",
        "channel_instance_id": "instance",
    }
    monkeypatch.setattr(ChannelStorage, "get_config", AsyncMock(return_value=config))
    monkeypatch.setattr(discussions.DiscussionStore, "register", AsyncMock(return_value=discussion))
    monkeypatch.setattr(discussions.DiscussionStore, "get", AsyncMock(return_value=discussion))
    monkeypatch.setattr(AssistantStore, "get", AsyncMock(return_value=assistant))
    monkeypatch.setattr(AssistantService, "validate_configuration", AsyncMock())
    monkeypatch.setattr(
        "src.infra.task.background_tasks._load_user",
        AsyncMock(return_value=TokenPayload(sub="owner", username="tester")),
    )
    monkeypatch.setattr("src.infra.agent.access.validate_user_agent_access", AsyncMock())
    monkeypatch.setattr(
        "src.infra.backend.workspace_selection.resolve_workspace_options",
        AsyncMock(return_value={"model_id": "approved"}),
    )
    values = await prepare_channel_assistant(
        {"channel_type": "telegram", "channel_instance_id": "instance", "chat_id": "group"},
        {
            "session_id": session_id,
            "user_id": "owner",
            "message": "Research",
            "agent_id": "quick",
            "agent_options": {"model_id": "stale"},
            "auto_mode": True,
        },
    )
    assert values["session_id"] == session_id != assistant.session_id
    assert values["executor"] is execute_assistant_stream
    assert values["agent_id"] == "search"
    assert values["agent_options"]["model_id"] == "approved"
    assert values["session_metadata"]["assistant_discussion_id"] == session_id
    assert values["session_metadata"]["executor_key"] == "assistant_stream"
    assert values["auto_mode"] is False
    assert values["persona_system_prompt"] == "Verify findings"
    assert "search_conversation_history" in values["disabled_tools"]


async def test_discussion_background_task_inherits_audience_memory_and_rechecks_revocation(
    monkeypatch,
):
    from src.infra.assistant import discussions
    from src.infra.assistant.memory import session_assistant_partition
    from src.infra.task.background_task_store import BackgroundTaskStore

    parent = discussions.discussion_session_id("owner", "helper", "source")
    record = {"assistant_id": "helper", "parent_session_id": parent}
    monkeypatch.setattr(
        BackgroundTaskStore,
        "collection",
        property(lambda self: SimpleNamespace(find_one=AsyncMock(return_value=record))),
    )
    monkeypatch.setattr(
        discussions.DiscussionStore, "get", AsyncMock(return_value={"session_id": parent})
    )
    validate = AsyncMock(return_value=SimpleNamespace(id="helper"))
    monkeypatch.setattr(discussions, "validate_discussion", validate)
    assert (
        await session_assistant_partition("child", "owner", {"background_task_id": "task"})
        == f"assistant-discussion-memory:{parent}"
    )
    validate.side_effect = AppError(ErrorCode.FORBIDDEN)
    with pytest.raises(AppError):
        await session_assistant_partition("child", "owner", {"background_task_id": "task"})


async def test_removed_channel_sender_cannot_resume_an_old_discussion(monkeypatch):
    from src.infra.assistant.discussions import validate_discussion
    from src.infra.assistant.store import AssistantStore
    from src.infra.channel.channel_storage import ChannelStorage

    config = {
        "enabled": True,
        "receive_enabled": True,
        "allowed_sender_ids": "current-sender",
        "allowed_chat_ids": "group",
        "runtime_config": {"assistant_id": "helper"},
    }
    monkeypatch.setattr(ChannelStorage, "get_config", AsyncMock(return_value=config))
    lookup = AsyncMock(return_value=SimpleNamespace(id="helper", status="active"))
    monkeypatch.setattr(AssistantStore, "get", lookup)
    discussion = {
        "user_id": "owner",
        "assistant_id": "helper",
        "channel_type": "telegram",
        "channel_instance_id": "instance",
        "sender_id": "removed-sender",
        "chat_id": "group",
    }
    with pytest.raises(AppError):
        await validate_discussion(discussion, "owner")
    lookup.assert_not_awaited()


async def test_private_assistant_results_never_fall_back_to_unrelated_default_channel(monkeypatch):
    from src.infra.channel import fallback
    from src.infra.session.manager import SessionManager

    monkeypatch.setattr(
        SessionManager,
        "get_session",
        AsyncMock(return_value=SimpleNamespace(metadata={"background_assistant_id": "helper"})),
    )
    target = AsyncMock(return_value=("feishu", "instance", "unrelated-group"))
    monkeypatch.setattr(fallback, "_resolve_fallback_target", target)
    assert not await fallback.deliver_task_fallback(
        user_id="owner",
        session_id="task",
        run_id="run",
        status_value="completed",
        message="Private result",
    )
    target.assert_not_awaited()
