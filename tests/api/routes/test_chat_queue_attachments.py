"""Attachment-only follow-ups retain the normal attachment authority boundary."""
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api.routes import chat
from src.infra.task.status import TaskStatus
from src.infra.task.steer import SteerItem, SteerQueue, emit_undelivered_steer_events
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.agent import SteerRequest

ATTACHMENT = {
    "id": "image-1", "key": "uploads/image-1", "name": "截图.png", "type": "image",
    "mimeType": "image/png", "size": 100, "url": "/api/files/image-1",
}

@pytest.fixture
def admission(monkeypatch):
    @asynccontextmanager
    async def lease(*args, **kwargs):
        yield
    session = SimpleNamespace(id="s1", user_id="u1", agent_id="search", metadata={"current_run_id": "r1"})
    queue = SteerQueue(redis=None)
    monkeypatch.setattr(chat, "conversation_submission", lease)
    monkeypatch.setattr(chat, "SessionManager", lambda: SimpleNamespace(get_session=AsyncMock(return_value=session)))
    monkeypatch.setattr(chat, "get_task_manager", lambda: SimpleNamespace(get_status=AsyncMock(return_value=TaskStatus.RUNNING)))
    monkeypatch.setattr("src.infra.task.steer.get_steer_queue", lambda: queue)
    return queue

async def test_attachment_only_steer_is_accepted_and_keeps_its_id(admission):
    result = await chat.steer_running_agent("s1", SteerRequest(message="", message_id="image-only", expected_run_id="r1", attachments=[ATTACHMENT]), user=SimpleNamespace(sub="u1"))
    assert result["message_id"] == "image-only"
    [item] = await admission.list_items("s1")
    assert item.content == ""
    assert item.attachments[0]["id"] == "image-1"

async def test_attachment_only_steer_still_checks_attachment_authority(admission, monkeypatch):
    validate = AsyncMock(side_effect=AppError(ErrorCode.FORBIDDEN))
    monkeypatch.setattr(chat, "validate_steer_attachments", validate)
    with pytest.raises(AppError) as error:
        await chat.steer_running_agent("s1", SteerRequest(message="", attachments=[ATTACHMENT]), user=SimpleNamespace(sub="u1"))
    assert error.value.error_code is ErrorCode.FORBIDDEN
    validate.assert_awaited_once()
    assert not await admission.list_items("s1")

async def test_empty_steer_without_attachments_remains_rejected(admission):
    with pytest.raises(AppError) as error:
        await chat.steer_running_agent("s1", SteerRequest(message=" "), user=SimpleNamespace(sub="u1"))
    assert error.value.error_code is ErrorCode.STEER_CONTENT_REQUIRED

async def test_attachment_only_undelivered_event_retains_the_same_payload():
    queue = SteerQueue(redis=None)
    await queue.enqueue_item("s1", SteerItem(id="image-only", content="", attachments=[ATTACHMENT]))
    presenter = SimpleNamespace(save_event=AsyncMock())
    assert await emit_undelivered_steer_events("s1", run_id="r1", presenter=presenter, queue=queue) == 1
    event = presenter.save_event.call_args.args[0]
    assert event["event"] == "steer:undelivered"
    assert event["data"]["content"] == ""
    assert event["data"]["message_id"] == "image-only"
    assert event["data"]["attachments"] == [ATTACHMENT]
