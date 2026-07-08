import asyncio

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from src.infra import pubsub_hub as pubsub_hub_module
from src.infra.pubsub_hub import RedisPubSubHub
from src.kernel.extensions import PluginManifest, PluginRuntime


class FakePubSub:
    def __init__(self) -> None:
        self.subscribed: list[str] = []
        self.unsubscribed: list[str] = []
        self.closed = False
        self._messages: asyncio.Queue[object] = asyncio.Queue()
        self.subscribed_event = asyncio.Event()

    async def subscribe(self, *channels: str) -> None:
        self.subscribed.extend(channels)
        self.subscribed_event.set()

    async def unsubscribe(self, *channels: str) -> None:
        self.unsubscribed.extend(channels)

    async def close(self) -> None:
        self.closed = True
        await self._messages.put(None)

    async def push(self, message: dict) -> None:
        await self._messages.put(message)

    async def listen(self):
        while True:
            message = await self._messages.get()
            if message is None:
                raise RedisConnectionError("Connection closed by server.")
            yield message


class FakeRedisClient:
    def __init__(self) -> None:
        self.pubsub_calls = 0
        self.pubsubs: list[FakePubSub] = []
        self.closed = False

    def pubsub(self) -> FakePubSub:
        self.pubsub_calls += 1
        pubsub = FakePubSub()
        self.pubsubs.append(pubsub)
        return pubsub

    async def aclose(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_hub_uses_one_pubsub_connection_for_multiple_channels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_redis = FakeRedisClient()
    create_calls: list[tuple[bool, object]] = []
    monkeypatch.setattr(
        "src.infra.pubsub_hub.create_redis_client",
        lambda isolated_pool=False, socket_timeout=object(): (
            create_calls.append((isolated_pool, socket_timeout)) or fake_redis
        ),
    )

    hub = RedisPubSubHub()

    async def noop(_: dict) -> None:
        return None

    hub.subscribe("task:cancel", noop)
    hub.subscribe("settings:changed", noop)

    await hub.start()
    await fake_redis.pubsubs[0].subscribed_event.wait()

    assert fake_redis.pubsub_calls == 1
    assert fake_redis.pubsubs[0].subscribed == [
        "settings:changed",
        "task:cancel",
    ]
    assert create_calls == [(True, None)]

    await hub.stop()


@pytest.mark.asyncio
async def test_hub_dispatches_message_only_to_matching_channel_handlers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_redis = FakeRedisClient()
    monkeypatch.setattr(
        "src.infra.pubsub_hub.create_redis_client",
        lambda **kwargs: fake_redis,
    )

    hub = RedisPubSubHub()
    received: list[tuple[str, str]] = []
    handled = asyncio.Event()

    async def task_handler(message: dict) -> None:
        received.append(("task", message["data"]))
        handled.set()

    async def settings_handler(message: dict) -> None:
        received.append(("settings", message["data"]))

    hub.subscribe("task:cancel", task_handler)
    hub.subscribe("settings:changed", settings_handler)

    await hub.start()
    pubsub = fake_redis.pubsubs[0]
    await pubsub.subscribed_event.wait()

    await pubsub.push(
        {
            "type": "message",
            "channel": "task:cancel",
            "data": '{"run_id":"run-123"}',
        }
    )
    await asyncio.wait_for(handled.wait(), timeout=1)

    assert received == [("task", '{"run_id":"run-123"}')]

    await hub.stop()


@pytest.mark.asyncio
async def test_plugin_owned_listener_dispatch_follows_plugin_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_redis = FakeRedisClient()
    monkeypatch.setattr(
        "src.infra.pubsub_hub.create_redis_client",
        lambda **kwargs: fake_redis,
    )

    runtime = PluginRuntime(
        [
            PluginManifest(
                id="feedback",
                name="Feedback",
                version="1.0.0",
                api_version="v1",
                permissions=["feedback:read"],
                resources=[
                    {
                        "id": "feedback.listener",
                        "type": "listener",
                        "retention_policy": "core_owned_do_not_delete",
                        "cleanup_strategy": "forbid_delete",
                    }
                ],
            )
        ]
    )
    hub = RedisPubSubHub()
    hub.set_plugin_runtime(runtime)
    handled = asyncio.Event()
    received: list[str] = []

    async def listener(message: dict) -> None:
        received.append(message["data"])
        handled.set()

    hub.subscribe(
        "feedback:events",
        listener,
        plugin_listener_id="feedback.listener",
    )

    await hub.start()
    pubsub = fake_redis.pubsubs[0]
    await pubsub.subscribed_event.wait()

    await pubsub.push({"type": "message", "channel": "feedback:events", "data": "enabled"})
    await asyncio.wait_for(handled.wait(), timeout=1)

    runtime.disable_plugin("feedback")
    handled.clear()
    await pubsub.push({"type": "message", "channel": "feedback:events", "data": "disabled"})
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert received == ["enabled"]

    await hub.stop()


@pytest.mark.asyncio
async def test_plugin_owned_listener_fails_closed_without_plugin_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_redis = FakeRedisClient()
    monkeypatch.setattr(
        "src.infra.pubsub_hub.create_redis_client",
        lambda **kwargs: fake_redis,
    )

    hub = RedisPubSubHub()
    received: list[str] = []

    async def listener(message: dict) -> None:
        received.append(message["data"])

    hub.subscribe(
        "feedback:events",
        listener,
        plugin_listener_id="feedback.listener",
    )

    await hub.start()
    pubsub = fake_redis.pubsubs[0]
    await pubsub.subscribed_event.wait()

    await pubsub.push({"type": "message", "channel": "feedback:events", "data": "blocked"})
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert received == []

    await hub.stop()


@pytest.mark.asyncio
async def test_slow_async_handler_does_not_block_later_pubsub_messages(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_redis = FakeRedisClient()
    monkeypatch.setattr(
        "src.infra.pubsub_hub.create_redis_client",
        lambda **kwargs: fake_redis,
    )

    hub = RedisPubSubHub()
    release_slow_handler = asyncio.Event()
    fast_handled = asyncio.Event()
    received: list[str] = []

    async def slow_handler(message: dict) -> None:
        received.append(f"slow:{message['data']}")
        await release_slow_handler.wait()

    async def fast_handler(message: dict) -> None:
        received.append(f"fast:{message['data']}")
        fast_handled.set()

    hub.subscribe("task:cancel", slow_handler)
    hub.subscribe("settings:changed", fast_handler)

    await hub.start()
    pubsub = fake_redis.pubsubs[0]
    await pubsub.subscribed_event.wait()

    await pubsub.push({"type": "message", "channel": "task:cancel", "data": "slow"})
    await asyncio.sleep(0)
    await pubsub.push({"type": "message", "channel": "settings:changed", "data": "fast"})

    await asyncio.wait_for(fast_handled.wait(), timeout=1)
    assert received == ["slow:slow", "fast:fast"]

    release_slow_handler.set()
    await hub.stop()


@pytest.mark.asyncio
async def test_hub_applies_backpressure_to_handler_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_redis = FakeRedisClient()
    monkeypatch.setattr(
        "src.infra.pubsub_hub.create_redis_client",
        lambda **kwargs: fake_redis,
    )

    hub = RedisPubSubHub(max_handler_tasks=1)
    started = 0
    release_handler = asyncio.Event()

    async def slow_handler(_: dict) -> None:
        nonlocal started
        started += 1
        await release_handler.wait()

    hub.subscribe("task:cancel", slow_handler)

    await hub.start()
    pubsub = fake_redis.pubsubs[0]
    await pubsub.subscribed_event.wait()

    await pubsub.push({"type": "message", "channel": "task:cancel", "data": "one"})
    await pubsub.push({"type": "message", "channel": "task:cancel", "data": "two"})
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert started == 1
    assert len(hub._handler_tasks) == 1

    async def _second_handler_started() -> bool:
        return started == 2

    release_handler.set()
    await _wait_until(_second_handler_started)
    await hub.stop()


@pytest.mark.asyncio
async def test_hub_drops_oversized_messages_before_handler_fanout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_redis = FakeRedisClient()
    monkeypatch.setattr(
        "src.infra.pubsub_hub.create_redis_client",
        lambda **kwargs: fake_redis,
    )

    hub = RedisPubSubHub(max_message_bytes=4)
    received: list[str] = []

    async def handler(message: dict) -> None:
        received.append(message["data"])

    hub.subscribe("settings:changed", handler)

    await hub.start()
    pubsub = fake_redis.pubsubs[0]
    await pubsub.subscribed_event.wait()

    await pubsub.push({"type": "message", "channel": "settings:changed", "data": "too-large"})
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    assert received == []
    assert len(hub._handler_tasks) == 0

    await hub.stop()


@pytest.mark.asyncio
async def test_hub_coalesces_resubscribe_poke_tasks() -> None:
    hub = RedisPubSubHub()
    release_poke = asyncio.Event()
    started = 0

    async def slow_poke() -> None:
        nonlocal started
        started += 1
        await release_poke.wait()

    async def noop(_: dict) -> None:
        return None

    hub._running = True
    hub._poke_listener = slow_poke  # type: ignore[method-assign]

    for index in range(5):
        hub.subscribe(f"channel:{index}", noop)

    await asyncio.sleep(0)

    assert started == 1

    release_poke.set()
    await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_hub_resubscribes_without_logging_error_for_intentional_reconnect(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    fake_redis = FakeRedisClient()
    monkeypatch.setattr(
        "src.infra.pubsub_hub.create_redis_client",
        lambda **kwargs: fake_redis,
    )

    hub = RedisPubSubHub()

    async def noop(_: dict) -> None:
        return None

    hub.subscribe("task:cancel", noop)

    await hub.start()
    await fake_redis.pubsubs[0].subscribed_event.wait()

    caplog.clear()
    hub.subscribe("settings:changed", noop)

    async def _resubscribed() -> bool:
        return fake_redis.pubsub_calls >= 2 and fake_redis.pubsubs[1].subscribed_event.is_set()

    await asyncio.wait_for(_wait_until(_resubscribed), timeout=1)

    assert fake_redis.pubsubs[1].subscribed == [
        "settings:changed",
        "task:cancel",
    ]
    assert "Pub/sub hub listener error: Connection closed by server." not in caplog.text

    await hub.stop()


def test_hub_reports_subscription_snapshot() -> None:
    hub = RedisPubSubHub()

    async def noop(_: dict) -> None:
        return None

    hub.subscribe("task:cancel", noop)
    hub.subscribe("task:cancel", noop)
    hub.subscribe("settings:changed", noop)

    assert hub.describe_state() == {
        "channel_count": 2,
        "subscription_count": 3,
        "channels": {
            "settings:changed": 1,
            "task:cancel": 2,
        },
    }


@pytest.mark.asyncio
async def test_close_pubsub_hub_stops_and_releases_global_hub() -> None:
    class _FakeHub:
        def __init__(self) -> None:
            self.stop_calls = 0

        async def stop(self) -> None:
            self.stop_calls += 1

    hub = _FakeHub()
    pubsub_hub_module._pubsub_hub = hub

    await pubsub_hub_module.close_pubsub_hub()

    assert hub.stop_calls == 1
    assert pubsub_hub_module._pubsub_hub is None


async def _wait_until(predicate, *, interval: float = 0.01) -> None:
    while not await predicate():
        await asyncio.sleep(interval)
