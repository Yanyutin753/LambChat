"""Transport acceptance is evidence, not a claim that a human read the result."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.infra.task.completion_events import TaskCompletionStore


async def test_receipt_requires_actual_acceptance_and_is_bound_to_owner_event():
    collection = SimpleNamespace(update_one=AsyncMock())
    store = TaskCompletionStore(collection)
    await store.record_delivery("owner", "task:run:completed", "websocket", 0)
    collection.update_one.assert_not_awaited()
    await store.record_delivery("owner", "task:run:completed", "websocket", 1)
    query, update = collection.update_one.call_args.args
    assert query["user_id"] == "owner"
    assert update["$set"]["delivery.websocket"]["recipients"] == 1
    assert "read_at" not in str(update)


async def test_executor_records_receipt_only_after_transport_accepts(monkeypatch):
    from src.infra.task.executor import TaskExecutor
    from src.infra.task.status import TaskStatus

    receipt = AsyncMock()

    async def record_once(user_id, data):
        return data, True

    monkeypatch.setattr(
        "src.infra.task.completion_events.TaskCompletionStore",
        lambda: SimpleNamespace(record_once=record_once, record_delivery=receipt),
    )
    monkeypatch.setattr(
        "src.infra.task.completion_recovery.TaskCompletionOutbox",
        lambda: SimpleNamespace(stage=AsyncMock(), clear=AsyncMock()),
    )
    monkeypatch.setattr(
        "src.infra.session.manager.SessionManager",
        lambda: SimpleNamespace(get_session=AsyncMock(return_value=None)),
    )
    send = AsyncMock(return_value=1)
    monkeypatch.setattr(
        "src.infra.websocket.get_connection_manager",
        lambda: SimpleNamespace(send_to_user_with_broadcast=send),
    )
    assert await TaskExecutor(None, {}, None)._send_task_notification(
        "chat", "run", TaskStatus.COMPLETED, "owner"
    )
    receipt.assert_awaited_once_with("owner", "task:run:completed", "websocket", 1)
