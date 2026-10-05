"""Shared receiving lifecycle, authorization and cross-instance isolation."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from src.infra.channel.chat import ChatChannel, ChatConfig
from src.kernel.schemas.channel import ChannelCapability, ChannelType


class Config(ChatConfig):
    channel_type = ChannelType.TELEGRAM
    bot_token: str = "test-token"

    @classmethod
    def get_schema_name(cls):
        return "test"

    @classmethod
    def get_capabilities(cls):
        return [ChannelCapability.SEND_MESSAGE, ChannelCapability.LONG_POLLING]


class Channel(ChatChannel):
    channel_type = ChannelType.TELEGRAM
    inbound_transport = False

    def _validate_inbound_config(self):
        return bool(self.config.bot_token)

    async def _run_inbound(self):
        pass

    async def _send(self, **kwargs):
        return True

    @classmethod
    def get_config_schema(cls):
        return {}

    @classmethod
    def get_setup_guide(cls):
        return []


MESSAGE = {"sender_id": "sender", "chat_id": "chat", "content": "Hello", "message_id": "1"}


pytestmark = pytest.mark.usefixtures("fake_channel_inbox")


def channel(**kwargs):
    return Channel(Config(user_id="owner", instance_id="instance", **kwargs), AsyncMock())


async def test_receiving_requires_explicit_authorization():
    ch = channel(receive_enabled=True)
    assert not await ch.start()
    assert not ch.is_running


async def test_old_outbound_config_starts_without_receiving_or_allowlist():
    ch = channel()
    assert await ch.start()
    assert ch.is_running
    assert await ch.enqueue_inbound(MESSAGE) is True
    ch.message_handler.assert_not_called()
    await ch.stop()


async def test_unauthorized_sender_is_ignored_before_persistence_or_agent(fake_channel_inbox):
    ch = channel(receive_enabled=True, allowed_sender_ids="someone-else")
    assert await ch.start()
    assert await ch.enqueue_inbound(MESSAGE)
    assert not fake_channel_inbox.rows
    ch.message_handler.assert_not_called()
    await ch.stop()


async def test_sender_and_chat_restrictions_both_apply():
    ch = channel(receive_enabled=True, allowed_sender_ids="sender", allowed_chat_ids="other")
    assert await ch.start()
    assert await ch.enqueue_inbound(MESSAGE)
    ch.message_handler.assert_not_called()
    await ch.stop()


async def test_accepted_message_is_dispatched_with_owner_and_instance():
    ch = channel(receive_enabled=True, allowed_sender_ids="sender")
    assert await ch.start()
    assert await ch.enqueue_inbound(MESSAGE)
    assert await ch.drain()
    args = ch.message_handler.call_args.kwargs
    assert args["user_id"] == "owner"
    assert args["metadata"]["instance_id"] == "instance"
    assert args["sender_id"] == "sender"
    await ch.stop()


async def test_duplicate_durable_input_executes_only_once():
    ch = channel(receive_enabled=True, allowed_sender_ids="sender")
    await ch.start()
    try:
        assert await ch.enqueue_inbound(MESSAGE)
        assert await ch.enqueue_inbound(MESSAGE)
        assert await ch.drain()
        assert await ch.enqueue_inbound(MESSAGE)
        assert await ch.drain()
        ch.message_handler.assert_awaited_once()
    finally:
        await ch.stop()


async def test_persistence_failure_does_not_acknowledge_or_execute(fake_channel_inbox):
    ch = channel(receive_enabled=True, allowed_sender_ids="sender")
    await ch.start()
    fake_channel_inbox.accept_error = OSError("database unavailable")
    try:
        assert not await ch.enqueue_inbound(MESSAGE)
        ch.message_handler.assert_not_called()
        assert not fake_channel_inbox.rows
    finally:
        await ch.stop()


async def test_stop_cancels_dispatch_workers_but_keeps_durable_input(fake_channel_inbox):
    ch = channel(receive_enabled=True, allowed_sender_ids="sender")
    entered, cancelled = asyncio.Event(), asyncio.Event()

    async def wait_handler(**kwargs):
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    ch.message_handler.side_effect = wait_handler
    await ch.start()
    assert await ch.enqueue_inbound(MESSAGE)
    await asyncio.wait_for(entered.wait(), 1)
    await ch.stop()
    assert cancelled.is_set()
    assert not ch.is_running
    assert len(await ch._inbox_worker.inbox.pending()) == 1
    replacement = channel(receive_enabled=True, allowed_sender_ids="sender")
    await replacement.start()
    try:
        assert await replacement.drain()
        replacement.message_handler.assert_awaited_once()
    finally:
        await replacement.stop()


async def test_stored_owner_cannot_be_overridden_by_nested_configuration():
    from src.infra.channel.channel_storage import ChannelStorage

    storage = ChannelStorage()
    storage._decrypt_config = AsyncMock(
        return_value={"user_id": "attacker", "instance_id": "other"}
    )
    result = await storage._doc_to_config(
        {"user_id": "owner", "instance_id": "instance", "config": {}}
    )
    assert result["user_id"] == "owner"
    assert result["instance_id"] == "instance"


def test_session_scope_separates_owner_instance_sender_and_thread():
    from src.infra.channel.chat_handler import session_scope

    ch = channel()
    key = session_scope(ch, "sender", "chat", {})
    assert key != session_scope(ch, "other", "chat", {})
    assert key != session_scope(ch, "sender", "chat", {"thread_ts": "thread"})
    ch.config.user_id = "another-owner"
    assert key != session_scope(ch, "sender", "chat", {})
    ch.config.user_id = "owner"
    ch.config.instance_id = "another-instance"
    assert key != session_scope(ch, "sender", "chat", {})
