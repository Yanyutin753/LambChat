"""daemon 注册表测试：注册/心跳/TTL/踢旧连/摘除/版本值编码。"""

import pytest

from src.infra.sandbox.relay.registry import SandboxClientRegistry, parse_daemon_version


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


# ---------- 版本地基：hash value 编码 node_id|version ----------


async def test_register_with_version_stores_encoded_value(registry):
    """带版本注册：hash value 存 ``node_id|version``，get_active 原样返回。"""
    await registry.register("u1", "c1", "node-a", version="0.1.0")
    assert await registry.get_active("u1") == ("c1", "node-a|0.1.0")


async def test_register_without_version_keeps_plain_node_id(registry):
    """向后兼容：无 version（旧调用方）时 value 就是纯 node_id。"""
    await registry.register("u1", "c1", "node-a")
    assert await registry.get_active("u1") == ("c1", "node-a")


async def test_heartbeat_with_version_rewrites_encoded_value(registry):
    """心跳带 version 重写同格式值：不随心跳把版本降级丢失。"""
    await registry.register("u1", "c1", "node-a", version="0.1.0")
    await registry.heartbeat("u1", "c1", "node-a", version="0.1.0")
    assert await registry.get_active("u1") == ("c1", "node-a|0.1.0")


async def test_new_connection_register_overrides_old_version(registry):
    """新连接（不同版本）覆盖旧值：踢旧连语义对版本同样成立。"""
    await registry.register("u1", "c1", "node-a", version="0.1.0")
    await registry.register("u1", "c2", "node-b", version="0.2.0")
    assert await registry.get_active("u1") == ("c2", "node-b|0.2.0")


def test_parse_daemon_version_both_formats():
    assert parse_daemon_version("node-a|0.1.0") == "0.1.0"
    assert parse_daemon_version("node-a") == ""  # 旧格式（无版本写入方）
    assert parse_daemon_version("node-a|") == ""  # 空版本与无版本等价
