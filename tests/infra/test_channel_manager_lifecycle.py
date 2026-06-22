from __future__ import annotations

from typing import Any

import pytest

from src.infra.channel.base import BaseChannel, UserChannelManager
from src.infra.channel.manager import ChannelCoordinator
from src.kernel.extensions import (
    PluginManifest,
    PluginRuntime,
    build_feishu_connector_plugin_manifest,
)
from src.kernel.schemas.channel import ChannelCapability, ChannelType


class _FakeChannel(BaseChannel):
    channel_type = ChannelType.FEISHU

    @classmethod
    def get_capabilities(cls) -> list[ChannelCapability]:
        return []

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return {}

    @classmethod
    def get_setup_guide(cls) -> list[str]:
        return []

    async def start(self) -> bool:
        return True

    async def stop(self) -> None:
        return None

    async def send_message(self, chat_id: str, content: str, **kwargs) -> bool:
        return True


class _FakeManager(UserChannelManager):
    channel_type = ChannelType.FEISHU
    config_class = object

    def __init__(self) -> None:
        super().__init__()
        self.stop_calls = 0

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        self.stop_calls += 1

    async def reload_user(self, user_id: str, instance_id: str | None = None) -> bool:
        return True

    def get_channel(self, user_id: str, instance_id: str | None = None):
        return _FakeChannel({})


@pytest.mark.asyncio
async def test_close_all_instances_stops_and_releases_channel_manager_singletons() -> None:
    UserChannelManager._instances.clear()
    manager = _FakeManager.get_instance()

    await UserChannelManager.close_all_instances()

    assert manager.stop_calls == 1
    assert UserChannelManager._instances == {}


@pytest.mark.asyncio
async def test_channel_coordinator_blocks_feishu_send_when_plugin_runtime_unavailable() -> None:
    coordinator = ChannelCoordinator()
    coordinator._managers[ChannelType.FEISHU] = _FakeManager()

    sent = await coordinator.send_message(
        "user-1",
        ChannelType.FEISHU,
        "chat-1",
        "hello",
        instance_id="bot-1",
    )

    assert sent is False


@pytest.mark.asyncio
async def test_channel_coordinator_blocks_feishu_send_when_connector_disabled() -> None:
    runtime = PluginRuntime([build_feishu_connector_plugin_manifest()])
    runtime.disable_plugin("feishu_connector")
    coordinator = ChannelCoordinator()
    coordinator.set_plugin_runtime(runtime)
    coordinator._managers[ChannelType.FEISHU] = _FakeManager()

    sent = await coordinator.send_message(
        "user-1",
        ChannelType.FEISHU,
        "chat-1",
        "hello",
        instance_id="bot-1",
    )

    assert sent is False


@pytest.mark.asyncio
async def test_channel_coordinator_uses_manifest_declared_connector_id() -> None:
    manifest = PluginManifest(
        id="alternate_feishu_connector",
        name="Alternate Feishu Connector",
        version="1.0.0",
        api_version="v1",
        frontend={
            "channel_connectors": [
                {
                    "id": "alternate_feishu_connector:feishu",
                    "channel_type": "feishu",
                }
            ]
        },
    )
    runtime = PluginRuntime([manifest])
    runtime.disable_plugin("alternate_feishu_connector")
    coordinator = ChannelCoordinator()
    coordinator.set_plugin_runtime(runtime)
    coordinator._managers[ChannelType.FEISHU] = _FakeManager()

    sent = await coordinator.send_message(
        "user-1",
        ChannelType.FEISHU,
        "chat-1",
        "hello",
        instance_id="bot-1",
    )

    assert sent is False


@pytest.mark.asyncio
async def test_channel_coordinator_allows_feishu_send_when_connector_enabled() -> None:
    runtime = PluginRuntime([build_feishu_connector_plugin_manifest()])
    coordinator = ChannelCoordinator()
    coordinator.set_plugin_runtime(runtime)
    coordinator._managers[ChannelType.FEISHU] = _FakeManager()

    sent = await coordinator.send_message(
        "user-1",
        ChannelType.FEISHU,
        "chat-1",
        "hello",
        instance_id="bot-1",
    )

    assert sent is True
