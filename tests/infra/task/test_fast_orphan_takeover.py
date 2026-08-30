"""缩短滚动更新/实例死亡后的对话恢复停顿：

1. 心跳按时间戳判过期（而非等 Redis key 的 120s TTL 自然消失）
2. 周期孤儿扫描同时接管 FAILED+recoverable（server_restart）任务，
   不再等「任意 Pod 重启」才恢复
3. 扫描周期默认 120s → 15s
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.infra.task import orphan_recovery
from src.infra.task.heartbeat import HEARTBEAT_INTERVAL, TaskHeartbeat
from src.infra.task.startup_cleanup import TaskStartupCleanupService


class _FakeRedis:
    def __init__(self, data: dict[str, str]):
        self._data = data

    async def get(self, key: str):
        return self._data.get(key)

    async def set(self, key, value, **kwargs):
        self._data[key] = value
        return True


def _iso(dt: datetime) -> str:
    return dt.isoformat()


class TestHeartbeatIsStale:
    @staticmethod
    def _with_redis(monkeypatch, data: dict[str, str]):
        monkeypatch.setattr("src.infra.task.heartbeat.get_redis_client", lambda: _FakeRedis(data))

    @pytest.mark.asyncio
    async def test_fresh_heartbeat_is_alive(self, monkeypatch):
        now = datetime.now(timezone.utc)
        self._with_redis(monkeypatch, {"task:heartbeat:run-1": _iso(now - timedelta(seconds=5))})
        assert await TaskHeartbeat().is_stale("run-1") is False

    @pytest.mark.asyncio
    async def test_old_heartbeat_is_stale_before_ttl_expiry(self, monkeypatch):
        # 35 秒没心跳即判死，无需等 120s TTL 自然过期
        now = datetime.now(timezone.utc)
        self._with_redis(monkeypatch, {"task:heartbeat:run-1": _iso(now - timedelta(seconds=35))})
        assert await TaskHeartbeat().is_stale("run-1") is True

    @pytest.mark.asyncio
    async def test_missing_heartbeat_is_stale(self, monkeypatch):
        self._with_redis(monkeypatch, {})
        assert await TaskHeartbeat().is_stale("run-1") is True

    @pytest.mark.asyncio
    async def test_unparseable_value_falls_back_to_alive(self, monkeypatch):
        # 解析失败按「存活」处理，避免误接管活任务
        self._with_redis(monkeypatch, {"task:heartbeat:run-1": "garbage"})
        assert await TaskHeartbeat().is_stale("run-1") is False

    def test_stale_threshold_is_three_beats(self):
        from src.infra.task.heartbeat import HEARTBEAT_STALE_THRESHOLD_SECONDS

        assert HEARTBEAT_STALE_THRESHOLD_SECONDS >= HEARTBEAT_INTERVAL * 3


class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    async def to_list(self, length: int = 100) -> list:
        return self._docs


class _FakeCollection:
    def __init__(self):
        self.queries: list[dict] = []

    def find(self, query: dict) -> _FakeCursor:
        self.queries.append(query)
        return _FakeCursor([])


class _FakeStorage:
    def __init__(self):
        self.collection = _FakeCollection()


class _FakeHeartbeat:
    async def is_stale(self, run_id: str) -> bool:
        return True


def _make_service() -> TaskStartupCleanupService:
    return TaskStartupCleanupService(
        storage=_FakeStorage(),
        heartbeat=_FakeHeartbeat(),
        ensure_executor=lambda: None,
        load_session_record=None,
        resume_interrupted_run=None,
        cleanup_stale_queues=None,
        replay_pending_queued_tasks=None,
    )


@pytest.fixture
def _lease_passthrough(monkeypatch: pytest.MonkeyPatch):
    from types import SimpleNamespace

    async def _fake_acquire_lease(redis):
        return SimpleNamespace(redis=redis, token=None)

    async def _no_op(*args, **kwargs):
        return None

    monkeypatch.setattr(
        "src.infra.task.startup_cleanup._acquire_startup_cleanup_lease", _fake_acquire_lease
    )
    monkeypatch.setattr(
        "src.infra.task.startup_cleanup._start_startup_cleanup_lease_renewal",
        lambda lease: None,
    )
    monkeypatch.setattr("src.infra.task.startup_cleanup._release_startup_cleanup_lease", _no_op)
    monkeypatch.setattr("src.infra.task.startup_cleanup._renew_startup_cleanup_lease", _no_op)


class TestPeriodicScanIncludesFailedRecoverable:
    @pytest.mark.asyncio
    async def test_running_only_scans_running_and_failed_recoverable(self, _lease_passthrough):
        """周期扫描也要接管优雅关停标记的 FAILED+recoverable 任务。"""
        service = _make_service()
        await service.cleanup_stale_tasks(running_only=True)

        queries = service._storage.collection.queries
        assert {"metadata.task_status": "running"} in queries
        assert {
            "metadata.task_status": "failed",
            "metadata.task_recoverable": True,
            "metadata.task_error_code": "server_restart",
        } in queries
        # PENDING/QUEUED 重放仍仅在启动时执行
        pending_query = {"metadata.task_status": {"$in": ["pending", "queued"]}}
        assert (
            pending_query
            not in [q for q in queries if "$in" in str(q.get("metadata.task_status", ""))]
            or pending_query not in queries
        )


def test_default_scan_interval_is_fast(monkeypatch: pytest.MonkeyPatch):
    """默认扫描间隔 15 秒，缩短恢复停顿。"""
    monkeypatch.setattr(
        orphan_recovery.settings,
        "TASK_ORPHAN_RECOVERY_INTERVAL_SECONDS",
        None,
        raising=False,
    )
    assert orphan_recovery.DEFAULT_ORPHAN_RECOVERY_INTERVAL_SECONDS == 15


def test_settings_default_scan_interval_is_15s():
    """settings 默认值（真正生效的配置源）也要是 15s。"""
    from src.kernel.config import settings as settings_module

    assert settings_module.TASK_ORPHAN_RECOVERY_INTERVAL_SECONDS == 15


def test_setting_definition_default_is_15s():
    """定义层（管理设置 UI 的默认值）也要是 15s——运行时以定义默认覆盖代码默认。"""
    from src.kernel.config.definitions import SETTING_DEFINITIONS

    definition = SETTING_DEFINITIONS.get("TASK_ORPHAN_RECOVERY_INTERVAL_SECONDS")
    assert definition is not None
    assert definition.get("default") == 15
