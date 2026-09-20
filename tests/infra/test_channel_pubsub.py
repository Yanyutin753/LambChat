from __future__ import annotations

import json

import pytest

from src.infra.channel.pubsub import (
    CHANNEL_CONFIG_CHANNEL,
    ChannelConfigPubSub,
    close_channel_config_pubsub,
    publish_channel_config_changed,
)
from src.infra.pubsub_hub import namespaced_channel


class _FakeHub:
    def __init__(self) -> None:
        self.subscriptions: list[tuple[str, object]] = []
        self.unsubscribed: list[str] = []
        self.start_calls = 0
        self.stop_if_idle_calls = 0

    def subscribe(self, channel: str, handler) -> str:
        token = f"token-{len(self.subscriptions) + 1}"
        self.subscriptions.append((channel, handler))
        return token

    def unsubscribe(self, token: str) -> None:
        self.unsubscribed.append(token)

    async def start(self) -> None:
        self.start_calls += 1

    async def stop_if_idle(self) -> None:
        self.stop_if_idle_calls += 1


class _FakeRedisClient:
    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []

    async def publish(self, channel: str, payload: str) -> int:
        self.published.append((channel, payload))
        return 1


class _FakeManager:
    def __init__(self) -> None:
        self.reload_calls: list[tuple[str, str | None]] = []

    async def reload_user(self, user_id: str, instance_id: str | None = None) -> bool:
        self.reload_calls.append((user_id, instance_id))
        return True


class _FakeManagerClass:
    _instance = _FakeManager()

    @classmethod
    def get_instance(cls) -> _FakeManager:
        return cls._instance


class _FakeRegistry:
    def __init__(self, manager_cls) -> None:
        self._manager_cls = manager_cls

    def get_manager_class(self, channel_type):
        return self._manager_cls


class _FakeChannelConfigPubSub:
    def __init__(self) -> None:
        self.stop_calls = 0

    async def stop_listener(self) -> None:
        self.stop_calls += 1


@pytest.mark.asyncio
async def test_channel_config_pubsub_subscribes_to_shared_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_hub = _FakeHub()
    monkeypatch.setattr("src.infra.channel.pubsub.get_pubsub_hub", lambda: fake_hub)

    pubsub = ChannelConfigPubSub()
    await pubsub.start_listener()

    assert fake_hub.start_calls == 1
    assert fake_hub.subscriptions[0][0] == CHANNEL_CONFIG_CHANNEL

    await pubsub.stop_listener()
    assert fake_hub.unsubscribed == ["token-1"]


@pytest.mark.asyncio
async def test_channel_config_pubsub_reloads_foreign_instance_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = _FakeRegistry(_FakeManagerClass)
    monkeypatch.setattr("src.infra.channel.pubsub.get_registry", lambda: registry)

    pubsub = ChannelConfigPubSub()
    pubsub._instance_id = "instance-a"

    await pubsub._handle_message(
        {
            "data": json.dumps(
                {
                    "instance_id": "instance-b",
                    "user_id": "user-1",
                    "channel_type": "feishu",
                    "channel_instance_id": "chan-1",
                    "action": "updated",
                }
            )
        }
    )

    assert _FakeManagerClass.get_instance().reload_calls == [("user-1", "chan-1")]


@pytest.mark.asyncio
async def test_publish_channel_config_changed_broadcasts_instance_scoped_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_redis = _FakeRedisClient()
    monkeypatch.setattr("src.infra.channel.pubsub.get_redis_client", lambda: fake_redis)

    pubsub = ChannelConfigPubSub()
    pubsub._instance_id = "instance-a"
    monkeypatch.setattr("src.infra.channel.pubsub.get_channel_config_pubsub", lambda: pubsub)

    await publish_channel_config_changed(
        user_id="user-1",
        channel_type="feishu",
        channel_instance_id="chan-1",
        action="deleted",
    )

    assert fake_redis.published == [
        (
            namespaced_channel(CHANNEL_CONFIG_CHANNEL),
            json.dumps(
                {
                    "instance_id": "instance-a",
                    "user_id": "user-1",
                    "channel_type": "feishu",
                    "channel_instance_id": "chan-1",
                    "action": "deleted",
                }
            ),
        )
    ]


@pytest.mark.asyncio
async def test_close_channel_config_pubsub_stops_and_releases_singleton(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_pubsub = _FakeChannelConfigPubSub()
    monkeypatch.setattr("src.infra.channel.pubsub._channel_config_pubsub", fake_pubsub)

    await close_channel_config_pubsub()

    assert fake_pubsub.stop_calls == 1
    from src.infra.channel import pubsub as channel_pubsub

    assert channel_pubsub._channel_config_pubsub is None


@pytest.mark.asyncio
async def test_close_channel_config_pubsub_does_not_create_singleton_when_unused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("src.infra.channel.pubsub._channel_config_pubsub", None)

    await close_channel_config_pubsub()

    from src.infra.channel import pubsub as channel_pubsub

    assert channel_pubsub._channel_config_pubsub is None
