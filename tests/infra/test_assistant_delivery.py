from types import SimpleNamespace
from unittest.mock import AsyncMock

from src.infra.assistant import delivery
from src.kernel.errors import AppError, ErrorCode


async def test_result_returns_only_to_the_fresh_authorized_discussion(monkeypatch):
    record = {"_id": "task", "user_id": "owner", "session_id": "child", "assistant_id": "a"}
    lookup = AsyncMock(return_value=record)
    monkeypatch.setattr(
        delivery,
        "BackgroundTaskStore",
        lambda: SimpleNamespace(collection=SimpleNamespace(find_one=lookup)),
    )
    audience = {"channel_type": "telegram", "channel_instance_id": "bound", "chat_id": "original"}
    validate = AsyncMock(return_value=audience)
    monkeypatch.setattr(delivery, "task_discussion", validate)
    monkeypatch.setattr(delivery, "_load_user", AsyncMock(return_value=SimpleNamespace()))
    monkeypatch.setattr(delivery, "_build_delivery_text", AsyncMock(return_value="actual result"))
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(
        delivery, "get_channel_coordinator", lambda: SimpleNamespace(send_message=send)
    )
    assert await delivery.deliver_assistant_task_result("owner", "child", "run", "completed", None)
    lookup.assert_awaited_once_with({"user_id": "owner", "session_id": "child"})
    validate.assert_awaited_once_with(record, "owner")
    assert send.call_args.args[2:4] == ("original", "actual result")
    assert send.call_args.kwargs["instance_id"] == "bound"
    validate.side_effect = AppError(ErrorCode.FORBIDDEN)
    send.reset_mock()
    assert not await delivery.deliver_assistant_task_result(
        "owner", "child", "run", "completed", None
    )
    send.assert_not_awaited()


async def test_private_task_or_nonterminal_status_does_not_send(monkeypatch):
    lookup = AsyncMock(return_value={"assistant_id": "a"})
    monkeypatch.setattr(
        delivery,
        "BackgroundTaskStore",
        lambda: SimpleNamespace(collection=SimpleNamespace(find_one=lookup)),
    )
    monkeypatch.setattr(delivery, "task_discussion", AsyncMock(return_value=None))
    monkeypatch.setattr(delivery, "_load_user", AsyncMock())
    send = AsyncMock()
    monkeypatch.setattr(
        delivery, "get_channel_coordinator", lambda: SimpleNamespace(send_message=send)
    )
    assert not await delivery.deliver_assistant_task_result(
        "owner", "child", "run", "completed", None
    )
    assert not await delivery.deliver_assistant_task_result(
        "owner", "child", "run", "running", None
    )
    send.assert_not_awaited()
