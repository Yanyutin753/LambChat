from __future__ import annotations

import json

import pytest

from src.infra.websocket import ConnectionManager


class _FakeWebSocket:
    def __init__(self) -> None:
        self.accepted = 0
        self.sent_texts: list[str] = []

    async def accept(self) -> None:
        self.accepted += 1

    async def send_text(self, text: str) -> None:
        self.sent_texts.append(text)


class _FakeRedisClient:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int] = {}
        self.published: list[tuple[str, str]] = []

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        self.values[key] = value
        if ex is not None:
            self.expirations[key] = ex
        return True

    async def delete(self, key: str) -> int:
        existed = key in self.values
        self.values.pop(key, None)
        self.expirations.pop(key, None)
        return 1 if existed else 0

    async def keys(self, pattern: str) -> list[str]:
        if pattern.endswith("*"):
            prefix = pattern[:-1]
            return sorted(key for key in self.values if key.startswith(prefix))
        return [pattern] if pattern in self.values else []

    async def publish(self, channel: str, message: str) -> int:
        self.published.append((channel, message))
        return 1


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


@pytest.mark.asyncio
async def test_connect_registers_user_route_in_redis(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_redis = _FakeRedisClient()
    isolated_pool_flags: list[bool] = []
    monkeypatch.setattr(
        "src.infra.websocket.create_redis_client",
        lambda isolated_pool=False: isolated_pool_flags.append(isolated_pool) or fake_redis,
    )

    manager = ConnectionManager()
    manager._instance_id = "instance-a"
    websocket = _FakeWebSocket()

    await manager.connect(websocket, "user-1")

    assert fake_redis.values["ws:route:user-1:instance-a"] == "1"
    assert fake_redis.expirations["ws:route:user-1:instance-a"] > 0
    assert isolated_pool_flags == [True]


@pytest.mark.asyncio
async def test_disconnect_removes_route_when_last_local_connection_closes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_redis = _FakeRedisClient()
    monkeypatch.setattr(
        "src.infra.websocket.create_redis_client",
        lambda isolated_pool=False: fake_redis,
    )

    manager = ConnectionManager()
    manager._instance_id = "instance-a"
    websocket = _FakeWebSocket()

    await manager.connect(websocket, "user-1")
    await manager.disconnect(websocket, "user-1")

    assert "ws:route:user-1:instance-a" not in fake_redis.values


@pytest.mark.asyncio
async def test_send_to_user_uses_instance_targeted_channels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_redis = _FakeRedisClient()
    fake_redis.values["ws:route:user-1:instance-a"] = "1"
    fake_redis.values["ws:route:user-1:instance-b"] = "2"
    isolated_pool_flags: list[bool] = []
    monkeypatch.setattr(
        "src.infra.websocket.create_redis_client",
        lambda isolated_pool=False: isolated_pool_flags.append(isolated_pool) or fake_redis,
    )

    manager = ConnectionManager()
    manager._instance_id = "instance-a"

    sent = await manager.send_to_user_with_broadcast(
        "user-1",
        {"type": "task:complete", "data": {"run_id": "run-1"}},
    )

    assert sent == 2
    assert fake_redis.published == [
        (
            "ws:deliver:instance-a",
            json.dumps(
                {
                    "user_id": "user-1",
                    "message": {"type": "task:complete", "data": {"run_id": "run-1"}},
                    "source_instance_id": "instance-a",
                }
            ),
        ),
        (
            "ws:deliver:instance-b",
            json.dumps(
                {
                    "user_id": "user-1",
                    "message": {"type": "task:complete", "data": {"run_id": "run-1"}},
                    "source_instance_id": "instance-a",
                }
            ),
        ),
    ]
    assert isolated_pool_flags == [True]


@pytest.mark.asyncio
async def test_listener_subscribes_to_instance_delivery_channel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_hub = _FakeHub()
    monkeypatch.setattr("src.infra.websocket.get_pubsub_hub", lambda: fake_hub)

    manager = ConnectionManager()
    manager._instance_id = "instance-a"

    await manager.start_pubsub_listener()

    assert fake_hub.start_calls == 1
    assert fake_hub.subscriptions[0][0] == "ws:deliver:instance-a"

    await manager.stop_pubsub_listener()


@pytest.mark.asyncio
async def test_delivery_message_for_local_instance_reaches_connected_websocket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_redis = _FakeRedisClient()
    monkeypatch.setattr(
        "src.infra.websocket.create_redis_client",
        lambda isolated_pool=False: fake_redis,
    )

    manager = ConnectionManager()
    manager._instance_id = "instance-a"
    websocket = _FakeWebSocket()
    await manager.connect(websocket, "user-1", accept=False)

    await manager._handle_pubsub_message(
        {
            "data": json.dumps(
                {
                    "user_id": "user-1",
                    "message": {"type": "task:complete", "data": {"run_id": "run-1"}},
                    "source_instance_id": "instance-b",
                }
            )
        }
    )

    assert websocket.sent_texts == [
        json.dumps(
            {"type": "task:complete", "data": {"run_id": "run-1"}},
            ensure_ascii=False,
        )
    ]
