import asyncio

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from src.infra.pubsub_hub import RedisPubSubHub


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
        lambda isolated_pool=False, socket_timeout=object(): create_calls.append(
            (isolated_pool, socket_timeout)
        )
        or fake_redis,
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


async def _wait_until(predicate, *, interval: float = 0.01) -> None:
    while not await predicate():
        await asyncio.sleep(interval)
