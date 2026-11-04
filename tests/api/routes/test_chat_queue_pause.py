"""Queue pause and turn fencing across serialized API callers."""

import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api.routes import chat
from src.infra.scheduler.conversation import conversation_submission as real_submission
from src.infra.task.status import TaskStatus
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.agent import SteerRequest
from tests.infra.test_chat_lease_ownership import lease_redis  # noqa: F401


@pytest.fixture
def state(monkeypatch):
    metadata = {"current_run_id": "run-1", "task_status": "running"}
    session = SimpleNamespace(id="s1", user_id="u1", metadata=metadata)
    lock = asyncio.Lock()

    @asynccontextmanager
    async def admission(*args, **kwargs):
        async with lock:
            yield

    async def update(session_id, run_id, values, **kwargs):
        if metadata["current_run_id"] != run_id:
            return False
        metadata.update(values)
        return True

    storage = SimpleNamespace(update_metadata_for_run=AsyncMock(side_effect=update))
    manager = SimpleNamespace(get_session=AsyncMock(return_value=session), storage=storage)

    async def cancel(*args, **kwargs):
        assert metadata.get("queue_paused_run_id") == "run-1"
        metadata["task_status"] = "cancelled"
        return {"success": True, "cancelled_locally": True, "run_id": "run-1"}

    task = SimpleNamespace(
        cancel=AsyncMock(side_effect=cancel),
        get_status=AsyncMock(side_effect=lambda _: TaskStatus(metadata["task_status"])),
        get_run_status=AsyncMock(side_effect=lambda *_: TaskStatus(metadata["task_status"])),
        get_error=AsyncMock(return_value=None),
        get_run_error=AsyncMock(return_value=None),
    )
    monkeypatch.setattr(chat, "SessionManager", lambda: manager)
    monkeypatch.setattr("src.infra.session.manager.SessionManager", lambda: manager)
    monkeypatch.setattr(chat, "get_task_manager", lambda: task)
    monkeypatch.setattr(chat, "conversation_submission", admission)
    monkeypatch.setattr("src.infra.scheduler.conversation.conversation_submission", admission)
    monkeypatch.setattr(
        "src.api.routes.hitl_interrupt_cleanup.reconcile_cancelled_hitl_approvals", AsyncMock()
    )
    return SimpleNamespace(metadata=metadata, session=session, task=task, storage=storage)


async def test_stop_persists_pause_before_cancelling_and_another_api_observes_it(state):
    await chat.cancel_session("s1", user=SimpleNamespace(sub="u1"), run_id="run-1")
    result = await chat.get_session_status("s1", user=SimpleNamespace(sub="u1"), run_id=None)
    assert result["run_id"] == "run-1"
    assert result["queue_paused"] is True


async def test_a_stale_stop_does_not_pause_or_cancel_the_new_run(state):
    with pytest.raises(AppError) as error:
        await chat.cancel_session("s1", user=SimpleNamespace(sub="u1"), run_id="older")
    assert error.value.error_code is ErrorCode.CONFLICT
    state.storage.update_metadata_for_run.assert_not_awaited()
    state.task.cancel.assert_not_awaited()


async def test_steering_an_old_turn_cannot_land_in_a_new_running_turn(state):
    with pytest.raises(AppError) as error:
        await chat.steer_running_agent(
            "s1",
            SteerRequest(message="old input", expected_run_id="older"),
            user=SimpleNamespace(sub="u1"),
        )
    assert error.value.error_code is ErrorCode.CONFLICT


async def test_resume_is_fenced_to_the_paused_run_and_does_not_start_a_task(state):
    from src.api.routes.chat_queue_control import resume_follow_up_queue

    state.metadata["task_status"] = "cancelled"
    state.metadata["queue_pause_token"] = "pause-1"
    state.metadata["queue_paused_run_id"] = "run-1"
    with pytest.raises(AppError):
        await resume_follow_up_queue(
            "s1", run_id="older", pause_token="pause-1", user=SimpleNamespace(sub="u1")
        )
    assert state.metadata["queue_paused_run_id"] == "run-1"
    result = await resume_follow_up_queue(
        "s1", run_id="run-1", pause_token="pause-1", user=SimpleNamespace(sub="u1")
    )
    assert result["queue_paused"] is False
    assert state.metadata["task_status"] == "cancelled"


async def test_follow_up_admission_rejects_a_stop_or_new_run_after_the_client_status_check(state):
    from src.api.routes.chat_queue_control import validate_follow_up_submission

    state.metadata["queue_paused_run_id"] = "run-1"
    with pytest.raises(AppError):
        validate_follow_up_submission(state.session, "run-1")
    state.metadata["queue_paused_run_id"] = None
    state.metadata["current_run_id"] = "run-2"
    with pytest.raises(AppError):
        validate_follow_up_submission(state.session, "run-1")


async def test_stale_resume_cannot_clear_a_second_stop_on_the_same_run(state):
    from src.api.routes.chat_queue_control import resume_follow_up_queue

    await chat.cancel_session("s1", user=SimpleNamespace(sub="u1"), run_id="run-1")
    first_token = state.metadata["queue_pause_token"]
    await chat.cancel_session("s1", user=SimpleNamespace(sub="u1"), run_id="run-1")
    with pytest.raises(AppError):
        await resume_follow_up_queue(
            "s1", run_id="run-1", pause_token=first_token, user=SimpleNamespace(sub="u1")
        )
    assert state.metadata["queue_paused_run_id"] == "run-1"


@pytest.mark.usefixtures("lease_redis")
async def test_separate_api_callers_cannot_resume_while_stop_owns_the_redis_lease(
    state, monkeypatch
):
    from src.api.routes.chat_queue_control import resume_follow_up_queue

    monkeypatch.setattr(chat, "conversation_submission", real_submission)
    monkeypatch.setattr("src.infra.scheduler.conversation.conversation_submission", real_submission)
    entered, release = asyncio.Event(), asyncio.Event()
    original = state.storage.update_metadata_for_run.side_effect

    async def hold_write(*args, **kwargs):
        result = await original(*args, **kwargs)
        entered.set()
        await release.wait()
        return result

    state.storage.update_metadata_for_run.side_effect = hold_write
    stopping = asyncio.create_task(
        chat.cancel_session("s1", user=SimpleNamespace(sub="u1"), run_id="run-1")
    )
    try:
        await asyncio.wait_for(entered.wait(), 2)
        with pytest.raises(AppError) as error:
            await resume_follow_up_queue(
                "s1", run_id="run-1", pause_token="older-pause", user=SimpleNamespace(sub="u1")
            )
        assert error.value.error_code is ErrorCode.CONFLICT
        state.task.cancel.assert_not_awaited()
    finally:
        release.set()
        await stopping
    assert state.metadata["queue_paused_run_id"] == "run-1"
