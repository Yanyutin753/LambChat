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
