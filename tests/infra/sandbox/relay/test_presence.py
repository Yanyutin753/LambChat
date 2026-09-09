"""presence 快照与推送：注册表状态 → 用户级 WS presence 事件。

推送链路复用既有 ``ConnectionManager.send_to_user_with_broadcast``（Redis
pub/sub 跨实例定向投递）；本模块只负责快照组装与「失败不上抛」的推送纪律——
presence 是加速信号，任何推送异常都不能拖垮注册/注销主流程。
"""

import json
import time

import pytest

from src.infra.sandbox.relay import presence
from src.infra.sandbox.relay.registry import SandboxClientRegistry


class _FakeRedis:
    """复用 test_registry_machines 的内存 Redis 形态（string/set/hash）。"""

    def __init__(self):
        self.strings: dict[str, str] = {}
        self.sets: dict[str, set[str]] = {}
        self.hashes: dict[str, dict[str, str]] = {}
        self.expires_at: dict[str, float] = {}

    def _alive(self, key: str) -> bool:
        exp = self.expires_at.get(key)
        return exp is None or exp > time.monotonic()

    async def get(self, key: str):
        if key in self.strings and self._alive(key):
            return self.strings[key]
        return None

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.strings[key] = value
        if ex is not None:
            self.expires_at[key] = time.monotonic() + ex

    async def sadd(self, key: str, member: str) -> None:
        self.sets.setdefault(key, set()).add(member)

    async def srem(self, key: str, member: str) -> None:
        self.sets.get(key, set()).discard(member)

    async def smembers(self, key: str) -> "set[str]":
        return set(self.sets.get(key, set()))

    async def hset(self, key: str, field: str, value: str) -> None:
        self.hashes.setdefault(key, {})[field] = value

    async def hget(self, key: str, field: str) -> str | None:
        return self.hashes.get(key, {}).get(field)

    async def hdel(self, key: str, field: str) -> None:
        self.hashes.get(key, {}).pop(field, None)

    async def hgetall(self, key: str) -> dict[str, str]:
        return dict(self.hashes.get(key, {}))

    async def delete(self, key: str) -> None:
        self.strings.pop(key, None)
        self.sets.pop(key, None)
        self.hashes.pop(key, None)
        self.expires_at.pop(key, None)

    async def exists(self, key: str) -> int:
        if key in self.strings and self._alive(key):
            return 1
        if key in self.sets and self.sets[key]:
            return 1
        if key in self.hashes and self.hashes[key]:
            return 1
        return 0

    async def expire(self, key: str, seconds: int) -> None:
        if key in self.strings:
            self.expires_at[key] = time.monotonic() + seconds


@pytest.fixture
def registry(monkeypatch) -> SandboxClientRegistry:
    fake = _FakeRedis()
    reg = SandboxClientRegistry()
    monkeypatch.setattr(reg, "_redis", lambda: fake)
    monkeypatch.setattr(presence, "_registry_factory", lambda: reg)
    reg.fake = fake  # type: ignore[attr-defined]
    return reg


@pytest.fixture
def pushed(monkeypatch):
    """捕获 send_to_user_with_broadcast 调用；失败模式可切换。"""
    calls: list[tuple[str, dict]] = []
    mode = {"fail": False}

    class _Manager:
        async def send_to_user_with_broadcast(self, user_id: str, message: dict) -> int:
            if mode["fail"]:
                raise RuntimeError("ws route broken")
            calls.append((user_id, message))
            return 1

    monkeypatch.setattr(presence, "get_connection_manager", lambda: _Manager())
    return {"calls": calls, "mode": mode}


async def test_snapshot_shape_with_offline_machines(registry, monkeypatch):
    """快照：machines 含离线机（include_offline 全量）、默认机、legacy_online、revision。"""
    monkeypatch.setattr("src.infra.sandbox.relay.registry.time.time", lambda: 1700_000_000.0)
    await registry.register(
        "u1",
        "c1",
        "n1",
        version="0.4.0",
        platform="win32",
        confirm_policy="all",
        machine_id="pc1",
        machine_name="PC",
    )
    # pc1 离线（TTL 失效但记忆层在），srv1 在线
    registry.fake.strings.pop("sandbox:machine:u1:pc1", None)
    registry.fake.sets["sandbox:machset:u1"].discard("pc1")
    await registry.register(
        "u1",
        "c2",
        "n2",
        version="0.4.1",
        platform="linux",
        confirm_policy="none",
        machine_id="srv1",
        machine_name="SRV",
    )
    await registry.set_default_machine("u1", "srv1")

    snapshot = await presence.build_presence_snapshot("u1")
    assert snapshot["type"] == "sandbox:presence"
    data = snapshot["data"]
    by_id = {m["machine_id"]: m for m in data["machines"]}
    assert by_id["srv1"]["online"] is True
    assert by_id["pc1"]["online"] is False
    assert by_id["pc1"]["last_seen"] == 1700_000_000.0
    assert data["default_machine_id"] == "srv1"
    assert data["legacy_online"] is False
    assert isinstance(data["revision"], float)


async def test_snapshot_legacy_online_flag(registry):
    await registry.register("u1", "c9", "n1", version="0.2.0")
    snapshot = await presence.build_presence_snapshot("u1")
    assert snapshot["data"]["legacy_online"] is True
    ids = [m["machine_id"] for m in snapshot["data"]["machines"]]
    assert "legacy" in ids


async def test_revision_monotonic(registry, monkeypatch):
    clock = {"now": 100.0}
    monkeypatch.setattr("src.infra.sandbox.relay.presence.time.time", lambda: clock["now"])
    s1 = await presence.build_presence_snapshot("u1")
    clock["now"] = 200.0
    s2 = await presence.build_presence_snapshot("u1")
    assert s2["data"]["revision"] > s1["data"]["revision"]


async def test_publish_pushes_snapshot_to_user_channel(registry, pushed, monkeypatch):
    monkeypatch.setattr(presence, "_registry_factory", lambda: registry)
    await registry.register("u1", "c1", "n1", version="0.4.0", machine_id="m1")

    await presence.publish_presence("u1")
    assert len(pushed["calls"]) == 1
    user_id, message = pushed["calls"][0]
    assert user_id == "u1"
    assert message["type"] == "sandbox:presence"
    assert any(m["machine_id"] == "m1" for m in message["data"]["machines"])


async def test_publish_failure_is_swallowed(registry, pushed, monkeypatch):
    """推送失败仅告警不上抛：presence 是加速信号，不得拖垮注册主流程。"""
    monkeypatch.setattr(presence, "_registry_factory", lambda: registry)
    pushed["mode"]["fail"] = True

    # 不抛异常即通过
    await presence.publish_presence("u1")


async def test_snapshot_json_serializable(registry):
    """快照要过 WS JSON 序列化：machines/revision 全部可 json.dumps。"""
    await registry.register("u1", "c1", "n1", version="0.4.0", platform="darwin", machine_id="m1")
    snapshot = await presence.build_presence_snapshot("u1")
    assert json.loads(json.dumps(snapshot))["type"] == "sandbox:presence"
