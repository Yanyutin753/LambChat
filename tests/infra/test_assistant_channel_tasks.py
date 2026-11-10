from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.assistant import channel_tasks
from src.infra.channel.inbox_worker import current_delivery


@pytest.fixture
def routing(monkeypatch):
    record = {
        "_id": "a" * 64,
        "user_id": "owner",
        "assistant_id": "helper",
        "session_id": "child",
        "agent_id": "search",
        "state": "submitted",
    }
    lookup = AsyncMock(return_value=record)
    monkeypatch.setattr(
        channel_tasks,
        "BackgroundTaskStore",
        lambda: SimpleNamespace(collection=SimpleNamespace(find_one=lookup)),
    )
    monkeypatch.setattr(
        channel_tasks,
        "DiscussionStore",
        lambda: SimpleNamespace(get=AsyncMock(return_value={"assistant_id": "helper"})),
    )
    monkeypatch.setattr(
        channel_tasks, "validate_discussion", AsyncMock(return_value=SimpleNamespace(id="helper"))
    )
    monkeypatch.setattr(
        channel_tasks, "_load_user", AsyncMock(return_value=SimpleNamespace(sub="owner"))
    )
    session = SimpleNamespace(
        user_id="owner", metadata={"background_task_id": record["_id"], "task_status": "completed"}
    )
    monkeypatch.setattr(
        channel_tasks,
        "SessionManager",
        lambda: SimpleNamespace(get_session=AsyncMock(return_value=session)),
    )
    submit = AsyncMock(return_value={"run_id": "new-run", "status": "queued"})
    monkeypatch.setattr(channel_tasks, "_submit", submit)
    context = SimpleNamespace(checkpoint={})

    async def save(**data):
        context.checkpoint.update(data)

    context.save = AsyncMock(side_effect=save)
    token = current_delivery.set(context)
    yield record, lookup, session, submit, context
    current_delivery.reset(token)


async def test_explicit_task_reference_keeps_original_audience_and_is_admitted_only_once(routing):
    record, lookup, _, submit, context = routing
    text = f"/task {record['_id']} Add a regression check"
    result = await channel_tasks.route_task_message("owner", "discussion", text)
    assert "admitted" in result
    query = lookup.call_args.args[0]
    assert query["user_id"] == "owner" and query["assistant_id"] == "helper"
    assert query["$or"] == [
        {"assistant_source_session_id": "discussion"},
        {"parent_session_id": "discussion"},
    ]
    assert submit.call_args.args[0].session_id == "child"
    assert submit.call_args.args[0].message == "Add a regression check"
    assert context.checkpoint["assistant_task_route"]["state"] == "submitted"
    assert await channel_tasks.route_task_message("owner", "discussion", text) == result
    submit.assert_awaited_once()


async def test_foreign_task_or_busy_task_cannot_start_a_turn(routing):
    record, lookup, session, submit, _ = routing
    lookup.return_value = None
    result = await channel_tasks.route_task_message(
        "owner", "discussion", f"/task {record['_id']} go"
    )
    assert "not available" in result
    lookup.return_value = record
    session.metadata["task_status"] = "running"
    result = await channel_tasks.route_task_message(
        "owner", "discussion", f"/task {record['_id']} go"
    )
    assert "running" in result
    submit.assert_not_awaited()


async def test_ambiguous_text_stays_with_coordinator_and_uncertain_admission_never_replays(routing):
    record, _, _, submit, _ = routing
    assert (
        await channel_tasks.route_task_message("owner", "discussion", "change the earlier task")
        is None
    )
    submit.side_effect = TimeoutError()
    message = f"/task {record['_id']} go"
    first = await channel_tasks.route_task_message("owner", "discussion", message)
    assert "Check" in first
    assert await channel_tasks.route_task_message("owner", "discussion", message) == first
    submit.assert_awaited_once()
