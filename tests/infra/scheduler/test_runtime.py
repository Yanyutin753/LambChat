from __future__ import annotations

import pytest

from src.infra.scheduler import runtime as runtime_module
from src.infra.scheduler.runtime import RuntimeScheduler, ScheduledJob


async def _noop_handler() -> None:
    return None


@pytest.mark.asyncio
async def test_close_runtime_scheduler_stops_clears_jobs_and_releases_singleton() -> None:
    scheduler = RuntimeScheduler()
    scheduler.register_job(
        ScheduledJob.from_interval(
            id="test-job",
            interval_seconds=60,
            handler=_noop_handler,
        )
    )
    runtime_module._runtime_scheduler = scheduler

    await runtime_module.close_runtime_scheduler()

    assert scheduler.has_job("test-job") is False
    assert scheduler._scheduled_intervals == {}
    assert runtime_module._runtime_scheduler is None


async def test_job_uses_submitted_fire_time_and_resets_context():
    from datetime import datetime, timezone

    from apscheduler.events import EVENT_JOB_SUBMITTED, JobSubmissionEvent

    observed = []

    async def handler():
        observed.append(runtime_module.SCHEDULED_FIRE_TIME.get())

    scheduler = RuntimeScheduler()
    scheduler.register_job(ScheduledJob.from_interval("job", 60, handler))
    fire_time = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)
    scheduler._record_scheduler_event(
        JobSubmissionEvent(EVENT_JOB_SUBMITTED, "job", "default", [fire_time])
    )
    await scheduler._make_job_runner("job")()
    assert observed == [fire_time]
    assert runtime_module.SCHEDULED_FIRE_TIME.get() is None


async def test_missed_fire_time_does_not_leak_into_next_execution():
    from datetime import datetime, timedelta, timezone

    from apscheduler.events import (
        EVENT_JOB_MISSED,
        EVENT_JOB_SUBMITTED,
        JobExecutionEvent,
        JobSubmissionEvent,
    )

    observed = []

    async def handler():
        observed.append(runtime_module.SCHEDULED_FIRE_TIME.get())

    scheduler = RuntimeScheduler()
    scheduler.register_job(ScheduledJob.from_interval("job", 60, handler))
    missed = datetime(2026, 10, 17, 12, 0, tzinfo=timezone.utc)
    scheduled = missed + timedelta(minutes=1)
    scheduler._record_scheduler_event(
        JobSubmissionEvent(EVENT_JOB_SUBMITTED, "job", "default", [missed])
    )
    scheduler._record_scheduler_event(JobExecutionEvent(EVENT_JOB_MISSED, "job", "default", missed))
    scheduler._record_scheduler_event(
        JobSubmissionEvent(EVENT_JOB_SUBMITTED, "job", "default", [scheduled])
    )
    await scheduler._make_job_runner("job")()
    assert observed == [scheduled]
