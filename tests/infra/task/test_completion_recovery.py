from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.infra.task.executor import TaskExecutor
from src.infra.task.status import TaskStatus
from tests.infra.task.test_completion_events import Collection


class Outbox:
    def __init__(self):
        self.events = []

    async def stage(self, session_id, user_id, data):
        value = {"session_id": session_id, "user_id": user_id, "data": deepcopy(data)}
        if value not in self.events:
            self.events.append(value)

    async def clear(self, session_id, user_id, key):
        self.events = [
            item
            for item in self.events
            if not (
                item["session_id"] == session_id
                and item["user_id"] == user_id
                and item["data"]["dedupe_key"] == key
            )
        ]

    async def pending(self, limit=25):
        return deepcopy(self.events[:limit])


async def test_journal_failure_keeps_pending_completion_and_scanner_recovers_without_model(
    monkeypatch,
):
    from src.infra.task import completion_events, completion_recovery

    outbox = Outbox()
    store = completion_events.TaskCompletionStore(Collection())
    monkeypatch.setattr(completion_events, "TaskCompletionStore", lambda: store)
    monkeypatch.setattr(completion_recovery, "TaskCompletionOutbox", lambda: outbox)
    session = SimpleNamespace(
        metadata={"background_parent_session_id": "parent"}, user_id="u", unread_count=0
    )
    monkeypatch.setattr(
        "src.infra.session.manager.SessionManager",
        lambda: SimpleNamespace(get_session=AsyncMock(return_value=session)),
    )
    monkeypatch.setattr(
        "src.infra.folder.storage.get_project_storage",
        lambda: SimpleNamespace(get_by_type=AsyncMock(return_value=None)),
    )
    live = AsyncMock(return_value=1)
    monkeypatch.setattr(
        "src.infra.websocket.get_connection_manager",
        lambda: SimpleNamespace(send_to_user_with_broadcast=live),
    )
    executor = TaskExecutor(None, {}, None)
    durable_record = store.record_once
    monkeypatch.setattr(
        store, "record_once", AsyncMock(side_effect=ConnectionError("temporary journal outage"))
    )
    await executor._send_task_notification("s", "r", TaskStatus.COMPLETED, "u")
    assert len(outbox.events) == 1
    assert outbox.events[0]["data"]["parent_session_id"] == "parent"
    assert not (await store.list_for_user("u"))["items"]
    live.assert_not_awaited()
    monkeypatch.setattr(store, "record_once", durable_record)
    # Current session state changed; recovery must retain the original classified event.
    session.metadata = {
        "persistent_goal_id": "new",
        "persistent_goal_status": "active",
        "persistent_goal_run_id": "r",
    }
    await completion_recovery.reconcile_pending_completions(outbox=outbox, executor=executor)
    assert not outbox.events
    items = (await store.list_for_user("u"))["items"]
    assert len(items) == 1
    assert items[0]["notification_kind"] == "background_task_complete"
    assert items[0]["parent_session_id"] == "parent"
    live.assert_awaited_once()


async def test_reconcile_batch_is_bounded_and_keeps_other_pending_completions():
    from src.infra.task.completion_recovery import reconcile_pending_completions

    outbox = Outbox()
    for index in range(30):
        await outbox.stage(
            "s",
            "u",
            {"run_id": str(index), "status": "completed", "dedupe_key": f"task:{index}:completed"},
        )
    calls = []

    async def notify(session_id, run_id, status, user_id, *, prepared_completion):
        calls.append(run_id)
        await outbox.clear(session_id, user_id, prepared_completion["dedupe_key"])

    await reconcile_pending_completions(
        outbox=outbox, executor=SimpleNamespace(_send_task_notification=notify)
    )
    assert len(calls) == 25
    assert len(outbox.events) == 5


async def test_existing_goal_scanner_reconciles_notifications_even_without_active_goals(
    monkeypatch,
):
    from src.infra import goal_continuation
    from src.infra.task import completion_recovery

    class EmptyCursor:
        def sort(self, *args):
            return self

        def __aiter__(self):
            return self

        async def __anext__(self):
            raise StopAsyncIteration

    reconcile = AsyncMock()
    monkeypatch.setattr(completion_recovery, "reconcile_pending_completions", reconcile)
    monkeypatch.setattr(
        goal_continuation,
        "GoalStore",
        lambda: SimpleNamespace(collection=SimpleNamespace(find=lambda query: EmptyCursor())),
    )
    await goal_continuation.scan_persistent_goals()
    reconcile.assert_awaited_once()


async def test_outbox_uses_add_and_keyed_clear_instead_of_overwriting_newer_run():
    from src.infra.task.completion_recovery import TaskCompletionOutbox

    update = AsyncMock()
    storage = SimpleNamespace(
        _find_doc=AsyncMock(return_value={"_id": "canonical"}),
        collection=SimpleNamespace(update_one=update),
    )
    outbox = TaskCompletionOutbox(storage)
    data = {"run_id": "old", "status": "completed", "dedupe_key": "task:old:completed"}
    await outbox.stage("s", "u", data)
    await outbox.clear("s", "u", data["dedupe_key"])
    assert update.call_args_list[0].args == (
        {"_id": "canonical", "user_id": "u"},
        {"$addToSet": {"metadata.pending_task_completions": data}},
    )
    assert update.call_args_list[1].args == (
        {"_id": "canonical", "user_id": "u"},
        {"$pull": {"metadata.pending_task_completions": {"dedupe_key": data["dedupe_key"]}}},
    )
