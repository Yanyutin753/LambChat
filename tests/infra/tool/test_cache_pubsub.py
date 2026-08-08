from __future__ import annotations

import json

import pytest

from src.infra.tool import cache_pubsub as cache_pubsub_module
from src.infra.tool.cache_pubsub import (
    TOOL_CACHE_INVALIDATION_CHANNEL,
    ToolCachePubSub,
    close_tool_cache_pubsub,
    get_tool_cache_pubsub,
    publish_tool_cache_invalidation,
)
from src.infra.tool.env_var_prompt import _env_var_prompt_cache


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


@pytest.mark.asyncio
async def test_tool_cache_pubsub_subscribes_to_shared_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_hub = _FakeHub()
    monkeypatch.setattr("src.infra.tool.cache_pubsub.get_pubsub_hub", lambda: fake_hub)

    pubsub = ToolCachePubSub()
    await pubsub.start_listener()

    assert fake_hub.start_calls == 1
    assert fake_hub.subscriptions[0][0] == TOOL_CACHE_INVALIDATION_CHANNEL

    await pubsub.stop_listener()
    assert fake_hub.unsubscribed == ["token-1"]


@pytest.mark.asyncio
async def test_tool_cache_pubsub_invalidates_foreign_env_var_prompt_cache() -> None:
    _env_var_prompt_cache["user-1"] = (("section",), 123.0)
    pubsub = ToolCachePubSub()
    pubsub._instance_id = "instance-a"

    await pubsub._handle_message(
        {
            "data": json.dumps(
                {
                    "instance_id": "instance-b",
                    "cache": "env_var_prompt",
                    "user_id": "user-1",
                }
            )
        }
    )

    assert "user-1" not in _env_var_prompt_cache


@pytest.mark.asyncio
async def test_publish_tool_cache_invalidation_broadcasts_cache_key_and_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_redis = _FakeRedisClient()
    monkeypatch.setattr("src.infra.tool.cache_pubsub.get_redis_client", lambda: fake_redis)

    pubsub = ToolCachePubSub()
    pubsub._instance_id = "instance-a"
    monkeypatch.setattr("src.infra.tool.cache_pubsub.get_tool_cache_pubsub", lambda: pubsub)

    await publish_tool_cache_invalidation("env_var_prompt", user_id="user-1")

    assert fake_redis.published == [
        (
            TOOL_CACHE_INVALIDATION_CHANNEL,
            json.dumps(
                {
                    "instance_id": "instance-a",
                    "cache": "env_var_prompt",
                    "user_id": "user-1",
                }
            ),
        )
    ]


@pytest.mark.asyncio
async def test_close_tool_cache_pubsub_stops_and_releases_singleton(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_hub = _FakeHub()
    monkeypatch.setattr("src.infra.tool.cache_pubsub.get_pubsub_hub", lambda: fake_hub)
    pubsub = get_tool_cache_pubsub()
    await pubsub.start_listener()

    await close_tool_cache_pubsub()

    assert cache_pubsub_module._tool_cache_pubsub is None
    assert fake_hub.unsubscribed == ["token-1"]


@pytest.mark.asyncio
async def test_close_tool_cache_pubsub_does_not_create_singleton_when_unused() -> None:
    cache_pubsub_module._tool_cache_pubsub = None

    await close_tool_cache_pubsub()

    assert cache_pubsub_module._tool_cache_pubsub is None
