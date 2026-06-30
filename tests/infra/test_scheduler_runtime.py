from __future__ import annotations

from typing import Any

import pytest

from src.infra.scheduler.runtime import RuntimeScheduler, ScheduledJob
from src.kernel.extensions import PluginManifest, PluginRuntime


class _FakeJob:
    def __init__(self, job_id: str) -> None:
        self.id = job_id


class _FakeAsyncIOScheduler:
    instances: list["_FakeAsyncIOScheduler"] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.added_jobs: list[dict[str, Any]] = []
        self.rescheduled_jobs: list[dict[str, Any]] = []
        self.started = False
        self.shutdown_wait: bool | None = None
        self.running = False
        _FakeAsyncIOScheduler.instances.append(self)

    def add_job(self, func: Any, trigger: Any, **kwargs: Any) -> _FakeJob:
        self.added_jobs.append({"func": func, "trigger": trigger, "kwargs": kwargs})
        return _FakeJob(str(kwargs["id"]))

    def reschedule_job(self, job_id: str, trigger: Any) -> None:
        self.rescheduled_jobs.append({"id": job_id, "trigger": trigger})

    def remove_job(self, job_id: str) -> None:
        pass

    def start(self) -> None:
        self.started = True
        self.running = True

    def shutdown(self, wait: bool = True) -> None:
        self.shutdown_wait = wait
        self.running = False


@pytest.fixture(autouse=True)
def reset_fake_scheduler() -> None:
    _FakeAsyncIOScheduler.instances.clear()


def test_start_registers_interval_job_with_apscheduler(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.infra.scheduler import runtime as scheduler_module

    monkeypatch.setattr(scheduler_module, "AsyncIOScheduler", _FakeAsyncIOScheduler)
    runtime_scheduler = RuntimeScheduler()

    async def handler() -> None:
        return None

    runtime_scheduler.register_interval_job(
        ScheduledJob.from_interval(
            id="memory.compaction", interval_seconds=lambda: 30, handler=handler
        )
    )

    runtime_scheduler.start()

    fake = _FakeAsyncIOScheduler.instances[-1]
    assert fake.started is True
    assert len(fake.added_jobs) == 1
    added = fake.added_jobs[0]
    assert added["kwargs"]["id"] == "memory.compaction"
    assert added["kwargs"]["replace_existing"] is True
    assert added["kwargs"]["coalesce"] is True
    assert added["kwargs"]["max_instances"] == 1
    assert added["trigger"].interval.total_seconds() == 30
    assert "next_run_time" not in added["kwargs"]


def test_start_can_register_job_to_run_immediately(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.infra.scheduler import runtime as scheduler_module

    monkeypatch.setattr(scheduler_module, "AsyncIOScheduler", _FakeAsyncIOScheduler)
    runtime_scheduler = RuntimeScheduler()

    async def handler() -> None:
        return None

    runtime_scheduler.register_interval_job(
        ScheduledJob.from_interval(
            id="memory.compaction",
            interval_seconds=30,
            handler=handler,
            run_on_start=True,
        )
    )

    runtime_scheduler.start()

    added = _FakeAsyncIOScheduler.instances[-1].added_jobs[0]
    assert added["kwargs"]["id"] == "memory.compaction"
    assert added["kwargs"]["next_run_time"] is not None


@pytest.mark.asyncio
async def test_run_job_now_skips_disabled_jobs() -> None:
    calls = 0
    runtime_scheduler = RuntimeScheduler()

    async def handler() -> None:
        nonlocal calls
        calls += 1

    runtime_scheduler.register_interval_job(
        ScheduledJob.from_interval(
            id="disabled.job",
            interval_seconds=60,
            handler=handler,
            enabled=lambda: False,
        )
    )

    result = await runtime_scheduler.run_job_now("disabled.job")

    assert result == {"skipped": True, "reason": "disabled"}
    assert calls == 0


@pytest.mark.asyncio
async def test_plugin_owned_job_skips_when_plugin_runtime_is_unavailable() -> None:
    calls = 0
    runtime_scheduler = RuntimeScheduler()

    async def handler() -> None:
        nonlocal calls
        calls += 1

    runtime_scheduler.register_interval_job(
        ScheduledJob.from_interval(
            id="feedback.sync",
            interval_seconds=60,
            handler=handler,
            plugin_id="feedback",
        )
    )

    result = await runtime_scheduler.run_job_now("feedback.sync")

    assert result == {
        "skipped": True,
        "reason": "plugin_runtime_unavailable",
        "plugin_id": "feedback",
    }
    assert calls == 0


@pytest.mark.asyncio
async def test_plugin_owned_job_runs_only_when_plugin_scheduler_job_is_available() -> None:
    calls = 0
    runtime_scheduler = RuntimeScheduler()
    plugin_runtime = PluginRuntime(
        [
            PluginManifest(
                id="feedback",
                name="Feedback",
                version="1.0.0",
                api_version="v1",
                permissions=["feedback:read"],
                scheduler_jobs=["feedback.sync"],
            )
        ]
    )
    runtime_scheduler.set_plugin_runtime(plugin_runtime)

    async def handler() -> str:
        nonlocal calls
        calls += 1
        return "ran"

    runtime_scheduler.register_interval_job(
        ScheduledJob.from_interval(
            id="feedback.sync",
            interval_seconds=60,
            handler=handler,
            plugin_id="feedback",
        )
    )

    assert await runtime_scheduler.run_job_now("feedback.sync") == "ran"
    plugin_runtime.disable_plugin("feedback")
    result = await runtime_scheduler.run_job_now("feedback.sync")

    assert result["skipped"] is True
    assert result["reason"] == "plugin_unavailable"
    assert result["plugin_id"] == "feedback"
    assert calls == 1


@pytest.mark.asyncio
async def test_job_refreshes_interval_when_config_changes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.scheduler import runtime as scheduler_module

    monkeypatch.setattr(scheduler_module, "AsyncIOScheduler", _FakeAsyncIOScheduler)
    seconds = 60
    runtime_scheduler = RuntimeScheduler()

    async def handler() -> None:
        return None

    runtime_scheduler.register_interval_job(
        ScheduledJob.from_interval(
            id="dynamic.job",
            interval_seconds=lambda: seconds,
            handler=handler,
        )
    )
    runtime_scheduler.start()
    seconds = 120

    await runtime_scheduler.run_job_now("dynamic.job")

    fake = _FakeAsyncIOScheduler.instances[-1]
    assert fake.rescheduled_jobs[-1]["id"] == "dynamic.job"
    assert fake.rescheduled_jobs[-1]["trigger"].interval.total_seconds() == 120


@pytest.mark.asyncio
async def test_stop_shuts_down_apscheduler_without_waiting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.scheduler import runtime as scheduler_module

    monkeypatch.setattr(scheduler_module, "AsyncIOScheduler", _FakeAsyncIOScheduler)
    runtime_scheduler = RuntimeScheduler()
    runtime_scheduler.start()

    await runtime_scheduler.stop()

    fake = _FakeAsyncIOScheduler.instances[-1]
    assert fake.shutdown_wait is False


# ── New tests for cron / unregister / has_job ─────


def test_register_cron_job(monkeypatch: pytest.MonkeyPatch) -> None:
    from apscheduler.triggers.cron import CronTrigger

    from src.infra.scheduler import runtime as scheduler_module

    monkeypatch.setattr(scheduler_module, "AsyncIOScheduler", _FakeAsyncIOScheduler)
    runtime_scheduler = RuntimeScheduler()

    async def handler() -> None:
        return None

    runtime_scheduler.register_job(
        ScheduledJob(
            id="report.daily",
            trigger=CronTrigger(hour=9, minute=0),
            handler=handler,
        )
    )
    runtime_scheduler.start()

    fake = _FakeAsyncIOScheduler.instances[-1]
    assert len(fake.added_jobs) == 1
    added = fake.added_jobs[0]
    assert added["kwargs"]["id"] == "report.daily"
    assert isinstance(added["trigger"], CronTrigger)


def test_unregister_job(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.infra.scheduler import runtime as scheduler_module

    monkeypatch.setattr(scheduler_module, "AsyncIOScheduler", _FakeAsyncIOScheduler)
    runtime_scheduler = RuntimeScheduler()

    async def handler() -> None:
        return None

    runtime_scheduler.register_job(
        ScheduledJob.from_interval(id="to.remove", interval_seconds=60, handler=handler)
    )
    assert runtime_scheduler.has_job("to.remove") is True

    runtime_scheduler.start()
    runtime_scheduler.unregister_job("to.remove")

    assert runtime_scheduler.has_job("to.remove") is False


def test_has_job_returns_false_for_unknown() -> None:
    runtime_scheduler = RuntimeScheduler()
    assert runtime_scheduler.has_job("nonexistent") is False


def test_from_interval_static() -> None:
    async def handler() -> None:
        pass

    job = ScheduledJob.from_interval(id="test", interval_seconds=120, handler=handler)
    from apscheduler.triggers.interval import IntervalTrigger

    assert isinstance(job.trigger, IntervalTrigger)
