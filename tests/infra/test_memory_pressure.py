from collections import deque
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.monitoring.memory import MemoryMonitor


@pytest.fixture
def monitor(monkeypatch):
    monkeypatch.setattr("src.infra.monitoring.memory.settings.MEMORY_MONITOR_ENABLED", True)
    monkeypatch.setattr(
        "src.infra.monitoring.memory.psutil", SimpleNamespace(Process=lambda pid: None)
    )
    m = MemoryMonitor(
        leak_threshold_bytes=64, min_samples_for_alert=3, heavy_diagnostics_enabled=False
    )
    m._build_distributed_snapshot_locked = AsyncMock(return_value=None)
    return m


def sample(rss, seconds, **extra):
    return {
        "rss_bytes": rss,
        "vms_bytes": rss * 2,
        "thread_count": 2,
        "open_file_count": 3,
        "timestamp": datetime(2026, 11, 15, tzinfo=timezone.utc) + timedelta(seconds=seconds),
        **extra,
    }


async def test_pressure_alert_does_not_require_monotonic_rss_growth(monitor, caplog):
    rows = iter(
        [
            sample(400, 0, memory_current_bytes=900, memory_limit_bytes=1000),
            sample(390, 60, memory_current_bytes=910, memory_limit_bytes=1000),
        ]
    )
    monitor._collect_process_sample = lambda: next(rows)
    await monitor._sample_once()
    await monitor._sample_once()
    summary = await monitor.get_summary()
    assert summary["memory_pressure"] is True
    assert summary["alerts_24h"] == 1
    assert "memory_pressure" in caplog.text


async def test_small_gc_dip_does_not_hide_sustained_growth(monitor):
    monitor._history = deque([sample(100, 0), sample(250, 60), sample(248, 120), sample(260, 180)])
    assert (await monitor.get_summary())["suspected_leak"] is True


async def test_zero_run_samples_do_not_claim_process_idle(monitor):
    monitor._history = deque(
        [
            sample(500, 0, active_runs=2, queued_runs=0),
            sample(520, 60, active_runs=0, queued_runs=0),
            sample(480, 660, active_runs=0, queued_runs=0),
        ]
    )
    summary = await monitor.get_summary()
    assert summary["history_window_seconds"] == 660
    assert summary["idle_seconds"] is None
    assert summary["idle_rss_change_bytes"] is None
    assert summary["sampled_no_run_window_seconds"] == 600
    assert summary["sampled_no_run_rss_change_bytes"] == -40


@pytest.mark.parametrize(
    "counts",
    [
        {},
        {"active_runs": 0},
        {"queued_runs": 0},
        {"active_runs": 1, "queued_runs": 0},
        {"active_runs": 0, "queued_runs": 1},
    ],
)
async def test_sampled_no_run_window_requires_known_zero_counts(monitor, counts):
    monitor._history = deque(
        [sample(500, 0, active_runs=0, queued_runs=0), sample(520, 60, **counts)]
    )
    summary = await monitor.get_summary()
    assert summary["sampled_no_run_window_seconds"] is None
    assert summary["sampled_no_run_rss_change_bytes"] is None
    assert summary["idle_seconds"] is None


async def test_memory_incident_survives_live_snapshot_expiry():
    from src.infra.monitoring import distributed_memory_health as health

    client = SimpleNamespace(set=AsyncMock())
    snapshot = {
        "instance_id": "process-1",
        "captured_at": "2026-11-15T00:00:00+00:00",
        "summary": {"memory_pressure": True},
    }
    await health.publish_memory_incident(snapshot, redis_client=client)
    key, payload = client.set.call_args.args
    assert key.startswith("health:memory:incident:process-1:")
    assert '"memory_pressure": true' in payload
    assert client.set.call_args.kwargs["ex"] == 86400


def test_pressure_is_not_reported_as_stable_or_as_a_leak():
    from src.infra.monitoring.distributed_memory_health import build_instance_snapshot

    snapshot = build_instance_snapshot(
        summary={"available": True, "memory_pressure": True, "suspected_leak": False}
    )
    assert snapshot["overview"]["status"] == "memory_pressure"
    assert snapshot["highlights"][0] == {
        "kind": "status",
        "status": "memory_pressure",
        "severity": "warning",
    }


@pytest.mark.parametrize(
    "files,expected",
    [
        (
            {"/sys/fs/cgroup/memory.current": "900", "/sys/fs/cgroup/memory.max": "1000"},
            {"memory_current_bytes": 900, "memory_limit_bytes": 1000},
        ),
        ({"/sys/fs/cgroup/memory.current": "900", "/sys/fs/cgroup/memory.max": "max"}, {}),
        (
            {
                "/sys/fs/cgroup/memory/memory.usage_in_bytes": "800",
                "/sys/fs/cgroup/memory/memory.limit_in_bytes": "1000",
            },
            {"memory_current_bytes": 800, "memory_limit_bytes": 1000},
        ),
        (
            {
                "/sys/fs/cgroup/memory/memory.usage_in_bytes": "800",
                "/sys/fs/cgroup/memory/memory.limit_in_bytes": str(2**63 - 1),
            },
            {},
        ),
        ({}, {}),
    ],
)
def test_cgroup_limits_support_both_versions_and_ignore_unlimited(monkeypatch, files, expected):
    from src.infra.monitoring.memory import Path, _cgroup_memory

    def read(path):
        if str(path) not in files:
            raise FileNotFoundError(str(path))
        return files[str(path)]

    monkeypatch.setattr(Path, "read_text", read)
    assert _cgroup_memory() == expected


def test_local_task_counts_do_not_create_manager_and_exclude_finished_tasks(monkeypatch):
    from src.infra.task import manager

    monkeypatch.setattr(manager, "_task_manager", None)
    assert manager.get_local_task_counts() == {"active_runs": 0, "queued_runs": 0}
    assert manager._task_manager is None
    monkeypatch.setattr(
        manager,
        "_task_manager",
        SimpleNamespace(
            _tasks={
                "active": SimpleNamespace(done=lambda: False),
                "done": SimpleNamespace(done=lambda: True),
            },
            _pending_tasks={"queued": {}},
        ),
    )
    assert manager.get_local_task_counts() == {"active_runs": 1, "queued_runs": 1}
