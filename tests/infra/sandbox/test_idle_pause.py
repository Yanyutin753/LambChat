"""idle_pause：对话轮终态后，无进行中对话需要沙箱时自动暂停沙箱（省成本）。"""

from __future__ import annotations

import asyncio

import pytest

import src.infra.sandbox.idle_pause as idle_pause_mod
from src.infra.sandbox.idle_pause import maybe_pause_user_sandbox, schedule_idle_pause
from src.kernel.config import settings


class _FakeManager:
    def __init__(self) -> None:
        self.stopped: list[str] = []

    async def stop(self, user_id: str) -> bool:
        self.stopped.append(user_id)
        return True


@pytest.fixture
def e2b_env(monkeypatch: pytest.MonkeyPatch) -> _FakeManager:
    monkeypatch.setattr(settings, "SANDBOX_PAUSE_WHEN_IDLE", True, raising=False)
    monkeypatch.setattr(settings, "SANDBOX_PLATFORM", "e2b")
    monkeypatch.setattr(settings, "MONGODB_DB", "idle_pause_test")

    manager = _FakeManager()
    monkeypatch.setattr(
        "src.infra.sandbox.session_manager.get_session_sandbox_manager",
        lambda: manager,
    )

    async def _no_lease(user_id: str) -> bool:
        return False

    monkeypatch.setattr(idle_pause_mod, "has_browse_lease", _no_lease)
    return manager


def _patch_active_count(monkeypatch: pytest.MonkeyPatch, statuses: list[str]) -> None:
    captured: dict[str, object] = {}

    async def fake_count(user_id: str) -> int:
        captured["user_id"] = user_id
        return len([s for s in statuses if s in idle_pause_mod._ACTIVE_TASK_STATUSES])

    monkeypatch.setattr(idle_pause_mod, "_count_active_runs", fake_count)
    monkeypatch.setattr(idle_pause_mod, "_captured", captured, raising=False)


async def test_no_active_runs_pauses_sandbox(
    monkeypatch: pytest.MonkeyPatch, e2b_env: _FakeManager
) -> None:
    _patch_active_count(monkeypatch, [])

    assert await maybe_pause_user_sandbox("user-1") is True
    assert e2b_env.stopped == ["user-1"]


async def test_active_run_blocks_pause(
    monkeypatch: pytest.MonkeyPatch, e2b_env: _FakeManager
) -> None:
    _patch_active_count(monkeypatch, ["running"])

    assert await maybe_pause_user_sandbox("user-1") is False
    assert e2b_env.stopped == []


async def test_waiting_human_is_not_active(
    monkeypatch: pytest.MonkeyPatch, e2b_env: _FakeManager
) -> None:
    """等人工输入期间也暂停：恢复对话时 get_or_create 自动唤醒，无感。"""
    _patch_active_count(monkeypatch, ["waiting_human", "completed"])

    assert await maybe_pause_user_sandbox("user-1") is True
    assert e2b_env.stopped == ["user-1"]


async def test_local_platform_skips(monkeypatch: pytest.MonkeyPatch, e2b_env: _FakeManager) -> None:
    monkeypatch.setattr(settings, "SANDBOX_PLATFORM", "local")
    called: list[str] = []

    async def fail_count(user_id: str) -> int:
        called.append(user_id)
        return 0

    monkeypatch.setattr(idle_pause_mod, "_count_active_runs", fail_count)

    assert await maybe_pause_user_sandbox("user-1") is False
    assert called == []
    assert e2b_env.stopped == []


async def test_setting_disabled_skips(
    monkeypatch: pytest.MonkeyPatch, e2b_env: _FakeManager
) -> None:
    monkeypatch.setattr(settings, "SANDBOX_PAUSE_WHEN_IDLE", False, raising=False)
    _patch_active_count(monkeypatch, [])

    assert await maybe_pause_user_sandbox("user-1") is False
    assert e2b_env.stopped == []


async def test_stop_failure_is_swallowed(
    monkeypatch: pytest.MonkeyPatch, e2b_env: _FakeManager
) -> None:
    async def boom(user_id: str) -> bool:
        raise RuntimeError("stop exploded")

    monkeypatch.setattr(e2b_env, "stop", boom)
    _patch_active_count(monkeypatch, [])

    assert await maybe_pause_user_sandbox("user-1") is False  # 不抛异常


async def test_count_active_runs_queries_sessions_collection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """活跃判定查 sessions：user_id + metadata.task_status ∈ 活跃集合。"""
    queries: list[dict] = []

    class _FakeColl:
        async def count_documents(self, q: dict) -> int:
            queries.append(q)
            return 2

        def __getitem__(self, name: str) -> "_FakeColl":
            assert name == "sessions"
            return self

    class _FakeClient:
        def __getitem__(self, name: str) -> _FakeColl:
            assert name == "idle_pause_test"
            return _FakeColl()

    import src.infra.storage.mongodb as mongo_mod

    monkeypatch.setattr(mongo_mod, "get_mongo_client", lambda: _FakeClient())
    monkeypatch.setattr(settings, "MONGODB_DB", "idle_pause_test")

    assert await idle_pause_mod._count_active_runs("user-9") == 2
    assert queries == [
        {
            "user_id": "user-9",
            "metadata.task_status": {"$in": sorted(idle_pause_mod._ACTIVE_TASK_STATUSES)},
        }
    ]


async def test_schedule_runs_after_grace_and_dedupes(
    monkeypatch: pytest.MonkeyPatch, e2b_env: _FakeManager
) -> None:
    monkeypatch.setattr(idle_pause_mod, "_IDLE_GRACE_SECONDS", 0)
    _patch_active_count(monkeypatch, [])

    schedule_idle_pause("user-1")
    schedule_idle_pause("user-1")  # 去重
    await asyncio.sleep(0.05)

    assert e2b_env.stopped == ["user-1"]


# ---------------------------------------------------------------------------
# 浏览租约：云端文件浏览期间的暂停豁免 + 回收器
# ---------------------------------------------------------------------------


class _FakeLeaseRedis:
    def __init__(self) -> None:
        self.kv: dict[str, str] = {}

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.kv[key] = value

    async def get(self, key: str) -> str | None:
        return self.kv.get(key)


@pytest.fixture
def lease_redis(monkeypatch: pytest.MonkeyPatch) -> _FakeLeaseRedis:
    fake = _FakeLeaseRedis()

    # e2b_env 已把公共名 patch 成「无租约」；本 fixture 恢复实现语义并
    # 指向 fake kv（键在=租约存续）
    async def _has(user_id: str) -> bool:
        return fake.kv.get(f"sandbox:browse:{user_id}") is not None

    monkeypatch.setattr(idle_pause_mod, "has_browse_lease", _has)
    return fake


async def test_browse_lease_blocks_idle_pause(
    monkeypatch: pytest.MonkeyPatch,
    e2b_env: _FakeManager,
    lease_redis: _FakeLeaseRedis,
) -> None:
    """浏览租约存续期间：即使无进行中对话也不暂停（用户正在看云端文件）。"""
    _patch_active_count(monkeypatch, [])
    lease_redis.kv["sandbox:browse:user-1"] = "1"

    assert await maybe_pause_user_sandbox("user-1") is False
    assert e2b_env.stopped == []


async def test_browse_lease_expiry_allows_pause(
    monkeypatch: pytest.MonkeyPatch,
    e2b_env: _FakeManager,
    lease_redis: _FakeLeaseRedis,
) -> None:
    """租约过期（Redis 无键）后恢复常规空闲暂停语义。"""
    _patch_active_count(monkeypatch, [])

    assert await maybe_pause_user_sandbox("user-1") is True
    assert e2b_env.stopped == ["user-1"]


async def test_lease_check_failure_fails_open(
    monkeypatch: pytest.MonkeyPatch,
    e2b_env: _FakeManager,
) -> None:
    """Redis 不可用时租约判定按存续处理：宁可多保留宽限窗，不打断浏览。"""
    _patch_active_count(monkeypatch, [])

    async def _fail_open(user_id: str) -> bool:
        # 复刻实现的 fail-open 分支:redis 不可用 → 按存续处理
        raise_and_return = RuntimeError("redis down")
        try:
            raise raise_and_return
        except RuntimeError:
            return True

    monkeypatch.setattr(idle_pause_mod, "has_browse_lease", _fail_open)

    assert await maybe_pause_user_sandbox("user-1") is False
    assert e2b_env.stopped == []


async def test_browse_reaper_pauses_after_lease_window(
    monkeypatch: pytest.MonkeyPatch,
    e2b_env: _FakeManager,
    lease_redis: _FakeLeaseRedis,
) -> None:
    """回收器：租约窗过后（无浏览、无对话）暂停沙箱；租约存续则再等一轮。"""
    import src.infra.sandbox.idle_pause as mod

    monkeypatch.setattr(mod, "BROWSE_LEASE_SECONDS", 0.05)
    _patch_active_count(monkeypatch, [])
    mod._reaping_users.discard("user-1")

    mod.schedule_browse_reaper("user-1")
    await asyncio.sleep(0.12)
    assert e2b_env.stopped == ["user-1"]
    assert "user-1" not in mod._reaping_users


async def test_browse_reaper_loops_while_leased(
    monkeypatch: pytest.MonkeyPatch,
    e2b_env: _FakeManager,
    lease_redis: _FakeLeaseRedis,
) -> None:
    """回收器循环重排：租约一直在（用户持续浏览）就不暂停。"""
    import src.infra.sandbox.idle_pause as mod

    monkeypatch.setattr(mod, "BROWSE_LEASE_SECONDS", 0.05)
    _patch_active_count(monkeypatch, [])
    mod._reaping_users.discard("user-1")

    mod.schedule_browse_reaper("user-1")
    for _ in range(3):
        await asyncio.sleep(0.03)
        lease_redis.kv[f"sandbox:browse:user-1"] = "1"  # 持续续租
    await asyncio.sleep(0.03)
    assert e2b_env.stopped == []  # 仍在浏览，从未暂停
    assert "user-1" in mod._reaping_users  # 回收器仍挂着

    lease_redis.kv.pop(f"sandbox:browse:user-1", None)  # 停止浏览
    await asyncio.sleep(0.12)
    assert e2b_env.stopped == ["user-1"]


async def test_browse_reaper_skips_non_pause_platforms(
    monkeypatch: pytest.MonkeyPatch,
    e2b_env: _FakeManager,
) -> None:
    """daytona 等平台不挂回收器（自身 auto-stop 兜底）。"""
    import src.infra.sandbox.idle_pause as mod

    monkeypatch.setattr(settings, "SANDBOX_PLATFORM", "daytona")
    mod.schedule_browse_reaper("user-1")
    assert "user-1" not in mod._reaping_users


async def test_lease_impl_fails_open_on_redis_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """真实现的 fail-open 分支：redis 抛错 → 按存续处理（不打断浏览）。"""
    from src.infra.sandbox.idle_pause import _has_browse_lease_impl

    async def broken_client():
        raise RuntimeError("redis down")

    import src.infra.storage.redis as redis_module

    monkeypatch.setattr(redis_module, "get_redis_client", broken_client)
    assert await _has_browse_lease_impl("user-1") is True
