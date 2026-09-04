"""daemon 注册表测试：注册/心跳/TTL/踢旧连/摘除。"""

import pytest

from src.infra.sandbox.relay.registry import SandboxClientRegistry


class _FakeRedis:
    def __init__(self):
        self.store: dict[str, dict[str, str]] = {}
        self.ttl: dict[str, int] = {}

    async def delete(self, key: str) -> None:
        self.store.pop(key, None)
        self.ttl.pop(key, None)

    async def hset(self, key: str, field: str, value: str) -> None:
        self.store.setdefault(key, {})[field] = value

    async def hdel(self, key: str, field: str) -> None:
        self.store.get(key, {}).pop(field, None)

    async def expire(self, key: str, seconds: int) -> None:
        self.ttl[key] = seconds

    async def exists(self, key: str) -> int:
        return 1 if key in self.store else 0

    async def hgetall(self, key: str) -> dict[str, str]:
        return dict(self.store.get(key, {}))


@pytest.fixture
def registry(monkeypatch) -> SandboxClientRegistry:
    fake = _FakeRedis()
    reg = SandboxClientRegistry()
    monkeypatch.setattr(reg, "_redis", lambda: fake)
    return reg


async def test_register_then_online(registry):
    await registry.register("u1", "c1", "node-a")
    assert await registry.is_online("u1") is True
    assert await registry.get_active("u1") == ("c1", "node-a")


async def test_new_connection_kicks_old(registry):
    await registry.register("u1", "c1", "node-a")
    await registry.register("u1", "c2", "node-b")
    assert await registry.get_active("u1") == ("c2", "node-b")


async def test_heartbeat_extends_ttl(registry):
    await registry.register("u1", "c1", "node-a")
    await registry.heartbeat("u1", "c1", "node-a")
    assert await registry.is_online("u1") is True


async def test_unregister_makes_offline(registry):
    await registry.register("u1", "c1", "node-a")
    await registry.unregister("u1", "c1")
    assert await registry.is_online("u1") is False


async def test_unknown_user_offline(registry):
    assert await registry.is_online("nobody") is False
