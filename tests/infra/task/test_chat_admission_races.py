"""Delayed work must never take ownership away from a newer human turn."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.goal_continuation import GOAL_DISPATCH
from src.infra.scheduler.conversation import ConversationBusyError, conversation_submission
from src.kernel.errors import AppError
from tests.api.routes.test_persistent_goal_hitl import SessionCollection, actual_storage
from tests.infra.agent.test_goal_runtime import runtime_redis  # noqa: F401


@pytest.mark.parametrize("automatic", [False, True])
async def test_submission_rechecks_busy_conversation_inside_lease(monkeypatch, automatic):
    session = SimpleNamespace(
        id="s",
        user_id="u",
        metadata={
            "current_run_id": "human",
            "task_status": "running",
        },
    )
    monkeypatch.setattr(
        "src.infra.session.manager.SessionManager.get_session", AsyncMock(return_value=session)
    )
    token = GOAL_DISPATCH.set(SimpleNamespace(id="goal") if automatic else None)
    try:
        with pytest.raises(ConversationBusyError if automatic else AppError):
            async with conversation_submission("s", "u"):
                pytest.fail("A running human turn must keep its ownership")
    finally:
        GOAL_DISPATCH.reset(token)


async def test_goal_control_cannot_interleave_with_chat_admission(runtime_redis):  # noqa: F811
    async with conversation_submission("s", "u", allow_busy=True):
        with pytest.raises(AppError):
            async with conversation_submission("s", "u", allow_busy=True):
                pytest.fail("A second mutation must not enter the same admission lease")
    assert not runtime_redis.values


async def test_delayed_session_configuration_cannot_restore_old_run(monkeypatch):
    from src.api.routes import chat
    from src.kernel.schemas.agent import AgentRequest

    collection = SessionCollection()
    storage = actual_storage(monkeypatch, collection)
    collection.race = True
    manager = SimpleNamespace(storage=storage, update_session_metadata=storage.update_metadata_only)
    monkeypatch.setattr(chat, "SessionManager", lambda: manager)
    await chat._update_session_config(
        collection.session_id, "old", "search", AgentRequest(message="old"), "en"
    )
    assert collection.doc["metadata"]["current_run_id"] == "new-human"
    assert "agent_options" not in collection.doc["metadata"]


async def test_old_cancellation_cannot_mark_new_run_unrecoverable(monkeypatch):
    import asyncio

    from src.infra.task import cancellation

    collection = SessionCollection()
    storage = actual_storage(monkeypatch, collection)
    collection.doc["metadata"].update(current_run_id="new-human", task_recoverable=True)
    monkeypatch.setattr(cancellation, "_interrupted_runs", {})
    monkeypatch.setattr(cancellation, "SessionStorage", lambda: storage)
    monkeypatch.setattr(cancellation, "get_redis_client", lambda: SimpleNamespace(set=AsyncMock()))
    await cancellation.TaskCancellation(asyncio.Lock(), {}).cancel_run(
        "old",
        publish=False,
        user_id="u",
        run_info={"session_id": collection.session_id},
    )
    assert collection.doc["metadata"]["task_recoverable"] is True
    assert "task_error_code" not in collection.doc["metadata"]


async def test_execution_clears_automatic_submission_context(monkeypatch):
    from contextlib import asynccontextmanager

    from src.infra.goal_runtime import with_goal_run_lease

    @asynccontextmanager
    async def lease(*args, **kwargs):
        yield None

    monkeypatch.setattr("src.infra.goal_runtime.goal_run_lease", lease)

    @with_goal_run_lease
    async def execute(session_id, user_id, run_id, active_goal):
        return GOAL_DISPATCH.get()

    token = GOAL_DISPATCH.set(SimpleNamespace(id="parent"))
    try:
        assert await execute("s", "u", "r", None) is None
        assert GOAL_DISPATCH.get().id == "parent"
    finally:
        GOAL_DISPATCH.reset(token)


@pytest.mark.parametrize("method", ["mark_run_failed", "mark_run_recoverable_failure"])
async def test_old_recovery_cannot_poison_new_run_metadata(monkeypatch, method):
    from src.infra.task.recovery import TaskRecoveryService

    collection = SessionCollection()
    storage = actual_storage(monkeypatch, collection)
    collection.doc["metadata"].update(current_run_id="new-human", task_recoverable=False)
    service = TaskRecoveryService(
        storage=storage,
        run_info={},
        heartbeat=None,
        ensure_executor=lambda: SimpleNamespace(_update_session_status=AsyncMock()),
        submit_task=AsyncMock(),
        mark_run_failed=AsyncMock(),
    )
    if method == "mark_run_failed":
        cursor = SimpleNamespace(
            sort=lambda *args: cursor,
            limit=lambda *args: cursor,
            to_list=AsyncMock(return_value=[]),
        )
        monkeypatch.setattr(
            "src.infra.task.recovery.get_trace_storage",
            lambda: SimpleNamespace(collection=SimpleNamespace(find=lambda *args: cursor)),
        )
        await service.mark_run_failed("old", "stale", SimpleNamespace(id=collection.session_id))
    else:
        await service.mark_run_recoverable_failure(collection.session_id, "old", "stale")
    assert collection.doc["metadata"]["task_recoverable"] is False
    assert "interrupted_run_id" not in collection.doc["metadata"]


async def test_delayed_first_execution_cannot_reclaim_new_human_run(monkeypatch):
    from src.infra.task.exceptions import TaskInterruptedError
    from src.infra.task.executor import TaskExecutor
    from tests.infra.task.test_executor_startup_latency import _executor

    collection = SessionCollection()
    storage = actual_storage(monkeypatch, collection)
    collection.race = True
    executor = _executor(monkeypatch)
    executor._storage = storage
    monkeypatch.setattr(
        executor, "_update_session_status", TaskExecutor._update_session_status.__get__(executor)
    )
    with pytest.raises(TaskInterruptedError):
        await executor.run_task(collection.session_id, "old", "search", "old", "u", object())
    assert collection.doc["metadata"]["current_run_id"] == "new-human"
    assert not executor._heartbeat.start_calls


def test_plain_turn_clears_previous_persona_and_team_authority():
    from src.api.routes.chat_request_config import build_conversation_config
    from src.kernel.schemas.agent import AgentRequest

    config = build_conversation_config("r", "search", AgentRequest(message="hello"), "en")
    for key in (
        "persona_preset_id",
        "persona_snapshot",
        "persona_preset_name",
        "persona_avatar",
        "team_id",
    ):
        assert key in config and config[key] is None


@pytest.mark.parametrize("phase", ["trace", "message"])
async def test_failed_user_message_persistence_releases_session_busy_state(monkeypatch, phase):
    from src.infra.task.manager import BackgroundTaskManager
    from src.infra.task.status import TaskStatus
    from tests.infra.task.test_arq_submission import _FakeExecutor

    manager = BackgroundTaskManager()
    manager._executor = executor = _FakeExecutor()
    presenter = SimpleNamespace(
        trace_id="trace",
        _ensure_trace=AsyncMock(),
        emit_user_message=AsyncMock(),
    )
    getattr(
        presenter, "_ensure_trace" if phase == "trace" else "emit_user_message"
    ).side_effect = RuntimeError("disk unavailable")
    monkeypatch.setattr("src.infra.writer.present.Presenter", lambda config: presenter)
    with pytest.raises(RuntimeError, match="disk unavailable"):
        await manager._persist_initial_user_message(
            session_id="s",
            agent_id="quick",
            user_id="u",
            run_id="r",
            trace_id=None,
            message="hello",
            display_message=None,
            attachments=None,
        )
    assert executor.status_calls[-1][0][1] == TaskStatus.FAILED
    assert executor.status_calls[-1][1]["run_id"] == "r"
