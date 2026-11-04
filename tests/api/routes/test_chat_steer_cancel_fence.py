"""Late steer requests expose cancellation without crossing session ownership."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api.routes import chat
from src.infra.task.status import TaskStatus
from src.infra.task.steer import SteerQueue
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.agent import SteerRequest


@pytest.fixture
def route_queue(monkeypatch):
    queue = SteerQueue(redis=None)
    monkeypatch.setattr("src.infra.task.steer.get_steer_queue", lambda: queue)
    monkeypatch.setattr(
        chat,
        "_get_owned_session",
        AsyncMock(return_value=SimpleNamespace(metadata={"current_run_id": "run-1"})),
    )
    monkeypatch.setattr(
        chat,
        "get_task_manager",
        lambda: SimpleNamespace(get_status=AsyncMock(return_value=TaskStatus.RUNNING)),
    )
    monkeypatch.setattr(chat, "validate_steer_attachments", AsyncMock())

    @asynccontextmanager
    async def submission(*args, **kwargs):
        yield

    monkeypatch.setattr(chat, "conversation_submission", submission)
    return queue


async def test_cancel_before_post_returns_cancelled_instead_of_accepted(route_queue):
    user = SimpleNamespace(sub="owner")
    request = SteerRequest(message="withdrawn", message_id="message", expected_run_id="run-1")
    await chat.cancel_steered_message("session", request, user)
    result = await chat.steer_running_agent("session", request, user)
    assert result["outcome"] == "cancelled"
    assert result["queued"] == 0
    assert await route_queue.list_items("session") == []


async def test_non_owner_cannot_create_a_cancellation_fence(route_queue, monkeypatch):
    cancel = AsyncMock()
    monkeypatch.setattr(route_queue, "remove_by_id", cancel)
    monkeypatch.setattr(
        chat, "_get_owned_session", AsyncMock(side_effect=AppError(ErrorCode.FORBIDDEN))
    )
    with pytest.raises(AppError):
        await chat.cancel_steered_message(
            "session",
            SteerRequest(message="withdrawn", message_id="message"),
            SimpleNamespace(sub="other-user"),
        )
    cancel.assert_not_awaited()


async def test_consumed_steer_returns_delivered_without_reenqueue(route_queue):
    from src.infra.task.steer import SteerItem

    await route_queue.enqueue_item("session", SteerItem("message", "once"))
    await route_queue.drain_items("session")
    await route_queue.ack_items("session")
    result = await chat.steer_running_agent(
        "session",
        SteerRequest(message="once", message_id="message", expected_run_id="run-1"),
        SimpleNamespace(sub="owner"),
    )
    assert result["outcome"] == "delivered"
    assert result["queued"] == 0
    assert await route_queue.list_items("session") == []


async def test_promotion_cleanup_does_not_withdraw_the_message_identity(route_queue):
    user = SimpleNamespace(sub="owner")
    request = SteerRequest(message="retry", message_id="message", expected_run_id="run-1")
    await chat.cancel_steered_message("session", request, user, prevent_reenqueue=False)
    result = await chat.steer_running_agent("session", request, user)
    assert result["outcome"] == "accepted"
