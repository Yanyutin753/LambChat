from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from src.infra.task import arq_runtime


class _FakeWorker:
    instances: list["_FakeWorker"] = []

    def __init__(self, *args, **kwargs) -> None:
        self.args = args
        self.kwargs = kwargs
        self.closed = asyncio.Event()
        _FakeWorker.instances.append(self)

    async def async_run(self) -> None:
        await self.closed.wait()

    async def close(self) -> None:
        self.closed.set()


@pytest.mark.asyncio
async def test_start_embedded_arq_worker_skips_when_backend_is_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = SimpleNamespace(TASK_BACKEND="local", ARQ_EMBEDDED_WORKER=True)
    monkeypatch.setattr(arq_runtime, "settings", settings)

    runtime = arq_runtime.EmbeddedArqRuntime(worker_factory=_FakeWorker)
    await runtime.start()

    assert runtime.is_running is False
    assert _FakeWorker.instances == []


@pytest.mark.asyncio
async def test_start_embedded_arq_worker_runs_with_signals_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakeWorker.instances.clear()
    settings = SimpleNamespace(
        TASK_BACKEND="arq",
        ARQ_EMBEDDED_WORKER=True,
        ARQ_WORKER_MAX_JOBS=128,
        ARQ_JOB_TIMEOUT_SECONDS=30,
        ARQ_QUEUE_NAME="lambchat:arq",
        REDIS_URL="redis://localhost:6379/0",
        REDIS_PASSWORD=None,
    )
    monkeypatch.setattr(arq_runtime, "settings", settings)

    runtime = arq_runtime.EmbeddedArqRuntime(worker_factory=_FakeWorker)
    await runtime.start()

    assert runtime.is_running is True
    assert _FakeWorker.instances
    worker = _FakeWorker.instances[0]
    assert worker.args[0] == [
        arq_runtime.run_agent_task,
        arq_runtime.update_user_message_search_index,
    ]
    assert worker.kwargs["handle_signals"] is False
    assert worker.kwargs["max_jobs"] == 128
    assert worker.kwargs["job_timeout"] == 30
    assert worker.kwargs["queue_name"] == "lambchat:arq"

    await runtime.stop()
    assert runtime.is_running is False


@pytest.mark.asyncio
async def test_start_embedded_arq_worker_accepts_future_returned_by_async_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FutureRunWorkerWithFuture(_FakeWorker):
        def __init__(self, *args, **kwargs) -> None:
            super().__init__(*args, **kwargs)
            self.run_future = asyncio.get_running_loop().create_future()

        def async_run(self) -> asyncio.Future[None]:
            return self.run_future

        async def close(self) -> None:
            if not self.run_future.done():
                self.run_future.set_result(None)

    _FakeWorker.instances.clear()
    settings = SimpleNamespace(
        TASK_BACKEND="arq",
        ARQ_EMBEDDED_WORKER=True,
        ARQ_WORKER_MAX_JOBS=128,
        ARQ_JOB_TIMEOUT_SECONDS=30,
        ARQ_QUEUE_NAME="lambchat:arq",
        REDIS_URL="redis://localhost:6379/0",
        REDIS_PASSWORD=None,
    )
    monkeypatch.setattr(arq_runtime, "settings", settings)

    runtime = arq_runtime.EmbeddedArqRuntime(worker_factory=_FutureRunWorkerWithFuture)
    await runtime.start()

    assert runtime.is_running is True

    await runtime.stop()
    assert runtime.is_running is False


@pytest.mark.asyncio
async def test_stop_embedded_arq_worker_awaits_future_returned_by_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FutureCloseWorker(_FakeWorker):
        close_done = False

        def close(self) -> asyncio.Future[None]:
            future = asyncio.get_running_loop().create_future()

            def _finish_close() -> None:
                type(self).close_done = True
                self.closed.set()
                future.set_result(None)

            asyncio.get_running_loop().call_later(0.01, _finish_close)
            return future

    _FutureCloseWorker.close_done = False
    _FakeWorker.instances.clear()
    settings = SimpleNamespace(
        TASK_BACKEND="arq",
        ARQ_EMBEDDED_WORKER=True,
        ARQ_WORKER_MAX_JOBS=128,
        ARQ_JOB_TIMEOUT_SECONDS=30,
        ARQ_QUEUE_NAME="lambchat:arq",
        REDIS_URL="redis://localhost:6379/0",
        REDIS_PASSWORD=None,
    )
    monkeypatch.setattr(arq_runtime, "settings", settings)

    runtime = arq_runtime.EmbeddedArqRuntime(worker_factory=_FutureCloseWorker)
    await runtime.start()
    await runtime.stop()

    assert _FutureCloseWorker.close_done is True


@pytest.mark.asyncio
async def test_stop_arq_runtime_releases_global_singleton() -> None:
    runtime = arq_runtime.EmbeddedArqRuntime(worker_factory=_FakeWorker)
    arq_runtime._runtime = runtime

    await arq_runtime.stop_arq_runtime()

    assert arq_runtime._runtime is None


@pytest.mark.asyncio
async def test_stop_arq_runtime_does_not_create_singleton_when_unused() -> None:
    arq_runtime._runtime = None

    await arq_runtime.stop_arq_runtime()

    assert arq_runtime._runtime is None


def _arq_settings() -> SimpleNamespace:
    return SimpleNamespace(
        TASK_BACKEND="arq",
        ARQ_EMBEDDED_WORKER=True,
        ARQ_WORKER_MAX_JOBS=128,
        ARQ_JOB_TIMEOUT_SECONDS=30,
        ARQ_QUEUE_NAME="lambchat:arq",
        REDIS_URL="redis://localhost:6379/0",
        REDIS_PASSWORD=None,
    )


async def _wait_until(predicate, timeout: float = 2.0) -> None:
    for _ in range(int(timeout / 0.01)):
        if predicate():
            return
        await asyncio.sleep(0.01)


@pytest.mark.asyncio
async def test_worker_crash_restarts_worker_and_keeps_running(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """worker 异常退出必须自动重建（2026-08-27 生产事故：裸 future 静默死亡，副本退出消费）。"""

    class _CrashOnceWorker(_FakeWorker):
        runs = 0

        async def async_run(self) -> None:
            type(self).runs += 1
            if type(self).runs == 1:
                raise RuntimeError("simulated worker crash")
            await self.closed.wait()

    _FakeWorker.instances.clear()
    monkeypatch.setattr(arq_runtime, "settings", _arq_settings())

    runtime = arq_runtime.EmbeddedArqRuntime(
        worker_factory=_CrashOnceWorker, restart_delay_seconds=0.01
    )
    await runtime.start()

    await _wait_until(lambda: len(_FakeWorker.instances) >= 2)

    assert len(_FakeWorker.instances) == 2
    assert runtime.is_running is True

    await runtime.stop()
    assert runtime.is_running is False
    assert _FakeWorker.instances[1].closed.is_set()


@pytest.mark.asyncio
async def test_worker_silent_exit_restarts_worker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """worker 无异常但返回（静默退出）同样要重建。"""

    class _ExitOnceWorker(_FakeWorker):
        runs = 0

        async def async_run(self) -> None:
            type(self).runs += 1
            if type(self).runs == 1:
                return
            await self.closed.wait()

    _FakeWorker.instances.clear()
    monkeypatch.setattr(arq_runtime, "settings", _arq_settings())

    runtime = arq_runtime.EmbeddedArqRuntime(
        worker_factory=_ExitOnceWorker, restart_delay_seconds=0.01
    )
    await runtime.start()

    await _wait_until(lambda: len(_FakeWorker.instances) >= 2)

    assert len(_FakeWorker.instances) == 2
    assert runtime.is_running is True

    await runtime.stop()


@pytest.mark.asyncio
async def test_worker_crash_triggers_post_restart_recovery_callback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """worker 崩溃重启后必须触发一次 FAILED-recoverable 恢复。

    回归防护：worker 被掐断的 run 落在 FAILED+recoverable（payload 已删），
    周期孤儿接管 running_only=True 会跳过它们——没有这个回调，会话只能
    等到下一次 Pod 重启才被恢复（分布式 P1 死区）。
    """

    class _CrashOnceWorker(_FakeWorker):
        runs = 0

        async def async_run(self) -> None:
            type(self).runs += 1
            if type(self).runs == 1:
                raise RuntimeError("simulated worker crash")
            await self.closed.wait()

    _FakeWorker.instances.clear()
    monkeypatch.setattr(arq_runtime, "settings", _arq_settings())
    recovery_calls: list[int] = []

    async def _on_worker_restarted() -> None:
        recovery_calls.append(1)

    runtime = arq_runtime.EmbeddedArqRuntime(
        worker_factory=_CrashOnceWorker,
        restart_delay_seconds=0.01,
        on_worker_restarted=_on_worker_restarted,
    )
    await runtime.start()

    await _wait_until(lambda: len(recovery_calls) >= 1)
    await asyncio.sleep(0.05)

    assert len(recovery_calls) == 1
    await runtime.stop()


@pytest.mark.asyncio
async def test_recovery_callback_not_invoked_without_worker_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _FakeWorker.instances.clear()
    monkeypatch.setattr(arq_runtime, "settings", _arq_settings())
    recovery_calls: list[int] = []

    async def _on_worker_restarted() -> None:
        recovery_calls.append(1)

    runtime = arq_runtime.EmbeddedArqRuntime(
        worker_factory=_FakeWorker, on_worker_restarted=_on_worker_restarted
    )
    await runtime.start()
    await asyncio.sleep(0.05)

    assert recovery_calls == []
    await runtime.stop()
