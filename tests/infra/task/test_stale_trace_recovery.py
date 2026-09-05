"""僵尸 trace 周期兜底任务的测试。

背景：startup_cleanup 只扫 ``sessions.metadata.task_status``（arq 任务路径），
直连 SSE run 与挂死 run 的 trace 停在 running 时无人清理。本模块把全局
``expire_stale_running_traces_globally`` 挂到统一运行时调度器周期执行，
模式对齐 ``task.orphan_recovery``。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from src.infra.task import stale_trace_recovery

RUNTIME_SERVICES_SOURCE = Path("src/infra/runtime_services.py").read_text()


@pytest.mark.asyncio
async def test_scheduled_recovery_expires_stale_traces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []

    class _FakeStorage:
        async def expire_stale_running_traces_globally(self, **kwargs):
            calls.append(kwargs)
            return 3

    monkeypatch.setattr(stale_trace_recovery, "get_trace_storage", lambda: _FakeStorage())

    result = await stale_trace_recovery.run_scheduled_stale_trace_recovery()

    assert result == {"status": "ok", "expired": 3}
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_scheduled_recovery_skips_while_shutting_down(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Boom:
        def __getattr__(self, name):
            raise AssertionError("storage must not be touched while shutting down")

    monkeypatch.setattr(stale_trace_recovery, "is_shutting_down", lambda: True)
    monkeypatch.setattr(stale_trace_recovery, "get_trace_storage", _Boom)

    result = await stale_trace_recovery.run_scheduled_stale_trace_recovery()

    assert result["status"] == "skipped"


@pytest.mark.asyncio
async def test_scheduled_recovery_reports_collection_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _BrokenStorage:
        async def expire_stale_running_traces_globally(self):
            raise RuntimeError("mongo down")

    monkeypatch.setattr(stale_trace_recovery, "get_trace_storage", lambda: _BrokenStorage())

    result = await stale_trace_recovery.run_scheduled_stale_trace_recovery()

    assert result == {"status": "error"}


def test_recovery_job_registers_with_scheduler(monkeypatch: pytest.MonkeyPatch) -> None:
    registered: list[object] = []

    class _FakeScheduler:
        def register_job(self, job):
            registered.append(job)

    monkeypatch.setattr(
        stale_trace_recovery, "get_runtime_scheduler", lambda: _FakeScheduler()
    )
    monkeypatch.setattr(
        stale_trace_recovery,
        "recovery_interval_seconds",
        lambda: 300,
    )

    stale_trace_recovery.register_stale_trace_recovery_job()

    assert len(registered) == 1


def test_recovery_job_disabled_when_interval_non_positive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Boom:
        def register_job(self, *_args, **_kwargs):
            raise AssertionError("must not register when disabled")

    monkeypatch.setattr(stale_trace_recovery, "get_runtime_scheduler", _Boom)
    monkeypatch.setattr(stale_trace_recovery, "recovery_interval_seconds", lambda: 0)

    stale_trace_recovery.register_stale_trace_recovery_job()


def test_runtime_services_registers_stale_trace_recovery() -> None:
    assert "register_stale_trace_recovery_job" in RUNTIME_SERVICES_SOURCE
