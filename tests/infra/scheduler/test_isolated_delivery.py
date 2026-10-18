"""Scheduled runs own a hidden session; only their final result reaches the parent."""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


@pytest.fixture(autouse=True)
def no_external_notifications():
    with patch("src.infra.scheduler.results.publish_result_notification", AsyncMock()):
        yield


async def test_hidden_task_session_does_not_change_running_parent():
    from src.infra.scheduler.conversation import ensure_execution_session

    task = SimpleNamespace(id="task", owner_id="owner", name="Numbers", agent_id="search")
    parent = SimpleNamespace(
        id="parent",
        user_id="owner",
        metadata={
            "task_status": "running",
            "current_run_id": "human",
            "agent_id": "search",
            "user_timezone": "Asia/Shanghai",
            "agent_options": {"model_id": "model"},
        },
    )
    sessions = SimpleNamespace(
        get_session=AsyncMock(return_value=None), storage=SimpleNamespace(create=AsyncMock())
    )
    sessions.storage.create.side_effect = lambda data, **kw: SimpleNamespace(
        id=kw["session_id"], metadata=data.metadata, user_id=kw["user_id"]
    )
    child = await ensure_execution_session(task, parent, sessions)
    assert child.id != parent.id
    assert child.metadata["scheduled_target_session_id"] == "parent"
    assert child.metadata["hidden_from_conversation_list"] is True
    assert "current_run_id" not in child.metadata
    assert "task_status" not in child.metadata
    assert parent.metadata["current_run_id"] == "human"
    assert parent.metadata["task_status"] == "running"
    sessions.storage.create.assert_awaited_once()


async def test_existing_hidden_session_requires_matching_owner_and_task():
    from src.infra.scheduler.conversation import ensure_execution_session

    task = SimpleNamespace(id="task", owner_id="owner", name="Numbers", agent_id="search")
    parent = SimpleNamespace(id="parent", user_id="owner", metadata={})
    sessions = SimpleNamespace(
        get_session=AsyncMock(
            return_value=SimpleNamespace(user_id="other", metadata={"scheduled_task_id": "task"})
        )
    )
    with pytest.raises(ValueError):
        await ensure_execution_session(task, parent, sessions)


async def test_result_delivery_does_not_emit_user_or_terminal_events():
    from src.infra.scheduler.results import deliver_result

    task = SimpleNamespace(
        id="task",
        owner_id="owner",
        name="Numbers",
        agent_id="search",
        target_session_id="parent",
        notification_policy="always",
    )
    record = {
        "_id": "scheduled-1",
        "session_id": "child",
        "created_at": datetime(2026, 10, 16, 17, 46, 0, tzinfo=timezone.utc),
        "finished_at": datetime(2026, 10, 16, 17, 46, 50, tzinfo=timezone.utc),
    }
    parent = SimpleNamespace(user_id="owner", metadata={"current_run_id": "human"})
    traces = SimpleNamespace(
        get_run_events=AsyncMock(
            return_value=[{"event_type": "message:chunk", "data": {"content": "748196"}}]
        ),
        acquire_session_trace_write=AsyncMock(return_value=True),
        release_session_trace_write=AsyncMock(),
        collection=SimpleNamespace(update_one=AsyncMock()),
    )
    websocket = SimpleNamespace(send_to_user_with_broadcast=AsyncMock())
    with (
        patch("src.infra.scheduler.results.get_trace_storage", return_value=traces),
        patch(
            "src.infra.session.manager.SessionManager.get_session", AsyncMock(return_value=parent)
        ),
        patch("src.infra.websocket.get_connection_manager", return_value=websocket),
    ):
        await deliver_result(task, record)
    written = traces.collection.update_one.call_args.args[1]["$setOnInsert"]
    assert written["session_id"] == "parent"
    assert written["status"] == "completed"
    assert [event["event_type"] for event in written["events"]] == ["scheduled:result"]
    event = websocket.send_to_user_with_broadcast.call_args.args[1]
    assert event["type"] == "scheduled:result"
    assert event["data"]["content"] == "748196"
    assert event["data"]["message_id"] == "scheduled-result:scheduled-1"
    assert event["data"]["execution_session_id"] == "child"
    assert event["data"]["timestamp"] == "2026-10-16T17:46:00+00:00"
    assert parent.metadata == {"current_run_id": "human"}


async def test_quiet_result_is_not_delivered():
    from src.infra.scheduler.results import deliver_result

    task = SimpleNamespace(
        id="task",
        owner_id="owner",
        target_session_id="parent",
        notification_policy="meaningful_changes",
    )
    traces = SimpleNamespace(
        get_run_events=AsyncMock(
            return_value=[{"event_type": "message:chunk", "data": {"content": "NO_UPDATE"}}]
        )
    )
    with patch("src.infra.scheduler.results.get_trace_storage", return_value=traces):
        assert await deliver_result(task, {"_id": "r", "session_id": "child"}) is True


async def test_result_keeps_original_target_after_task_is_retargeted():
    from src.infra.scheduler.results import deliver_result

    task = SimpleNamespace(
        id="task",
        owner_id="owner",
        name="Numbers",
        agent_id="search",
        target_session_id="new-parent",
        notification_policy="always",
    )
    record = {"_id": "r", "session_id": "child", "target_session_id": "original-parent"}
    traces = SimpleNamespace(
        get_run_events=AsyncMock(
            return_value=[{"event_type": "message:chunk", "data": {"content": "result"}}]
        ),
        acquire_session_trace_write=AsyncMock(return_value=True),
        release_session_trace_write=AsyncMock(),
        collection=SimpleNamespace(
            update_one=AsyncMock(return_value=SimpleNamespace(upserted_id="new"))
        ),
    )
    sessions = AsyncMock(return_value=SimpleNamespace(user_id="owner"))
    websocket = SimpleNamespace(send_to_user_with_broadcast=AsyncMock())
    with (
        patch("src.infra.scheduler.results.get_trace_storage", return_value=traces),
        patch("src.infra.session.manager.SessionManager.get_session", sessions),
        patch("src.infra.websocket.get_connection_manager", return_value=websocket),
    ):
        await deliver_result(task, record)
    sessions.assert_awaited_once_with("original-parent")
    written = traces.collection.update_one.call_args.args[1]["$setOnInsert"]
    assert written["session_id"] == "original-parent"
    assert (
        websocket.send_to_user_with_broadcast.call_args.args[1]["data"]["session_id"]
        == "original-parent"
    )


async def test_reconciled_result_is_not_broadcast_twice():
    from src.infra.scheduler.results import deliver_result

    task = SimpleNamespace(
        id="task",
        owner_id="owner",
        name="Numbers",
        agent_id="search",
        target_session_id="parent",
        notification_policy="always",
    )
    traces = SimpleNamespace(
        get_run_events=AsyncMock(
            return_value=[{"event_type": "message:chunk", "data": {"content": "result"}}]
        ),
        acquire_session_trace_write=AsyncMock(return_value=True),
        release_session_trace_write=AsyncMock(),
        collection=SimpleNamespace(
            update_one=AsyncMock(
                side_effect=[
                    SimpleNamespace(upserted_id="new"),
                    SimpleNamespace(upserted_id=None),
                ]
            )
        ),
    )
    websocket = SimpleNamespace(send_to_user_with_broadcast=AsyncMock())
    with (
        patch("src.infra.scheduler.results.get_trace_storage", return_value=traces),
        patch(
            "src.infra.session.manager.SessionManager.get_session",
            AsyncMock(return_value=SimpleNamespace(user_id="owner")),
        ),
        patch("src.infra.websocket.get_connection_manager", return_value=websocket),
    ):
        await deliver_result(task, {"_id": "r", "session_id": "child"})
        await deliver_result(task, {"_id": "r", "session_id": "child"})
    websocket.send_to_user_with_broadcast.assert_awaited_once()


async def test_user_chat_and_steer_queue_do_not_delay_scheduled_admission():
    from src.infra.scheduler.conversation import dispatch_pending

    task = SimpleNamespace(
        id="t",
        owner_id="owner",
        enabled=True,
        status="active",
        target_session_id="parent",
        name="Numbers",
        agent_id="search",
        timeout_seconds=0,
        timezone="Asia/Shanghai",
        input_payload={"message": "Send a number"},
        notification_policy="always",
    )
    parent = SimpleNamespace(
        id="parent", user_id="owner", metadata={"task_status": "running", "current_run_id": "human"}
    )
    child = SimpleNamespace(
        id="sch_conversation_t",
        user_id="owner",
        metadata={"scheduled_task_id": "t", "scheduled_target_session_id": "parent"},
    )
    record = {
        "_id": "scheduled-1",
        "task_id": "t",
        "session_id": child.id,
        "target_session_id": "parent",
        "conversation_state": "pending",
    }
    storage = SimpleNamespace(
        pending_conversation_runs=AsyncMock(return_value=[record]),
        get_task=AsyncMock(return_value=task),
        claim_conversation_run=AsyncMock(return_value=record),
        update_run=AsyncMock(),
    )
    sessions = SimpleNamespace(
        get_session=AsyncMock(side_effect=lambda sid: parent if sid == "parent" else child)
    )
    submit = AsyncMock(return_value={"trace_id": "trace"})

    async def pending(sid, uid):
        return sid == "parent"

    with (
        patch("src.infra.scheduler.runner.reconcile_standalone_finalizations", AsyncMock()),
        patch("src.infra.scheduler.storage.get_scheduled_task_storage", return_value=storage),
        patch("src.infra.session.manager.SessionManager", return_value=sessions),
        patch("src.infra.goal_continuation._has_pending", pending),
        patch(
            "src.api.deps._load_user_payload",
            AsyncMock(return_value=SimpleNamespace(permissions=["chat:write"])),
        ),
        patch("src.api.routes.chat.chat_stream", submit),
    ):
        await dispatch_pending()
    assert submit.call_args.args[0].session_id == child.id
    assert parent.metadata == {"task_status": "running", "current_run_id": "human"}
    assert storage.update_run.call_args.args[1]["conversation_state"] == "submitted"


async def test_internal_schedule_instruction_is_not_persisted_as_user_input():
    from src.infra.writer.present import Presenter, PresenterConfig

    presenter = Presenter(
        PresenterConfig(
            session_id="sch_conversation_t",
            user_id="owner",
            run_id="scheduled-1",
            agent_id="search",
        )
    )
    with patch.object(presenter, "save_event", AsyncMock()) as save:
        event = await presenter.emit_user_message("Internal scheduling instruction")
    assert event["event"] == "scheduled:instruction"
    assert save.call_args.args[0]["event"] != "user:message"
