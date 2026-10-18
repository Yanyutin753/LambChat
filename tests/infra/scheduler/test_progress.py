"""Progress is sent only to the authorized parent, without parent lifecycle writes."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.infra.scheduler.results import relay_progress


@pytest.mark.parametrize("recreate_presenter", [False, True])
async def test_progress_relays_public_text_with_a_stable_result_id(recreate_presenter):
    identity = {"kind": "agent", "agent_id": "quick", "name": "Quick"}
    record = {
        "_id": "scheduled-1",
        "task_id": "t",
        "session_id": "sch_conversation_t",
        "owner_id": "owner",
        "target_session_id": "parent",
    }
    storage = SimpleNamespace(
        _get_collection=lambda _: SimpleNamespace(find_one=AsyncMock(return_value=record)),
        get_task=AsyncMock(
            return_value=SimpleNamespace(name="Numbers", notification_policy="always")
        ),
    )
    presenter = SimpleNamespace(
        config=SimpleNamespace(session_id=record["session_id"], user_id="owner"),
        run_id=record["_id"],
        trace_id="trace",
    )
    websocket = SimpleNamespace(send_to_user_with_broadcast=AsyncMock())
    with (
        patch("src.infra.scheduler.storage.get_scheduled_task_storage", return_value=storage),
        patch(
            "src.infra.session.manager.SessionManager.get_session",
            AsyncMock(return_value=SimpleNamespace(user_id="owner")),
        ),
        patch("src.infra.websocket.get_connection_manager", return_value=websocket),
        patch(
            "src.infra.scheduler.results.get_trace_storage",
            return_value=SimpleNamespace(
                get_last_trace_event=AsyncMock(
                    return_value={"data": {"assistant_identity": identity}}
                )
            ),
        ),
    ):
        await relay_progress(
            presenter,
            {
                "event": "scheduled:instruction",
                "data": {"content": "INTERNAL", "assistant_identity": identity},
            },
        )
        if recreate_presenter:
            del presenter._scheduled_progress
        await relay_progress(
            presenter,
            {"event": "thinking", "data": {"content": "Checking", "thinking_id": "thought"}},
        )
        await relay_progress(
            presenter, {"event": "message:chunk", "data": {"content": "child", "depth": 1}}
        )
        await relay_progress(presenter, {"event": "message:chunk", "data": {"content": "748196"}})
        await relay_progress(
            presenter,
            {
                "event": "tool:start",
                "data": {"tool": "execute", "tool_call_id": "exec-1", "args": {"command": "date"}},
            },
        )
        await relay_progress(presenter, {"event": "done", "data": {}})
    events = [call.args[1] for call in websocket.send_to_user_with_broadcast.await_args_list]
    assert events[0]["type"] == "scheduled:progress"
    assert events[0]["data"]["content"] == ""
    assert events[-1]["data"]["content"] == "748196"
    assert all(e["data"]["session_id"] == "parent" for e in events)
    assert all(e["data"]["message_id"] == "scheduled-result:scheduled-1" for e in events)
    assert all(e["data"]["assistant_identity"] == identity for e in events)
    assert not any("INTERNAL" in str(e) for e in events)
    public = events[-1]["data"]["events"]
    assert [event["event_type"] for event in public] == [
        "thinking",
        "message:chunk",
        "message:chunk",
        "tool:start",
        "done",
    ]
    assert public[0]["data"]["content"] == "Checking"
    assert events[-1]["data"]["execution_session_id"] == "sch_conversation_t"


async def test_foreground_events_do_not_query_or_publish_scheduled_progress():
    presenter = SimpleNamespace(
        config=SimpleNamespace(session_id="parent", user_id="owner"), run_id="human"
    )
    with patch("src.infra.scheduler.storage.get_scheduled_task_storage") as storage:
        await relay_progress(presenter, {"event": "message:chunk", "data": {"content": "normal"}})
    storage.assert_not_called()


async def test_scheduled_pending_approval_has_parent_display_and_original_resume_target():
    from src.infra.scheduler.results import approval_view

    approval = SimpleNamespace(
        session_id="sch_conversation_t",
        user_id="owner",
        metadata={"run_id": "scheduled-1", "mode": "interrupt"},
        model_dump=lambda **_kwargs: {
            "id": "approval",
            "session_id": "sch_conversation_t",
            "metadata": {"run_id": "scheduled-1", "mode": "interrupt"},
        },
    )
    record = {"target_session_id": "parent", "task_id": "t"}
    find = AsyncMock(return_value=record)
    storage = SimpleNamespace(_get_collection=lambda _: SimpleNamespace(find_one=find))
    with (
        patch("src.infra.scheduler.storage.get_scheduled_task_storage", return_value=storage),
        patch(
            "src.infra.session.manager.SessionManager.get_session",
            AsyncMock(return_value=SimpleNamespace(id="parent", user_id="owner")),
        ),
    ):
        view = await approval_view(approval)
    assert view["session_id"] == "sch_conversation_t"
    assert view["metadata"]["scheduled_target_session_id"] == "parent"
    assert view["metadata"]["run_id"] == "scheduled-1"
    assert "scheduled_target_session_id" not in approval.metadata
    assert find.call_args.args[0] == {
        "_id": "scheduled-1",
        "session_id": "sch_conversation_t",
        "owner_id": "owner",
    }


async def test_scheduled_approval_never_projects_into_another_owners_parent():
    from src.infra.scheduler.results import approval_view

    approval = SimpleNamespace(
        session_id="sch_conversation_t",
        user_id="owner",
        metadata={"run_id": "scheduled-1"},
        model_dump=lambda **_kwargs: {"metadata": {"run_id": "scheduled-1"}},
    )
    storage = SimpleNamespace(
        _get_collection=lambda _: SimpleNamespace(
            find_one=AsyncMock(return_value={"target_session_id": "parent"})
        )
    )
    with (
        patch("src.infra.scheduler.storage.get_scheduled_task_storage", return_value=storage),
        patch(
            "src.infra.session.manager.SessionManager.get_session",
            AsyncMock(return_value=SimpleNamespace(id="parent", user_id="another")),
        ),
    ):
        view = await approval_view(approval)
    assert "scheduled_target_session_id" not in view["metadata"]


@pytest.mark.parametrize("followup", [None, "token:usage", "approval_resolved"])
async def test_suspension_relays_approval_to_parent_without_changing_its_resume_session(followup):
    from src.infra.storage.mongodb import PendingApproval

    record = {"task_id": "t", "target_session_id": "parent"}
    storage = SimpleNamespace(
        _get_collection=lambda _: SimpleNamespace(find_one=AsyncMock(return_value=record)),
        get_task=AsyncMock(
            return_value=SimpleNamespace(name="Confirm", notification_policy="always")
        ),
    )
    approval = PendingApproval(
        id="confirm",
        message="Confirm test command",
        user_id="owner",
        session_id="sch_conversation_t",
        metadata={"run_id": "scheduled-1", "mode": "interrupt"},
    )
    presenter = SimpleNamespace(
        config=SimpleNamespace(session_id="sch_conversation_t", user_id="owner"),
        run_id="scheduled-1",
        trace_id="trace",
    )
    websocket = SimpleNamespace(send_to_user_with_broadcast=AsyncMock())
    with (
        patch("src.infra.scheduler.storage.get_scheduled_task_storage", return_value=storage),
        patch(
            "src.infra.session.manager.SessionManager.get_session",
            AsyncMock(return_value=SimpleNamespace(id="parent", user_id="owner")),
        ),
        patch(
            "src.infra.storage.mongodb.get_approval_storage",
            return_value=SimpleNamespace(list_pending=AsyncMock(return_value=[approval])),
        ),
        patch(
            "src.infra.scheduler.results.get_trace_storage",
            return_value=SimpleNamespace(get_last_trace_event=AsyncMock(return_value=None)),
        ),
        patch("src.infra.websocket.get_connection_manager", return_value=websocket),
    ):
        await relay_progress(presenter, {"event": "hitl:suspended", "data": {}})
        if followup:
            await relay_progress(presenter, {"event": followup, "data": {"id": "confirm"}})
    event = websocket.send_to_user_with_broadcast.call_args.args[1]
    if followup == "approval_resolved":
        assert event["data"]["status"] == "running"
        assert not event["data"].get("approvals")
        return
    assert event["data"]["status"] == "waiting_human"
    assert event["data"]["session_id"] == "parent"
    assert event["data"]["approvals"][0]["session_id"] == "sch_conversation_t"
    assert event["data"]["approvals"][0]["metadata"]["scheduled_target_session_id"] == "parent"


async def test_parent_reentry_restores_a_scheduled_run_waiting_for_confirmation():
    from datetime import datetime, timezone

    from src.infra.scheduler.results import get_session_progress
    from src.infra.task.status import TaskStatus

    record = {
        "_id": "scheduled-1",
        "task_id": "t",
        "session_id": "sch_conversation_t",
        "target_session_id": "parent",
        "owner_id": "owner",
        "created_at": datetime.now(timezone.utc),
    }

    class Cursor:
        def __aiter__(self):
            async def rows():
                yield record

            return rows()

    storage = SimpleNamespace(
        _get_collection=lambda _: SimpleNamespace(find=lambda _: Cursor()),
        get_task=AsyncMock(return_value=SimpleNamespace(name="Numbers", owner_id="owner")),
    )
    events = [
        {"event_type": "scheduled:instruction", "data": {"content": "INTERNAL"}},
        {
            "event_type": "tool:start",
            "data": {"tool": "execute", "tool_call_id": "exec", "args": {}},
        },
        {"event_type": "hitl:suspended", "data": {}},
    ]
    active_events = AsyncMock(return_value=events)
    with (
        patch("src.infra.scheduler.storage.get_scheduled_task_storage", return_value=storage),
        patch(
            "src.infra.session.manager.SessionManager.get_session",
            AsyncMock(return_value=SimpleNamespace(user_id="owner")),
        ),
        patch(
            "src.infra.scheduler.results.get_trace_storage",
            return_value=SimpleNamespace(
                get_run_events=AsyncMock(return_value=[]),
                get_session_events=active_events,
            ),
        ),
        patch(
            "src.infra.task.manager.get_task_manager",
            return_value=SimpleNamespace(
                get_run_status=AsyncMock(return_value=TaskStatus.WAITING_HUMAN)
            ),
        ),
    ):
        progress = await get_session_progress("parent", "owner")
    active_events.assert_awaited_once_with(
        "sch_conversation_t", run_id="scheduled-1", completed_only=False
    )
    assert len(progress) == 1
    assert progress[0]["session_id"] == "parent"
    assert progress[0]["status"] == "waiting_human"
    assert progress[0]["message_id"] == "scheduled-result:scheduled-1"
    assert [item["event_type"] for item in progress[0]["events"]] == [
        "tool:start",
        "hitl:suspended",
    ]


async def test_progress_catchup_rejects_a_foreign_parent_before_reading_runs():
    from src.infra.scheduler.results import get_session_progress
    from src.kernel.errors import AppError

    with (
        patch(
            "src.infra.session.manager.SessionManager.get_session",
            AsyncMock(return_value=SimpleNamespace(user_id="other")),
        ),
        patch("src.infra.scheduler.storage.get_scheduled_task_storage") as storage,
    ):
        with pytest.raises(AppError):
            await get_session_progress("parent", "owner")
    storage.assert_not_called()


@pytest.mark.parametrize(
    ("live_status", "stored_status", "content", "expected"),
    [
        ("completed", "success", "NO_UPDATE", "quiet"),
        ("completed", "success", "", "quiet"),
        ("failed", "failed", "", "failed"),
        (None, "failed", "", "failed"),
        ("pending", "failed", "", "failed"),
        ("running", "running", "", "running"),
    ],
)
async def test_catchup_restores_known_terminal_run_without_a_delivered_result(
    live_status, stored_status, content, expected
):
    from datetime import datetime, timezone
    from unittest.mock import Mock

    from src.infra.scheduler.results import get_session_progress
    from src.infra.task.status import TaskStatus

    record = {
        "_id": "scheduled-1",
        "task_id": "t",
        "session_id": "sch_conversation_t",
        "target_session_id": "parent",
        "owner_id": "owner",
        "created_at": datetime.now(timezone.utc),
        "conversation_state": "finished" if stored_status != "running" else "submitted",
        "status": stored_status,
    }

    class Cursor:
        def __aiter__(self):
            async def rows():
                yield record

            return rows()

    find = Mock(return_value=Cursor())
    storage = SimpleNamespace(
        _get_collection=lambda _: SimpleNamespace(find=find),
        get_task=AsyncMock(
            return_value=SimpleNamespace(
                name="Numbers", owner_id="owner", notification_policy="meaningful_changes"
            )
        ),
    )
    events = [{"event_type": "message:chunk", "data": {"content": content}}] if content else []
    with (
        patch("src.infra.scheduler.storage.get_scheduled_task_storage", return_value=storage),
        patch(
            "src.infra.session.manager.SessionManager.get_session",
            AsyncMock(return_value=SimpleNamespace(user_id="owner")),
        ),
        patch(
            "src.infra.scheduler.results.get_trace_storage",
            return_value=SimpleNamespace(
                get_session_events=AsyncMock(return_value=events),
                get_run_events=AsyncMock(return_value=events),
            ),
        ),
        patch(
            "src.infra.task.manager.get_task_manager",
            return_value=SimpleNamespace(
                get_run_status=AsyncMock(
                    return_value=TaskStatus(live_status) if live_status else None
                )
            ),
        ),
    ):
        progress = await get_session_progress("parent", "owner", run_ids=["scheduled-1"])
    assert len(progress) == 1
    assert progress[0]["status"] == expected
    assert progress[0]["run_id"] == "scheduled-1"
    query = find.call_args.args[0]
    assert query["owner_id"] == "owner"
    assert query["target_session_id"] == "parent"
    assert {"_id": {"$in": ["scheduled-1"]}} in query["$or"]
