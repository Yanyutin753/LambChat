"""Detached resume admission cannot overwrite a later human conversation run."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.session.manager import SessionManager
from src.infra.task import arq_worker
from src.infra.task.background_task_store import BackgroundTaskStore
from src.infra.task.exceptions import TaskInterruptedError
from src.infra.task.executor import TaskExecutor
from tests.api.routes.test_persistent_goal_hitl import SessionCollection, actual_storage
from tests.infra.agent.test_goal_runtime import runtime_redis as runtime_redis
from tests.infra.task.test_arq_worker import _FakeLimiter, _FakePayloadStore
from tests.infra.task.test_executor_startup_latency import _executor, _FakePresenter


def setup_background(monkeypatch, *, stale=False, race=False, registry_run="old"):
    collection = SessionCollection()
    collection.doc["metadata"]["background_task_id"] = "task-id"
    if stale:
        collection.doc["metadata"].update(
            current_run_id="new-human", task_status="running", trace_id="new-trace"
        )
    collection.race = race
    storage = actual_storage(monkeypatch, collection)
    monkeypatch.setattr(
        SessionManager,
        "get_session",
        AsyncMock(
            side_effect=lambda _: SimpleNamespace(
                user_id="u", metadata=deepcopy(collection.doc["metadata"])
            )
        ),
    )
    record = {
        "_id": "task-id",
        "user_id": "u",
        "session_id": collection.session_id,
        "run_id": registry_run,
        "state": "submitted",
    }
    monkeypatch.setattr(
        BackgroundTaskStore,
        "collection",
        property(lambda self: SimpleNamespace(find_one=AsyncMock(return_value=record))),
    )
    executor = _executor(monkeypatch)
    executor._storage = storage
    monkeypatch.setattr(
        executor, "_update_session_status", TaskExecutor._update_session_status.__get__(executor)
    )
    monkeypatch.setattr(executor, "_schedule_idle_pause_check", lambda _: None)
    source = AsyncMock()

    async def stream(*args, **kwargs):
        await source()
        yield {"event": "message:chunk", "data": {"content": "must not execute"}}

    return collection, executor, stream, source


@pytest.mark.parametrize("stale,race", [(True, False), (False, True)])
async def test_executor_background_resume_fences_current_run_before_lifecycle(
    monkeypatch, stale, race
):
    collection, executor, stream, source = setup_background(monkeypatch, stale=stale, race=race)
    with pytest.raises(TaskInterruptedError):
        await executor.run_task(
            collection.session_id, "old", "fast", "resume", "u", stream, interrupted_resume=True
        )
    assert collection.doc["metadata"]["current_run_id"] == "new-human"
    assert collection.doc["metadata"]["task_status"] == "running"
    assert not executor._heartbeat.start_calls
    assert not _FakePresenter.instances
    source.assert_not_awaited()


@pytest.mark.parametrize("resume", ["hitl_resume", "interrupted_resume"])
@pytest.mark.parametrize("stale,race", [(True, False), (False, True)])
async def test_arq_background_resume_fences_pending_before_slots(monkeypatch, resume, stale, race):
    collection, executor, stream, source = setup_background(monkeypatch, stale=stale, race=race)
    limiter = _FakeLimiter()
    manager = SimpleNamespace(
        _ensure_executor=lambda: executor,
        _tasks={},
        _run_info=executor._run_info,
        storage=executor._storage,
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
        "message": "resume",
        "executor_key": "background_agent_stream",
        resume: {"approval_id": "approval"} if resume == "hitl_resume" else True,
    }
    store = _FakePayloadStore(payload)
    await arq_worker.run_agent_task({"payload_store": store}, "old")
    assert collection.doc["metadata"]["current_run_id"] == "new-human"
    assert collection.doc["metadata"]["task_status"] == "running"
    assert not limiter.acquire_calls and not limiter.release_calls
    assert not _FakePresenter.instances
    source.assert_not_awaited()


async def test_registered_background_identity_must_match_even_when_session_looks_current(
    monkeypatch,
):
    from src.infra.task.background_admission import validate_background_run_admission

    collection, _, _, _ = setup_background(monkeypatch, registry_run="different-run")
    with pytest.raises(TaskInterruptedError):
        await validate_background_run_admission(collection.session_id, "u", "old")


async def test_local_background_resume_rejects_before_pending_submission(monkeypatch):
    from src.infra.task.manager import BackgroundTaskManager

    collection, executor, stream, source = setup_background(monkeypatch, stale=True)
    manager = BackgroundTaskManager()
    manager._executor = executor
    with pytest.raises(TaskInterruptedError):
        await manager.submit(
            collection.session_id,
            "fast",
            "resume",
            "u",
            stream,
            run_id="old",
            interrupted_resume=True,
        )
    assert collection.doc["metadata"]["current_run_id"] == "new-human"
    assert not manager._tasks
    assert not _FakePresenter.instances
    source.assert_not_awaited()


async def test_later_ordinary_human_turn_in_background_chat_keeps_normal_recovery(monkeypatch):
    from src.infra.task.background_admission import validate_background_resume

    collection, executor, _, _ = setup_background(monkeypatch, stale=True)
    assert not await validate_background_resume(
        executor._storage, collection.session_id, "u", "new-human"
    )


async def test_delayed_initial_background_executor_cannot_replace_new_human_run(
    monkeypatch, runtime_redis
):
    from src.infra.task.background_tasks import execute_background_stream

    collection, executor, _, _ = setup_background(monkeypatch, stale=True)
    with pytest.raises(TaskInterruptedError):
        await executor.run_task(
            collection.session_id, "old", "fast", "task", "u", execute_background_stream
        )
    assert collection.doc["metadata"]["current_run_id"] == "new-human"
    assert not executor._heartbeat.start_calls
    assert not _FakePresenter.instances


@pytest.mark.parametrize(
    "status,recoverable",
    [
        ("completed", False),
        ("cancelled", False),
        ("cancelling", False),
        ("expired", False),
        ("failed", False),
        ("failed", None),
    ],
)
async def test_finished_background_run_rejects_delayed_dispatch(monkeypatch, status, recoverable):
    from src.infra.task.background_admission import validate_background_run_admission

    collection, _executor_value, _stream, _source = setup_background(monkeypatch)
    collection.doc["metadata"].update(task_status=status, task_recoverable=recoverable)
    with pytest.raises(TaskInterruptedError):
        await validate_background_run_admission(collection.session_id, "u", "old")


@pytest.mark.parametrize(
    "status,recoverable",
    [("failed", True), ("waiting_human", False), ("running", False), ("pending", False)],
)
async def test_live_or_recoverable_background_run_remains_admissible(
    monkeypatch, status, recoverable
):
    from src.infra.task.background_admission import validate_background_run_admission

    collection, _executor_value, _stream, _source = setup_background(monkeypatch)
    collection.doc["metadata"].update(task_status=status, task_recoverable=recoverable)
    await validate_background_run_admission(collection.session_id, "u", "old")


async def test_cancelled_failure_flag_does_not_authorize_background_recovery(monkeypatch):
    from src.infra.task.background_admission import validate_background_run_admission

    collection, _executor_value, _stream, _source = setup_background(monkeypatch)
    collection.doc["metadata"].update(
        task_status="failed", task_recoverable=True, task_error_code="cancelled"
    )
    with pytest.raises(TaskInterruptedError):
        await validate_background_run_admission(collection.session_id, "u", "old")
