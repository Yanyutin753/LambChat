"""Unified process-local scheduler built on APScheduler."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, TypeAlias

from apscheduler.jobstores.base import JobLookupError
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.base import BaseTrigger
from apscheduler.triggers.interval import IntervalTrigger

from src.infra.logging import get_logger
from src.infra.utils.datetime import utc_now

if TYPE_CHECKING:
    from src.kernel.extensions import PluginRuntime

logger = get_logger(__name__)

IntervalValue = int | Callable[[], int]
EnabledValue = bool | Callable[[], bool]
JobHandler = Callable[[], Awaitable[Any]]
TriggerValue: TypeAlias = BaseTrigger | Callable[[], BaseTrigger]


@dataclass(frozen=True, slots=True)
class ScheduledJob:
    """A managed scheduled task."""

    id: str
    trigger: TriggerValue
    handler: JobHandler
    enabled: EnabledValue = True
    name: str | None = None
    max_instances: int = 1
    coalesce: bool = True
    run_on_start: bool = False
    plugin_id: str | None = None

    # ── Factory helpers ────────────────────────────

    @classmethod
    def from_interval(
        cls,
        id: str,
        interval_seconds: IntervalValue,
        handler: JobHandler,
        **kwargs: Any,
    ) -> "ScheduledJob":
        """Create a ScheduledJob with an IntervalTrigger (backward compatible)."""
        if callable(interval_seconds):

            def _make_trigger() -> BaseTrigger:
                return IntervalTrigger(seconds=max(1, int(interval_seconds())))

            return cls(id=id, trigger=_make_trigger, handler=handler, **kwargs)
        return cls(
            id=id,
            trigger=IntervalTrigger(seconds=max(1, int(interval_seconds))),
            handler=handler,
            **kwargs,
        )


class RuntimeScheduler:
    """Small APScheduler facade for LambChat runtime services."""

    def __init__(self) -> None:
        self._scheduler: AsyncIOScheduler | None = None
        self._jobs: dict[str, ScheduledJob] = {}
        self._scheduled_intervals: dict[str, int] = {}
        self._plugin_runtime: PluginRuntime | None = None

    # ── Public API ─────────────────────────────────

    def register_interval_job(self, job: ScheduledJob) -> None:
        """Register or replace an interval job (backward compatible)."""
        self.register_job(job)

    def register_job(self, job: ScheduledJob) -> None:
        """Register or replace a scheduled job (supports interval and cron)."""
        if not job.id:
            raise ValueError("scheduled job id is required")
        self._jobs[job.id] = job
        logger.info(
            "[Scheduler] registered job %s trigger=%s run_on_start=%s",
            job.id,
            type(self._resolve_trigger(job)).__name__,
            job.run_on_start,
        )
        if self._scheduler is not None:
            self._add_or_replace_job(job)

    def set_plugin_runtime(self, runtime: PluginRuntime | None) -> None:
        """Attach the current Plugin Runtime for plugin-owned job guards."""
        self._plugin_runtime = runtime

    def unregister_job(self, job_id: str) -> None:
        """Remove a job from the scheduler."""
        self._jobs.pop(job_id, None)
        self._scheduled_intervals.pop(job_id, None)
        if self._scheduler is not None:
            try:
                self._scheduler.remove_job(job_id)
            except JobLookupError:
                pass
        logger.info("[Scheduler] unregistered job %s", job_id)

    def has_job(self, job_id: str) -> bool:
        """Check whether a job is registered."""
        return job_id in self._jobs

    def start(self) -> None:
        """Start APScheduler and add all registered jobs."""
        if self._scheduler is not None and getattr(self._scheduler, "running", False):
            return
        self._scheduler = AsyncIOScheduler(timezone="UTC")
        self._scheduled_intervals.clear()
        for job in self._jobs.values():
            self._add_or_replace_job(job)
        self._scheduler.start()
        logger.info("[Scheduler] started with %d jobs", len(self._jobs))

    async def stop(self) -> None:
        """Stop APScheduler without waiting for long-running jobs."""
        if self._scheduler is None:
            return
        scheduler = self._scheduler
        self._scheduler = None
        self._scheduled_intervals.clear()
        shutdown_result = scheduler.shutdown(wait=False)
        if inspect.isawaitable(shutdown_result):
            await shutdown_result
        logger.info("[Scheduler] stopped")

    def clear(self) -> None:
        """Release registered job handlers and interval bookkeeping."""
        self._jobs.clear()
        self._scheduled_intervals.clear()

    async def run_job_now(self, job_id: str) -> Any:
        """Run a registered job immediately; mainly useful for tests and admin hooks."""
        job = self._jobs[job_id]
        return await self._run_job(job)

    # ── Internal ───────────────────────────────────

    def _add_or_replace_job(self, job: ScheduledJob) -> None:
        if self._scheduler is None:
            return
        trigger = self._resolve_trigger(job)
        # Track interval for legacy dynamic-refresh support
        if isinstance(trigger, IntervalTrigger):
            self._scheduled_intervals[job.id] = trigger.interval_length
        self._scheduler.add_job(
            self._make_job_runner(job.id),
            trigger=trigger,
            id=job.id,
            name=job.name or job.id,
            replace_existing=True,
            coalesce=job.coalesce,
            max_instances=job.max_instances,
            **({"next_run_time": utc_now()} if job.run_on_start else {}),
        )
        logger.info(
            "[Scheduler] scheduled job %s with trigger=%s%s",
            job.id,
            type(trigger).__name__,
            " starting now" if job.run_on_start else "",
        )

    def _make_job_runner(self, job_id: str) -> Callable[[], Awaitable[Any]]:
        async def _runner() -> Any:
            job = self._jobs[job_id]
            return await self._run_job(job)

        return _runner

    async def _run_job(self, job: ScheduledJob) -> Any:
        try:
            if not self._resolve_enabled(job):
                return {"skipped": True, "reason": "disabled"}
            plugin_skip = self._plugin_skip_reason(job)
            if plugin_skip is not None:
                return plugin_skip
            result = await job.handler()
            return result
        except Exception as exc:
            logger.warning("[Scheduler] job %s failed: %s", job.id, exc)
            raise
        finally:
            self._refresh_trigger_if_needed(job)

    def _refresh_trigger_if_needed(self, job: ScheduledJob) -> None:
        """Reschedule if the trigger is a callable that may have changed."""
        if self._scheduler is None:
            return
        if not callable(job.trigger):
            return
        # Only refresh interval-style callable triggers (legacy pattern)
        new_trigger = self._resolve_trigger(job)
        if isinstance(new_trigger, IntervalTrigger):
            current = self._scheduled_intervals.get(job.id)
            if current != new_trigger.interval_length:
                self._scheduler.reschedule_job(job.id, trigger=new_trigger)
                self._scheduled_intervals[job.id] = new_trigger.interval_length

    @staticmethod
    def _resolve_trigger(job: ScheduledJob) -> BaseTrigger:
        """Resolve the trigger, evaluating callables."""
        trigger = job.trigger
        if callable(trigger):
            return trigger()
        return trigger

    @staticmethod
    def _resolve_interval_seconds(job: ScheduledJob) -> int:
        """Legacy helper: resolve interval from an IntervalTrigger-based job."""
        from apscheduler.triggers.interval import IntervalTrigger

        trigger = RuntimeScheduler._resolve_trigger(job)
        if isinstance(trigger, IntervalTrigger):
            return max(1, int(trigger.interval_length))
        return 0

    @staticmethod
    def _resolve_enabled(job: ScheduledJob) -> bool:
        value = job.enabled() if callable(job.enabled) else job.enabled
        return bool(value)

    def _plugin_skip_reason(self, job: ScheduledJob) -> dict[str, str] | None:
        if not job.plugin_id:
            return None
        if self._plugin_runtime is None:
            return {
                "skipped": True,
                "reason": "plugin_runtime_unavailable",
                "plugin_id": job.plugin_id,
            }
        try:
            self._plugin_runtime.ensure_scheduler_job_available(job.id)
        except Exception as exc:  # noqa: BLE001 - scheduler guard must not run plugin jobs open
            return {
                "skipped": True,
                "reason": "plugin_unavailable",
                "plugin_id": job.plugin_id,
                "message": str(exc),
            }
        return None


_runtime_scheduler: RuntimeScheduler | None = None


def get_runtime_scheduler() -> RuntimeScheduler:
    global _runtime_scheduler
    if _runtime_scheduler is None:
        _runtime_scheduler = RuntimeScheduler()
    return _runtime_scheduler


async def close_runtime_scheduler() -> None:
    """Stop and release the process-local scheduler without creating it."""
    global _runtime_scheduler
    scheduler = _runtime_scheduler
    _runtime_scheduler = None
    if scheduler is None:
        return
    await scheduler.stop()
    scheduler.clear()
