"""Shared receiving lifecycle, authorization and cross-instance isolation."""

import asyncio
from unittest.mock import AsyncMock, patch

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


async def test_unauthorized_sender_is_ignored_before_redis_or_agent():
    ch = channel(receive_enabled=True, allowed_sender_ids="someone-else")
    assert await ch.start()
    with patch("src.infra.channel.chat.get_redis_client") as redis:
        assert await ch.enqueue_inbound(MESSAGE)
        redis.assert_not_called()
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
    redis = AsyncMock()
    redis.set.return_value = True
    with patch("src.infra.channel.chat.get_redis_client", return_value=redis):
        assert await ch.enqueue_inbound(MESSAGE)
        await ch.drain()
    args = ch.message_handler.call_args.kwargs
    assert args["user_id"] == "owner"
    assert args["metadata"]["instance_id"] == "instance"
    assert args["sender_id"] == "sender"
    await ch.stop()


async def test_duplicate_and_redis_failure_never_execute_agent():
    ch = channel(receive_enabled=True, allowed_sender_ids="sender")
    assert await ch.start()
    redis = AsyncMock()
    redis.set.return_value = False
    with patch("src.infra.channel.chat.get_redis_client", return_value=redis):
        assert await ch.enqueue_inbound(MESSAGE)
        redis.set.side_effect = RuntimeError("unavailable")
        assert not await ch.enqueue_inbound(MESSAGE)
    ch.message_handler.assert_not_called()
    await ch.stop()


async def test_stop_cancels_dispatch_workers():
    ch = channel(receive_enabled=True, allowed_sender_ids="sender")
    gate = asyncio.Event()
    ch.message_handler.side_effect = lambda **kwargs: gate.wait()

    async def wait_handler(**kwargs):
        await gate.wait()

    ch.message_handler.side_effect = wait_handler
    await ch.start()
    with patch("src.infra.channel.chat.get_redis_client", return_value=AsyncMock()):
        assert await ch.enqueue_inbound(MESSAGE)
        await asyncio.sleep(0)
        await ch.stop()
    assert not ch.is_running
    assert not ch._pending


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
