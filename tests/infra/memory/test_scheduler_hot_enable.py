"""A disabled feature must keep dormant jobs so a hot enable works after boot."""

from dataclasses import replace
from unittest.mock import AsyncMock

from src.infra import runtime_services
from src.infra.memory import extraction, tools
from src.infra.scheduler import RuntimeScheduler
from src.kernel.config import settings


async def test_all_memory_jobs_follow_hot_global_enable_without_reregistration(monkeypatch):
    scheduler = RuntimeScheduler()
    monkeypatch.setattr("src.infra.scheduler.get_runtime_scheduler", lambda: scheduler)
    monkeypatch.setattr(tools, "get_runtime_scheduler", lambda: scheduler)
    monkeypatch.setattr(settings, "ENABLE_MEMORY", False)
    monkeypatch.setattr(settings, "MEMORY_EXTRACTION_ENABLED", True)
    monkeypatch.setattr(settings, "NATIVE_MEMORY_SELF_EVOLVE_ENABLED", True)
    monkeypatch.setattr(settings, "NATIVE_MEMORY_AUTO_COMPACT_ENABLED", True)
    tools.start_memory_compaction_agent()
    extraction.start_memory_extraction_agent()
    runtime_services.start_memory_evolution_scheduler()

    expected = {"memory.compaction", "memory.extraction", "memory.evolution"}
    assert set(scheduler._jobs) == expected
    handlers = {}
    for name, job in list(scheduler._jobs.items()):
        handlers[name] = AsyncMock(return_value={"ran": name})
        scheduler.register_job(replace(job, handler=handlers[name]))
        assert await scheduler.run_job_now(name) == {"skipped": True, "reason": "disabled"}
        handlers[name].assert_not_awaited()

    monkeypatch.setattr(settings, "ENABLE_MEMORY", True)
    for name in expected:
        assert await scheduler.run_job_now(name) == {"ran": name}
        handlers[name].assert_awaited_once()

    monkeypatch.setattr(settings, "ENABLE_MEMORY", False)
    for name in expected:
        assert await scheduler.run_job_now(name) == {"skipped": True, "reason": "disabled"}
        handlers[name].assert_awaited_once()
