"""A task's deadline and instructions survive worker restart."""

import asyncio
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.utils.datetime import utc_now
from src.kernel.errors import AppError
from src.kernel.schemas.agent import AgentRequest


@pytest.mark.parametrize("expired", [False, True])
async def test_detached_assistant_instructions_and_deadline_are_enforced(monkeypatch, expired):
    from src.api.routes import chat_agent_execution
    from src.infra.task import background_admission, background_tasks

    record = {
        "assistant_instructions": "Verify every calculation",
        "timeout_seconds": 30,
        "created_at": utc_now() - timedelta(seconds=31 if expired else 0),
    }
    monkeypatch.setattr(
        background_admission, "validate_background_run_admission", AsyncMock(return_value=record)
    )
    validate = AsyncMock(return_value=AgentRequest(message="", persona_system_prompt="Role"))
    monkeypatch.setattr(background_tasks, "validate_background_execution", validate)
    calls = []

    async def execute(*args, **kwargs):
        calls.append(kwargs)
        yield {"event": "done"}

    monkeypatch.setattr(chat_agent_execution, "_execute_agent_stream", execute)
    stream = background_tasks.execute_background_stream(
        "child", "search", "work", "owner", presenter=SimpleNamespace(run_id="run")
    )
    if expired:
        with pytest.raises(AppError) as caught:
            async for _ in stream:
                pass
        assert caught.value.error_code.code == "assistant_task_deadline"
        assert calls == []
        validate.assert_not_awaited()
    else:
        assert [event async for event in stream] == [{"event": "done"}]
        assert calls[0]["persona_system_prompt"] == "Role\n\nVerify every calculation"


async def test_deadline_closes_a_stalled_source_instead_of_restarting_it(monkeypatch):
    from src.infra.task.background_tasks import stream_with_task_deadline

    closed = []

    async def source():
        try:
            yield {"event": "started"}
            await asyncio.sleep(10)
            yield {"event": "unexpected"}
        finally:
            closed.append(True)

    record = {"timeout_seconds": 30, "created_at": utc_now() - timedelta(seconds=29.95)}
    stream = stream_with_task_deadline(source(), record)
    assert (await anext(stream))["event"] == "started"
    with pytest.raises(AppError) as caught:
        await anext(stream)
    assert caught.value.error_code.code == "assistant_task_deadline"
    assert closed == [True]


async def test_upstream_timeout_is_not_reported_as_the_assistant_deadline():
    from src.infra.task.background_tasks import stream_with_task_deadline

    async def source():
        raise TimeoutError("provider timed out")
        yield

    record = {"timeout_seconds": 300, "created_at": utc_now()}
    with pytest.raises(TimeoutError, match="provider timed out"):
        await anext(stream_with_task_deadline(source(), record))


@pytest.mark.parametrize("current", ["run", "newer"])
async def test_deadline_failure_is_persisted_without_recovering_or_overwriting_new_work(
    monkeypatch, current
):
    from src.infra.task.executor import TaskExecutor
    from src.kernel.errors import ErrorCode

    metadata = {"current_run_id": current, "task_status": "running"}

    async def update(session_id, run_id, values):
        if metadata["current_run_id"] != run_id:
            return False
        metadata.update(values)
        return True

    storage = SimpleNamespace(update_metadata_for_run=AsyncMock(side_effect=update))
    executor = TaskExecutor(storage, {}, SimpleNamespace())
    executor._update_session_status = AsyncMock()
    executor._send_task_notification = AsyncMock()
    executor._expire_terminal_stream = AsyncMock()
    monkeypatch.setattr("src.infra.task.executor.emit_undelivered_steer_events", AsyncMock())
    writer = SimpleNamespace(
        _flush_redis_buffer=AsyncMock(), flush_mongo_buffer=AsyncMock(), write_event=AsyncMock()
    )
    await executor._handle_generic_error(
        "child", "run", "owner", AppError(ErrorCode.ASSISTANT_TASK_DEADLINE), writer, None
    )
    executor._update_session_status.assert_not_awaited()
    if current == "run":
        assert metadata["task_status"] == "failed"
        assert metadata["task_error_code"] == "assistant_task_deadline"
        assert metadata["task_recoverable"] is False
    else:
        assert metadata == {"current_run_id": "newer", "task_status": "running"}


def test_human_authorized_followup_has_its_own_deadline_but_preserves_original_creation():
    from src.infra.task.background_tasks import task_time_remaining

    now = utc_now()
    remaining = task_time_remaining(
        {
            "created_at": now - timedelta(days=1),
            "timeout_seconds": 300,
            "authorized_run_id": "followup",
            "authorized_run_started_at": now,
        }
    )
    assert 295 < remaining <= 300


async def test_queued_assistant_task_cannot_use_a_revoked_project(monkeypatch):
    from src.api.routes import chat_agent_execution
    from src.infra.assistant.store import AssistantStore
    from src.infra.folder.storage import ProjectStorage
    from src.infra.task import background_admission, background_tasks
    from tests.infra.test_assistant_tasks import helper

    monkeypatch.setattr(AssistantStore, "get", AsyncMock(return_value=helper()))
    record = {"user_id": "owner", "assistant_id": "helper", "config": {"project_id": "revoked"}}
    monkeypatch.setattr(
        background_admission, "validate_background_run_admission", AsyncMock(return_value=record)
    )
    monkeypatch.setattr(ProjectStorage, "get_by_id", AsyncMock(return_value=None))
    monkeypatch.setattr(
        background_tasks,
        "validate_background_execution",
        AsyncMock(return_value=AgentRequest(message="")),
    )
    executed = []

    async def execute(*args, **kwargs):
        executed.append(True)
        yield {}

    monkeypatch.setattr(chat_agent_execution, "_execute_agent_stream", execute)
    with pytest.raises(AppError) as caught:
        await anext(
            background_tasks.execute_background_stream(
                "child", "search", "work", "owner", presenter=SimpleNamespace(run_id="run")
            )
        )
    assert caught.value.error_code.code == "project_not_found"
    assert executed == []
