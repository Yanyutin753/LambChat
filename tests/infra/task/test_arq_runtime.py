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
    assert [function.__name__ for function in worker.args[0]] == [
        "run_agent_task",
        "run_workflow_task",
    ]
    assert worker.kwargs["handle_signals"] is False
    assert worker.kwargs["max_jobs"] == 128
    assert worker.kwargs["job_timeout"] == 30
    assert worker.kwargs["queue_name"] == "lambchat:arq"
    assert list(worker.kwargs["ctx"].keys()) == ["payload_store"]
    assert isinstance(worker.kwargs["ctx"]["payload_store"], arq_runtime.TaskArqPayloadStore)

    await runtime.stop()
    assert runtime.is_running is False


@pytest.mark.asyncio
async def test_start_embedded_arq_worker_includes_plugin_runtime_context(
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
    plugin_runtime = object()
    plugin_runtime_state_storage = object()

    runtime = arq_runtime.EmbeddedArqRuntime(worker_factory=_FakeWorker)
    await runtime.start(
        worker_context={
            "plugin_runtime": plugin_runtime,
            "plugin_runtime_state_storage": plugin_runtime_state_storage,
            "ignored_none": None,
        }
    )

    worker = _FakeWorker.instances[0]
    assert worker.kwargs["ctx"]["plugin_runtime"] is plugin_runtime
    assert worker.kwargs["ctx"]["plugin_runtime_state_storage"] is plugin_runtime_state_storage
    assert "ignored_none" not in worker.kwargs["ctx"]
    assert isinstance(worker.kwargs["ctx"]["payload_store"], arq_runtime.TaskArqPayloadStore)

    await runtime.stop()
    assert runtime.is_running is False


@pytest.mark.asyncio
async def test_start_arq_runtime_forwards_plugin_runtime_context(
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
    arq_runtime._runtime = arq_runtime.EmbeddedArqRuntime(worker_factory=_FakeWorker)
    plugin_runtime = object()
    plugin_runtime_state_storage = object()

    try:
        await arq_runtime.start_arq_runtime(
            plugin_runtime=plugin_runtime,
            plugin_runtime_state_storage=plugin_runtime_state_storage,
        )

        worker = _FakeWorker.instances[0]
        assert worker.kwargs["ctx"]["plugin_runtime"] is plugin_runtime
        assert worker.kwargs["ctx"]["plugin_runtime_state_storage"] is plugin_runtime_state_storage
    finally:
        await arq_runtime.stop_arq_runtime()


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
