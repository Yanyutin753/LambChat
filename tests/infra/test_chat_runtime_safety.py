"""Concurrent receiving and real shared-handler authorization boundaries."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from src.infra.channel.chat_handler import (
    create_chat_message_handler,
    execute_chat_agent,
    session_scope,
)
from src.infra.channel.dingtalk import DingTalkChannel, DingTalkConfig

pytestmark = pytest.mark.usefixtures("fake_channel_inbox")


def channel():
    ch = DingTalkChannel(
        DingTalkConfig(
            user_id="owner",
            instance_id="instance",
            receive_enabled=True,
            allowed_sender_ids="sender",
            client_id="app",
            client_secret="secret",
            corp_id="corp",
        )
    )
    ch._running = True
    ch.message_handler = AsyncMock()
    return ch


MESSAGE = {"sender_id": "sender", "chat_id": "chat", "content": "hello", "message_id": "one"}


async def test_concurrent_admission_persists_backlog_before_dispatch(fake_channel_inbox):
    ch = channel()
    fake_channel_inbox.accept_gate = gate = asyncio.Event()
    tasks = [
        asyncio.create_task(ch.enqueue_inbound({**MESSAGE, "message_id": str(i)}))
        for i in range(40)
    ]
    await asyncio.sleep(0)
    assert not fake_channel_inbox.rows
    gate.set()
    assert all(await asyncio.gather(*tasks))
    assert len(fake_channel_inbox.rows) == 40
    ch.message_handler.assert_not_awaited()
    await ch.stop()
    assert len(fake_channel_inbox.rows) == 40
    assert all(row["state"] == "pending" for row in fake_channel_inbox.rows.values())
    assert len(await ch._inbox_worker.inbox.pending(limit=40)) == 1


async def test_stop_during_acceptance_preserves_input_without_launching_agent(fake_channel_inbox):
    ch = channel()
    fake_channel_inbox.accept_gate = gate = asyncio.Event()
    pending = asyncio.create_task(ch.enqueue_inbound(MESSAGE))
    await asyncio.sleep(0)
    await ch.stop()
    gate.set()
    assert await pending
    ch.message_handler.assert_not_awaited()
    assert len(await ch._inbox_worker.inbox.pending()) == 1


async def test_stop_before_dispatch_keeps_input_for_new_reader():
    ch = channel()
    assert await ch.enqueue_inbound(MESSAGE)
    await ch.stop()
    ch.message_handler.assert_not_awaited()
    replacement = channel()
    try:
        assert await replacement.drain()
        replacement.message_handler.assert_awaited_once()
    finally:
        await replacement.stop()


async def test_handler_failures_remain_visible_to_drain():
    ch = channel()
    ch.message_handler.side_effect = RuntimeError("agent failed")
    assert await ch.enqueue_inbound(MESSAGE)
    try:
        assert not await ch.drain()
        assert len(await ch._inbox_worker.inbox.pending()) == 1
    finally:
        await ch.stop()


@pytest.fixture
def handler_dependencies(monkeypatch):
    monkeypatch.setattr("src.infra.channel.recovery.settings.TASK_BACKEND", "local")
    monkeypatch.setattr(
        "src.infra.folder.storage.ProjectStorage.get_by_id",
        AsyncMock(return_value=SimpleNamespace(workspace=None)),
    )
    config = {
        "enabled": True,
        "receive_enabled": True,
        "allowed_sender_ids": "sender",
        "agent_id": "chosen",
        "model_id": "model",
        "persona_preset_id": "persona",
        "project_id": "project",
        "team_id": "team",
    }
    storage = AsyncMock()
    storage.get_config.return_value = config
    redis = AsyncMock()
    redis.get.return_value = None
    task_manager = AsyncMock()
    task_manager.submit.return_value = ("run", "trace")
    session_manager = AsyncMock()
    persona = AsyncMock()
    persona.use_preset.return_value = SimpleNamespace(
        system_prompt="persona prompt", skill_names=["skill"]
    )
    events = [
        {"event_type": "message:chunk", "data": {"depth": 0, "content": "answer"}},
        {"event_type": "done", "data": {}},
    ]

    async def read(*args, **kwargs):
        for event in events:
            yield event

    monkeypatch.setattr("src.infra.channel.chat_handler.ChannelStorage", lambda: storage)
    monkeypatch.setattr("src.infra.channel.chat_handler.RedisStorage", lambda: redis)
    monkeypatch.setattr(
        "src.infra.session.dual_writer.get_dual_writer",
        lambda: SimpleNamespace(read_from_redis=read),
    )
    monkeypatch.setattr("src.infra.task.manager.get_task_manager", lambda: task_manager)
    monkeypatch.setattr("src.infra.session.manager.SessionManager", lambda: session_manager)
    monkeypatch.setattr("src.infra.persona_preset.manager.PersonaPresetManager", lambda: persona)
    ch = channel()
    ch.send_message = AsyncMock(return_value=True)
    handle = create_chat_message_handler(ch, "fallback")
    return SimpleNamespace(
        config=config,
        channel=ch,
        handle=handle,
        manager=task_manager,
        sessions=session_manager,
        events=events,
        persona=persona,
    )


async def test_handler_passes_configured_options_and_preserves_reply_context(handler_dependencies):
    deps = handler_dependencies
    await deps.handle(
        user_id="owner",
        sender_id="sender",
        chat_id="chat",
        content="hello",
        metadata={"session_webhook": "ephemeral"},
    )
    args = deps.manager.submit.call_args.kwargs
    assert {
        key: args[key]
        for key in (
            "agent_id",
            "agent_options",
            "persona_system_prompt",
            "enabled_skills",
            "project_id",
            "team_id",
            "user_id",
            "auto_mode",
        )
    } == {
        "agent_id": "chosen",
        "agent_options": {"model_id": "model"},
        "persona_system_prompt": "persona prompt",
        "enabled_skills": ["skill"],
        "project_id": "project",
        "team_id": "team",
        "user_id": "owner",
        "auto_mode": False,
    }
    deps.channel.send_message.assert_awaited_once_with(
        "chat", "answer", session_webhook="ephemeral"
    )


async def test_handler_rechecks_updated_sender_authorization(handler_dependencies):
    deps = handler_dependencies
    deps.config["allowed_sender_ids"] = "new-owner"
    await deps.handle(
        user_id="owner", sender_id="sender", chat_id="chat", content="hello", metadata={}
    )
    deps.manager.submit.assert_not_awaited()


async def test_handler_uses_channel_receive_default_when_field_is_omitted(handler_dependencies):
    deps = handler_dependencies
    deps.config.pop("receive_enabled")
    await deps.handle(
        user_id="owner", sender_id="sender", chat_id="chat", content="hello", metadata={}
    )
    assert deps.manager.submit.await_count == 1


async def test_handler_never_sends_subagent_or_user_chunks(handler_dependencies):
    deps = handler_dependencies
    deps.events[:0] = [
        {"event_type": "message:chunk", "data": {"depth": 1, "content": "private subagent"}},
        {"event_type": "message:chunk", "data": {"role": "user", "content": "user message"}},
    ]
    await deps.handle(
        user_id="owner", sender_id="sender", chat_id="chat", content="hello", metadata={}
    )
    deps.channel.send_message.assert_awaited_once_with("chat", "answer")


async def test_cancelling_handler_preserves_recoverable_background_run(
    handler_dependencies, monkeypatch
):
    deps = handler_dependencies
    reading = asyncio.Event()

    async def read(*args, **kwargs):
        reading.set()
        await asyncio.Event().wait()
        yield {}

    monkeypatch.setattr(
        "src.infra.session.dual_writer.get_dual_writer",
        lambda: SimpleNamespace(read_from_redis=read),
    )
    task = asyncio.create_task(
        deps.handle(
            user_id="owner", sender_id="sender", chat_id="chat", content="hello", metadata={}
        )
    )
    await reading.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    deps.manager.cancel_run.assert_not_awaited()


def test_telegram_forum_threads_have_isolated_sessions():
    ch = channel()
    assert session_scope(ch, "sender", "chat", {"message_thread_id": 1}) != session_scope(
        ch, "sender", "chat", {"message_thread_id": 2}
    )


async def test_execute_agent_forwards_team_and_attachment_options(monkeypatch):
    seen = {}

    async def stream(*args, **kwargs):
        seen.update(kwargs)
        yield {"event": "done"}

    factory = AsyncMock(return_value=SimpleNamespace(stream=stream))
    monkeypatch.setattr("src.agents.core.base.AgentFactory.get", factory)
    events = [
        event
        async for event in execute_chat_agent(
            "session",
            "chosen",
            "hello",
            "owner",
            team_id="team",
            attachments=[{"name": "file"}],
            recommendation_input="hint",
        )
    ]
    assert events == [{"event": "done"}]
    assert seen["team_id"] == "team"
    assert seen["attachments"] == [{"name": "file"}]
    assert seen["recommendation_input"] == "hint"


async def test_handler_sessions_are_isolated_by_actual_owner_sender_and_instance(
    handler_dependencies,
):
    deps = handler_dependencies
    deps.config["allowed_sender_ids"] = "sender other"
    for owner, sender, instance in [
        ("owner", "sender", "instance"),
        ("owner", "other", "instance"),
        ("other-owner", "sender", "instance"),
        ("owner", "sender", "other-instance"),
    ]:
        deps.channel.config.user_id = owner
        deps.channel.config.instance_id = instance
        await deps.handle(
            user_id=owner, sender_id=sender, chat_id="chat", content="hello", metadata={}
        )
    submissions = [call.kwargs for call in deps.manager.submit.call_args_list]
    assert len({item["session_id"] for item in submissions}) == 4
    assert [item["user_id"] for item in submissions] == ["owner", "owner", "other-owner", "owner"]


def test_invalid_saved_credentials_are_hidden_from_validation_log_text():
    with pytest.raises(ValidationError) as failure:
        DingTalkConfig(client_secret={"private": "do-not-log-this-secret"})
    assert "do-not-log-this-secret" not in str(failure.value)


async def test_oversized_inbound_text_is_ignored_without_truncation_or_agent(monkeypatch):
    ch = channel()
    redis = AsyncMock()
    monkeypatch.setattr("src.infra.channel.chat.get_redis_client", lambda: redis)
    assert await ch.enqueue_inbound({**MESSAGE, "content": "x" * 65537})
    await ch.drain()
    redis.set.assert_not_awaited()
    ch.message_handler.assert_not_awaited()


async def test_handler_uses_registered_arq_executor_when_configured(
    handler_dependencies, monkeypatch
):
    deps = handler_dependencies
    monkeypatch.setattr("src.infra.channel.recovery.settings.TASK_BACKEND", "arq")
    deps.manager.submit_arq.return_value = ("run", "trace")
    await deps.handle(
        user_id="owner", sender_id="sender", chat_id="chat", content="hello", metadata={}
    )
    deps.manager.submit.assert_not_awaited()
    args = deps.manager.submit_arq.call_args.kwargs
    assert args["executor_key"] == "agent_stream"
    assert "executor" not in args
    assert args["user_id"] == "owner"
    deps.channel.send_message.assert_awaited_once_with("chat", "answer")
