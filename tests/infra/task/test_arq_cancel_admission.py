"""Cross-replica cancellation must reach ARQ jobs before graph registration."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.task import arq_worker, cancellation
from src.infra.task.manager import BackgroundTaskManager
from tests.infra.task.test_arq_worker import _FakeLimiter, _FakePayloadStore, _FakeStorage


async def test_pubsub_cancel_reaches_worker_during_agent_setup(monkeypatch):
    manager = BackgroundTaskManager()
    manager._storage = _FakeStorage({"current_run_id": "run-1", "task_status": "running"})
    started = asyncio.Event()
    interrupted = asyncio.Event()

    async def execute(**kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            interrupted.set()
            raise

    manager._executor = SimpleNamespace(run_task=execute)
    payload = {
        "session_id": "session-1",
        "run_id": "run-1",
        "user_id": "user-1",
        "agent_id": "search",
        "message": "hello",
        "executor_key": "agent_stream",
    }
    store = _FakePayloadStore(payload)
    monkeypatch.setattr(arq_worker, "get_task_manager", lambda: manager)
    monkeypatch.setattr(arq_worker, "get_registered_executor", lambda key: object())
    monkeypatch.setattr(arq_worker, "get_concurrency_limiter", _FakeLimiter)
    monkeypatch.setattr(cancellation, "_interrupted_runs", {})
    task = asyncio.create_task(arq_worker.run_agent_task({"payload_store": store}, "run-1"))
    try:
        await asyncio.wait_for(started.wait(), 1)
        manager._storage.metadata["task_status"] = "cancelled"
        await manager._pubsub._handle_cancel_message({"data": json.dumps({"run_id": "run-1"})})
        await asyncio.sleep(0)
        assert interrupted.is_set(), "Cancellation must interrupt setup before a graph task exists"
        await asyncio.wait_for(task, 1)
        assert store.deleted == ["run-1"]
        assert manager._tasks == {}
        assert manager._run_info == {}
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.parametrize("failure", [False, True])
async def test_worker_releases_task_registration_after_execution(monkeypatch, failure):
    manager = BackgroundTaskManager()

    async def execute(**kwargs):
        assert manager._tasks["run-1"] is asyncio.current_task()
        if failure:
            raise RuntimeError("model failed")

    manager._executor = SimpleNamespace(run_task=execute)
    store = _FakePayloadStore(
        {
            "session_id": "session-1",
            "run_id": "run-1",
            "user_id": "user-1",
            "agent_id": "search",
            "message": "hello",
            "executor_key": "agent_stream",
        }
    )
    monkeypatch.setattr(arq_worker, "get_task_manager", lambda: manager)
    monkeypatch.setattr(arq_worker, "get_registered_executor", lambda key: object())
    monkeypatch.setattr(arq_worker, "get_concurrency_limiter", _FakeLimiter)
    manager._mark_run_recoverable_failure = AsyncMock()
    if failure:
        with pytest.raises(RuntimeError, match="model failed"):
            await arq_worker.run_agent_task({"payload_store": store}, "run-1")
    else:
        await arq_worker.run_agent_task({"payload_store": store}, "run-1")
    assert manager._tasks == {}
    assert manager._run_info == {}


async def test_source_cleanup_preserves_resumed_run_ownership(monkeypatch):
    manager = BackgroundTaskManager()
    replacement = asyncio.create_task(asyncio.Event().wait())
    resumed_info = {"owner": "resumed"}

    async def execute(**kwargs):
        manager._tasks["run-1"] = replacement
        manager._run_info["run-1"] = resumed_info

    manager._executor = SimpleNamespace(run_task=execute)
    store = _FakePayloadStore(
        {
            "session_id": "session-1",
            "run_id": "run-1",
            "user_id": "user-1",
            "agent_id": "search",
            "message": "hello",
            "executor_key": "agent_stream",
        }
    )
    monkeypatch.setattr(arq_worker, "get_task_manager", lambda: manager)
    monkeypatch.setattr(arq_worker, "get_registered_executor", lambda key: object())
    monkeypatch.setattr(arq_worker, "get_concurrency_limiter", _FakeLimiter)
    try:
        await arq_worker.run_agent_task({"payload_store": store}, "run-1")
        assert manager._tasks["run-1"] is replacement
        assert manager._run_info["run-1"] is resumed_info
    finally:
        replacement.cancel()
        await asyncio.gather(replacement, return_exceptions=True)
