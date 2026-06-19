from __future__ import annotations

import asyncio
import json
import sys
from types import ModuleType
from typing import Any

import pytest

from src.infra.channel.feishu import handler as feishu_handler
from src.kernel.extensions import PluginRuntime, build_agent_team_plugin_manifest


class _FakeManager:
    def __init__(self) -> None:
        self.sent_messages: list[tuple[str, str, str]] = []
        self.sent_cards: list[tuple[str, str, str, str | None]] = []

    async def send_message(
        self, user_id: str, chat_id: str, content: str, instance_id: str | None = None
    ) -> None:
        self.sent_messages.append((user_id, chat_id, content))

    async def send_card_message_with_id(
        self,
        user_id: str,
        chat_id: str,
        card_content: str,
        instance_id: str | None = None,
        reply_to_id: str | None = None,
    ) -> tuple[bool, str]:
        self.sent_cards.append((user_id, chat_id, card_content, reply_to_id))
        return True, f"approval-card-{len(self.sent_cards)}"


class _FakeReactionManager:
    def __init__(self) -> None:
        self.add_calls: list[tuple[str, str, str]] = []
        self.delete_calls: list[tuple[str, str, str]] = []
        self.sent_cards: list[tuple[str, str, str, str | None]] = []

    async def add_reaction(
        self,
        user_id: str,
        message_id: str,
        emoji_type: str,
        instance_id: str | None = None,
    ) -> str:
        self.add_calls.append((user_id, message_id, emoji_type))
        return "reaction-1"

    async def delete_reaction(
        self,
        user_id: str,
        message_id: str,
        reaction_id: str,
        instance_id: str | None = None,
    ) -> bool:
        self.delete_calls.append((user_id, message_id, reaction_id))
        return True

    async def send_card_message_with_id(
        self,
        user_id: str,
        chat_id: str,
        card_content: str,
        instance_id: str | None = None,
        reply_to_id: str | None = None,
    ) -> tuple[bool, str]:
        self.sent_cards.append((user_id, chat_id, card_content, reply_to_id))
        return True, f"approval-card-{len(self.sent_cards)}"


class _FakeStreamingClient:
    def __init__(self) -> None:
        self.created = 0
        self.initial_texts: list[str] = []
        self.sent: list[tuple[str, str, str | None]] = []
        self.updates: list[tuple[str, str, int]] = []
        self.finalized: list[tuple[str, str, int]] = []
        self.patched_cards: list[tuple[str, str]] = []

    async def create_stream_card(self, initial_text: str = "...") -> str:
        self.created += 1
        self.initial_texts.append(initial_text)
        return "card-1"

    async def send_card_by_id(
        self, chat_id: str, card_id: str, *, reply_to_id: str | None = None
    ) -> tuple[bool, str]:
        self.sent.append((chat_id, card_id, reply_to_id))
        return True, "message-1"

    async def update_stream_card(self, card_id: str, content: str, sequence: int) -> bool:
        self.updates.append((card_id, content, sequence))
        return True

    async def finalize_stream_card(self, card_id: str, content: str, sequence: int) -> bool:
        self.finalized.append((card_id, content, sequence))
        return True

    async def patch_card_message(self, message_id: str, card_content: str) -> bool:
        self.patched_cards.append((message_id, card_content))
        return True


class _FakeFileClient:
    def __init__(self) -> None:
        self.uploads: list[tuple[bytes, str]] = []
        self.file_uploads: list[tuple[str, str]] = []
        self.image_uploads: list[bytes] = []
        self.image_file_uploads: list[tuple[str, bytes]] = []
        self.sent_files: list[tuple[str, str, str, str | None]] = []
        self.sent_images: list[tuple[str, str, str | None]] = []

    async def upload_bytes(self, file_data: bytes, file_name: str) -> str:
        self.uploads.append((file_data, file_name))
        return f"feishu-{file_name}"

    async def upload_image(self, image_data: bytes) -> str:
        self.image_uploads.append(image_data)
        return "feishu-image-key"

    async def upload_file(self, file_path: str, file_name: str) -> str:
        self.file_uploads.append((file_path, file_name))
        return f"feishu-{file_name}"

    async def upload_image_file(self, file_path: str) -> str:
        from pathlib import Path

        self.image_file_uploads.append((file_path, Path(file_path).read_bytes()))
        return "feishu-image-key"

    async def send_file_by_key(
        self,
        chat_id: str,
        file_key: str,
        file_name: str,
        reply_to_id: str | None = None,
    ) -> bool:
        self.sent_files.append((chat_id, file_key, file_name, reply_to_id))
        return True

    async def send_image_by_key(
        self,
        chat_id: str,
        image_key: str,
        reply_to_id: str | None = None,
    ) -> bool:
        self.sent_images.append((chat_id, image_key, reply_to_id))
        return True


class _FakeImageBytesOnlyClient:
    def __init__(self) -> None:
        self.image_uploads: list[bytes] = []

    async def upload_image(self, image_data: bytes) -> str:
        self.image_uploads.append(image_data)
        return "feishu-image-key"


class _FakeStreamingManager:
    def __init__(self, client: Any) -> None:
        self.client = client

    def _find_channel(self, user_id: str, instance_id: str | None = None):
        return self.client if user_id == "user-1" else None


class _FakeTaskManager:
    def __init__(self) -> None:
        self.submit_calls: list[dict[str, Any]] = []

    async def submit(self, **kwargs: Any) -> tuple[str, str]:
        self.submit_calls.append(kwargs)
        executor = kwargs["executor"]
        async for _event in executor(
            kwargs["session_id"],
            kwargs["agent_id"],
            kwargs["message"],
            kwargs["user_id"],
            enabled_skills=["planning"],
            persona_system_prompt="Persona prompt",
            disabled_mcp_tools=["mcp.tool"],
            recommendation_input="hello",
            team_id="team-1",
            active_goal={"objective": "ship it"},
        ):
            pass
        return "run-1", ""


def _install_fake_task_manager_module(
    monkeypatch: pytest.MonkeyPatch, fake_task_manager: _FakeTaskManager
) -> None:
    task_module = ModuleType("src.infra.task")
    manager_module = ModuleType("src.infra.task.manager")
    manager_module.get_task_manager = lambda: fake_task_manager  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "src.infra.task", task_module)
    monkeypatch.setitem(sys.modules, "src.infra.task.manager", manager_module)


class _FakeChannelStorage:
    def __init__(self) -> None:
        self.cleared_configs: list[tuple[str, Any, str]] = []

    async def get_config(self, user_id: str, channel_type: Any, instance_id: str):
        return {
            "name": "Feishu Channel",
            "agent_id": "search",
            "model_id": None,
            "project_id": "deleted-project",
        }

    async def clear_config_project_id(
        self, user_id: str, channel_type: Any, instance_id: str
    ) -> int:
        self.cleared_configs.append((user_id, channel_type, instance_id))
        return 1


class _FakePersonaChannelStorage:
    async def get_config(self, user_id: str, channel_type: Any, instance_id: str):
        return {
            "name": "Feishu Channel",
            "agent_id": "search",
            "model_id": "model-1",
            "project_id": None,
            "persona_preset_id": "persona-1",
        }


class _FakeTeamChannelStorage:
    async def get_config(self, user_id: str, channel_type: Any, instance_id: str):
        return {
            "name": "Feishu Team Channel",
            "agent_id": "team",
            "model_id": None,
            "project_id": None,
            "team_id": "team-channel-1",
            "persona_preset_id": "persona-1",
        }


class _FakePluginOptionTeamChannelStorage:
    async def get_config(self, user_id: str, channel_type: Any, instance_id: str):
        return {
            "name": "Feishu Team Channel",
            "agent_id": "team",
            "model_id": None,
            "project_id": None,
            "team_id": "legacy-team",
            "plugin_options": {
                "agent_team": {"SELECTED_TEAM_ID": "plugin-option-team"},
            },
            "persona_preset_id": "persona-1",
        }


class _FakePersonaPresetManager:
    async def use_preset(self, preset_id: str, *, user_id: str, is_admin: bool):
        assert preset_id == "persona-1"
        assert user_id == "user-1"
        assert is_admin is False
        return type(
            "Snapshot",
            (),
            {
                "preset_id": "persona-1",
                "name": "Planner",
                "system_prompt": "Plan first.",
                "skill_names": ["planning"],
                "missing_skill_names": [],
                "version": 2,
                "avatar": "icon:brain",
                "starter_prompts": [],
                "model_dump": lambda self: {
                    "preset_id": "persona-1",
                    "name": "Planner",
                    "system_prompt": "Plan first.",
                    "skill_names": ["planning"],
                    "missing_skill_names": [],
                    "version": 2,
                    "avatar": "icon:brain",
                    "starter_prompts": [],
                },
            },
        )()


class _FakeSessionManager:
    def __init__(self) -> None:
        self.updates: list[tuple[str, Any]] = []

    async def update_session(self, session_id: str, session_update: Any):
        self.updates.append((session_id, session_update))
        return None


class _FakeProjectStorage:
    def __init__(self) -> None:
        self.created_names: list[tuple[str, str]] = []

    async def get_by_id(self, project_id: str, user_id: str):
        return None

    async def get_or_create_by_name(self, user_id: str, name: str):
        self.created_names.append((user_id, name))
        return type("Project", (), {"id": "project-from-channel-name"})()


@pytest.mark.asyncio
async def test_feishu_executor_accepts_task_runtime_skill_kwargs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    fake_task_manager = _FakeTaskManager()
    fake_manager = _FakeManager()
    fake_session_manager = _FakeSessionManager()

    async def _fake_execute_feishu_agent(**kwargs: Any):
        captured.update(kwargs)
        yield {"event": "done", "data": {}}

    async def _no_op_process_events(**kwargs: Any) -> None:
        return None

    async def _no_op_collector_method(self) -> None:
        return None

    monkeypatch.setattr(
        feishu_handler,
        "_get_feishu_session_id",
        lambda chat_id: _async_return(f"feishu_{chat_id}"),
    )
    _install_fake_task_manager_module(monkeypatch, fake_task_manager)
    monkeypatch.setattr(feishu_handler, "execute_feishu_agent", _fake_execute_feishu_agent)
    monkeypatch.setattr(feishu_handler, "_process_events", _no_op_process_events)
    monkeypatch.setattr(
        feishu_handler.FeishuResponseCollector,
        "stop_processing_indicator",
        _no_op_collector_method,
    )
    monkeypatch.setattr(
        feishu_handler.FeishuResponseCollector,
        "send_card_message",
        _no_op_collector_method,
    )
    monkeypatch.setattr(
        feishu_handler.FeishuResponseCollector,
        "upload_and_send_files",
        _no_op_collector_method,
    )

    handler = feishu_handler.create_feishu_message_handler(fake_manager, default_agent="search")

    await handler(
        user_id="user-1",
        sender_id="sender-1",
        chat_id="chat-1",
        content="hello",
        metadata={},
    )

    assert fake_manager.sent_messages == []
    assert captured["enabled_skills"] == ["planning"]
    assert captured["persona_system_prompt"] == "Persona prompt"
    assert captured["disabled_mcp_tools"] == ["mcp.tool"]
    assert captured["recommendation_input"] == "hello"


@pytest.mark.asyncio
async def test_feishu_handler_ignores_stale_channel_project_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_task_manager = _FakeTaskManager()
    fake_manager = _FakeManager()
    fake_project_storage = _FakeProjectStorage()
    fake_channel_storage = _FakeChannelStorage()

    async def _fake_execute_feishu_agent(**kwargs: Any):
        yield {"event": "done", "data": {}}

    async def _no_op_process_events(**kwargs: Any) -> None:
        return None

    async def _no_op_collector_method(self) -> None:
        return None

    monkeypatch.setattr(
        feishu_handler,
        "_get_feishu_session_id",
        lambda chat_id: _async_return(f"feishu_{chat_id}"),
    )
    _install_fake_task_manager_module(monkeypatch, fake_task_manager)
    monkeypatch.setattr(
        "src.infra.channel.channel_storage.ChannelStorage",
        lambda: fake_channel_storage,
    )
    monkeypatch.setattr(
        "src.infra.folder.storage.get_project_storage",
        lambda: fake_project_storage,
    )
    monkeypatch.setattr(feishu_handler, "execute_feishu_agent", _fake_execute_feishu_agent)
    monkeypatch.setattr(feishu_handler, "_process_events", _no_op_process_events)
    monkeypatch.setattr(
        feishu_handler.FeishuResponseCollector,
        "stop_processing_indicator",
        _no_op_collector_method,
    )
    monkeypatch.setattr(
        feishu_handler.FeishuResponseCollector,
        "send_card_message",
        _no_op_collector_method,
    )
    monkeypatch.setattr(
        feishu_handler.FeishuResponseCollector,
        "upload_and_send_files",
        _no_op_collector_method,
    )

    handler = feishu_handler.create_feishu_message_handler(fake_manager, default_agent="fast")

    await handler(
        user_id="user-1",
        sender_id="sender-1",
        chat_id="chat-1",
        content="hello",
        metadata={"instance_id": "instance-1"},
    )

    assert fake_project_storage.created_names == [("user-1", "Feishu Channel")]
    assert fake_channel_storage.cleared_configs
    assert fake_task_manager.submit_calls[0]["project_id"] == "project-from-channel-name"


@pytest.mark.asyncio
async def test_feishu_handler_applies_channel_persona_preset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_task_manager = _FakeTaskManager()
    fake_manager = _FakeManager()
    fake_session_manager = _FakeSessionManager()

    async def _fake_execute_feishu_agent(**kwargs: Any):
        yield {"event": "done", "data": {}}

    async def _no_op_process_events(**kwargs: Any) -> None:
        return None

    async def _no_op_collector_method(self) -> None:
        return None

    monkeypatch.setattr(
        feishu_handler,
        "_get_feishu_session_id",
        lambda chat_id: _async_return(f"feishu_{chat_id}"),
    )
    _install_fake_task_manager_module(monkeypatch, fake_task_manager)
    monkeypatch.setattr(
        "src.infra.channel.channel_storage.ChannelStorage",
        lambda: _FakePersonaChannelStorage(),
    )
    monkeypatch.setattr(
        "src.infra.persona_preset.manager.PersonaPresetManager",
        lambda: _FakePersonaPresetManager(),
    )
    monkeypatch.setattr(
        "src.infra.session.manager.SessionManager",
        lambda: fake_session_manager,
    )
    monkeypatch.setattr(feishu_handler, "execute_feishu_agent", _fake_execute_feishu_agent)
    monkeypatch.setattr(feishu_handler, "_process_events", _no_op_process_events)
    monkeypatch.setattr(
        feishu_handler.FeishuResponseCollector,
        "stop_processing_indicator",
        _no_op_collector_method,
    )
    monkeypatch.setattr(
        feishu_handler.FeishuResponseCollector,
        "send_card_message",
        _no_op_collector_method,
    )
    monkeypatch.setattr(
        feishu_handler.FeishuResponseCollector,
        "upload_and_send_files",
        _no_op_collector_method,
    )

    handler = feishu_handler.create_feishu_message_handler(fake_manager, default_agent="fast")

    await handler(
        user_id="user-1",
        sender_id="sender-1",
        chat_id="chat-1",
        content="hello",
        metadata={"instance_id": "instance-1"},
    )

    submit_call = fake_task_manager.submit_calls[0]
    assert submit_call["agent_options"] == {"model_id": "model-1"}
    assert submit_call["enabled_skills"] == ["planning"]
    assert submit_call["persona_system_prompt"] == "Plan first."
    session_id, session_update = fake_session_manager.updates[0]
    metadata = session_update.metadata
    assert session_id == "feishu_chat-1"
    assert metadata["persona_preset_id"] == "persona-1"
    assert metadata["persona_preset_name"] == "Planner"
    assert metadata["persona_avatar"] == "icon:brain"
    assert metadata["persona_snapshot"]["system_prompt"] == "Plan first."
    assert metadata["enabled_skills"] == ["planning"]


@pytest.mark.asyncio
async def test_feishu_handler_passes_channel_team_id_to_team_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_task_manager = _FakeTaskManager()
    fake_manager = _FakeManager()
    fake_session_manager = _FakeSessionManager()

    async def _fake_execute_feishu_agent(**kwargs: Any):
        yield {"event": "done", "data": {}}

    async def _no_op_process_events(**kwargs: Any) -> None:
        return None

    async def _no_op_collector_method(self) -> None:
        return None

    monkeypatch.setattr(
        feishu_handler,
        "_get_feishu_session_id",
        lambda chat_id: _async_return(f"feishu_{chat_id}"),
    )
    _install_fake_task_manager_module(monkeypatch, fake_task_manager)
    monkeypatch.setattr(
        "src.infra.channel.channel_storage.ChannelStorage",
        lambda: _FakeTeamChannelStorage(),
    )
    monkeypatch.setattr(
        "src.infra.persona_preset.manager.PersonaPresetManager",
        lambda: _FakePersonaPresetManager(),
    )
    monkeypatch.setattr(
        "src.infra.session.manager.SessionManager",
        lambda: fake_session_manager,
    )
    monkeypatch.setattr(feishu_handler, "execute_feishu_agent", _fake_execute_feishu_agent)
    monkeypatch.setattr(feishu_handler, "_process_events", _no_op_process_events)
    monkeypatch.setattr(
        feishu_handler.FeishuResponseCollector,
        "stop_processing_indicator",
        _no_op_collector_method,
    )
    monkeypatch.setattr(
        feishu_handler.FeishuResponseCollector,
        "send_card_message",
        _no_op_collector_method,
    )
    monkeypatch.setattr(
        feishu_handler.FeishuResponseCollector,
        "upload_and_send_files",
        _no_op_collector_method,
    )

    handler = feishu_handler.create_feishu_message_handler(fake_manager, default_agent="fast")

    await handler(
        user_id="user-1",
        sender_id="sender-1",
        chat_id="chat-1",
        content="hello",
        metadata={"instance_id": "instance-1"},
    )

    submit_call = fake_task_manager.submit_calls[0]
    assert submit_call["agent_id"] == "team"
    assert submit_call["team_id"] == "team-channel-1"
    assert submit_call["persona_system_prompt"] is None
    assert submit_call["enabled_skills"] is None
    assert fake_session_manager.updates == []


@pytest.mark.asyncio
async def test_feishu_handler_prefers_plugin_option_team_id_for_team_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_task_manager = _FakeTaskManager()
    fake_manager = _FakeManager()

    async def _fake_execute_feishu_agent(**kwargs: Any):
        yield {"event": "done", "data": {}}

    async def _no_op_process_events(**kwargs: Any) -> None:
        return None

    async def _no_op_collector_method(self) -> None:
        return None

    monkeypatch.setattr(
        feishu_handler,
        "_get_feishu_session_id",
        lambda chat_id: _async_return(f"feishu_{chat_id}"),
    )
    _install_fake_task_manager_module(monkeypatch, fake_task_manager)
    monkeypatch.setattr(
        "src.infra.channel.channel_storage.ChannelStorage",
        lambda: _FakePluginOptionTeamChannelStorage(),
    )
    monkeypatch.setattr(feishu_handler, "execute_feishu_agent", _fake_execute_feishu_agent)
    monkeypatch.setattr(feishu_handler, "_process_events", _no_op_process_events)
    monkeypatch.setattr(
        feishu_handler.FeishuResponseCollector,
        "stop_processing_indicator",
        _no_op_collector_method,
    )
    monkeypatch.setattr(
        feishu_handler.FeishuResponseCollector,
        "send_card_message",
        _no_op_collector_method,
    )
    monkeypatch.setattr(
        feishu_handler.FeishuResponseCollector,
        "upload_and_send_files",
        _no_op_collector_method,
    )

    handler = feishu_handler.create_feishu_message_handler(fake_manager, default_agent="fast")

    await handler(
        user_id="user-1",
        sender_id="sender-1",
        chat_id="chat-1",
        content="hello",
        metadata={"instance_id": "instance-1"},
    )

    submit_call = fake_task_manager.submit_calls[0]
    assert submit_call["agent_id"] == "team"
    assert submit_call["team_id"] == "plugin-option-team"


@pytest.mark.asyncio
async def test_feishu_handler_rejects_disabled_plugin_owned_team_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.agents import set_plugin_runtime

    fake_task_manager = _FakeTaskManager()
    fake_manager = _FakeManager()
    runtime = PluginRuntime([build_agent_team_plugin_manifest()])
    runtime.disable_plugin("agent_team")
    set_plugin_runtime(runtime)

    async def _unexpected_execute_feishu_agent(**kwargs: Any):
        raise AssertionError("disabled plugin-owned agent should not execute")
        if False:
            yield None

    monkeypatch.setattr(
        feishu_handler,
        "_get_feishu_session_id",
        lambda chat_id: _async_return(f"feishu_{chat_id}"),
    )
    _install_fake_task_manager_module(monkeypatch, fake_task_manager)
    monkeypatch.setattr(
        "src.infra.channel.channel_storage.ChannelStorage",
        lambda: _FakeTeamChannelStorage(),
    )
    monkeypatch.setattr(feishu_handler, "execute_feishu_agent", _unexpected_execute_feishu_agent)

    handler = feishu_handler.create_feishu_message_handler(
        fake_manager,
        default_agent="fast",
        plugin_runtime=runtime,
    )

    try:
        await handler(
            user_id="user-1",
            sender_id="sender-1",
            chat_id="chat-1",
            content="hello",
            metadata={"instance_id": "instance-1"},
        )
    finally:
        set_plugin_runtime(None)

    assert fake_task_manager.submit_calls == []
    assert len(fake_manager.sent_messages) == 1
    user_id, chat_id, content = fake_manager.sent_messages[0]
    assert (user_id, chat_id) == ("user-1", "chat-1")
    assert "agent_team" in content


@pytest.mark.asyncio
async def test_feishu_handler_deletes_received_reaction_when_processing_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_task_manager = _FakeTaskManager()
    fake_manager = _FakeReactionManager()

    async def _fake_execute_feishu_agent(**kwargs: Any):
        yield {"event": "done", "data": {}}

    async def _no_op_process_events(**kwargs: Any) -> None:
        return None

    class _CaptureCollector:
        def __init__(self, **_kwargs: Any) -> None:
            return None

        async def finalize_stream_message(self) -> bool:
            return False

        async def send_card_message(self) -> bool:
            return True

        async def upload_and_send_files(self) -> None:
            return None

    monkeypatch.setattr(
        feishu_handler,
        "_get_feishu_session_id",
        lambda chat_id: _async_return(f"feishu_{chat_id}"),
    )
    _install_fake_task_manager_module(monkeypatch, fake_task_manager)
    monkeypatch.setattr(feishu_handler, "execute_feishu_agent", _fake_execute_feishu_agent)
    monkeypatch.setattr(feishu_handler, "_process_events", _no_op_process_events)
    monkeypatch.setattr(feishu_handler, "FeishuResponseCollector", _CaptureCollector)

    handler = feishu_handler.create_feishu_message_handler(fake_manager, default_agent="search")

    await handler(
        user_id="user-1",
        sender_id="ou_sender",
        chat_id="oc_chat",
        content="hello",
        metadata={
            "message_id": "om_original",
            "reaction_id": "reaction-1",
            "instance_id": "instance-1",
        },
    )

    assert fake_manager.delete_calls == [("user-1", "om_original", "reaction-1")]


@pytest.mark.asyncio
async def test_feishu_handler_uses_event_chat_id_for_p2p_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_task_manager = _FakeTaskManager()
    fake_manager = _FakeManager()
    captured_collector: dict[str, Any] = {}

    async def _fake_execute_feishu_agent(**kwargs: Any):
        yield {"event": "done", "data": {}}

    async def _no_op_process_events(**kwargs: Any) -> None:
        return None

    class _CaptureCollector:
        def __init__(self, **kwargs: Any) -> None:
            captured_collector.update(kwargs)

        async def start_processing_indicator(self, message_id: str) -> None:
            return None

        async def stop_processing_indicator(self) -> None:
            return None

        async def finalize_stream_message(self) -> bool:
            return False

        async def send_card_message(self) -> bool:
            return True

        async def upload_and_send_files(self) -> None:
            return None

    monkeypatch.setattr(
        feishu_handler,
        "_get_feishu_session_id",
        lambda chat_id: _async_return(f"feishu_{chat_id}"),
    )
    _install_fake_task_manager_module(monkeypatch, fake_task_manager)
    monkeypatch.setattr(feishu_handler, "execute_feishu_agent", _fake_execute_feishu_agent)
    monkeypatch.setattr(feishu_handler, "_process_events", _no_op_process_events)
    monkeypatch.setattr(feishu_handler, "FeishuResponseCollector", _CaptureCollector)

    handler = feishu_handler.create_feishu_message_handler(fake_manager, default_agent="search")

    await handler(
        user_id="user-1",
        sender_id="ou_sender",
        chat_id="ou_sender",
        content="hello",
        metadata={
            "message_id": "om_original",
            "chat_type": "p2p",
            "reply_chat_id": "oc_p2p_chat",
        },
    )

    assert fake_task_manager.submit_calls[0]["session_id"] == "feishu_ou_sender"
    assert captured_collector["chat_id"] == "oc_p2p_chat"
    assert captured_collector["reply_to_message_id"] == "om_original"


@pytest.mark.asyncio
async def test_feishu_handler_does_not_add_processing_indicator_reaction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_task_manager = _FakeTaskManager()
    fake_manager = _FakeManager()
    processing_calls: list[str] = []

    async def _fake_execute_feishu_agent(**kwargs: Any):
        yield {"event": "done", "data": {}}

    async def _no_op_process_events(**kwargs: Any) -> None:
        return None

    class _CaptureCollector:
        def __init__(self, **_kwargs: Any) -> None:
            return None

        async def start_processing_indicator(self, message_id: str) -> None:
            processing_calls.append(message_id)

        async def stop_processing_indicator(self) -> None:
            return None

        async def finalize_stream_message(self) -> bool:
            return False

        async def send_card_message(self) -> bool:
            return True

        async def upload_and_send_files(self) -> None:
            return None

    monkeypatch.setattr(
        feishu_handler,
        "_get_feishu_session_id",
        lambda chat_id: _async_return(f"feishu_{chat_id}"),
    )
    _install_fake_task_manager_module(monkeypatch, fake_task_manager)
    monkeypatch.setattr(feishu_handler, "execute_feishu_agent", _fake_execute_feishu_agent)
    monkeypatch.setattr(feishu_handler, "_process_events", _no_op_process_events)
    monkeypatch.setattr(feishu_handler, "FeishuResponseCollector", _CaptureCollector)

    handler = feishu_handler.create_feishu_message_handler(fake_manager, default_agent="search")

    await handler(
        user_id="user-1",
        sender_id="ou_sender",
        chat_id="oc_chat",
        content="hello",
        metadata={
            "message_id": "om_original",
            "chat_type": "group",
            "sender_id": "ou_sender",
        },
    )

    assert processing_calls == []


async def _async_return(value: Any) -> Any:
    return value


@pytest.mark.asyncio
async def test_feishu_processing_indicator_adds_once_and_removes_on_stop() -> None:
    manager = _FakeReactionManager()
    collector = feishu_handler.FeishuResponseCollector(
        manager=manager,
        user_id="user-1",
        chat_id="chat-1",
    )

    await collector.start_processing_indicator("message-1")
    await collector.start_processing_indicator("message-1")
    await collector.stop_processing_indicator()
    await collector.stop_processing_indicator()

    assert manager.add_calls == [("user-1", "message-1", "StatusInFlight")]
    assert manager.delete_calls == [("user-1", "message-1", "reaction-1")]


@pytest.mark.asyncio
async def test_feishu_collector_streams_chunks_and_finalizes_card() -> None:
    client = _FakeStreamingClient()
    collector = feishu_handler.FeishuResponseCollector(
        manager=_FakeStreamingManager(client),
        user_id="user-1",
        chat_id="oc_chat",
        reply_to_message_id="original-message",
        stream_reply=True,
    )
    collector.set_session_link("session-1", "run-1")

    await collector.append_stream_chunk("hello")
    await asyncio.sleep(0)
    await collector.append_stream_chunk(" world")
    await asyncio.sleep(feishu_handler.FEISHU_STREAM_UPDATE_DEBOUNCE_SECONDS + 0.05)

    assert client.created == 1
    assert client.initial_texts == ["hello"]
    assert client.sent == [("oc_chat", "card-1", "original-message")]
    assert client.updates == [("card-1", "hello world", 1)]

    assert await collector.finalize_stream_message() is True
    assert client.finalized == [
        ("card-1", "hello world\n\n[查看这条消息](/chat/session-1?run_id=run-1)", 2)
    ]


@pytest.mark.asyncio
async def test_feishu_collector_appends_session_link_to_card_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent_cards: list[str] = []

    class _FakeCardClient:
        async def send_card_message(
            self,
            chat_id: str,
            card_content: str,
            reply_to_id: str | None = None,
        ) -> bool:
            sent_cards.append(card_content)
            return True

    monkeypatch.setattr(feishu_handler.settings, "APP_BASE_URL", "https://app.example.com")

    collector = feishu_handler.FeishuResponseCollector(
        manager=_FakeStreamingManager(_FakeCardClient()),
        user_id="user-1",
        chat_id="oc_chat",
        stream_reply=False,
    )
    collector.append_text("hello")
    collector.set_session_link("feishu_oc_chat", "run-123")

    assert await collector.send_card_message() is True
    card = json.loads(sent_cards[0])
    markdown_contents = [
        element["content"]
        for element in card["elements"]
        if element.get("tag") == "markdown" and "content" in element
    ]
    assert (
        markdown_contents[-1]
        == "[查看这条消息](https://app.example.com/chat/feishu_oc_chat?run_id=run-123)"
    )


@pytest.mark.asyncio
async def test_feishu_collector_offloads_card_json_serialization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[Any, dict[str, Any]]] = []

    async def _fake_run_blocking_io(func, /, *args, **kwargs):
        calls.append((func, kwargs))
        return func(*args, **kwargs)

    monkeypatch.setattr(feishu_handler, "run_blocking_io", _fake_run_blocking_io)

    collector = feishu_handler.FeishuResponseCollector(
        manager=_FakeStreamingManager(_FakeStreamingClient()),
        user_id="user-1",
        chat_id="oc_chat",
        stream_reply=False,
    )
    collector.append_text("hello")

    card_json = await collector._build_card_content_async(_FakeStreamingClient())

    assert json.loads(card_json)["config"]["wide_screen_mode"] is True
    assert calls == [(json.dumps, {"ensure_ascii": False})]


@pytest.mark.asyncio
async def test_feishu_collector_splits_large_first_stream_update() -> None:
    client = _FakeStreamingClient()
    collector = feishu_handler.FeishuResponseCollector(
        manager=_FakeStreamingManager(client),
        user_id="user-1",
        chat_id="oc_chat",
        stream_reply=True,
    )

    first_chunk = "这是一段比较长的开头内容，应该先推很短的一小段"
    await collector.append_stream_chunk(first_chunk)
    await asyncio.sleep(feishu_handler.FEISHU_STREAM_UPDATE_DEBOUNCE_SECONDS + 0.05)

    assert client.initial_texts == [first_chunk[: feishu_handler.FEISHU_STREAM_FIRST_PAINT_CHARS]]
    assert client.updates == [("card-1", first_chunk, 1)]


@pytest.mark.asyncio
async def test_feishu_stream_updates_keep_only_latest_pending_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(feishu_handler, "FEISHU_STREAM_UPDATE_DEBOUNCE_SECONDS", 60)

    class _SlowStreamingClient(_FakeStreamingClient):
        def __init__(self) -> None:
            super().__init__()
            self.update_started = asyncio.Event()
            self.release_update = asyncio.Event()

        async def update_stream_card(self, card_id: str, content: str, sequence: int) -> bool:
            self.update_started.set()
            await self.release_update.wait()
            return await super().update_stream_card(card_id, content, sequence)

    client = _SlowStreamingClient()
    collector = feishu_handler.FeishuResponseCollector(
        manager=_FakeStreamingManager(client),
        user_id="user-1",
        chat_id="oc_chat",
        stream_reply=True,
    )

    await collector.append_stream_chunk("hello")
    await collector.append_stream_chunk(" world")
    await asyncio.wait_for(client.update_started.wait(), timeout=1)

    for index in range(20):
        await collector.append_stream_chunk(f" chunk-{index}")

    assert collector._stream_update_queue.qsize() <= 1

    client.release_update.set()
    await collector._cancel_stream_update_worker()


def test_feishu_stream_update_queue_has_hard_capacity_limit() -> None:
    collector = feishu_handler.FeishuResponseCollector(
        manager=_FakeStreamingManager(_FakeStreamingClient()),
        user_id="user-1",
        chat_id="oc_chat",
        stream_reply=True,
    )

    assert collector._stream_update_queue.maxsize == 1


@pytest.mark.asyncio
async def test_feishu_stream_update_queue_stores_signal_not_full_content() -> None:
    collector = feishu_handler.FeishuResponseCollector(
        manager=_FakeStreamingManager(_FakeStreamingClient()),
        user_id="user-1",
        chat_id="oc_chat",
        stream_reply=True,
    )
    collector._stream_card_id = "card-1"
    collector._ensure_stream_update_worker = lambda: None  # type: ignore[method-assign]

    await collector.append_stream_chunk("x" * 10_000)

    queued = collector._stream_update_queue.get_nowait()
    assert queued is not None
    assert not isinstance(queued, str)
    assert not hasattr(collector, "_stream_full_content")


@pytest.mark.asyncio
async def test_feishu_stream_update_avoids_joining_all_chunks_on_each_append(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(feishu_handler, "FEISHU_STREAM_UPDATE_DEBOUNCE_SECONDS", 60)

    class _SlowStreamingClient(_FakeStreamingClient):
        def __init__(self) -> None:
            super().__init__()
            self.update_started = asyncio.Event()
            self.release_update = asyncio.Event()

        async def update_stream_card(self, card_id: str, content: str, sequence: int) -> bool:
            self.update_started.set()
            await self.release_update.wait()
            return await super().update_stream_card(card_id, content, sequence)

    client = _SlowStreamingClient()
    collector = feishu_handler.FeishuResponseCollector(
        manager=_FakeStreamingManager(client),
        user_id="user-1",
        chat_id="oc_chat",
        stream_reply=True,
    )

    await collector.append_stream_chunk("hello")
    await collector.append_stream_chunk(" world")
    await asyncio.wait_for(client.update_started.wait(), timeout=1)

    collector.text_parts.insert(0, object())  # type: ignore[arg-type]
    await collector.append_stream_chunk(" latest")

    assert collector._stream_update_queue.qsize() <= 1

    client.release_update.set()
    await collector._cancel_stream_update_worker()


@pytest.mark.asyncio
async def test_feishu_collector_falls_back_when_stream_card_creation_fails() -> None:
    class _FailingClient(_FakeStreamingClient):
        async def create_stream_card(self, initial_text: str = "...") -> None:
            self.created += 1
            return None

    client = _FailingClient()
    collector = feishu_handler.FeishuResponseCollector(
        manager=_FakeStreamingManager(client),
        user_id="user-1",
        chat_id="oc_chat",
        stream_reply=True,
    )

    await collector.append_stream_chunk("hello")

    assert collector.text_parts == ["hello"]
    assert await collector.finalize_stream_message() is False
    assert client.sent == []


@pytest.mark.asyncio
async def test_upload_and_send_files_replies_to_original_message_and_skips_sent_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeFileClient()
    collector = feishu_handler.FeishuResponseCollector(
        manager=_FakeStreamingManager(client),
        user_id="user-1",
        chat_id="oc_chat",
        reply_to_message_id="om_original",
    )
    collector.add_file_to_reveal({"key": "revealed_files/doc.md", "name": "doc.md"})

    class _FakeBackend:
        download_called = False

        async def download_stream(self, key: str, chunk_size: int = 1024 * 1024):
            yield b"file-"
            yield b"bytes"

        async def download(self, key: str) -> bytes:
            self.download_called = True
            raise AssertionError("download_stream should be used for Feishu reveal files")

    class _FakeStorage:
        def __init__(self) -> None:
            self.backend = _FakeBackend()

        def _get_backend(self) -> _FakeBackend:
            return self.backend

    fake_storage = _FakeStorage()

    async def _fake_get_storage() -> _FakeStorage:
        return fake_storage

    monkeypatch.setattr(
        "src.infra.storage.s3.service.get_or_init_storage",
        _fake_get_storage,
    )

    await collector.upload_and_send_files()
    await collector.upload_and_send_files()

    assert client.uploads == []
    assert client.file_uploads == [(client.file_uploads[0][0], "doc.md")]
    assert fake_storage.backend.download_called is False
    assert client.sent_files == [
        ("oc_chat", "feishu-doc.md", "doc.md", "om_original"),
    ]


@pytest.mark.asyncio
async def test_upload_and_send_files_sends_images_as_native_feishu_images(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeFileClient()
    collector = feishu_handler.FeishuResponseCollector(
        manager=_FakeStreamingManager(client),
        user_id="user-1",
        chat_id="oc_chat",
        reply_to_message_id="om_original",
    )
    collector.add_file_to_reveal(
        {
            "key": "generated-images/user-1/cat.png",
            "name": "cat.png",
            "type": "image",
            "mime_type": "image/png",
        }
    )

    class _FakeBackend:
        download_called = False

        async def download_stream(self, key: str, chunk_size: int = 1024 * 1024):
            yield b"image-"
            yield b"bytes"

        async def download(self, key: str) -> bytes:
            self.download_called = True
            raise AssertionError("download_stream should be used for Feishu reveal images")

    class _FakeStorage:
        def __init__(self) -> None:
            self.backend = _FakeBackend()

        def _get_backend(self) -> _FakeBackend:
            return self.backend

    fake_storage = _FakeStorage()

    async def _fake_get_storage() -> _FakeStorage:
        return fake_storage

    monkeypatch.setattr(
        "src.infra.storage.s3.service.get_or_init_storage",
        _fake_get_storage,
    )

    await collector.upload_and_send_files()
    await collector.upload_and_send_files()

    assert client.uploads == []
    assert client.sent_files == []
    assert client.image_uploads == []
    assert client.image_file_uploads == [(client.image_file_uploads[0][0], b"image-bytes")]
    assert fake_storage.backend.download_called is False
    assert client.sent_images == [("oc_chat", "feishu-image-key", "om_original")]


@pytest.mark.asyncio
async def test_upload_image_from_uri_streams_storage_object_to_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeFileClient()
    collector = feishu_handler.FeishuResponseCollector(
        manager=_FakeStreamingManager(client),
        user_id="user-1",
        chat_id="oc_chat",
    )

    class _FakeBackend:
        download_called = False

        async def download_stream(self, key: str, chunk_size: int = 1024 * 1024):
            assert key == "generated-images/user-1/cat.png"
            yield b"cat-"
            yield b"image"

        async def download(self, key: str) -> bytes:
            self.download_called = True
            raise AssertionError("send:// images should be streamed from storage")

    class _FakeStorage:
        def __init__(self) -> None:
            self.backend = _FakeBackend()

        def _get_backend(self) -> _FakeBackend:
            return self.backend

    fake_storage = _FakeStorage()

    async def _fake_get_storage() -> _FakeStorage:
        return fake_storage

    monkeypatch.setattr(
        "src.infra.storage.s3.service.get_or_init_storage",
        _fake_get_storage,
    )

    image_key = await collector._upload_image_from_uri("send://generated-images/user-1/cat.png")

    assert image_key == "feishu-image-key"
    assert client.image_uploads == []
    assert client.image_file_uploads == [(client.image_file_uploads[0][0], b"cat-image")]
    assert fake_storage.backend.download_called is False


@pytest.mark.asyncio
async def test_download_storage_object_rejects_large_legacy_bytes_download(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _LegacyBytesBackend:
        async def download(self, key: str) -> bytes:
            assert key == "revealed_files/large.bin"
            return b"x" * 16

    monkeypatch.setattr(
        feishu_handler,
        "FEISHU_REVEAL_LEGACY_DOWNLOAD_MAX_BYTES",
        8,
        raising=False,
    )

    target = tmp_path / "large.bin"
    with target.open("w+b") as file:
        with pytest.raises(ValueError, match="too large"):
            await feishu_handler._download_storage_object_to_file(
                _LegacyBytesBackend(),
                "revealed_files/large.bin",
                file,
            )

        file.seek(0)
        assert file.read() == b""


@pytest.mark.asyncio
async def test_download_storage_object_rejects_known_large_object_before_streaming(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _SizedBackend:
        download_called = False

        async def get_size(self, key: str) -> int:
            assert key == "revealed_files/large.bin"
            return 9

        async def download_to_file(self, key: str, file, chunk_size: int = 1024 * 1024):
            self.download_called = True
            raise AssertionError("known oversized object should not be downloaded")

    monkeypatch.setattr(
        feishu_handler,
        "FEISHU_REVEAL_DOWNLOAD_MAX_BYTES",
        8,
        raising=False,
    )

    backend = _SizedBackend()
    target = tmp_path / "large.bin"
    with target.open("w+b") as file:
        with pytest.raises(ValueError, match="too large"):
            await feishu_handler._download_storage_object_to_file(
                backend,
                "revealed_files/large.bin",
                file,
            )

        file.seek(0)
        assert file.read() == b""
    assert backend.download_called is False


@pytest.mark.asyncio
async def test_download_storage_object_stops_stream_before_writing_oversized_chunk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeStreamBackend:
        async def download_stream(self, key: str, chunk_size: int = 1024 * 1024):
            assert key == "revealed_files/large.bin"
            yield b"1234"
            yield b"56789"

    class _RecordingFile:
        def __init__(self) -> None:
            self.data = bytearray()

        def write(self, chunk: bytes) -> int:
            self.data.extend(chunk)
            return len(chunk)

        def seek(self, position: int) -> int:
            del position
            return 0

    monkeypatch.setattr(
        feishu_handler,
        "FEISHU_REVEAL_DOWNLOAD_MAX_BYTES",
        8,
        raising=False,
    )

    target = _RecordingFile()
    with pytest.raises(ValueError, match="too large"):
        await feishu_handler._download_storage_object_to_file(
            _FakeStreamBackend(),
            "revealed_files/large.bin",
            target,
        )

    assert bytes(target.data) == b"1234"


@pytest.mark.asyncio
async def test_download_storage_object_offloads_stream_file_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeStreamBackend:
        async def download_stream(self, key: str, chunk_size: int = 1024 * 1024):
            assert key == "revealed_files/report.txt"
            yield b"part-1"
            yield b"part-2"

    class _RecordingFile:
        def __init__(self) -> None:
            self.data = bytearray()
            self.position = 0

        def write(self, chunk: bytes) -> int:
            self.data.extend(chunk)
            self.position += len(chunk)
            return len(chunk)

        def seek(self, position: int) -> int:
            self.position = position
            return position

    calls: list[tuple[str, tuple[Any, ...]]] = []

    async def _fake_run_blocking_io(func, /, *args, **kwargs):
        calls.append((getattr(func, "__name__", repr(func)), args))
        return func(*args, **kwargs)

    monkeypatch.setattr(
        feishu_handler,
        "run_blocking_io",
        _fake_run_blocking_io,
        raising=False,
    )

    target = _RecordingFile()
    size = await feishu_handler._download_storage_object_to_file(
        _FakeStreamBackend(),
        "revealed_files/report.txt",
        target,
    )

    assert size == len(b"part-1part-2")
    assert bytes(target.data) == b"part-1part-2"
    assert calls == [
        ("write", (b"part-1",)),
        ("write", (b"part-2",)),
        ("seek", (0,)),
    ]


@pytest.mark.asyncio
async def test_upload_image_from_uri_requires_file_upload_api(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeImageBytesOnlyClient()
    collector = feishu_handler.FeishuResponseCollector(
        manager=_FakeStreamingManager(client),
        user_id="user-1",
        chat_id="oc_chat",
    )

    class _FakeBackend:
        async def download_stream(self, key: str, chunk_size: int = 1024 * 1024):
            yield b"cat-image"

    class _FakeStorage:
        def __init__(self) -> None:
            self.backend = _FakeBackend()

        def _get_backend(self) -> _FakeBackend:
            return self.backend

    async def _fake_get_storage() -> _FakeStorage:
        return _FakeStorage()

    monkeypatch.setattr(
        "src.infra.storage.s3.service.get_or_init_storage",
        _fake_get_storage,
    )

    image_key = await collector._upload_image_from_uri("send://generated-images/user-1/cat.png")

    assert image_key is None
    assert client.image_uploads == []


@pytest.mark.asyncio
async def test_process_events_sends_approval_card_and_updates_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = [
        {
            "event_type": feishu_handler.EVENT_MESSAGE_CHUNK,
            "data": {"content": "我需要确认"},
        },
        {
            "event_type": "approval_required",
            "data": {
                "id": "approval-1",
                "message": "Please confirm creation of this scheduled task.",
                "type": "confirm",
                "fields": [],
                "timeout": 300,
            },
        },
        {
            "event_type": feishu_handler.EVENT_TOOL_RESULT,
            "data": {
                "tool": "scheduled_task_create",
                "result": json.dumps({"approval_id": "approval-1", "status": "approved"}),
            },
        },
        {"event_type": "done", "data": {}},
    ]

    class _FakeDualWriter:
        async def read_from_redis(self, session_id: str, run_id: str):
            for event in events:
                yield event

    monkeypatch.setattr(
        "src.infra.session.dual_writer.get_dual_writer",
        lambda: _FakeDualWriter(),
    )

    manager = _FakeManager()
    client = _FakeStreamingClient()
    manager._find_channel = lambda user_id, instance_id=None: client  # type: ignore[attr-defined]
    collector = feishu_handler.FeishuResponseCollector(
        manager=manager,  # type: ignore[arg-type]
        user_id="user-1",
        chat_id="oc_chat",
        reply_to_message_id="om_original",
    )
    collector.set_session_link("session-1", "run-1")

    await feishu_handler._process_events(
        collector=collector,
        session_id="session-1",
        run_id="run-1",
        show_tools=True,
    )

    assert len(manager.sent_cards) == 1
    sent_card = json.loads(manager.sent_cards[0][2])
    action_buttons = sent_card["elements"][-1]["actions"]
    values = [button.get("value") for button in action_buttons if "value" in button]
    assert values == [
        {
            "action": feishu_handler.FEISHU_APPROVAL_ACTION,
            "approval_id": "approval-1",
            "approved": True,
        },
        {
            "action": feishu_handler.FEISHU_APPROVAL_ACTION,
            "approval_id": "approval-1",
            "approved": False,
        },
    ]
    assert client.patched_cards
    patched = json.loads(client.patched_cards[0][1])
    assert "已确认" in patched["elements"][2]["content"]
    assert collector._stream_status_text is None


@pytest.mark.asyncio
async def test_process_events_refreshes_status_when_tool_result_omits_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A tool result that carries an approval_id but omits its outcome must not
    revert an already-resolved card back to pending — the handler refreshes the
    authoritative status from the approval record instead."""
    events = [
        {
            "event_type": "approval_required",
            "data": {
                "id": "approval-1",
                "message": "Please confirm creation of this scheduled task.",
                "type": "confirm",
                "fields": [],
                "timeout": 300,
            },
        },
        {
            "event_type": feishu_handler.EVENT_TOOL_RESULT,
            "data": {
                "tool": "scheduled_task_create",
                # approval_id present, status/approved omitted → extracts to
                # "pending" without the defensive fallback.
                "result": json.dumps({"approval_id": "approval-1"}),
            },
        },
        {"event_type": "done", "data": {}},
    ]

    class _FakeDualWriter:
        async def read_from_redis(self, session_id: str, run_id: str):
            for event in events:
                yield event

    monkeypatch.setattr(
        "src.infra.session.dual_writer.get_dual_writer",
        lambda: _FakeDualWriter(),
    )

    async def fake_existing_status(approval_id: str) -> str:
        assert approval_id == "approval-1"
        return "approved"

    monkeypatch.setattr(feishu_handler, "_get_existing_approval_status", fake_existing_status)

    manager = _FakeManager()
    client = _FakeStreamingClient()
    manager._find_channel = lambda user_id, instance_id=None: client  # type: ignore[attr-defined]
    collector = feishu_handler.FeishuResponseCollector(
        manager=manager,  # type: ignore[arg-type]
        user_id="user-1",
        chat_id="oc_chat",
        reply_to_message_id="om_original",
    )
    collector.set_session_link("session-1", "run-1")

    await feishu_handler._process_events(
        collector=collector,
        session_id="session-1",
        run_id="run-1",
        show_tools=True,
    )

    assert client.patched_cards
    patched = json.loads(client.patched_cards[0][1])
    assert "已确认" in patched["elements"][2]["content"]
    assert "等待确认" not in patched["elements"][2]["content"]


@pytest.mark.asyncio
async def test_process_events_sends_one_approval_card_for_duplicate_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    approval_event = {
        "event_type": "approval_required",
        "data": {
            "id": "approval-1",
            "message": "Please confirm creation of this scheduled task.",
            "type": "confirm",
            "fields": [],
            "timeout": 300,
        },
    }
    events = [
        approval_event,
        approval_event,
        {"event_type": "done", "data": {}},
    ]

    class _FakeDualWriter:
        async def read_from_redis(self, session_id: str, run_id: str):
            for event in events:
                yield event

    monkeypatch.setattr(
        "src.infra.session.dual_writer.get_dual_writer",
        lambda: _FakeDualWriter(),
    )

    manager = _FakeManager()
    collector = feishu_handler.FeishuResponseCollector(
        manager=manager,  # type: ignore[arg-type]
        user_id="user-1",
        chat_id="oc_chat",
        reply_to_message_id="om_original",
    )

    await feishu_handler._process_events(
        collector=collector,
        session_id="session-1",
        run_id="run-1",
        show_tools=True,
    )

    assert len(manager.sent_cards) == 1


@pytest.mark.asyncio
async def test_feishu_approval_action_responds_and_patches_card(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[str, bool, str]] = []

    async def fake_respond_to_approval(
        approval_id: str, *, approved: bool, response: str = "{}"
    ) -> dict[str, Any]:
        calls.append((approval_id, approved, response))
        return {"status": "success"}

    async def fake_respond_helper(approval_id: str, *, approved: bool) -> None:
        await fake_respond_to_approval(approval_id, approved=approved, response="{}")

    async def fake_claim(approval_id: str) -> bool:
        assert approval_id == "approval-1"
        return True

    monkeypatch.setattr(feishu_handler, "_respond_to_human_approval", fake_respond_helper)
    monkeypatch.setattr(feishu_handler, "_claim_feishu_approval_action", fake_claim)

    client = _FakeStreamingClient()
    manager = _FakeStreamingManager(client)

    handled = await feishu_handler.handle_feishu_approval_action(
        value={
            "action": feishu_handler.FEISHU_APPROVAL_ACTION,
            "approval_id": "approval-1",
            "approved": True,
        },
        message_id="om_card",
        user_id="user-1",
        manager=manager,  # type: ignore[arg-type]
    )

    assert handled is True
    assert calls == [("approval-1", True, "{}")]
    assert client.patched_cards
    patched = json.loads(client.patched_cards[0][1])
    assert "已确认" in patched["elements"][2]["content"]


@pytest.mark.asyncio
async def test_feishu_approval_action_is_idempotent_for_already_handled_clicks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from fastapi import HTTPException

    async def fake_respond_to_approval(
        approval_id: str, *, approved: bool, response: str = "{}"
    ) -> dict[str, Any]:
        raise HTTPException(status_code=400, detail="审批请求已处理")

    async def fake_existing_status(approval_id: str) -> str:
        assert approval_id == "approval-1"
        return "approved"

    async def fake_respond_helper(approval_id: str, *, approved: bool) -> None:
        await fake_respond_to_approval(approval_id, approved=approved, response="{}")

    async def fake_claim(approval_id: str) -> bool:
        assert approval_id == "approval-1"
        return True

    monkeypatch.setattr(feishu_handler, "_respond_to_human_approval", fake_respond_helper)
    monkeypatch.setattr(feishu_handler, "_claim_feishu_approval_action", fake_claim)
    monkeypatch.setattr(feishu_handler, "_get_existing_approval_status", fake_existing_status)

    client = _FakeStreamingClient()
    manager = _FakeStreamingManager(client)

    handled = await feishu_handler.handle_feishu_approval_action(
        value={
            "action": feishu_handler.FEISHU_APPROVAL_ACTION,
            "approval_id": "approval-1",
            "approved": True,
        },
        message_id="om_card",
        user_id="user-1",
        manager=manager,  # type: ignore[arg-type]
    )

    assert handled is True
    assert client.patched_cards
    patched = json.loads(client.patched_cards[0][1])
    assert "已确认" in patched["elements"][2]["content"]
    assert "处理失败" not in patched["elements"][2]["content"]


@pytest.mark.asyncio
async def test_feishu_approval_action_dedupes_repeated_clicks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def fake_claim(approval_id: str) -> bool:
        calls.append(f"claim:{approval_id}")
        return len([call for call in calls if call.startswith("claim:")]) == 1

    async def fake_existing_status(approval_id: str) -> str:
        calls.append(f"status:{approval_id}")
        return "approved"

    async def fake_respond_to_approval(
        approval_id: str, *, approved: bool, response: str = "{}"
    ) -> dict[str, Any]:
        calls.append(f"respond:{approval_id}:{approved}")
        return {"status": "success"}

    async def fake_respond_helper(approval_id: str, *, approved: bool) -> None:
        await fake_respond_to_approval(approval_id, approved=approved, response="{}")

    monkeypatch.setattr(feishu_handler, "_respond_to_human_approval", fake_respond_helper)
    monkeypatch.setattr(feishu_handler, "_claim_feishu_approval_action", fake_claim)
    monkeypatch.setattr(feishu_handler, "_get_existing_approval_status", fake_existing_status)

    client = _FakeStreamingClient()
    manager = _FakeStreamingManager(client)
    value = {
        "action": feishu_handler.FEISHU_APPROVAL_ACTION,
        "approval_id": "approval-1",
        "approved": True,
    }

    await feishu_handler.handle_feishu_approval_action(
        value=value,
        message_id="om_card",
        user_id="user-1",
        manager=manager,  # type: ignore[arg-type]
    )
    await feishu_handler.handle_feishu_approval_action(
        value=value,
        message_id="om_card",
        user_id="user-1",
        manager=manager,  # type: ignore[arg-type]
    )

    assert calls == [
        "claim:approval-1",
        "respond:approval-1:True",
        "claim:approval-1",
        "status:approval-1",
    ]


@pytest.mark.asyncio
async def test_process_events_uploads_revealed_file_when_tool_result_arrives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = [
        {
            "event_type": feishu_handler.EVENT_MESSAGE_CHUNK,
            "data": {"content": "before"},
        },
        {
            "event_type": feishu_handler.EVENT_TOOL_RESULT,
            "data": {
                "tool": "reveal_file",
                "result": {"key": "revealed_files/doc.md", "name": "doc.md"},
            },
        },
        {
            "event_type": feishu_handler.EVENT_MESSAGE_CHUNK,
            "data": {"content": "after"},
        },
        {"event_type": "done", "data": {}},
    ]

    class _FakeDualWriter:
        async def read_from_redis(self, session_id: str, run_id: str):
            for event in events:
                yield event

    class _CaptureCollector:
        def __init__(self) -> None:
            self.files_to_reveal: list[dict[str, Any]] = []
            self.calls: list[str] = []

        async def append_stream_chunk(self, chunk: str) -> None:
            self.calls.append(f"chunk:{chunk}")

        def add_tool(self, tool_name: str) -> None:
            self.calls.append(f"tool:{tool_name}")

        def add_file_to_reveal(self, file_info: dict) -> None:
            self.files_to_reveal.append(file_info)
            self.calls.append(f"add:{file_info['name']}")

        async def upload_and_send_files(self) -> None:
            names = ",".join(file["name"] for file in self.files_to_reveal)
            self.calls.append(f"upload:{names}")

    monkeypatch.setattr(
        "src.infra.session.dual_writer.get_dual_writer",
        lambda: _FakeDualWriter(),
    )

    collector = _CaptureCollector()
    await feishu_handler._process_events(
        collector=collector,
        session_id="session-1",
        run_id="run-1",
        show_tools=True,
    )

    assert collector.calls == [
        "chunk:before",
        "add:doc.md",
        "upload:doc.md",
        "chunk:after",
    ]


@pytest.mark.asyncio
async def test_process_events_offloads_reveal_file_result_json_parse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = [
        {
            "event_type": feishu_handler.EVENT_TOOL_RESULT,
            "data": {
                "tool": "reveal_file",
                "result": '{"key":"revealed_files/doc.md","name":"doc.md"}',
            },
        },
        {"event_type": "done", "data": {}},
    ]

    class _FakeDualWriter:
        async def read_from_redis(self, session_id: str, run_id: str):
            for event in events:
                yield event

    class _CaptureCollector:
        def __init__(self) -> None:
            self.files_to_reveal: list[dict[str, Any]] = []

        async def append_stream_chunk(self, chunk: str) -> None:
            raise AssertionError(f"unexpected chunk: {chunk}")

        def add_tool(self, tool_name: str) -> None:
            raise AssertionError(f"unexpected tool: {tool_name}")

        def add_file_to_reveal(self, file_info: dict) -> None:
            self.files_to_reveal.append(file_info)

        async def upload_and_send_files(self) -> None:
            return None

    calls: list[tuple[Any, tuple[Any, ...]]] = []

    async def _fake_run_blocking_io(func, /, *args, **kwargs):
        calls.append((func, args))
        return func(*args, **kwargs)

    monkeypatch.setattr(
        "src.infra.session.dual_writer.get_dual_writer",
        lambda: _FakeDualWriter(),
    )
    monkeypatch.setattr(feishu_handler, "run_blocking_io", _fake_run_blocking_io)

    collector = _CaptureCollector()
    await feishu_handler._process_events(
        collector=collector,
        session_id="session-1",
        run_id="run-1",
        show_tools=True,
    )

    assert collector.files_to_reveal == [{"key": "revealed_files/doc.md", "name": "doc.md"}]
    assert calls == [(json.loads, ('{"key":"revealed_files/doc.md","name":"doc.md"}',))]


@pytest.mark.asyncio
async def test_process_events_uploads_generated_images_when_tool_result_arrives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = [
        {
            "event_type": feishu_handler.EVENT_TOOL_RESULT,
            "data": {
                "tool": "image_generate",
                "result": {
                    "success": True,
                    "images": [
                        {
                            "url": "https://app.example.com/api/upload/file/generated-images/user-1/cat.png",
                            "key": "generated-images/user-1/cat.png",
                            "content_type": "image/png",
                        }
                    ],
                },
            },
        },
        {"event_type": "done", "data": {}},
    ]

    class _FakeDualWriter:
        async def read_from_redis(self, session_id: str, run_id: str):
            for event in events:
                yield event

    class _CaptureCollector:
        def __init__(self) -> None:
            self.files_to_reveal: list[dict[str, Any]] = []
            self.calls: list[str] = []

        async def append_stream_chunk(self, chunk: str) -> None:
            self.calls.append(f"chunk:{chunk}")

        def add_tool(self, tool_name: str) -> None:
            self.calls.append(f"tool:{tool_name}")

        def add_file_to_reveal(self, file_info: dict) -> None:
            self.files_to_reveal.append(file_info)
            self.calls.append(f"add:{file_info['name']}")

        async def upload_and_send_files(self) -> None:
            names = ",".join(file["name"] for file in self.files_to_reveal)
            self.calls.append(f"upload:{names}")

    monkeypatch.setattr(
        "src.infra.session.dual_writer.get_dual_writer",
        lambda: _FakeDualWriter(),
    )

    collector = _CaptureCollector()
    await feishu_handler._process_events(
        collector=collector,
        session_id="session-1",
        run_id="run-1",
        show_tools=True,
    )

    assert collector.files_to_reveal == [
        {
            "key": "generated-images/user-1/cat.png",
            "name": "cat.png",
            "type": "image",
            "mime_type": "image/png",
            "url": "https://app.example.com/api/upload/file/generated-images/user-1/cat.png",
        }
    ]
    assert collector.calls == ["add:cat.png", "upload:cat.png"]


@pytest.mark.asyncio
async def test_process_events_uploads_mcp_media_blocks_when_tool_result_arrives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = [
        {
            "event_type": feishu_handler.EVENT_TOOL_RESULT,
            "data": {
                "tool": "read_file",
                "result": {
                    "text": "",
                    "blocks": [
                        {
                            "type": "file",
                            "url": "/api/upload/file/tool_binaries/report.pdf",
                            "mime_type": "application/pdf",
                        },
                        {
                            "type": "image",
                            "url": "/api/upload/file/tool_binaries/chart.png",
                            "mime_type": "image/png",
                        },
                    ],
                },
            },
        },
        {"event_type": "done", "data": {}},
    ]

    class _FakeDualWriter:
        async def read_from_redis(self, session_id: str, run_id: str):
            for event in events:
                yield event

    class _CaptureCollector:
        def __init__(self) -> None:
            self.files_to_reveal: list[dict[str, Any]] = []
            self.calls: list[str] = []

        async def append_stream_chunk(self, chunk: str) -> None:
            self.calls.append(f"chunk:{chunk}")

        def add_tool(self, tool_name: str) -> None:
            self.calls.append(f"tool:{tool_name}")

        def add_file_to_reveal(self, file_info: dict) -> None:
            self.files_to_reveal.append(file_info)
            self.calls.append(f"add:{file_info['name']}")

        async def upload_and_send_files(self) -> None:
            names = ",".join(file["name"] for file in self.files_to_reveal)
            self.calls.append(f"upload:{names}")

    monkeypatch.setattr(
        "src.infra.session.dual_writer.get_dual_writer",
        lambda: _FakeDualWriter(),
    )

    collector = _CaptureCollector()
    await feishu_handler._process_events(
        collector=collector,
        session_id="session-1",
        run_id="run-1",
        show_tools=True,
    )

    assert collector.files_to_reveal == [
        {
            "key": "tool_binaries/report.pdf",
            "name": "report.pdf",
            "type": "document",
            "mime_type": "application/pdf",
            "url": "/api/upload/file/tool_binaries/report.pdf",
        },
        {
            "key": "tool_binaries/chart.png",
            "name": "chart.png",
            "type": "image",
            "mime_type": "image/png",
            "url": "/api/upload/file/tool_binaries/chart.png",
        },
    ]
    assert collector.calls == [
        "add:report.pdf",
        "upload:report.pdf",
        "add:chart.png",
        "upload:report.pdf,chart.png",
    ]
