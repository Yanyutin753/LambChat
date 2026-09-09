"""注册表多机化测试：每用户多台 daemon 机器共存、legacy 单机兼容、目标解析。

Redis 布局（多机）::

    sandbox:machine:{uid}:{mid}   string  node_id|version|platform|policy|name   TTL 35s
    sandbox:machset:{uid}         set     在册 machine_id 集合
    sandbox:machname:{uid}        hash    mid -> 自定义展示名（rename 覆盖层，重连保留）
    sandbox:machdefault:{uid}     string  默认机 mid

legacy（未上报 machine_id 的 0.2.0 daemon）沿用旧 ``sandbox:clients:{uid}``
hash + ``sandbox:req:{uid}`` 队列，语义零变化；在机器列表中以 ``legacy``
伪机器出现，选择它时路由回旧队列。
"""

import time

import pytest

from src.infra.sandbox.relay.registry import (
    LEGACY_MACHINE_ID,
    SandboxClientRegistry,
)


class _FakeRedis:
    """覆盖 string/set/hash 三类操作的内存 Redis。TTL 由 expires_at 模拟。"""

    def __init__(self):
        self.strings: dict[str, str] = {}
        self.sets: "dict[str, set[str]]" = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self.expires_at: dict[str, float] = {}

    def _alive(self, key: str) -> bool:
        exp = self.expires_at.get(key)
        return exp is None or exp > time.monotonic()

    # string
    async def get(self, key: str):
        if key in self.strings and self._alive(key):
            return self.strings[key]
        return None

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.strings[key] = value
        if ex is not None:
            self.expires_at[key] = time.monotonic() + ex

    # set
    async def sadd(self, key: str, member: str) -> None:
        self.sets.setdefault(key, set()).add(member)

    async def srem(self, key: str, member: str) -> None:
        self.sets.get(key, set()).discard(member)

    async def smembers(self, key: str) -> "set[str]":
        return set(self.sets.get(key, set()))

    # hash
    async def hset(self, key: str, field: str, value: str) -> None:
        self.hashes.setdefault(key, {})[field] = value

    async def hdel(self, key: str, field: str) -> None:
        self.hashes.get(key, {}).pop(field, None)

    async def hgetall(self, key: str) -> dict[str, str]:
        if not self._alive(key):
            return {}
        return dict(self.hashes.get(key, {}))

    # 通用
    async def delete(self, key: str) -> None:
        self.strings.pop(key, None)
        self.sets.pop(key, None)
        self.hashes.pop(key, None)
        self.expires_at.pop(key, None)

    async def expire(self, key: str, seconds: int) -> None:
        self.expires_at[key] = time.monotonic() + seconds

    async def exists(self, key: str) -> int:
        return (
            1
            if self._alive(key) and (key in self.strings or key in self.sets or key in self.hashes)
            else 0
        )


@pytest.fixture
def registry(monkeypatch) -> SandboxClientRegistry:
    fake = _FakeRedis()
    reg = SandboxClientRegistry()
    monkeypatch.setattr(reg, "_redis", lambda: fake)
    reg.fake = fake  # type: ignore[attr-defined]
    return reg


async def test_machines_coexist_without_kicking_each_other(registry):
    """多机并存：A 机注册后 B 机注册，A 仍在线（不再后连踢前连）。"""
    await registry.register(
        "u1", "c1", "n1", version="0.3.0", machine_id="mac1", machine_name="MacBook"
    )
    await registry.register(
        "u1", "c2", "n2", version="0.3.0", machine_id="srv1", machine_name="Server"
    )
    machines = {m["machine_id"]: m for m in await registry.list_machines("u1")}
    assert set(machines) == {"mac1", "srv1"}
    assert machines["mac1"]["name"] == "MacBook"
    assert machines["srv1"]["online"] is True


async def test_same_machine_reconnect_replaces_only_own_entry(registry):
    await registry.register(
        "u1", "c1", "n1", version="0.3.0", machine_id="mac1", machine_name="MacBook"
    )
    await registry.register(
        "u1", "c2", "n2", version="0.3.0", machine_id="srv1", machine_name="Server"
    )
    # 同机重连（新 client 连接）
    await registry.register(
        "u1", "c3", "n1b", version="0.3.1", machine_id="mac1", machine_name="MacBook"
    )
    machines = {m["machine_id"]: m for m in await registry.list_machines("u1")}
    assert machines["mac1"]["version"] == "0.3.1"
    assert machines["srv1"]["online"] is True  # 其他机不受影响


async def test_list_machines_drops_expired_entries(registry):
    await registry.register("u1", "c1", "n1", version="0.3.0", machine_id="mac1")
    # 模拟 TTL 过期
    for k in list(registry.fake.expires_at):
        registry.fake.expires_at[k] = time.monotonic() - 1
    assert await registry.list_machines("u1") == []


async def test_rename_overrides_reported_name_and_survives_reconnect(registry):
    await registry.register(
        "u1", "c1", "n1", version="0.3.0", machine_id="mac1", machine_name="MacBook"
    )
    await registry.rename_machine("u1", "mac1", "主力机")
    machines = {m["machine_id"]: m for m in await registry.list_machines("u1")}
    assert machines["mac1"]["name"] == "主力机"
    # 重连上报旧名，rename 覆盖层仍生效
    await registry.register(
        "u1", "c2", "n1", version="0.3.0", machine_id="mac1", machine_name="MacBook"
    )
    machines = {m["machine_id"]: m for m in await registry.list_machines("u1")}
    assert machines["mac1"]["name"] == "主力机"


async def test_legacy_daemon_appears_as_legacy_machine(registry):
    """旧 daemon（无 machine_id）走 legacy 路径，仍出现在机器列表。"""
    await registry.register("u1", "c1", "n1", version="0.2.0")
    machines = {m["machine_id"]: m for m in await registry.list_machines("u1")}
    assert LEGACY_MACHINE_ID in machines
    assert machines[LEGACY_MACHINE_ID]["online"] is True


async def test_forget_machine_clears_default_and_entry(registry):
    await registry.register("u1", "c1", "n1", version="0.3.0", machine_id="old1")
    await registry.set_default_machine("u1", "old1")
    # 机器 TTL 过期离线后才可移除
    for k in list(registry.fake.expires_at):
        registry.fake.expires_at[k] = time.monotonic() - 1
    assert await registry.forget_machine("u1", "old1") is True
    assert await registry.list_machines("u1") == []
    assert await registry.get_default_machine("u1") is None


async def test_forget_machine_rejects_online_machine(registry):
    await registry.register("u1", "c1", "n1", version="0.3.0", machine_id="mac1")
    assert await registry.forget_machine("u1", "mac1") is False


async def test_resolve_target_explicit_default_single(registry):
    assert await registry.resolve_target("u1") is None  # 无任何机器

    await registry.register("u1", "c1", "n1", version="0.3.0", machine_id="mac1")
    # 唯一在线机：缺省解析到它
    assert await registry.resolve_target("u1") == "mac1"

    await registry.register("u1", "c2", "n2", version="0.3.0", machine_id="srv1")
    # 多机无默认：显式指定仍可用
    assert await registry.resolve_target("u1", "srv1") == "srv1"
    # 设默认后缺省解析到默认
    await registry.set_default_machine("u1", "mac1")
    assert await registry.resolve_target("u1") == "mac1"
    # 默认机离线：退回唯一在线机
    for k in list(registry.fake.expires_at):
        registry.fake.expires_at[k] = time.monotonic() - 1
    await registry.register("u1", "c3", "n2", version="0.3.0", machine_id="srv1")
    assert await registry.resolve_target("u1") == "srv1"


async def test_resolve_target_legacy_compatible(registry):
    """legacy 在线可被解析，且队列键保持旧格式（不带机器后缀）。"""
    await registry.register("u1", "c1", "n1", version="0.2.0")  # 无 machine_id → legacy
    assert await registry.resolve_target("u1") == LEGACY_MACHINE_ID
    assert registry.queue_key("u1", LEGACY_MACHINE_ID) == "sandbox:req:u1"
    assert registry.queue_key("u1", "mac1") == "sandbox:req:u1:mac1"


async def test_get_confirm_policy_per_machine(registry):
    await registry.register(
        "u1",
        "c1",
        "n1",
        version="0.3.0",
        platform="linux",
        confirm_policy="none",
        machine_id="mac1",
    )
    await registry.register(
        "u1", "c2", "n2", version="0.3.0", platform="win32", confirm_policy="all", machine_id="srv1"
    )
    assert await registry.get_confirm_policy("u1", "srv1") == "all"
    assert await registry.get_confirm_policy("u1", "mac1") == "none"
    assert await registry.get_platform("u1", "srv1") == "win32"


# 机器记忆层（machseen）：last_seen 记录 + 离线机保留（include_offline）
# ---------------------------------------------------------------------------


async def test_register_records_last_seen(registry, monkeypatch):
    """多机注册/心跳写入 machseen 记忆（ts/名称/平台/版本），供离线展示与 last_seen。"""
    import time as _time

    monkeypatch.setattr("src.infra.sandbox.relay.registry.time.time", lambda: 1700_000_000.0)
    assert _time.time() > 0  # 仅确保 import 路径可用
    await registry.register(
        "u1",
        "c1",
        "n1",
        version="0.4.0",
        platform="darwin",
        confirm_policy="none",
        machine_id="mac1",
        machine_name="MacBook",
    )
    seen = registry.fake.hashes.get("sandbox:machseen:u1")
    assert seen is not None and "mac1" in seen
    import json as _json

    record = _json.loads(seen["mac1"])
    assert record["ts"] == 1700_000_000.0
    assert record["name"] == "MacBook"
    assert record["platform"] == "darwin"
    assert record["version"] == "0.4.0"


async def test_list_machines_online_entries_carry_last_seen(registry):
    await registry.register(
        "u1", "c1", "n1", version="0.4.0", platform="linux", machine_id="srv1", machine_name="SRV"
    )
    machines = await registry.list_machines("u1")
    assert len(machines) == 1
    assert machines[0]["online"] is True
    assert isinstance(machines[0]["last_seen"], float)
    assert machines[0]["last_seen"] > 0


async def test_list_machines_include_offline_keeps_known_machines(registry):
    """离线机（TTL 过期）默认消失；include_offline=True 时保留并标 online=False。"""
    await registry.register(
        "u1", "c1", "n1", version="0.4.0", platform="win32", machine_id="pc1", machine_name="PC"
    )
    # 模拟 TTL 过期：机器键失效但 machseen 记忆仍在
    registry.fake.strings.pop("sandbox:machine:u1:pc1", None)
    registry.fake.sets["sandbox:machset:u1"].discard("pc1")

    assert await registry.list_machines("u1") == []

    machines = await registry.list_machines("u1", include_offline=True)
    assert len(machines) == 1
    offline = machines[0]
    assert offline["machine_id"] == "pc1"
    assert offline["online"] is False
    assert offline["name"] == "PC"
    assert offline["platform"] == "win32"
    assert offline["version"] == "0.4.0"
    assert offline["last_seen"] > 0


async def test_list_machines_include_offline_merges_online_and_offline(registry):
    await registry.register(
        "u1", "c1", "n1", version="0.4.0", platform="linux", machine_id="srv1", machine_name="SRV"
    )
    await registry.register(
        "u1", "c2", "n2", version="0.4.0", platform="win32", machine_id="pc1", machine_name="PC"
    )
    registry.fake.strings.pop("sandbox:machine:u1:pc1", None)
    registry.fake.sets["sandbox:machset:u1"].discard("pc1")

    machines = await registry.list_machines("u1", include_offline=True)
    by_id = {m["machine_id"]: m for m in machines}
    assert by_id["srv1"]["online"] is True
    assert by_id["pc1"]["online"] is False


async def test_rename_overlay_wins_over_seen_name(registry):
    """离线机展示名：rename 覆盖层 > 上报名。"""
    await registry.register(
        "u1", "c1", "n1", version="0.4.0", platform="linux", machine_id="srv1", machine_name="SRV"
    )
    await registry.rename_machine("u1", "srv1", "我的服务器")
    registry.fake.strings.pop("sandbox:machine:u1:srv1", None)
    registry.fake.sets["sandbox:machset:u1"].discard("srv1")

    machines = await registry.list_machines("u1", include_offline=True)
    assert machines[0]["name"] == "我的服务器"


async def test_forget_machine_clears_seen_record(registry):
    await registry.register(
        "u1", "c1", "n1", version="0.4.0", platform="linux", machine_id="srv1", machine_name="SRV"
    )
    registry.fake.strings.pop("sandbox:machine:u1:srv1", None)
    registry.fake.sets["sandbox:machset:u1"].discard("srv1")

    assert await registry.forget_machine("u1", "srv1") is True
    assert await registry.list_machines("u1", include_offline=True) == []
    assert "sandbox:machseen:u1" not in registry.fake.hashes or "srv1" not in (
        registry.fake.hashes.get("sandbox:machseen:u1") or {}
    )


async def test_update_confirm_policy_rewrites_live_machine_and_memory(registry):
    await registry.register(
        "u1",
        "c1",
        "node1",
        version="1",
        platform="linux",
        confirm_policy="all",
        machine_id="m1",
        machine_name="box",
    )
    await registry.update_confirm_policy("u1", "m1", "commands")
    machines = await registry.list_machines("u1")
    assert machines[0]["confirm_policy"] == "commands"
    assert await registry.get_confirm_policy("u1", "m1") == "commands"
