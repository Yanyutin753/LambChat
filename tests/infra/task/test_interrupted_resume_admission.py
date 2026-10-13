"""Ordinary interrupted resumes must recheck authority at each admission boundary."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.task import arq_worker
from src.infra.task.exceptions import TaskInterruptedError
from src.infra.task.heartbeat import TaskHeartbeat
from src.infra.task.manager import BackgroundTaskManager
from tests.infra.task.test_arq_worker import _FakeLimiter, _FakePayloadStore, _RecoveryStorage
from tests.infra.task.test_executor_interrupted_resume import _executor_fixture


def setup_resume(monkeypatch, current_run, status):
    executor, writer, holder, status_updates = _executor_fixture(monkeypatch, interrupt_flag=False)
    storage = _RecoveryStorage(
        {
            "current_run_id": current_run,
            "task_status": status,
            "task_recoverable": False,
            "trace_id": "trace-current",
        }
    )
    executor._storage = storage
    executor._heartbeat = SimpleNamespace(start=AsyncMock(), stop=AsyncMock())
    source = AsyncMock()

    async def stream(*args, **kwargs):
        await source()
        yield {"event": "message:chunk", "data": {"content": "must not run"}}

    return executor, storage, writer, holder, status_updates, source, stream


@pytest.mark.parametrize("current_run,status", [("run-1", "completed"), ("new-run", "queued")])
async def test_executor_rejects_late_ordinary_resume_before_any_lifecycle(
    monkeypatch, current_run, status
):
    executor, storage, writer, holder, updates, source, stream = setup_resume(
        monkeypatch, current_run, status
    )
    metadata = dict(storage.metadata)
    with pytest.raises(TaskInterruptedError):
        await executor.run_task(
            "session-1",
            "run-1",
            "fast",
            "",
            "user-1",
            stream,
            interrupted_resume=True,
            user_message_written=True,
        )
    assert storage.metadata == metadata
    assert updates == []
    assert holder == {}
    assert not writer.written and not writer.expired
    executor._heartbeat.start.assert_not_awaited()
    executor._heartbeat.stop.assert_not_awaited()
    source.assert_not_awaited()


@pytest.mark.parametrize("current_run,status", [("run-1", "completed"), ("new-run", "queued")])
async def test_arq_resume_losing_authority_during_slot_await_drops_only_own_dispatch(
    monkeypatch, current_run, status
):
    executor, storage, writer, holder, updates, source, stream = setup_resume(
        monkeypatch, "run-1", "pending"
    )
    final_metadata = {**storage.metadata, "current_run_id": current_run, "task_status": status}

    class CompletingLimiter(_FakeLimiter):
        async def try_acquire_run_slot(self, user_id, run_id):
            acquired = await super().try_acquire_run_slot(user_id, run_id)
            storage.metadata.update(current_run_id=current_run, task_status=status)
            final_metadata.clear()
            final_metadata.update(storage.metadata)
            return acquired

    limiter = CompletingLimiter()
    manager = SimpleNamespace(
        storage=storage, _run_info=executor._run_info, _ensure_executor=lambda: executor
    )
    manager._run_info["new-run"] = {"owner": "new-worker"}
    payload = {
        "session_id": "session-1",
        "run_id": "run-1",
        "trace_id": "old-trace",
        "agent_id": "fast",
        "message": "",
        "user_id": "user-1",
        "executor_key": "agent_stream",
        "interrupted_resume": True,
        "user_message_written": True,
    }
    store = _FakePayloadStore(payload, key="own-resume-dispatch")
    monkeypatch.setattr(arq_worker, "get_task_manager", lambda: manager)
    monkeypatch.setattr(arq_worker, "get_concurrency_limiter", lambda: limiter)
    monkeypatch.setattr(arq_worker, "_resolve_executor", lambda _: stream)
    monkeypatch.setattr(TaskHeartbeat, "is_stale", AsyncMock(return_value=True))

    await arq_worker.run_agent_task({"payload_store": store}, "own-resume-dispatch")

    assert storage.metadata == final_metadata
    assert updates == []
    assert holder == {}
    assert not writer.written and not writer.expired
    executor._heartbeat.start.assert_not_awaited()
    source.assert_not_awaited()
    assert store.deleted == ["own-resume-dispatch"]
    assert limiter.release_calls == [("user-1", "run-1", True)]
    assert manager._run_info == {"new-run": {"owner": "new-worker"}}


@pytest.mark.parametrize("current_run,status", [("run-1", "completed"), ("new-run", "queued")])
async def test_local_submit_rejects_late_ordinary_resume_before_pending_or_task_creation(
    monkeypatch, current_run, status
):
    executor, storage, _, holder, updates, source, stream = setup_resume(
        monkeypatch, current_run, status
    )
    metadata = dict(storage.metadata)
    manager = BackgroundTaskManager()
    manager._storage = storage
    manager._executor = executor
    monkeypatch.setattr(executor, "ensure_session", AsyncMock())
    monkeypatch.setattr(manager, "_on_task_done", lambda *_: None)
    try:
        with pytest.raises(TaskInterruptedError):
            await manager.submit(
                "session-1",
                "fast",
                "",
                "user-1",
                stream,
                run_id="run-1",
                interrupted_resume=True,
                user_message_written=True,
            )
        assert storage.metadata == metadata
        assert updates == []
        assert not manager._tasks and not manager._run_info
        assert holder == {}
        source.assert_not_awaited()
    finally:
        tasks = list(manager._tasks.values())
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
