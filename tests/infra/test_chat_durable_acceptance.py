"""Transport acknowledgement must follow persistence, not an in-memory task."""

from unittest.mock import AsyncMock

from tests.infra.test_chat_channels import MESSAGE, channel


async def test_inbound_ack_follows_durable_acceptance():
    ch = channel(receive_enabled=True, allowed_sender_ids="sender")
    ch._running = True
    worker = AsyncMock()
    worker.accept.return_value = False
    ch._inbox_worker = worker
    assert not await ch.enqueue_inbound(MESSAGE)
    worker.accept.assert_awaited_once()
    ch.message_handler.assert_not_called()


async def test_durable_payload_preserves_reply_target_and_instance():
    ch = channel(receive_enabled=True, allowed_sender_ids="sender")
    ch._running = True
    worker = AsyncMock()
    worker.accept.return_value = True
    ch._inbox_worker = worker
    assert await ch.enqueue_inbound({**MESSAGE, "metadata": {"thread_ts": "thread"}})
    payload = worker.accept.call_args.args[0]
    assert payload["metadata"]["thread_ts"] == "thread"
    assert payload["metadata"]["instance_id"] == "instance"
    assert payload["message_id"] == MESSAGE["message_id"]
