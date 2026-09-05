"""daemon 注册表测试：注册/心跳/TTL/踢旧连/摘除/版本与平台值编码。"""

import pytest

from src.infra.sandbox.relay.registry import (
    SandboxClientRegistry,
    parse_daemon_platform,
    parse_daemon_version,
)


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

    # 多机路径占位（legacy 测试不触及；注册表新分支按需调用）
    async def smembers(self, key: str) -> set:
        return set()

    async def get(self, key: str):
        return None

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        pass

    async def sadd(self, key: str, member: str) -> None:
        pass

    async def srem(self, key: str, member: str) -> None:
        pass


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


# ---------- 平台上报（M4 T3）：hash value 扩展 node_id|version|platform ----------


async def test_register_with_platform_stores_third_segment(registry):
    """版本+平台注册：value 为 ``node_id|version|platform`` 三段。"""
    await registry.register("u1", "c1", "node-a", version="0.1.0", platform="win32")
    assert await registry.get_active("u1") == ("c1", "node-a|0.1.0|win32")


async def test_register_platform_without_version_keeps_placeholder(registry):
    """仅平台（无版本）：空版本段占位 ``node_id||platform``——保住第三段可解析。"""
    await registry.register("u1", "c1", "node-a", platform="darwin")
    assert await registry.get_active("u1") == ("c1", "node-a||darwin")


async def test_register_version_without_platform_keeps_two_segments(registry):
    """仅版本（旧调用方）：value 字节形态保持 M2 的 ``node_id|version`` 不变。"""
    await registry.register("u1", "c1", "node-a", version="0.1.0")
    assert await registry.get_active("u1") == ("c1", "node-a|0.1.0")


async def test_heartbeat_with_platform_rewrites_encoded_value(registry):
    """心跳带平台重写同格式值：不随心跳把平台降级丢失（对齐版本语义）。"""
    await registry.register("u1", "c1", "node-a", version="0.1.0", platform="win32")
    await registry.heartbeat("u1", "c1", "node-a", version="0.1.0", platform="win32")
    assert await registry.get_active("u1") == ("c1", "node-a|0.1.0|win32")


async def test_get_platform_returns_active_daemon_platform(registry):
    await registry.register("u1", "c1", "node-a", version="0.1.0", platform="win32")
    assert await registry.get_platform("u1") == "win32"


async def test_get_platform_empty_when_offline_or_legacy(registry):
    """离线、旧格式 value、未上报平台（第三段缺失/为空）都返回空串——
    调用方（local.py 命令生成分支）按空串归一 posix。"""
    assert await registry.get_platform("nobody") == ""  # 离线
    await registry.register("u1", "c1", "node-a")
    assert await registry.get_platform("u1") == ""  # M1 纯 node_id
    await registry.register("u1", "c2", "node-b", version="0.1.0")
    assert await registry.get_platform("u1") == ""  # M2 node|version


def test_parse_daemon_platform_all_formats():
    assert parse_daemon_platform("node-a|0.1.0|win32") == "win32"
    assert parse_daemon_platform("node-a||darwin") == "darwin"
    assert parse_daemon_platform("node-a|0.1.0") == ""  # 两段：平台段缺失
    assert parse_daemon_platform("node-a") == ""  # 旧格式（无版本写入方）
    assert parse_daemon_platform("node-a|0.1.0|") == ""  # 空平台与未上报等价


# ---- 确认策略四段式（服务端统一确认门，spec §3.5）----


def test_encode_with_confirm_policy_four_segments():
    from src.infra.sandbox.relay.registry import encode_node_value, parse_confirm_policy

    value = encode_node_value("n1", "0.2.0", "linux", "none")
    assert value == "n1|0.2.0|linux|none"
    assert parse_confirm_policy(value) == "none"


def test_parse_confirm_policy_missing_segments_returns_empty():
    from src.infra.sandbox.relay.registry import parse_confirm_policy

    assert parse_confirm_policy("n1|0.2.0|linux") == ""
    assert parse_confirm_policy("n1|0.2.0") == ""
    assert parse_confirm_policy("n1") == ""


async def test_register_stores_confirm_policy(registry):
    await registry.register(
        "u1", "c1", "node-a", version="0.2.0", platform="linux", confirm_policy="none"
    )
    assert await registry.get_confirm_policy("u1") == "none"


async def test_get_confirm_policy_offline_returns_empty(registry):
    assert await registry.get_confirm_policy("u1") == ""


async def test_heartbeat_rewrites_confirm_policy(registry):
    await registry.register("u1", "c1", "node-a", confirm_policy="all")
    await registry.heartbeat(
        "u1", "c1", "node-a", version="0.2.0", platform="linux", confirm_policy="commands"
    )
    assert await registry.get_confirm_policy("u1") == "commands"
