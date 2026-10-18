"""Persistent Goal recovery must not re-admit a superseded run."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.goal_runtime import _run_goal
from src.infra.persistent_goal import GoalService
from src.infra.task import arq_worker
from src.infra.task.exceptions import TaskInterruptedError
from src.infra.task.executor import TaskExecutor
from src.kernel.schemas.persistent_goal import PersistentGoalCreate
from tests.api.routes.test_persistent_goal_hitl import SessionCollection, actual_storage
from tests.infra.agent.test_goal_runtime import runtime_redis  # noqa: F401
from tests.infra.agent.test_persistent_goal import Store
from tests.infra.task.test_arq_worker import _FakeLimiter, _FakePayloadStore
from tests.infra.task.test_executor_startup_latency import _executor, _FakePresenter


async def setup_admission(monkeypatch, *, stale):
    collection = SessionCollection()
    storage = actual_storage(monkeypatch, collection)
    service = GoalService(Store())
    await service.create(
        collection.session_id, "u", PersistentGoalCreate(objective="finish", rubric="tests")
    )
    goal = await service.attach_user_run(collection.session_id, "u", "old")
    if stale:
        await service.control(collection.session_id, "u", "pause")
        collection.doc["metadata"].update(
            current_run_id="new-human", task_status="running", trace_id="new-trace"
        )
    else:
        collection.race = True
    monkeypatch.setattr("src.infra.goal_runtime.GoalService", lambda: service)
    executor = _executor(monkeypatch)
    executor._storage = storage
    monkeypatch.setattr(
        executor, "_update_session_status", TaskExecutor._update_session_status.__get__(executor)
    )
    monkeypatch.setattr(executor, "_schedule_idle_pause_check", lambda _: None)
    source = AsyncMock()

    async def stream(*args, **kwargs):
        await source()
        yield {"event": "message:chunk", "data": {"content": "bad"}}

    return collection, executor, _run_goal(goal), stream, source


@pytest.mark.parametrize("stale", [True, False], ids=["superseded", "atomic-race"])
async def test_executor_rejects_old_goal_before_starting_lifecycle(monkeypatch, stale):
    collection, executor, goal, stream, source = await setup_admission(monkeypatch, stale=stale)
    clear = AsyncMock()
    monkeypatch.setattr("src.infra.task.cancellation.TaskCancellation.clear_interrupt", clear)
    with pytest.raises(TaskInterruptedError):
        await executor.run_task(
            collection.session_id,
            "old",
            "fast",
            "continue",
            "u",
            stream,
            active_goal=goal,
            interrupted_resume=True,
        )
    assert collection.doc["metadata"] == {
        "current_run_id": "new-human",
        "task_status": "running",
        "trace_id": "new-trace",
    }
    assert not executor._heartbeat.start_calls
    assert not executor._heartbeat.stop_calls
    assert not _FakePresenter.instances
    source.assert_not_awaited()
    clear.assert_not_awaited()


@pytest.mark.parametrize("resume", ["hitl_resume", "interrupted_resume"])
@pytest.mark.parametrize("stale", [True, False], ids=["superseded", "atomic-race"])
async def test_arq_rejects_old_goal_before_pending_slots_or_trace(monkeypatch, resume, stale):
    collection, executor, goal, stream, source = await setup_admission(monkeypatch, stale=stale)
    limiter = _FakeLimiter()
    owner = {"trace_id": "new-trace"}
    executor._run_info["new-human"] = owner
    manager = SimpleNamespace(
        _ensure_executor=lambda: executor, _run_info=executor._run_info, storage=executor._storage
    )
    monkeypatch.setattr(arq_worker, "get_task_manager", lambda: manager)
    monkeypatch.setattr(arq_worker, "get_concurrency_limiter", lambda: limiter)
    monkeypatch.setattr(
        arq_worker, "_acquire_hitl_resume_startup_lock", AsyncMock(return_value="startup")
    )
    monkeypatch.setattr(arq_worker, "_release_hitl_resume_startup_lock", AsyncMock())
    monkeypatch.setattr(arq_worker, "wait_for_hitl_source_release", AsyncMock(return_value=True))
    monkeypatch.setattr(
        "src.infra.task.heartbeat.TaskHeartbeat.is_stale", AsyncMock(return_value=True)
    )
    monkeypatch.setattr(arq_worker, "_resolve_executor", lambda _: stream)
    monkeypatch.setattr(arq_worker, "_run_watchdog_timeout", lambda: None)
    payload = {
        "session_id": collection.session_id,
        "run_id": "old",
        "user_id": "u",
        "agent_id": "fast",
        "message": "continue",
        "executor_key": "agent_stream",
        "active_goal": goal,
        resume: {"approval_id": "approval"} if resume == "hitl_resume" else True,
    }
    store = _FakePayloadStore(payload)
    await arq_worker.run_agent_task({"payload_store": store}, "old")
    assert collection.doc["metadata"] == {
        "current_run_id": "new-human",
        "task_status": "running",
        "trace_id": "new-trace",
    }
    assert executor._run_info == {"new-human": owner}
    assert not limiter.acquire_calls
    assert not limiter.release_calls
    assert not _FakePresenter.instances
    source.assert_not_awaited()


async def test_local_submit_rejects_superseded_goal_before_pending_or_user_trace(monkeypatch):
    from src.infra.task.manager import BackgroundTaskManager
    from tests.infra.task.test_arq_submission import _FakeExecutor

    collection, _, goal, stream, _ = await setup_admission(monkeypatch, stale=True)
    manager = BackgroundTaskManager()
    executor = _FakeExecutor()
    manager._executor = executor
    manager._persist_initial_user_message = AsyncMock()
    manager._release_concurrency = AsyncMock()
    with pytest.raises(TaskInterruptedError):
        await manager.submit(
            collection.session_id,
            "fast",
            "continue",
            "u",
            stream,
            run_id="old",
            active_goal=goal,
            write_user_message_immediately=True,
        )
    assert not executor.ensure_calls
    assert not executor.status_calls
    assert not executor.run_calls
    manager._persist_initial_user_message.assert_not_awaited()
    assert not manager._tasks
