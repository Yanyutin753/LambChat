from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import src.infra.monitoring.distributed_memory_health as distributed_memory_health

_CHECKPOINTER_SUMMARY = {
    "configured_backend": "mongodb",
    "backend_enabled": True,
    "mongo_checkpointer_active": False,
    "postgres_checkpointer_active": False,
    "postgres_pool_active": False,
    "memory_saver_singleton_active": False,
    "memory_saver_cache_active": False,
    "memory_saver_cache_size": 0,
    "memory_saver_cache_limit": 200,
    "memory_saver_ttl_seconds": 3600,
}


@pytest.fixture(autouse=True)
def _enable_memory_monitor(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.infra.monitoring.memory.settings.MEMORY_MONITOR_ENABLED", True)
    monkeypatch.setattr(
        "src.infra.monitoring.memory.psutil",
        SimpleNamespace(Process=lambda _pid: object()),
    )
    monkeypatch.setattr(
        "src.infra.storage.checkpoint.get_checkpointer_diagnostics",
        lambda: _CHECKPOINTER_SUMMARY,
    )

    async def _noop_publish_instance_snapshot(
        snapshot: dict[str, object],
        *,
        interval_seconds: float,
        redis_client: object | None = None,
    ) -> dict[str, object]:
        del interval_seconds, redis_client
        return snapshot

    monkeypatch.setattr(
        distributed_memory_health,
        "publish_instance_snapshot",
        _noop_publish_instance_snapshot,
    )


@pytest.mark.asyncio
async def test_monitor_marks_suspicious_growth_when_rss_keeps_rising() -> None:
    from src.infra.monitoring.memory import MemoryMonitor

    rss_values = iter([100 * 1024 * 1024, 150 * 1024 * 1024, 230 * 1024 * 1024])
    diagnostics_calls: list[int] = []

    monitor = MemoryMonitor(
        interval_seconds=60.0,
        history_limit=10,
        leak_threshold_bytes=64 * 1024 * 1024,
        min_samples_for_alert=3,
        alert_cooldown_seconds=0.0,
        heavy_diagnostics_enabled=True,
    )

    def _fake_process_sample() -> dict[str, int]:
        return {
            "rss_bytes": next(rss_values),
            "vms_bytes": 400 * 1024 * 1024,
            "thread_count": 12,
            "open_file_count": 3,
        }

    def _fake_capture_diagnostics() -> dict[str, object]:
        diagnostics_calls.append(1)
        return {
            "top_growth": [{"location": "src/example.py:10", "size_diff_bytes": 1024}],
            "top_allocations": [{"location": "src/example.py:10", "size_bytes": 2048}],
            "top_object_types": [{"type": "dict", "count": 42}],
        }

    monitor._collect_process_sample = _fake_process_sample  # type: ignore[method-assign]
    monitor._capture_diagnostics_snapshot = _fake_capture_diagnostics  # type: ignore[method-assign]
    monitor._build_distributed_snapshot_locked = lambda: asyncio.sleep(0, result=None)  # type: ignore[method-assign]

    await monitor._sample_once()
    await monitor._sample_once()
    await monitor._sample_once()

    summary = await monitor.get_summary()
    diagnostics = await monitor.get_diagnostics()

    assert summary["suspected_leak"] is True
    assert summary["growth_bytes"] == 130 * 1024 * 1024
    assert diagnostics_calls == [1]
    assert diagnostics["last_alert"]["top_growth"][0]["location"] == "src/example.py:10"


@pytest.mark.asyncio
async def test_monitor_logs_hotspot_summary_when_alert_fires(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from src.infra.monitoring.memory import MemoryMonitor

    rss_values = iter([100 * 1024 * 1024, 150 * 1024 * 1024, 230 * 1024 * 1024])

    monitor = MemoryMonitor(
        interval_seconds=60.0,
        history_limit=10,
        leak_threshold_bytes=64 * 1024 * 1024,
        min_samples_for_alert=3,
        alert_cooldown_seconds=0.0,
        heavy_diagnostics_enabled=True,
    )

    def _fake_process_sample() -> dict[str, int]:
        return {
            "rss_bytes": next(rss_values),
            "vms_bytes": 400 * 1024 * 1024,
            "thread_count": 12,
            "open_file_count": 3,
        }

    def _fake_capture_diagnostics() -> dict[str, object]:
        return {
            "top_growth": [{"location": "src/leaky.py:88", "size_diff_bytes": 64 * 1024 * 1024}],
            "top_allocations": [{"location": "src/cache.py:21", "size_bytes": 32 * 1024 * 1024}],
            "top_object_types": [{"type": "dict", "count": 4200}],
        }

    monitor._collect_process_sample = _fake_process_sample  # type: ignore[method-assign]
    monitor._capture_diagnostics_snapshot = _fake_capture_diagnostics  # type: ignore[method-assign]
    monitor._build_distributed_snapshot_locked = lambda: asyncio.sleep(0, result=None)  # type: ignore[method-assign]

    with caplog.at_level("WARNING", logger="src.infra.monitoring.memory"):
        await monitor._sample_once()
        await monitor._sample_once()
        await monitor._sample_once()

    assert "src/leaky.py:88" in caplog.text
    assert "src/cache.py:21" in caplog.text
    assert "dict=4200" in caplog.text


@pytest.mark.asyncio
async def test_monitor_omits_empty_hotspot_fields_from_alert_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from src.infra.monitoring.memory import MemoryMonitor

    rss_values = iter([100 * 1024 * 1024, 150 * 1024 * 1024, 230 * 1024 * 1024])

    monitor = MemoryMonitor(
        interval_seconds=60.0,
        history_limit=10,
        leak_threshold_bytes=64 * 1024 * 1024,
        min_samples_for_alert=3,
        alert_cooldown_seconds=0.0,
        heavy_diagnostics_enabled=True,
    )

    def _fake_process_sample() -> dict[str, int]:
        return {
            "rss_bytes": next(rss_values),
            "vms_bytes": 400 * 1024 * 1024,
            "thread_count": 12,
            "open_file_count": 3,
        }

    def _fake_capture_diagnostics() -> dict[str, object]:
        return {
            "top_growth": [],
            "top_allocations": [],
            "top_object_types": [],
        }

    monitor._collect_process_sample = _fake_process_sample  # type: ignore[method-assign]
    monitor._capture_diagnostics_snapshot = _fake_capture_diagnostics  # type: ignore[method-assign]
    monitor._build_distributed_snapshot_locked = lambda: asyncio.sleep(0, result=None)  # type: ignore[method-assign]

    with caplog.at_level("WARNING", logger="src.infra.monitoring.memory"):
        await monitor._sample_once()
        await monitor._sample_once()
        await monitor._sample_once()

    assert "[MemoryMonitor] suspicious memory growth detected rss=" in caplog.text
    assert "top_growth=" not in caplog.text
    assert "top_allocations=" not in caplog.text
    assert "top_objects=" not in caplog.text


@pytest.mark.asyncio
async def test_monitor_summary_reports_not_available_before_sampling() -> None:
    from src.infra.monitoring.memory import MemoryMonitor

    monitor = MemoryMonitor()

    assert (await monitor.get_summary())["available"] is False


@pytest.mark.asyncio
async def test_reset_baseline_reanchors_growth_window() -> None:
    from src.infra.monitoring.memory import MemoryMonitor

    monitor = MemoryMonitor(interval_seconds=60.0, history_limit=10)

    first_timestamp = datetime(2026, 4, 30, 3, 20, tzinfo=timezone.utc)
    samples = iter(
        [
            {
                "timestamp": first_timestamp,
                "rss_bytes": 100 * 1024 * 1024,
                "vms_bytes": 400 * 1024 * 1024,
                "thread_count": 12,
                "open_file_count": 3,
            },
            {
                "timestamp": first_timestamp + timedelta(minutes=1),
                "rss_bytes": 180 * 1024 * 1024,
                "vms_bytes": 420 * 1024 * 1024,
                "thread_count": 12,
                "open_file_count": 3,
            },
            {
                "timestamp": first_timestamp + timedelta(minutes=2),
                "rss_bytes": 210 * 1024 * 1024,
                "vms_bytes": 430 * 1024 * 1024,
                "thread_count": 12,
                "open_file_count": 3,
            },
        ]
    )

    monitor._collect_process_sample = lambda: next(samples)  # type: ignore[method-assign]
    monitor._build_distributed_snapshot_locked = lambda: asyncio.sleep(0, result=None)  # type: ignore[method-assign]

    await monitor._sample_once()
    await monitor._sample_once()

    assert (await monitor.get_summary())["growth_bytes"] == 80 * 1024 * 1024

    await monitor.reset_baseline()
    summary = await monitor.get_summary()

    assert summary["growth_bytes"] == 0
    assert summary["history_size"] == 1
    assert summary["baseline_reset_at"] == first_timestamp + timedelta(minutes=2)


@pytest.mark.asyncio
async def test_reset_baseline_clears_previous_alert_state() -> None:
    from src.infra.monitoring.memory import MemoryMonitor

    monitor = MemoryMonitor(interval_seconds=60.0, history_limit=10)
    reset_timestamp = datetime(2026, 4, 30, 3, 25, tzinfo=timezone.utc)

    monitor._collect_process_sample = lambda: {
        "timestamp": reset_timestamp,
        "rss_bytes": 220 * 1024 * 1024,
        "vms_bytes": 440 * 1024 * 1024,
        "thread_count": 12,
        "open_file_count": 4,
    }  # type: ignore[method-assign]
    monitor._build_distributed_snapshot_locked = lambda: asyncio.sleep(0, result=None)  # type: ignore[method-assign]
    monitor._last_alert = {"captured_at": "2026-04-30T03:24:00+00:00"}
    monitor._last_alert_at = reset_timestamp - timedelta(minutes=1)

    await monitor.reset_baseline()

    diagnostics = await monitor.get_diagnostics()

    assert diagnostics["last_alert"] is None
    assert diagnostics["summary"]["baseline_reset_at"] == reset_timestamp


@pytest.mark.asyncio
async def test_reset_baseline_publishes_fresh_instance_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.monitoring.memory import MemoryMonitor

    reset_timestamp = datetime(2026, 4, 30, 3, 25, tzinfo=timezone.utc)
    published_calls: list[tuple[dict[str, object], float]] = []
    built_snapshots: list[dict[str, object]] = []

    monitor = MemoryMonitor(
        interval_seconds=45.0,
        history_limit=10,
        heavy_diagnostics_enabled=True,
    )
    monitor._collect_process_sample = lambda: {  # type: ignore[method-assign]
        "timestamp": reset_timestamp,
        "rss_bytes": 220 * 1024 * 1024,
        "vms_bytes": 440 * 1024 * 1024,
        "thread_count": 12,
        "open_file_count": 4,
    }
    monitor._capture_diagnostics_snapshot = lambda: {  # type: ignore[method-assign]
        "captured_at": "2026-04-30T03:25:30+00:00",
        "top_growth": [{"location": "src/reset.py:10", "size_diff_bytes": 1024}],
        "top_allocations": [{"location": "src/reset.py:10", "size_bytes": 2048}],
        "top_object_types": [{"type": "dict", "count": 10}],
    }
    monitor._last_alert = {"captured_at": "2026-04-30T03:24:00+00:00"}
    monitor._last_alert_at = reset_timestamp - timedelta(minutes=1)

    def _fake_build_instance_snapshot(
        *,
        instance_id: str | None = None,
        captured_at: object | None = None,
        summary: dict[str, object] | None = None,
        details: dict[str, object] | None = None,
    ) -> dict[str, object]:
        snapshot = {
            "instance_id": instance_id,
            "captured_at": captured_at,
            "summary": summary,
            "details": details,
        }
        built_snapshots.append(snapshot)
        return snapshot

    async def _fake_publish_instance_snapshot(
        snapshot: dict[str, object],
        *,
        interval_seconds: float,
        redis_client: object | None = None,
    ) -> dict[str, object]:
        del redis_client
        published_calls.append((snapshot, interval_seconds))
        return snapshot

    monkeypatch.setattr(
        distributed_memory_health,
        "build_instance_snapshot",
        _fake_build_instance_snapshot,
    )
    monkeypatch.setattr(
        distributed_memory_health,
        "publish_instance_snapshot",
        _fake_publish_instance_snapshot,
    )

    await monitor.reset_baseline()

    assert len(built_snapshots) == 1
    assert built_snapshots[0]["captured_at"] == "2026-04-30T03:25:00+00:00"
    assert built_snapshots[0]["summary"] == {
        "available": True,
        "rss_bytes": 220 * 1024 * 1024,
        "vms_bytes": 440 * 1024 * 1024,
        "thread_count": 12,
        "open_file_count": 4,
        "history_size": 1,
        "growth_bytes": 0,
        "suspected_leak": False,
        "alerts_24h": 0,
        "heavy_diagnostics_enabled": True,
        "tracemalloc_tracing": False,
        "sample_interval_seconds": 45.0,
        "baseline_reset_at": reset_timestamp,
        "last_sample_at": reset_timestamp,
        "last_error": None,
        "checkpointer": _CHECKPOINTER_SUMMARY,
    }
    assert built_snapshots[0]["details"] == {
        "captured_at": "2026-04-30T03:25:00+00:00",
        "heavy_diagnostics_enabled": False,
        "reason": "heavy_diagnostics_disabled",
        "top_growth": [],
        "top_allocations": [],
        "top_object_types": [],
    }
    assert published_calls == [(built_snapshots[0], 45.0)]


@pytest.mark.asyncio
async def test_sample_once_publishes_current_snapshot_when_no_alert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.monitoring.memory import MemoryMonitor

    sample_timestamp = datetime(2026, 4, 30, 3, 25, tzinfo=timezone.utc)
    published_calls: list[tuple[dict[str, object], float]] = []
    built_snapshots: list[dict[str, object]] = []

    monitor = MemoryMonitor(
        interval_seconds=60.0,
        history_limit=10,
        leak_threshold_bytes=1024 * 1024 * 1024,
        min_samples_for_alert=2,
        heavy_diagnostics_enabled=True,
    )
    monitor._collect_process_sample = lambda: {  # type: ignore[method-assign]
        "timestamp": sample_timestamp,
        "rss_bytes": 220 * 1024 * 1024,
        "vms_bytes": 440 * 1024 * 1024,
        "thread_count": 12,
        "open_file_count": 4,
    }
    monitor._capture_diagnostics_snapshot = lambda: {  # type: ignore[method-assign]
        "captured_at": "2026-04-30T03:25:30+00:00",
        "top_growth": [{"location": "src/current.py:10", "size_diff_bytes": 4096}],
        "top_allocations": [{"location": "src/current.py:10", "size_bytes": 8192}],
        "top_object_types": [{"type": "list", "count": 6}],
    }

    def _fake_build_instance_snapshot(
        *,
        instance_id: str | None = None,
        captured_at: object | None = None,
        summary: dict[str, object] | None = None,
        details: dict[str, object] | None = None,
    ) -> dict[str, object]:
        snapshot = {
            "instance_id": instance_id,
            "captured_at": captured_at,
            "summary": summary,
            "details": details,
        }
        built_snapshots.append(snapshot)
        return snapshot

    async def _fake_publish_instance_snapshot(
        snapshot: dict[str, object],
        *,
        interval_seconds: float,
        redis_client: object | None = None,
    ) -> dict[str, object]:
        del redis_client
        published_calls.append((snapshot, interval_seconds))
        return snapshot

    monkeypatch.setattr(
        distributed_memory_health,
        "build_instance_snapshot",
        _fake_build_instance_snapshot,
    )
    monkeypatch.setattr(
        distributed_memory_health,
        "publish_instance_snapshot",
        _fake_publish_instance_snapshot,
    )

    await monitor._sample_once()

    assert len(built_snapshots) == 1
    assert built_snapshots[0]["captured_at"] == "2026-04-30T03:25:00+00:00"
    assert built_snapshots[0]["summary"] == {
        "available": True,
        "rss_bytes": 220 * 1024 * 1024,
        "vms_bytes": 440 * 1024 * 1024,
        "thread_count": 12,
        "open_file_count": 4,
        "history_size": 1,
        "growth_bytes": 0,
        "suspected_leak": False,
        "alerts_24h": 0,
        "heavy_diagnostics_enabled": True,
        "tracemalloc_tracing": False,
        "sample_interval_seconds": 60.0,
        "baseline_reset_at": None,
        "last_sample_at": sample_timestamp,
        "last_error": None,
        "checkpointer": _CHECKPOINTER_SUMMARY,
    }
    assert built_snapshots[0]["details"] == {
        "captured_at": "2026-04-30T03:25:00+00:00",
        "heavy_diagnostics_enabled": False,
        "reason": "heavy_diagnostics_disabled",
        "top_growth": [],
        "top_allocations": [],
        "top_object_types": [],
    }
    assert published_calls == [(built_snapshots[0], 60.0)]


@pytest.mark.asyncio
async def test_sample_once_publishes_last_alert_snapshot_when_alert_fires(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.monitoring.memory import MemoryMonitor

    first_timestamp = datetime(2026, 4, 30, 3, 25, tzinfo=timezone.utc)
    second_timestamp = first_timestamp + timedelta(minutes=1)
    samples = iter(
        [
            {
                "timestamp": first_timestamp,
                "rss_bytes": 100 * 1024 * 1024,
                "vms_bytes": 400 * 1024 * 1024,
                "thread_count": 12,
                "open_file_count": 3,
            },
            {
                "timestamp": second_timestamp,
                "rss_bytes": 220 * 1024 * 1024,
                "vms_bytes": 440 * 1024 * 1024,
                "thread_count": 12,
                "open_file_count": 4,
            },
        ]
    )
    alert_snapshot = {
        "captured_at": "2026-04-30T03:26:30+00:00",
        "top_growth": [{"location": "src/leaky.py:88", "size_diff_bytes": 64 * 1024 * 1024}],
        "top_allocations": [{"location": "src/cache.py:21", "size_bytes": 32 * 1024 * 1024}],
        "top_object_types": [{"type": "dict", "count": 4200}],
    }
    diagnostics_calls: list[int] = []
    published_calls: list[tuple[dict[str, object], float]] = []
    built_snapshots: list[dict[str, object]] = []

    monitor = MemoryMonitor(
        interval_seconds=60.0,
        history_limit=10,
        leak_threshold_bytes=64 * 1024 * 1024,
        min_samples_for_alert=2,
        alert_cooldown_seconds=0.0,
        heavy_diagnostics_enabled=True,
    )
    monitor._collect_process_sample = lambda: next(samples)  # type: ignore[method-assign]

    def _capture() -> dict[str, object]:
        diagnostics_calls.append(1)
        return alert_snapshot

    monitor._capture_diagnostics_snapshot = _capture  # type: ignore[method-assign]

    def _fake_build_instance_snapshot(
        *,
        instance_id: str | None = None,
        captured_at: object | None = None,
        summary: dict[str, object] | None = None,
        details: dict[str, object] | None = None,
    ) -> dict[str, object]:
        snapshot = {
            "instance_id": instance_id,
            "captured_at": captured_at,
            "summary": summary,
            "details": details,
        }
        built_snapshots.append(snapshot)
        return snapshot

    async def _fake_publish_instance_snapshot(
        snapshot: dict[str, object],
        *,
        interval_seconds: float,
        redis_client: object | None = None,
    ) -> dict[str, object]:
        del redis_client
        published_calls.append((snapshot, interval_seconds))
        return snapshot

    monkeypatch.setattr(
        distributed_memory_health,
        "build_instance_snapshot",
        _fake_build_instance_snapshot,
    )
    monkeypatch.setattr(
        distributed_memory_health,
        "publish_instance_snapshot",
        _fake_publish_instance_snapshot,
    )

    await monitor._sample_once()
    await monitor._sample_once()

    assert diagnostics_calls == [1]
    assert len(built_snapshots) == 2
    assert built_snapshots[-1]["captured_at"] == "2026-04-30T03:26:30+00:00"
    assert built_snapshots[-1]["summary"] == {
        "available": True,
        "rss_bytes": 220 * 1024 * 1024,
        "vms_bytes": 440 * 1024 * 1024,
        "thread_count": 12,
        "open_file_count": 4,
        "history_size": 2,
        "growth_bytes": 120 * 1024 * 1024,
        "suspected_leak": True,
        "alerts_24h": 1,
        "heavy_diagnostics_enabled": True,
        "tracemalloc_tracing": False,
        "sample_interval_seconds": 60.0,
        "baseline_reset_at": None,
        "last_sample_at": second_timestamp,
        "last_error": None,
        "checkpointer": _CHECKPOINTER_SUMMARY,
    }
    assert built_snapshots[-1]["details"] == alert_snapshot
    assert published_calls[-1] == (built_snapshots[-1], 60.0)


@pytest.mark.asyncio
async def test_sample_once_records_alert_when_heavy_diagnostics_times_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.monitoring.memory import MemoryMonitor

    first_timestamp = datetime(2026, 4, 30, 3, 25, tzinfo=timezone.utc)
    second_timestamp = first_timestamp + timedelta(minutes=1)
    samples = iter(
        [
            {
                "timestamp": first_timestamp,
                "rss_bytes": 100 * 1024 * 1024,
                "vms_bytes": 400 * 1024 * 1024,
                "thread_count": 12,
                "open_file_count": 3,
            },
            {
                "timestamp": second_timestamp,
                "rss_bytes": 220 * 1024 * 1024,
                "vms_bytes": 440 * 1024 * 1024,
                "thread_count": 12,
                "open_file_count": 4,
            },
        ]
    )
    built_snapshots: list[dict[str, object]] = []
    published_calls: list[tuple[dict[str, object], float]] = []

    monitor = MemoryMonitor(
        interval_seconds=60.0,
        history_limit=10,
        leak_threshold_bytes=64 * 1024 * 1024,
        min_samples_for_alert=2,
        alert_cooldown_seconds=300.0,
        heavy_diagnostics_enabled=True,
    )
    monitor._collect_process_sample = lambda: next(samples)  # type: ignore[method-assign]

    def _capture() -> dict[str, object]:
        raise AssertionError("timeout is injected before diagnostics run")

    async def _run_monitor_blocking(func, *, timeout: float = 10.0):  # type: ignore[no-untyped-def]
        del timeout
        if func is _capture:
            raise asyncio.TimeoutError
        return func()

    monitor._capture_diagnostics_snapshot = _capture  # type: ignore[method-assign]
    monitor._run_monitor_blocking = _run_monitor_blocking  # type: ignore[method-assign]

    def _fake_build_instance_snapshot(
        *,
        instance_id: str | None = None,
        captured_at: object | None = None,
        summary: dict[str, object] | None = None,
        details: dict[str, object] | None = None,
    ) -> dict[str, object]:
        snapshot = {
            "instance_id": instance_id,
            "captured_at": captured_at,
            "summary": summary,
            "details": details,
        }
        built_snapshots.append(snapshot)
        return snapshot

    async def _fake_publish_instance_snapshot(
        snapshot: dict[str, object],
        *,
        interval_seconds: float,
        redis_client: object | None = None,
    ) -> dict[str, object]:
        del redis_client
        published_calls.append((snapshot, interval_seconds))
        return snapshot

    monkeypatch.setattr(
        distributed_memory_health,
        "build_instance_snapshot",
        _fake_build_instance_snapshot,
    )
    monkeypatch.setattr(
        distributed_memory_health,
        "publish_instance_snapshot",
        _fake_publish_instance_snapshot,
    )

    await monitor._sample_once()
    await monitor._sample_once()

    diagnostics = await monitor.get_diagnostics()

    assert diagnostics["last_error"] == "heavy diagnostics timed out"
    assert diagnostics["last_alert"] == {
        "captured_at": "2026-04-30T03:26:00+00:00",
        "heavy_diagnostics_enabled": True,
        "reason": "heavy_diagnostics_timeout",
        "top_growth": [],
        "top_allocations": [],
        "top_object_types": [],
    }
    assert built_snapshots[-1]["details"] == diagnostics["last_alert"]
    assert built_snapshots[-1]["summary"]["last_error"] == "heavy diagnostics timed out"
    assert published_calls[-1] == (built_snapshots[-1], 60.0)


@pytest.mark.asyncio
async def test_sample_once_swallow_publish_failures_without_breaking_sampling(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.monitoring.memory import MemoryMonitor

    sample_timestamp = datetime(2026, 4, 30, 3, 25, tzinfo=timezone.utc)
    built_snapshots: list[dict[str, object]] = []
    publish_attempts: list[tuple[dict[str, object], float]] = []

    monitor = MemoryMonitor(
        interval_seconds=30.0,
        history_limit=10,
        leak_threshold_bytes=1024 * 1024 * 1024,
        min_samples_for_alert=2,
        heavy_diagnostics_enabled=False,
    )
    monitor._collect_process_sample = lambda: {  # type: ignore[method-assign]
        "timestamp": sample_timestamp,
        "rss_bytes": 220 * 1024 * 1024,
        "vms_bytes": 440 * 1024 * 1024,
        "thread_count": 12,
        "open_file_count": 4,
    }

    def _fake_build_instance_snapshot(
        *,
        instance_id: str | None = None,
        captured_at: object | None = None,
        summary: dict[str, object] | None = None,
        details: dict[str, object] | None = None,
    ) -> dict[str, object]:
        snapshot = {
            "instance_id": instance_id,
            "captured_at": captured_at,
            "summary": summary,
            "details": details,
        }
        built_snapshots.append(snapshot)
        return snapshot

    async def _failing_publish_instance_snapshot(
        snapshot: dict[str, object],
        *,
        interval_seconds: float,
        redis_client: object | None = None,
    ) -> dict[str, object]:
        del snapshot, interval_seconds, redis_client
        publish_attempts.append((built_snapshots[-1], 30.0))
        raise RuntimeError("redis unavailable")

    monkeypatch.setattr(
        distributed_memory_health,
        "build_instance_snapshot",
        _fake_build_instance_snapshot,
    )
    monkeypatch.setattr(
        distributed_memory_health,
        "publish_instance_snapshot",
        _failing_publish_instance_snapshot,
    )

    await monitor._sample_once()

    summary = await monitor.get_summary()
    diagnostics = await monitor.get_diagnostics(refresh=True)

    assert len(built_snapshots) == 1
    assert publish_attempts == [(built_snapshots[0], 30.0)]
    assert summary["available"] is True
    assert summary["rss_bytes"] == 220 * 1024 * 1024
    assert summary["history_size"] == 1
    assert diagnostics["last_alert"] is None
    assert diagnostics["current_snapshot"] == {
        "captured_at": diagnostics["current_snapshot"]["captured_at"],
        "heavy_diagnostics_enabled": False,
        "reason": "heavy_diagnostics_disabled",
        "top_growth": [],
        "top_allocations": [],
        "top_object_types": [],
    }


@pytest.mark.asyncio
async def test_get_diagnostics_skips_live_snapshot_when_refresh_is_false() -> None:
    from src.infra.monitoring.memory import MemoryMonitor

    monitor = MemoryMonitor(interval_seconds=60.0, history_limit=10)
    monitor._history.append(
        {
            "timestamp": datetime(2026, 4, 30, 3, 25, tzinfo=timezone.utc),
            "rss_bytes": 220 * 1024 * 1024,
            "vms_bytes": 440 * 1024 * 1024,
            "thread_count": 12,
            "open_file_count": 4,
        }
    )
    called = False

    def _capture() -> dict[str, object]:
        nonlocal called
        called = True
        return {"captured_at": "2026-04-30T03:26:00+00:00"}

    monitor._capture_diagnostics_snapshot = _capture  # type: ignore[method-assign]

    diagnostics = await monitor.get_diagnostics(refresh=False)

    assert diagnostics["current_snapshot"] is None
    assert called is False


@pytest.mark.asyncio
async def test_get_diagnostics_refreshes_live_snapshot_when_requested() -> None:
    from src.infra.monitoring.memory import MemoryMonitor

    monitor = MemoryMonitor(
        interval_seconds=60.0,
        history_limit=10,
        heavy_diagnostics_enabled=True,
    )
    monitor._history.append(
        {
            "timestamp": datetime(2026, 4, 30, 3, 25, tzinfo=timezone.utc),
            "rss_bytes": 220 * 1024 * 1024,
            "vms_bytes": 440 * 1024 * 1024,
            "thread_count": 12,
            "open_file_count": 4,
        }
    )

    monitor._capture_diagnostics_snapshot = lambda: {  # type: ignore[method-assign]
        "captured_at": "2026-04-30T03:26:00+00:00"
    }

    diagnostics = await monitor.get_diagnostics(refresh=True)

    assert diagnostics["current_snapshot"] == {"captured_at": "2026-04-30T03:26:00+00:00"}


@pytest.mark.asyncio
async def test_monitor_skips_heavy_diagnostics_when_disabled() -> None:
    from src.infra.monitoring.memory import MemoryMonitor

    rss_values = iter([100 * 1024 * 1024, 150 * 1024 * 1024, 230 * 1024 * 1024])
    diagnostics_calls: list[int] = []

    monitor = MemoryMonitor(
        interval_seconds=60.0,
        history_limit=10,
        leak_threshold_bytes=64 * 1024 * 1024,
        min_samples_for_alert=3,
        alert_cooldown_seconds=0.0,
        heavy_diagnostics_enabled=False,
    )

    monitor._collect_process_sample = lambda: {  # type: ignore[method-assign]
        "rss_bytes": next(rss_values),
        "vms_bytes": 400 * 1024 * 1024,
        "thread_count": 12,
        "open_file_count": 3,
    }

    def _fake_capture_diagnostics() -> dict[str, object]:
        diagnostics_calls.append(1)
        return {"captured_at": "unexpected"}

    monitor._capture_diagnostics_snapshot = _fake_capture_diagnostics  # type: ignore[method-assign]

    await monitor._sample_once()
    await monitor._sample_once()
    await monitor._sample_once()

    summary = await monitor.get_summary()
    diagnostics = await monitor.get_diagnostics(refresh=True)

    assert summary["suspected_leak"] is True
    assert summary["heavy_diagnostics_enabled"] is False
    assert diagnostics_calls == []
    assert diagnostics["last_alert"] is None
    assert diagnostics["current_snapshot"]["reason"] == "heavy_diagnostics_disabled"


@pytest.mark.asyncio
async def test_start_does_not_enable_tracemalloc_when_heavy_diagnostics_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.monitoring.memory import MemoryMonitor

    monitor = MemoryMonitor(heavy_diagnostics_enabled=False)
    start_calls: list[int] = []
    stop_calls: list[int] = []
    release_loop = asyncio.Event()
    loop_started = asyncio.Event()

    monkeypatch.setattr("src.infra.monitoring.memory.tracemalloc.is_tracing", lambda: False)
    monkeypatch.setattr(
        "src.infra.monitoring.memory.tracemalloc.start",
        lambda *_args, **_kwargs: start_calls.append(1),
    )
    monkeypatch.setattr(
        "src.infra.monitoring.memory.tracemalloc.stop",
        lambda: stop_calls.append(1),
    )

    async def _fake_run_loop() -> None:
        loop_started.set()
        await release_loop.wait()

    monkeypatch.setattr(monitor, "_run_loop", _fake_run_loop)

    await monitor.start()
    await asyncio.wait_for(loop_started.wait(), timeout=0.05)
    release_loop.set()
    await monitor.stop()

    assert start_calls == []
    assert stop_calls == []


@pytest.mark.asyncio
async def test_close_memory_monitor_stops_and_releases_singleton() -> None:
    from src.infra.monitoring import memory as memory_module
    from src.infra.monitoring.memory import MemoryMonitor

    monitor = MemoryMonitor(interval_seconds=60.0, history_limit=10)
    memory_module._memory_monitor = monitor

    await memory_module.close_memory_monitor()

    assert memory_module._memory_monitor is None


@pytest.mark.asyncio
async def test_close_memory_monitor_does_not_create_monitor_when_unused() -> None:
    from src.infra.monitoring import memory as memory_module

    memory_module._memory_monitor = None

    await memory_module.close_memory_monitor()

    assert memory_module._memory_monitor is None


@pytest.mark.asyncio
async def test_start_returns_without_waiting_for_initial_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.monitoring.memory import MemoryMonitor

    monitor = MemoryMonitor(interval_seconds=60.0, history_limit=10)
    release_loop = asyncio.Event()
    loop_started = asyncio.Event()

    def _blocking_reset_baseline() -> None:
        time.sleep(0.2)

    async def _fake_run_loop() -> None:
        loop_started.set()
        await release_loop.wait()

    monkeypatch.setattr(monitor, "reset_baseline", _blocking_reset_baseline)
    monkeypatch.setattr(monitor, "_run_loop", _fake_run_loop)

    await asyncio.wait_for(monitor.start(), timeout=0.05)
    await asyncio.wait_for(loop_started.wait(), timeout=0.05)

    release_loop.set()
    await monitor.stop()


@pytest.mark.asyncio
async def test_alert_log_and_summary_track_rolling_24h_alert_count(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """#1217：每条报警与 summary 携带滚动 24h 报警数，供巡检与 agent 活动量对账。"""
    from src.infra.monitoring.memory import MemoryMonitor
    from src.infra.utils.datetime import utc_now

    rss_values = iter([100, 150, 230, 260])
    started = utc_now()
    timestamps = iter(
        [
            started,
            started + timedelta(minutes=10),
            started + timedelta(minutes=20),
            started + timedelta(minutes=30),
        ]
    )

    monitor = MemoryMonitor(
        interval_seconds=60.0,
        history_limit=10,
        leak_threshold_bytes=64 * 1024 * 1024,
        min_samples_for_alert=3,
        alert_cooldown_seconds=0.0,
        heavy_diagnostics_enabled=False,
    )

    def _fake_process_sample() -> dict[str, object]:
        return {
            "timestamp": next(timestamps),
            "rss_bytes": next(rss_values) * 1024 * 1024,
            "vms_bytes": 400 * 1024 * 1024,
            "thread_count": 12,
            "open_file_count": 3,
        }

    monitor._collect_process_sample = _fake_process_sample  # type: ignore[method-assign]
    monitor._build_distributed_snapshot_locked = lambda: asyncio.sleep(0, result=None)  # type: ignore[method-assign]

    with caplog.at_level("WARNING", logger="src.infra.monitoring.memory"):
        await monitor._sample_once()
        await monitor._sample_once()
        await monitor._sample_once()

    assert "alerts_24h=1" in caplog.text

    await monitor._sample_once()

    assert "alerts_24h=2" in caplog.text
    summary = await monitor.get_summary()
    assert summary["alerts_24h"] == 2


@pytest.mark.asyncio
async def test_alert_count_window_drops_entries_older_than_24h() -> None:
    from src.infra.monitoring.memory import MemoryMonitor
    from src.infra.utils.datetime import utc_now

    monitor = MemoryMonitor(heavy_diagnostics_enabled=False)
    now = utc_now()
    monitor._alert_timestamps.append(now - timedelta(hours=25))
    monitor._alert_timestamps.append(now - timedelta(hours=1))
    monitor._alert_timestamps.append(now)

    assert monitor._count_recent_alerts(now) == 2


@pytest.mark.asyncio
async def test_reset_baseline_clears_rolling_alert_count() -> None:
    from src.infra.monitoring.memory import MemoryMonitor
    from src.infra.utils.datetime import utc_now

    monitor = MemoryMonitor(heavy_diagnostics_enabled=False)

    def _fake_process_sample() -> dict[str, object]:
        return {
            "rss_bytes": 100 * 1024 * 1024,
            "vms_bytes": 200 * 1024 * 1024,
            "thread_count": 4,
            "open_file_count": 5,
        }

    monitor._collect_process_sample = _fake_process_sample  # type: ignore[method-assign]
    monitor._alert_timestamps.append(utc_now())

    await monitor.reset_baseline()

    assert monitor._count_recent_alerts(utc_now()) == 0
