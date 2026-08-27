"""周期性孤儿任务接管（分布式部署 P1 修复）的测试。

覆盖测试报告 P1 缺口：执行实例死亡后，存活副本无需重启即可通过周期
调度接管 RUNNING 且心跳过期的任务；PENDING/QUEUED 与 FAILED 恢复保持
仅在启动清理时执行，避免周期扫描误重放排队中的任务。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.infra.task import orphan_recovery
from src.infra.task.startup_cleanup import TaskStartupCleanupService


class _FakeCursor:
    def __init__(self) -> None:
        self.fetched = False

    async def to_list(self, length: int = 100) -> list:
        self.fetched = True
        return []


class _FakeCollection:
    def __init__(self) -> None:
        self.queries: list[dict] = []

    def find(self, query: dict) -> _FakeCursor:
        self.queries.append(query)
        return _FakeCursor()


class _FakeStorage:
    def __init__(self) -> None:
        self.collection = _FakeCollection()


class _FakeHeartbeat:
    async def check_exists(self, run_id: str) -> bool:  # pragma: no cover - not reached
        return False


class _FakeManager:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def cleanup_stale_tasks(self, **kwargs) -> None:
        self.calls.append(kwargs)


@pytest.mark.asyncio
async def test_scheduled_recovery_runs_running_only(monkeypatch: pytest.MonkeyPatch) -> None:
    manager = _FakeManager()
    monkeypatch.setattr(orphan_recovery, "get_task_manager", lambda: manager)

    result = await orphan_recovery.run_scheduled_orphan_recovery()

    assert manager.calls == [{"running_only": True}]
    assert result["status"] == "ok"


@pytest.mark.asyncio
async def test_running_only_cleanup_scans_running_but_not_pending_or_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _FakeStorage()
    service = TaskStartupCleanupService(
        storage=storage,
        heartbeat=_FakeHeartbeat(),
        ensure_executor=lambda: None,
        load_session_record=None,
        resume_interrupted_run=None,
        cleanup_stale_queues=None,
        replay_pending_queued_tasks=None,
    )

    async def _fake_acquire_lease(redis):
        return SimpleNamespace(redis=redis, token=None)

    async def _no_renew(lease) -> None:
        return None

    async def _no_release(lease) -> None:
        return None

    monkeypatch.setattr(
        "src.infra.task.startup_cleanup._acquire_startup_cleanup_lease", _fake_acquire_lease
    )
    monkeypatch.setattr(
        "src.infra.task.startup_cleanup._start_startup_cleanup_lease_renewal",
        lambda lease: None,
    )
    monkeypatch.setattr(
        "src.infra.task.startup_cleanup._release_startup_cleanup_lease", _no_release
    )
    monkeypatch.setattr("src.infra.task.startup_cleanup._renew_startup_cleanup_lease", _no_renew)

    await service.cleanup_stale_tasks(running_only=True)

    assert len(storage.collection.queries) == 1
    assert storage.collection.queries[0] == {"metadata.task_status": "running"}


def test_recovery_interval_reads_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(orphan_recovery.settings, "TASK_ORPHAN_RECOVERY_INTERVAL_SECONDS", 300)
    assert orphan_recovery.recovery_interval_seconds() == 300


def test_register_orphan_recovery_job_respects_disabled_setting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(orphan_recovery.settings, "TASK_ORPHAN_RECOVERY_INTERVAL_SECONDS", 0)
    registered: list[object] = []
    fake_scheduler = SimpleNamespace(register_job=registered.append)
    monkeypatch.setattr(orphan_recovery, "get_runtime_scheduler", lambda: fake_scheduler)

    orphan_recovery.register_orphan_recovery_job()

    assert registered == []


def test_register_orphan_recovery_job_registers_interval_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(orphan_recovery.settings, "TASK_ORPHAN_RECOVERY_INTERVAL_SECONDS", 120)
    registered: list[object] = []
    fake_scheduler = SimpleNamespace(register_job=registered.append)
    monkeypatch.setattr(orphan_recovery, "get_runtime_scheduler", lambda: fake_scheduler)

    orphan_recovery.register_orphan_recovery_job()

    assert len(registered) == 1
    job = registered[0]
    assert job.id == "task.orphan_recovery"
    assert job.handler is orphan_recovery.run_scheduled_orphan_recovery
