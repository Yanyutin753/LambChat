from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any, cast

import pytest

from src.infra.task.manager import BackgroundTaskManager
from src.infra.task.status import TaskStatus
from src.kernel.extensions import (
    PluginRuntime,
    PluginUnavailableError,
    build_agent_team_plugin_manifest,
)


class _FakePayloadStore:
    def __init__(self) -> None:
        self.saved: list[tuple[str, dict]] = []

    async def save(self, run_id: str, payload: dict) -> None:
        self.saved.append((run_id, payload))


class _FakeArqPool:
    def __init__(self) -> None:
        self.enqueued: list[tuple[str, tuple, dict]] = []
        self.close_calls = 0
        self.wait_closed_calls = 0

    async def enqueue_job(self, function: str, *args, **kwargs) -> SimpleNamespace:
        self.enqueued.append((function, args, kwargs))
        return SimpleNamespace(job_id="job-1")

    async def close(self) -> None:
        self.close_calls += 1

    async def wait_closed(self) -> None:
        self.wait_closed_calls += 1


class _FutureCloseArqPool(_FakeArqPool):
    def __init__(self) -> None:
        super().__init__()
        self.close_future: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        self.wait_closed_future: asyncio.Future[None] = asyncio.get_running_loop().create_future()

    def close(self) -> asyncio.Future[None]:
        self.close_calls += 1
        asyncio.get_running_loop().call_later(0.01, self.close_future.set_result, None)
        return self.close_future

    def wait_closed(self) -> asyncio.Future[None]:
        self.wait_closed_calls += 1
        asyncio.get_running_loop().call_later(
            0.01,
            self.wait_closed_future.set_result,
            None,
        )
        return self.wait_closed_future


class _LockCheckingArqPool(_FakeArqPool):
    def __init__(self, manager: BackgroundTaskManager) -> None:
        super().__init__()
        self._manager = manager

    async def enqueue_job(self, function: str, *args, **kwargs) -> SimpleNamespace:
        assert not self._manager._lock.locked()
        return await super().enqueue_job(function, *args, **kwargs)


class _FakeExecutor:
    def __init__(self) -> None:
        self.ensure_calls: list[tuple] = []
        self.status_calls: list[tuple] = []
        self.run_calls: list[dict] = []

    async def ensure_session(self, *args, **kwargs) -> None:
        self.ensure_calls.append((args, kwargs))

    async def _update_session_status(self, *args, **kwargs) -> None:
        self.status_calls.append((args, kwargs))

    async def run_task(self, *args, **kwargs) -> None:
        self.run_calls.append({"args": args, **kwargs})


class _FakePresenter:
    calls: list[object] = []

    def __init__(self, config) -> None:
        self.trace_id = config.trace_id or "generated-trace"
        self.config = config
        self.calls.append(config)

    async def _ensure_trace(self) -> None:
        self.calls.append(("ensure_trace", self.trace_id))

    async def emit_user_message(self, message: str, attachments=None) -> None:
        self.calls.append(("emit_user_message", message, attachments))


@pytest.mark.asyncio
async def test_submit_arq_persists_payload_and_enqueues_job() -> None:
    manager = BackgroundTaskManager()
    fake_executor = _FakeExecutor()
    payload_store = _FakePayloadStore()
    arq_pool = _FakeArqPool()
    manager._executor = fake_executor  # type: ignore[assignment]

    run_id, trace_id = await manager.submit_arq(
        session_id="session-1",
        agent_id="search",
        message="hello",
        user_id="user-1",
        executor_key="agent_stream",
        payload_store=cast(Any, payload_store),
        arq_pool=arq_pool,
        run_id="run-1",
        trace_id="trace-1",
        agent_options={"model": "test"},
        display_message="hello display",
    )

    assert (run_id, trace_id) == ("run-1", "trace-1")
    assert fake_executor.ensure_calls
    assert fake_executor.status_calls[0][0][1] == TaskStatus.QUEUED
    assert payload_store.saved[0][0] == "run-1"
    assert payload_store.saved[0][1]["executor_key"] == "agent_stream"
    assert payload_store.saved[0][1]["trace_id"] == "trace-1"
    assert payload_store.saved[0][1]["display_message"] == "hello display"
    assert arq_pool.enqueued == [("run_agent_task", ("run-1",), {"_job_id": "run-1"})]


@pytest.mark.asyncio
async def test_submit_arq_passes_session_metadata_to_initial_session() -> None:
    manager = BackgroundTaskManager()
    fake_executor = _FakeExecutor()
    payload_store = _FakePayloadStore()
    arq_pool = _FakeArqPool()
    manager._executor = fake_executor  # type: ignore[assignment]

    session_metadata = {
        "source": "scheduled_task",
        "scheduled_task_id": "task-1",
        "hidden_from_conversation_list": True,
    }

    await manager.submit_arq(
        session_id="session-1",
        agent_id="search",
        message="hello",
        user_id="user-1",
        executor_key="agent_stream",
        payload_store=cast(Any, payload_store),
        arq_pool=arq_pool,
        run_id="run-1",
        session_metadata=session_metadata,
    )

    assert fake_executor.ensure_calls[0][1]["session_metadata"] == session_metadata


@pytest.mark.asyncio
async def test_submit_arq_does_not_keep_run_info_in_submitter_memory() -> None:
    manager = BackgroundTaskManager()
    fake_executor = _FakeExecutor()
    payload_store = _FakePayloadStore()
    arq_pool = _FakeArqPool()
    manager._executor = fake_executor  # type: ignore[assignment]

    await manager.submit_arq(
        session_id="session-1",
        agent_id="search",
        message="hello",
        user_id="user-1",
        executor_key="agent_stream",
        payload_store=cast(Any, payload_store),
        arq_pool=arq_pool,
        run_id="run-1",
        trace_id="trace-1",
    )

    assert manager._run_info == {}
    assert payload_store.saved[0][1]["trace_id"] == "trace-1"


@pytest.mark.asyncio
async def test_submit_arq_enqueues_after_releasing_manager_lock() -> None:
    manager = BackgroundTaskManager()
    fake_executor = _FakeExecutor()
    payload_store = _FakePayloadStore()
    arq_pool = _LockCheckingArqPool(manager)
    manager._executor = fake_executor  # type: ignore[assignment]

    await manager.submit_arq(
        session_id="session-1",
        agent_id="search",
        message="hello",
        user_id="user-1",
        executor_key="agent_stream",
        payload_store=cast(Any, payload_store),
        arq_pool=arq_pool,
        run_id="run-1",
    )

    assert arq_pool.enqueued == [("run_agent_task", ("run-1",), {"_job_id": "run-1"})]


@pytest.mark.asyncio
async def test_submit_arq_reuses_manager_owned_pool_until_shutdown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = BackgroundTaskManager()
    fake_executor = _FakeExecutor()
    payload_store = _FakePayloadStore()
    manager._executor = fake_executor  # type: ignore[assignment]
    created_pools: list[_FakeArqPool] = []

    async def _fake_create_pool(*args, **kwargs) -> _FakeArqPool:
        del args, kwargs
        pool = _FakeArqPool()
        created_pools.append(pool)
        return pool

    monkeypatch.setattr("src.infra.task.manager.create_pool", _fake_create_pool)

    await manager.submit_arq(
        session_id="session-1",
        agent_id="search",
        message="hello",
        user_id="user-1",
        executor_key="agent_stream",
        payload_store=cast(Any, payload_store),
        run_id="run-1",
    )
    await manager.submit_arq(
        session_id="session-1",
        agent_id="search",
        message="hello again",
        user_id="user-1",
        executor_key="agent_stream",
        payload_store=cast(Any, payload_store),
        run_id="run-2",
    )

    assert len(created_pools) == 1
    assert created_pools[0].enqueued == [
        ("run_agent_task", ("run-1",), {"_job_id": "run-1"}),
        ("run_agent_task", ("run-2",), {"_job_id": "run-2"}),
    ]
    assert created_pools[0].close_calls == 0

    await manager.shutdown()

    assert created_pools[0].close_calls == 1
    assert created_pools[0].wait_closed_calls == 1


@pytest.mark.asyncio
async def test_shutdown_awaits_future_returned_by_arq_pool_close_methods() -> None:
    manager = BackgroundTaskManager()
    arq_pool = _FutureCloseArqPool()
    manager._arq_pool = arq_pool

    await manager.shutdown()

    assert arq_pool.close_calls == 1
    assert arq_pool.wait_closed_calls == 1
    assert arq_pool.close_future.done() is True
    assert arq_pool.wait_closed_future.done() is True
    assert manager._arq_pool is None


@pytest.mark.asyncio
async def test_submit_persists_user_message_before_background_task_starts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = BackgroundTaskManager()
    fake_executor = _FakeExecutor()
    manager._executor = fake_executor  # type: ignore[assignment]
    _FakePresenter.calls = []

    async def _release_no_op(*args, **kwargs):
        return None

    async def _executor_fn(*args, **kwargs):
        if False:
            yield None

    monkeypatch.setattr("src.infra.writer.present.Presenter", _FakePresenter)
    monkeypatch.setattr(manager, "_release_concurrency", _release_no_op)

    run_id, trace_id = await manager.submit(
        session_id="session-1",
        agent_id="search",
        message="[timestamp] hello",
        user_id="user-1",
        executor=_executor_fn,
        run_id="run-1",
        trace_id="trace-1",
        display_message="hello",
        attachments=[{"name": "a.txt"}],
        write_user_message_immediately=True,
    )

    await asyncio.sleep(0)

    assert (run_id, trace_id) == ("run-1", "trace-1")
    assert _FakePresenter.calls[1:] == [
        ("ensure_trace", "trace-1"),
        ("emit_user_message", "hello", [{"name": "a.txt"}]),
    ]


@pytest.mark.asyncio
async def test_submit_rejects_disabled_plugin_owned_agent_before_session_side_effects() -> None:
    from src.agents import set_plugin_runtime

    runtime = PluginRuntime([build_agent_team_plugin_manifest()])
    runtime.disable_plugin("agent_team")
    set_plugin_runtime(runtime)
    manager = BackgroundTaskManager()
    fake_executor = _FakeExecutor()
    manager._executor = fake_executor  # type: ignore[assignment]

    async def _executor_fn(*args, **kwargs):
        raise AssertionError("disabled plugin-owned agent should not run")
        if False:
            yield None

    try:
        with pytest.raises(PluginUnavailableError):
            await manager.submit(
                session_id="session-1",
                agent_id="team",
                message="hello",
                user_id="user-1",
                executor=_executor_fn,
                run_id="run-1",
            )
    finally:
        set_plugin_runtime(None)

    assert fake_executor.ensure_calls == []
    assert fake_executor.status_calls == []
    assert manager._tasks == {}
    assert manager._run_info == {}


@pytest.mark.asyncio
async def test_shutdown_drains_release_concurrency_tasks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = BackgroundTaskManager()
    release_started = asyncio.Event()
    release_finished = False

    class _FakeHeartbeat:
        async def stop_all(self) -> None:
            return None

    class _FakeExecutor:
        pass

    class _FakeLimiter:
        async def release(self, *args, **kwargs) -> None:
            return None

    async def _release_concurrency(user_id: str, run_id: str) -> None:
        nonlocal release_finished
        del user_id, run_id
        release_started.set()
        await asyncio.sleep(0.01)
        release_finished = True

    async def _close_arq_pool() -> None:
        return None

    monkeypatch.setattr(
        "src.infra.task.concurrency.get_concurrency_limiter",
        lambda: _FakeLimiter(),
        raising=False,
    )
    monkeypatch.setattr(manager, "_release_concurrency", _release_concurrency)
    monkeypatch.setattr(manager, "_close_arq_pool", _close_arq_pool)
    manager._heartbeat = _FakeHeartbeat()  # type: ignore[assignment]
    manager._executor = _FakeExecutor()  # type: ignore[assignment]
    manager._run_info["run-1"] = {"user_id": "user-1", "session_id": "session-1"}

    completed_task = asyncio.create_task(asyncio.sleep(0))
    await completed_task
    manager._tasks["run-1"] = completed_task
    manager._on_task_done("run-1", completed_task)
    await release_started.wait()

    assert manager._release_tasks

    await manager.shutdown()

    assert release_finished is True
    assert manager._release_tasks == set()


@pytest.mark.asyncio
async def test_submit_arq_can_persist_user_message_before_enqueue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = BackgroundTaskManager()
    fake_executor = _FakeExecutor()
    payload_store = _FakePayloadStore()
    arq_pool = _FakeArqPool()
    manager._executor = fake_executor  # type: ignore[assignment]
    _FakePresenter.calls = []

    monkeypatch.setattr("src.infra.writer.present.Presenter", _FakePresenter)

    await manager.submit_arq(
        session_id="session-1",
        agent_id="search",
        message="[timestamp] hello",
        user_id="user-1",
        executor_key="agent_stream",
        payload_store=cast(Any, payload_store),
        arq_pool=arq_pool,
        run_id="run-1",
        trace_id="trace-1",
        display_message="hello",
        write_user_message_immediately=True,
    )

    assert _FakePresenter.calls[1:] == [
        ("ensure_trace", "trace-1"),
        ("emit_user_message", "hello", None),
    ]
    assert payload_store.saved[0][1]["user_message_written"] is True


@pytest.mark.asyncio
async def test_submit_arq_rejects_disabled_plugin_owned_agent_before_queue_side_effects() -> None:
    from src.agents import set_plugin_runtime

    runtime = PluginRuntime([build_agent_team_plugin_manifest()])
    runtime.disable_plugin("agent_team")
    set_plugin_runtime(runtime)
    manager = BackgroundTaskManager()
    fake_executor = _FakeExecutor()
    payload_store = _FakePayloadStore()
    arq_pool = _FakeArqPool()
    manager._executor = fake_executor  # type: ignore[assignment]

    try:
        with pytest.raises(PluginUnavailableError):
            await manager.submit_arq(
                session_id="session-1",
                agent_id="team",
                message="hello",
                user_id="user-1",
                executor_key="agent_stream",
                payload_store=cast(Any, payload_store),
                arq_pool=arq_pool,
                run_id="run-1",
            )
    finally:
        set_plugin_runtime(None)

    assert fake_executor.ensure_calls == []
    assert fake_executor.status_calls == []
    assert payload_store.saved == []
    assert arq_pool.enqueued == []
