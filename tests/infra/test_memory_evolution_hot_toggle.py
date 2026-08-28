"""自进化调度任务的热开关语义——注册与启用解耦。

启动时只要 ENABLE_MEMORY 就注册 memory.evolution 任务；NATIVE_MEMORY_SELF_EVOLVE_ENABLED
由任务 enabled lambda 动态读取（settings 热刷新后无需重启即可生效）。
"""

from __future__ import annotations

from typing import Any

import pytest

from src.infra import runtime_services
from src.infra.scheduler import get_runtime_scheduler


def _job_enabled(job: Any) -> bool:
    return job.enabled() if callable(job.enabled) else bool(job.enabled)


@pytest.fixture(autouse=True)
def _clean_scheduler():
    sched = get_runtime_scheduler()
    sched.clear()
    yield
    sched.clear()


def test_evolution_job_registered_when_memory_on_but_evolve_off(monkeypatch):
    """记忆总开关开、自进化关：任务仍注册（enabled=False），热开立即变 True。"""
    monkeypatch.setattr(runtime_services.settings, "ENABLE_MEMORY", True)
    monkeypatch.setattr(runtime_services.settings, "NATIVE_MEMORY_SELF_EVOLVE_ENABLED", False)

    runtime_services.start_memory_evolution_scheduler()

    sched = get_runtime_scheduler()
    assert sched.has_job("memory.evolution")
    job = sched._jobs["memory.evolution"]
    assert _job_enabled(job) is False  # 关着

    # 模拟 settings 热刷新（settings:changed → refresh_settings → setattr）
    monkeypatch.setattr(runtime_services.settings, "NATIVE_MEMORY_SELF_EVOLVE_ENABLED", True)
    assert _job_enabled(job) is True  # 立即生效，无需重启


def test_evolution_job_not_registered_when_memory_off(monkeypatch):
    """记忆总开关关：整个记忆体系不启动，任务不注册。"""
    monkeypatch.setattr(runtime_services.settings, "ENABLE_MEMORY", False)
    monkeypatch.setattr(runtime_services.settings, "NATIVE_MEMORY_SELF_EVOLVE_ENABLED", True)

    runtime_services.start_memory_evolution_scheduler()

    assert not get_runtime_scheduler().has_job("memory.evolution")
