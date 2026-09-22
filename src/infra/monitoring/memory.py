"""Process memory monitoring and diagnostics."""

from __future__ import annotations

import asyncio
import gc
import os
import tracemalloc
from collections import Counter, deque
from datetime import datetime
from typing import Any

from src.infra.async_utils import run_long_blocking_io
from src.infra.logging import get_logger
from src.infra.utils.datetime import utc_now
from src.kernel.config import settings

try:
    import psutil
except ImportError:  # pragma: no cover - dependency is expected to be installed
    psutil = None

logger = get_logger(__name__)

_BLOCKING_SAMPLE_TIMEOUT_SECONDS = 10.0


def _format_trace_location(trace: tracemalloc.Frame) -> str:
    return f"{trace.filename}:{trace.lineno}"


def _format_bytes_as_mb(value: int) -> str:
    return f"{round(value / 1024 / 1024, 2)}MB"


class MemoryMonitor:
    """Background process memory sampler with on-demand diagnostics."""

    def __init__(
        self,
        *,
        interval_seconds: float | None = None,
        history_limit: int | None = None,
        leak_threshold_bytes: int | None = None,
        min_samples_for_alert: int | None = None,
        alert_cooldown_seconds: float | None = None,
        traceback_limit: int | None = None,
        top_stats_limit: int | None = None,
        gc_object_limit: int | None = None,
        heavy_diagnostics_enabled: bool | None = None,
    ) -> None:
        self.interval_seconds = (
            interval_seconds
            if interval_seconds is not None
            else settings.MEMORY_MONITOR_INTERVAL_SECONDS
        )
        self.history_limit = (
            history_limit if history_limit is not None else settings.MEMORY_MONITOR_HISTORY_LIMIT
        )
        self.leak_threshold_bytes = (
            leak_threshold_bytes
            if leak_threshold_bytes is not None
            else settings.MEMORY_MONITOR_LEAK_THRESHOLD_MB * 1024 * 1024
        )
        self.min_samples_for_alert = (
            min_samples_for_alert
            if min_samples_for_alert is not None
            else settings.MEMORY_MONITOR_MIN_SAMPLES
        )
        self.alert_cooldown_seconds = (
            alert_cooldown_seconds
            if alert_cooldown_seconds is not None
            else settings.MEMORY_MONITOR_ALERT_COOLDOWN_SECONDS
        )
        self.traceback_limit = (
            traceback_limit
            if traceback_limit is not None
            else settings.MEMORY_MONITOR_TRACEBACK_LIMIT
        )
        self.top_stats_limit = (
            top_stats_limit
            if top_stats_limit is not None
            else settings.MEMORY_MONITOR_TOP_STATS_LIMIT
        )
        self.gc_object_limit = (
            gc_object_limit
            if gc_object_limit is not None
            else settings.MEMORY_MONITOR_GC_OBJECT_LIMIT
        )
        self.heavy_diagnostics_enabled = (
            heavy_diagnostics_enabled
            if heavy_diagnostics_enabled is not None
            else settings.MEMORY_MONITOR_HEAVY_DIAGNOSTICS or settings.DEBUG
        )

        self._history: deque[dict[str, Any]] = deque(maxlen=max(1, self.history_limit))
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._state_lock = asyncio.Lock()
        self._process = psutil.Process(os.getpid()) if psutil is not None else None
        self._baseline_snapshot: tracemalloc.Snapshot | None = None
        self._baseline_reset_at: datetime | None = None
        self._started_tracemalloc = False
        self._last_alert: dict[str, Any] | None = None
        self._last_alert_at: datetime | None = None
        self._last_error: str | None = None

    async def _run_monitor_blocking(
        self, func, *, timeout: float = _BLOCKING_SAMPLE_TIMEOUT_SECONDS
    ):
        return await run_long_blocking_io(func, timeout=timeout)

    async def start(self) -> None:
        """Start the background monitor if enabled."""
        if self._running or not settings.MEMORY_MONITOR_ENABLED:
            return
        self._running = True

        if psutil is None:
            self._last_error = "psutil is not installed"
            logger.warning("[MemoryMonitor] psutil is unavailable; monitoring disabled")
            return

        if self.heavy_diagnostics_enabled and not tracemalloc.is_tracing():
            tracemalloc.start(self.traceback_limit)
            self._started_tracemalloc = True

        self._task = asyncio.create_task(self._run_loop())
        self._task.add_done_callback(
            lambda task: task.exception() if not task.cancelled() else None
        )
        logger.info(
            "[MemoryMonitor] started interval=%ss threshold=%sMB",
            self.interval_seconds,
            round(self.leak_threshold_bytes / 1024 / 1024, 2),
        )

    async def stop(self) -> None:
        """Stop the background monitor."""
        self._running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        if self._started_tracemalloc and tracemalloc.is_tracing():
            tracemalloc.stop()
            self._started_tracemalloc = False

    async def _run_loop(self) -> None:
        if not self._history:
            try:
                await self.reset_baseline()
            except Exception as exc:
                self._last_error = str(exc)
                logger.warning(
                    "[MemoryMonitor] initial baseline capture failed: %s",
                    exc,
                    exc_info=True,
                )

        while self._running:
            try:
                await asyncio.sleep(self.interval_seconds)
                await self._sample_once()
            except asyncio.CancelledError:
                break
            except Exception as exc:  # pragma: no cover - defensive logging path
                self._last_error = str(exc)
                logger.warning("[MemoryMonitor] sampling failed: %s", exc, exc_info=True)

    async def _sample_once(self) -> None:
        distributed_snapshot: dict[str, Any] | None = None
        async with self._state_lock:
            sample = await self._run_monitor_blocking(self._collect_process_sample)
            sample.setdefault("timestamp", utc_now())
            self._history.append(sample)

            if self._is_suspicious_growth(sample["timestamp"]):
                now = sample["timestamp"]
                if self._should_emit_alert(now):
                    self._last_alert = None
                    if self.heavy_diagnostics_enabled:
                        try:
                            self._last_alert = await self._run_monitor_blocking(
                                self._capture_diagnostics_snapshot
                            )
                        except asyncio.TimeoutError:
                            self._last_error = "heavy diagnostics timed out"
                            self._last_alert = self._build_timeout_diagnostics_snapshot(
                                captured_at=now
                            )
                            logger.warning(
                                "[MemoryMonitor] heavy diagnostics timed out after %ss",
                                _BLOCKING_SAMPLE_TIMEOUT_SECONDS,
                            )
                    self._last_alert_at = now
                    alert_parts = [
                        f"rss={_format_bytes_as_mb(sample['rss_bytes'])}",
                        f"growth={_format_bytes_as_mb(self._growth_bytes())}",
                    ]
                    growth_summary = self._format_growth_summary(self._last_alert)
                    if growth_summary is not None:
                        alert_parts.append(f"top_growth={growth_summary}")
                    allocation_summary = self._format_allocation_summary(self._last_alert)
                    if allocation_summary is not None:
                        alert_parts.append(f"top_allocations={allocation_summary}")
                    object_summary = self._format_object_summary(self._last_alert)
                    if object_summary is not None:
                        alert_parts.append(f"top_objects={object_summary}")
                    logger.warning(
                        "[MemoryMonitor] suspicious memory growth detected %s",
                        " ".join(alert_parts),
                    )
            distributed_snapshot = await self._build_distributed_snapshot_locked()

        await self._publish_distributed_snapshot(distributed_snapshot)

    def _collect_process_sample(self) -> dict[str, Any]:
        if self._process is None:
            raise RuntimeError("psutil process is unavailable")

        memory = self._process.memory_info()
        try:
            open_file_count = self._process.num_fds()  # type: ignore[attr-defined]
        except (AttributeError, NotImplementedError):
            open_file_count = len(self._process.open_files())

        return {
            "timestamp": utc_now(),
            "rss_bytes": int(memory.rss),
            "vms_bytes": int(memory.vms),
            "thread_count": int(self._process.num_threads()),
            "open_file_count": int(open_file_count),
        }

    def _capture_diagnostics_snapshot(self) -> dict[str, Any]:
        return {
            "captured_at": utc_now().isoformat(),
            "heavy_diagnostics_enabled": self.heavy_diagnostics_enabled,
            "top_growth": self._build_growth_stats(),
            "top_allocations": self._build_allocation_stats(),
            "top_object_types": self._build_object_type_stats(),
        }

    async def reset_baseline(self) -> None:
        """Re-anchor growth tracking to the current process state."""
        distributed_snapshot: dict[str, Any] | None = None
        async with self._state_lock:
            sample = await self._run_monitor_blocking(self._collect_process_sample)
            sample.setdefault("timestamp", utc_now())

            if tracemalloc.is_tracing():
                try:
                    self._baseline_snapshot = await self._run_monitor_blocking(
                        tracemalloc.take_snapshot
                    )
                except RuntimeError:
                    self._baseline_snapshot = None
            else:
                self._baseline_snapshot = None

            self._baseline_reset_at = sample["timestamp"]
            self._history = deque([sample], maxlen=max(1, self.history_limit))
            self._last_alert = None
            self._last_alert_at = None
            distributed_snapshot = await self._build_distributed_snapshot_locked()

        await self._publish_distributed_snapshot(distributed_snapshot)

    def _format_growth_summary(self, diagnostics: dict[str, Any] | None) -> str | None:
        if not diagnostics:
            return None
        rows = diagnostics.get("top_growth") or []
        if not rows:
            return None
        return ", ".join(
            f"{row['location']} (+{_format_bytes_as_mb(int(row['size_diff_bytes']))})"
            for row in rows[:3]
        )

    def _format_allocation_summary(self, diagnostics: dict[str, Any] | None) -> str | None:
        if not diagnostics:
            return None
        rows = diagnostics.get("top_allocations") or []
        if not rows:
            return None
        return ", ".join(
            f"{row['location']} ({_format_bytes_as_mb(int(row['size_bytes']))})" for row in rows[:3]
        )

    def _format_object_summary(self, diagnostics: dict[str, Any] | None) -> str | None:
        if not diagnostics:
            return None
        rows = diagnostics.get("top_object_types") or []
        if not rows:
            return None
        return ", ".join(f"{row['type']}={int(row['count'])}" for row in rows[:3])

    def _build_growth_stats(self) -> list[dict[str, Any]]:
        if self._baseline_snapshot is None or not tracemalloc.is_tracing():
            return []

        snapshot = tracemalloc.take_snapshot()
        growth_stats = snapshot.compare_to(self._baseline_snapshot, "lineno")
        rows: list[dict[str, Any]] = []

        for stat in growth_stats:
            if stat.size_diff <= 0:
                continue
            rows.append(
                {
                    "location": _format_trace_location(stat.traceback[0]),
                    "size_diff_bytes": int(stat.size_diff),
                    "count_diff": int(stat.count_diff),
                }
            )
            if len(rows) >= self.top_stats_limit:
                break

        return rows

    def _build_allocation_stats(self) -> list[dict[str, Any]]:
        if not tracemalloc.is_tracing():
            return []

        snapshot = tracemalloc.take_snapshot()
        rows: list[dict[str, Any]] = []

        for stat in snapshot.statistics("lineno")[: self.top_stats_limit]:
            rows.append(
                {
                    "location": _format_trace_location(stat.traceback[0]),
                    "size_bytes": int(stat.size),
                    "count": int(stat.count),
                }
            )

        return rows

    def _build_object_type_stats(self) -> list[dict[str, Any]]:
        counts = Counter(type(obj).__name__ for obj in gc.get_objects())
        return [
            {"type": object_type, "count": count}
            for object_type, count in counts.most_common(self.gc_object_limit)
        ]

    def _growth_bytes(self) -> int:
        if len(self._history) < 2:
            return 0
        return int(self._history[-1]["rss_bytes"] - self._history[0]["rss_bytes"])

    def _is_suspicious_growth(self, sampled_at: datetime) -> bool:
        del sampled_at
        if len(self._history) < self.min_samples_for_alert:
            return False

        growth_bytes = self._growth_bytes()
        if growth_bytes < self.leak_threshold_bytes:
            return False

        rss_series = [sample["rss_bytes"] for sample in self._history]
        return all(current >= previous for previous, current in zip(rss_series, rss_series[1:]))

    def _should_emit_alert(self, now: datetime) -> bool:
        if self._last_alert_at is None:
            return True
        elapsed = (now - self._last_alert_at).total_seconds()
        return elapsed >= self.alert_cooldown_seconds

    def _get_summary_locked(self) -> dict[str, Any]:
        if not settings.MEMORY_MONITOR_ENABLED:
            return {"available": False, "reason": "disabled"}

        if psutil is None:
            return {
                "available": False,
                "reason": "psutil_unavailable",
                "last_error": self._last_error,
            }

        if not self._history:
            return {"available": False, "reason": "no_samples", "last_error": self._last_error}

        latest = self._history[-1]
        try:
            from src.infra.storage.checkpoint import get_checkpointer_diagnostics

            checkpointer = get_checkpointer_diagnostics()
        except Exception as exc:
            checkpointer = {"available": False, "last_error": str(exc)}
        return {
            "available": True,
            "rss_bytes": latest["rss_bytes"],
            "vms_bytes": latest["vms_bytes"],
            "thread_count": latest["thread_count"],
            "open_file_count": latest["open_file_count"],
            "history_size": len(self._history),
            "growth_bytes": self._growth_bytes(),
            "suspected_leak": self._is_suspicious_growth(latest["timestamp"]),
            "heavy_diagnostics_enabled": self.heavy_diagnostics_enabled,
            "tracemalloc_tracing": tracemalloc.is_tracing(),
            "sample_interval_seconds": self.interval_seconds,
            "baseline_reset_at": self._baseline_reset_at,
            "last_sample_at": latest["timestamp"],
            "last_error": self._last_error,
            "checkpointer": checkpointer,
        }

    def _build_disabled_current_snapshot_locked(
        self,
        *,
        captured_at: datetime | None = None,
    ) -> dict[str, Any]:
        return {
            "captured_at": (captured_at or utc_now()).isoformat(),
            "heavy_diagnostics_enabled": False,
            "reason": "heavy_diagnostics_disabled",
            "top_growth": [],
            "top_allocations": [],
            "top_object_types": [],
        }

    def _build_timeout_diagnostics_snapshot(
        self,
        *,
        captured_at: datetime | None = None,
    ) -> dict[str, Any]:
        return {
            "captured_at": (captured_at or utc_now()).isoformat(),
            "heavy_diagnostics_enabled": True,
            "reason": "heavy_diagnostics_timeout",
            "top_growth": [],
            "top_allocations": [],
            "top_object_types": [],
        }

    async def _resolve_snapshot_details_locked(self) -> dict[str, Any] | None:
        if not self._history:
            return None
        if self._last_alert is not None:
            return self._last_alert
        latest = self._history[-1]
        return self._build_disabled_current_snapshot_locked(
            captured_at=latest.get("timestamp") if isinstance(latest, dict) else None
        )

    async def _build_distributed_snapshot_locked(self) -> dict[str, Any] | None:
        if not self._history:
            return None

        from src.infra.monitoring.distributed_memory_health import build_instance_snapshot

        summary = self._get_summary_locked()
        details = await self._resolve_snapshot_details_locked()
        captured_at = details.get("captured_at") if isinstance(details, dict) else None
        return build_instance_snapshot(
            captured_at=captured_at,
            summary=summary,
            details=details,
        )

    async def _publish_distributed_snapshot(
        self,
        snapshot: dict[str, Any] | None,
    ) -> None:
        if snapshot is None:
            return

        try:
            from src.infra.monitoring.distributed_memory_health import publish_instance_snapshot

            await publish_instance_snapshot(snapshot, interval_seconds=self.interval_seconds)
        except Exception as exc:
            logger.warning(
                "[MemoryMonitor] failed to publish distributed snapshot: %s",
                exc,
                exc_info=True,
            )

    async def get_summary(self) -> dict[str, Any]:
        async with self._state_lock:
            return self._get_summary_locked()

    async def get_diagnostics(self, refresh: bool = False) -> dict[str, Any]:
        async with self._state_lock:
            summary = self._get_summary_locked()
            current_snapshot = self._last_alert
            if refresh and self._history and self.heavy_diagnostics_enabled:
                current_snapshot = await self._run_monitor_blocking(
                    self._capture_diagnostics_snapshot
                )
            elif refresh and self._history and not self.heavy_diagnostics_enabled:
                current_snapshot = self._build_disabled_current_snapshot_locked()

        diagnostics = {
            "summary": summary,
            "last_alert": self._last_alert,
            "last_error": self._last_error,
            "current_snapshot": current_snapshot,
        }

        return diagnostics


_memory_monitor: MemoryMonitor | None = None


def get_memory_monitor() -> MemoryMonitor:
    global _memory_monitor
    if _memory_monitor is None:
        _memory_monitor = MemoryMonitor()
    return _memory_monitor


async def close_memory_monitor() -> None:
    """Stop and release the singleton memory monitor without creating it."""
    global _memory_monitor
    monitor = _memory_monitor
    _memory_monitor = None
    if monitor is not None:
        await monitor.stop()
