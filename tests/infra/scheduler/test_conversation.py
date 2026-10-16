"""Conversation schedules preserve history and defer without stealing a running chat."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.kernel.schemas.scheduled_task import ScheduledTaskCreate


def request(**fields):
    return ScheduledTaskCreate(
        name="Follow up",
        agent_id="search",
        trigger_type="interval",
        trigger_config={"seconds": 60},
        **fields,
    )


def test_legacy_requests_remain_standalone():
    assert request().execution_mode == "standalone"


def test_conversation_fields_survive_validation():
    task = request(
        execution_mode="conversation",
        target_session_id="chat-1",
        notification_policy="meaningful_changes",
    )
    assert task.execution_mode == "conversation"
    assert task.target_session_id == "chat-1"
    assert task.notification_policy == "meaningful_changes"


async def test_conversation_target_requires_ownership():
    from src.infra.scheduler.service import ScheduledTaskService
    from src.kernel.errors import AppError

    with patch(
        "src.infra.session.manager.SessionManager.get_session",
        AsyncMock(return_value=SimpleNamespace(user_id="someone-else")),
    ):
        with pytest.raises(AppError):
            await ScheduledTaskService()._validate_conversation("conversation", "chat-1", "owner")


def test_request_inherits_latest_configuration_without_provider_secrets():
    from src.infra.scheduler.conversation import build_request

    task = SimpleNamespace(
        id="t",
        name="Follow up",
        input_payload={"message": "Check PR"},
        notification_policy="meaningful_changes",
    )
    session = SimpleNamespace(
        id="chat-1",
        metadata={
            "agent_id": "search",
            "project_id": "p",
            "enabled_skills": ["review"],
            "agent_options": {"model_id": "latest", "api_key": "secret", "_resolved": True},
        },
    )
    result = build_request(task, session, "run-1")
    assert result.session_id == "chat-1"
    assert result.project_id == "p"
    assert result.enabled_skills == ["review"]
    assert result.agent_options == {"model_id": "latest"}
    assert "Check PR" in result.message
    assert "NO_UPDATE" in result.message


async def test_busy_conversation_does_not_admit_schedule():
    from src.infra.scheduler.conversation import ConversationBusyError, ensure_idle

    session = SimpleNamespace(
        id="chat-1", user_id="owner", metadata={"task_status": "waiting_human"}
    )
    with pytest.raises(ConversationBusyError):
        await ensure_idle(session)


def test_quiet_completion_requires_exact_final_result():
    from src.infra.scheduler.conversation import is_quiet_result

    assert is_quiet_result("completed", "meaningful_changes", " NO_UPDATE\n")
    assert not is_quiet_result("failed", "meaningful_changes", "NO_UPDATE")
    assert not is_quiet_result("waiting_human", "meaningful_changes", "NO_UPDATE")
    assert not is_quiet_result("completed", "always", "NO_UPDATE")
    assert not is_quiet_result("completed", "meaningful_changes", "Found NO_UPDATE in a file")


async def test_old_run_status_does_not_read_new_run_status():
    from src.infra.task.status import TaskStatus
    from src.infra.task.status_queries import TaskStatusQueries

    storage = SimpleNamespace(
        get_by_session_id=AsyncMock(
            return_value=SimpleNamespace(
                metadata={"current_run_id": "new", "task_status": "running"}
            )
        )
    )
    cursor = SimpleNamespace(
        sort=lambda *a: cursor,
        limit=lambda *a: cursor,
        to_list=AsyncMock(return_value=[{"status": "completed"}]),
    )
    with patch(
        "src.infra.task.status_queries.get_trace_storage",
        return_value=SimpleNamespace(collection=SimpleNamespace(find=lambda *a: cursor)),
    ):
        assert (
            await TaskStatusQueries(storage=storage, run_info={}).get_run_status("chat", "old")
            == TaskStatus.COMPLETED
        )


async def test_two_wakeups_cannot_claim_the_same_pending_record():
    """The database predicate, rather than a process-local busy flag, selects one owner."""
    from src.infra.scheduler.storage import ScheduledTaskStorage

    storage = ScheduledTaskStorage()
    calls = []

    class Collection:
        async def find_one_and_update(self, query, update, **kwargs):
            calls.append(query)
            return {"_id": "r"} if len(calls) == 1 else None

    storage._collections["task_run_records"] = Collection()
    import asyncio

    owners = await asyncio.gather(
        storage.claim_conversation_run("r"), storage.claim_conversation_run("r")
    )
    assert sum(owner is not None for owner in owners) == 1
    assert all(query == {"_id": "r", "conversation_state": "pending"} for query in calls)


def test_cold_arq_worker_resolves_conversation_executor():
    from src.infra.scheduler.conversation import execute_conversation_schedule
    from src.infra.task.arq_worker import _resolve_executor

    with patch("src.infra.task.arq_worker.get_registered_executor", return_value=None):
        assert _resolve_executor("conversation_schedule") is execute_conversation_schedule


@pytest.mark.parametrize("status", ["cancelled", "cancelling", "completed", "expired", "failed"])
async def test_terminal_schedule_cannot_be_resurrected(status):
    from src.infra.goal_runtime import GoalRunAdmissionError
    from src.infra.scheduler.conversation import validate_scheduled_run_admission

    session = SimpleNamespace(
        user_id="owner", metadata={"current_run_id": "r", "task_status": status}
    )
    collection = SimpleNamespace(find_one=AsyncMock(return_value={"_id": "r"}))
    storage = SimpleNamespace(_get_collection=lambda name: collection)
    with (
        patch(
            "src.infra.session.manager.SessionManager.get_session", AsyncMock(return_value=session)
        ),
        patch("src.infra.scheduler.storage.get_scheduled_task_storage", return_value=storage),
    ):
        with pytest.raises(GoalRunAdmissionError):
            await validate_scheduled_run_admission("chat", "owner", "r")


async def test_scheduled_execution_clears_submission_identity_for_nested_tasks():
    from contextlib import asynccontextmanager

    from src.infra.goal_runtime import with_goal_run_lease
    from src.infra.scheduler.conversation import SCHEDULED_SUBMISSION, execute_conversation_schedule
    from src.kernel.schemas.agent import AgentRequest

    @asynccontextmanager
    async def lease(*args, **kwargs):
        yield None

    @with_goal_run_lease
    async def consume(session_id, user_id, run_id, executor):
        return [
            event
            async for event in executor(
                session_id, "quick", "check", user_id, presenter=SimpleNamespace(run_id=run_id)
            )
        ]

    observed = []

    async def stream(*args, **kwargs):
        observed.append(SCHEDULED_SUBMISSION.get())
        yield {"event": "done"}

    with (
        patch("src.infra.goal_runtime.goal_run_lease", lease),
        patch("src.infra.scheduler.conversation.validate_scheduled_run_admission", AsyncMock()),
        patch(
            "src.infra.task.background_tasks.validate_background_execution",
            AsyncMock(return_value=AgentRequest(message="")),
        ),
        patch("src.api.routes.chat_agent_execution._execute_agent_stream", stream),
    ):
        token = SCHEDULED_SUBMISSION.set({"task_id": "parent", "run_id": "r"})
        try:
            events = await consume("chat", "owner", "r", execute_conversation_schedule)
            assert observed == [None]
            assert events == [{"event": "done"}]
            assert SCHEDULED_SUBMISSION.get()["run_id"] == "r"
        finally:
            SCHEDULED_SUBMISSION.reset(token)


async def test_pending_scan_rotates_past_busy_first_page():
    from datetime import datetime, timezone

    from src.infra.scheduler.storage import ScheduledTaskStorage

    now = datetime.now(timezone.utc)
    records = [{"_id": str(index), "created_at": now} for index in range(100)]
    queries = []

    class Cursor:
        def sort(self, *args):
            return self

        def limit(self, *args):
            return self

        async def to_list(self, **kwargs):
            return records if len(queries) == 1 else []

    class Collection:
        def find(self, query):
            queries.append(query)
            return Cursor()

    storage = ScheduledTaskStorage()
    storage._collections["task_run_records"] = Collection()
    await storage.pending_conversation_runs()
    await storage.pending_conversation_runs()
    assert queries[1]["$or"] == [
        {"created_at": {"$gt": now}},
        {"created_at": now, "_id": {"$gt": "99"}},
    ]
    assert storage._conversation_scan_after is None


async def test_scheduled_stream_survives_watchdog_task_boundaries():
    from src.infra.scheduler.conversation import execute_conversation_schedule
    from src.infra.task.stall_watchdog import aiter_with_stall_timeout
    from src.kernel.schemas.agent import AgentRequest

    async def stream(*args, **kwargs):
        yield {"event": "message", "data": {"content": "OK"}}
        yield {"event": "done"}

    with (
        patch("src.infra.scheduler.conversation.validate_scheduled_run_admission", AsyncMock()),
        patch(
            "src.infra.task.background_tasks.validate_background_execution",
            AsyncMock(return_value=AgentRequest(message="")),
        ),
        patch("src.api.routes.chat_agent_execution._execute_agent_stream", stream),
    ):
        events = [
            event
            async for event in aiter_with_stall_timeout(
                execute_conversation_schedule(
                    "chat", "quick", "check", "owner", presenter=SimpleNamespace(run_id="r")
                ),
                timeout=1,
            )
        ]
        assert [event["event"] for event in events] == ["message", "done"]


async def test_conversation_enqueue_preserves_wire_identity_and_owner():
    from src.infra.scheduler.storage import ScheduledTaskStorage

    class Collection:
        async def find_one_and_update(self, query, update, **kwargs):
            return update["$setOnInsert"]

    storage = ScheduledTaskStorage()
    storage._collections["task_run_records"] = Collection()
    task = SimpleNamespace(
        id="task",
        agent_id="quick",
        target_session_id="chat",
        input_payload={"message": "check"},
        owner_id="owner",
        timeout_seconds=60,
    )
    record = await storage.enqueue_conversation(task, "manual")
    assert record["_id"].startswith("scheduled-")
    assert record["session_id"] == "chat"
    assert record["owner_id"] == "owner"
    assert record["conversation_pending"] is True
    assert record["input_snapshot"] == {"message": "check"}


async def test_finish_resolves_quiet_result_before_channel_delivery():
    from src.infra.scheduler.conversation import _finish

    collection = SimpleNamespace(
        update_one=AsyncMock(return_value=SimpleNamespace(modified_count=1)),
        find_one=AsyncMock(return_value={}),
    )
    storage = SimpleNamespace(
        _get_collection=lambda name: collection,
        update_task_run_stats=AsyncMock(),
        get_task=AsyncMock(
            return_value=SimpleNamespace(delivery={"channel": "test"}, trigger_type="interval")
        ),
        update_run=AsyncMock(),
    )
    record = {
        "_id": "run",
        "task_id": "task",
        "session_id": "chat",
        "conversation_state": "submitted",
    }
    resolve = AsyncMock(return_value=("task", True))
    deliver = AsyncMock()
    with (
        patch(
            "src.infra.session.trace_storage.get_trace_storage",
            return_value=SimpleNamespace(
                collection=SimpleNamespace(find_one=AsyncMock(return_value={}))
            ),
        ),
        patch("src.infra.scheduler.conversation.completion_context", resolve),
        patch("src.infra.scheduler.runner.ScheduledTaskRunner._deliver_success_result", deliver),
    ):
        await _finish(storage, record, "success")
    resolve.assert_awaited_once_with("chat", "run", "completed")
    deliver.assert_not_awaited()
