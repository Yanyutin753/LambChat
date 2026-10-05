"""Replayed deliveries reuse already-published Feishu replies."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.channel.feishu.collector import FeishuResponseCollector
from src.infra.channel.inbox_worker import current_delivery


@pytest.fixture
def delivery():
    class Delivery:
        checkpoint = {}
        fail = False

        async def save(self, **values):
            if self.fail:
                raise RuntimeError("checkpoint unavailable")
            self.checkpoint.update(values)

    state = Delivery()
    token = current_delivery.set(state)
    yield state
    current_delivery.reset(token)


def collector(client):
    manager = SimpleNamespace(_find_channel=lambda *_: client)
    return FeishuResponseCollector(manager, "user", "chat")


def client():
    return SimpleNamespace(
        create_stream_card=AsyncMock(return_value="card"),
        send_card_by_id=AsyncMock(return_value=(True, "message")),
        update_stream_card=AsyncMock(return_value=True),
        finalize_stream_card=AsyncMock(return_value=True),
        send_card_message=AsyncMock(return_value=True),
    )


async def test_replayed_collector_updates_existing_stream_card(delivery):
    sender = client()
    first = collector(sender)
    await first.append_stream_chunk("one")
    await first._cancel_stream_update_worker()
    assert delivery.checkpoint["feishu_stream_card_id"] == "card"
    assert delivery.checkpoint["feishu_stream_message_id"] == "message"

    restored = collector(sender)
    await restored.append_stream_chunk("one plus replayed text")
    await asyncio.sleep(0)
    await restored._cancel_stream_update_worker()
    assert sender.create_stream_card.await_count == 1
    assert sender.send_card_by_id.await_count == 1
    sender.update_stream_card.assert_awaited_once_with("card", "one plus replayed text", 1)
    assert delivery.checkpoint["feishu_stream_sequence"] == 1
    assert await restored.finalize_stream_message()
    again = collector(sender)
    assert await again.finalize_stream_message()
    assert sender.finalize_stream_card.await_count == 1


async def test_card_checkpoint_failure_reaches_delivery_worker(delivery):
    delivery.fail = True
    instance = collector(client())
    with pytest.raises(RuntimeError, match="checkpoint unavailable"):
        await instance.append_stream_chunk("one")
    await instance._cancel_stream_update_worker()


async def test_successful_fallback_is_not_resent_after_reconnect(delivery):
    sender = client()
    first = collector(sender)
    first.append_text("completed reply")
    assert await first.send_card_message()
    again = collector(sender)
    again.append_text("completed reply")
    assert await again.send_card_message()
    assert sender.send_card_message.await_count == 1


async def test_background_checkpoint_failure_is_not_silently_finalized(delivery):
    sender = client()
    first = collector(sender)
    await first.append_stream_chunk("one")
    delivery.fail = True
    await first.append_stream_chunk("two")
    await asyncio.sleep(0)
    with pytest.raises(RuntimeError, match="checkpoint unavailable"):
        await first.finalize_stream_message()
    assert sender.finalize_stream_card.await_count == 0


async def test_fallback_checkpoint_prevents_replayed_stream_creation(delivery):
    sender = client()
    first = collector(sender)
    first.append_text("reply")
    assert await first.send_card_message()
    restored = collector(sender)
    try:
        await restored.append_stream_chunk("reply")
        assert await restored.finalize_stream_message()
        assert sender.create_stream_card.await_count == 0
    finally:
        await restored._cancel_stream_update_worker()


async def test_approval_checkpoint_preserves_reply_for_later_updates(delivery, monkeypatch):
    sender = client()
    sender.patch_card_message = AsyncMock(return_value=True)
    manager = SimpleNamespace(
        _find_channel=lambda *_: sender,
        send_card_message_with_id=AsyncMock(return_value=(True, "approval-message")),
    )
    monkeypatch.setattr(
        "src.infra.channel.feishu.collector._build_approval_card_content",
        AsyncMock(return_value="card-content"),
    )
    first = FeishuResponseCollector(manager, "user", "chat")
    assert await first.send_approval_card({"id": "approval"})
    restored = FeishuResponseCollector(manager, "user", "chat")
    assert restored.has_sent_approval_card("approval")
    assert await restored.send_approval_card({"id": "approval"})
    assert await restored.update_approval_card("approval", {}, status="approved")
    assert manager.send_card_message_with_id.await_count == 1
    sender.patch_card_message.assert_awaited_once_with("approval-message", "card-content")


@pytest.mark.parametrize("send_success", [True, False])
async def test_file_delivery_checkpoints_success_and_retries_failure(
    delivery, monkeypatch, send_success
):
    sender = client()
    sender.upload_file = AsyncMock(return_value="file-key")
    sender.send_file_by_key = AsyncMock(return_value=send_success)
    monkeypatch.setattr(
        "src.infra.channel.feishu.collector._download_storage_object_to_file",
        AsyncMock(return_value=1),
    )
    monkeypatch.setattr(
        "src.infra.storage.s3.service.get_or_init_storage",
        AsyncMock(return_value=SimpleNamespace(_get_backend=lambda: object())),
    )
    first = collector(sender)
    first.add_file_to_reveal({"key": "files/one", "name": "one.txt"})
    if not send_success:
        with pytest.raises(RuntimeError):
            await first.upload_and_send_files()
        assert "feishu_sent_file_keys" not in delivery.checkpoint
        return
    await first.upload_and_send_files()
    assert delivery.checkpoint["feishu_sent_file_keys"] == ["files/one"]
    restored = collector(sender)
    restored.add_file_to_reveal({"key": "files/one", "name": "one.txt"})
    await restored.upload_and_send_files()
    assert sender.send_file_by_key.await_count == 1
