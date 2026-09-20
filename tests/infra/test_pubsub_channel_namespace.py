"""Redis pub/sub 通道环境命名空间测试。

Redis pub/sub 通道是实例级全局：SELECT db 隔离不了 PUBLISH/SUBSCRIBE。
生产（redis db3）与 staging（redis db6）共用同一 Redis 实例时，裸通道名
会让取消 / 缓存失效等广播跨环境串台（2026-09-20 生产实测：staging worker
收到并处理了生产 run 的 cancel 信号）。通道名必须带按 MONGODB_DB 派生的
环境命名空间，订阅（hub）与发布两侧一致使用。
"""

from __future__ import annotations

import asyncio

import pytest

from src.infra.pubsub_hub import RedisPubSubHub, namespaced_channel


def test_namespaced_channel_includes_environment_db() -> None:
    channel = namespaced_channel("task:cancel")
    assert channel.endswith(":task:cancel")
    assert "task:cancel" != channel


def test_namespaced_channel_isolates_environments(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.kernel.config import settings

    monkeypatch.setattr(settings, "MONGODB_DB", "agent_state", raising=False)
    prod = namespaced_channel("task:cancel")
    monkeypatch.setattr(settings, "MONGODB_DB", "agent_state_staging", raising=False)
    staging = namespaced_channel("task:cancel")
    assert prod != staging
    assert "agent_state" in prod
    assert "agent_state_staging" in staging


def test_namespaced_channel_falls_back_when_db_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.kernel.config import settings

    monkeypatch.setattr(settings, "MONGODB_DB", "", raising=False)
    assert namespaced_channel("task:cancel").endswith(":task:cancel")


class _FakePubSub:
    def __init__(self) -> None:
        self.subscribed: list[str] = []
        self.subscribed_event = asyncio.Event()

    async def subscribe(self, *channels: str) -> None:
        self.subscribed.extend(channels)
        self.subscribed_event.set()

    async def close(self) -> None:
        pass


class _FakeRedisClient:
    def __init__(self) -> None:
        self.pubsubs: list[_FakePubSub] = []

    def pubsub(self) -> _FakePubSub:
        ps = _FakePubSub()
        self.pubsubs.append(ps)
        return ps

    async def aclose(self) -> None:
        pass


@pytest.mark.asyncio
async def test_hub_subscribes_on_namespaced_channel(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.kernel.config import settings

    monkeypatch.setattr(settings, "MONGODB_DB", "agent_state_ns_test", raising=False)
    fake = _FakeRedisClient()
    monkeypatch.setattr("src.infra.pubsub_hub.create_redis_client", lambda **_: fake)

    hub = RedisPubSubHub()
    try:
        hub.subscribe("task:cancel", lambda _msg: None)
        await hub.start()
        await asyncio.wait_for(fake.pubsubs[0].subscribed_event.wait(), timeout=2)
        # 订阅到 Redis 的必须是带环境前缀的通道，而不是裸名
        assert fake.pubsubs[0].subscribed == [namespaced_channel("task:cancel")]
        assert "agent_state_ns_test" in fake.pubsubs[0].subscribed[0]
    finally:
        await hub.stop()
