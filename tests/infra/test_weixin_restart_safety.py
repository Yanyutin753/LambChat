"""Failure boundaries around Weixin reconnect and distributed ownership."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from src.infra.channel.weixin.channel import WeixinChannel
from src.kernel.schemas.weixin import WeixinConfig


async def test_base_dispatch_failure_remains_retryable():
    channel = WeixinChannel(
        WeixinConfig(user_id="u", instance_id="i", bot_token="token"),
        AsyncMock(side_effect=RuntimeError("temporary failure")),
    )
    with pytest.raises(RuntimeError, match="temporary failure"):
        await channel._handle_message(sender_id="s", chat_id="c", content="hello")


async def test_lost_lease_cancels_inflight_dispatch(monkeypatch):
    channel = WeixinChannel(WeixinConfig(user_id="u", instance_id="i", bot_token="token"))
    channel._lock_owner = "old"
    cancelled = asyncio.Event()

    async def work():
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr("src.infra.channel.weixin.channel.LOCK_RENEW_INTERVAL_SECONDS", 0.001)
    monkeypatch.setattr(
        "src.infra.channel.weixin.channel._renew_poll_lock", AsyncMock(return_value=False)
    )
    with pytest.raises(RuntimeError, match="lease"):
        await asyncio.wait_for(channel._with_lock_renewal(work()), timeout=0.1)
    assert cancelled.is_set()


async def test_message_returned_after_lease_loss_is_not_dispatched(monkeypatch):
    handler = AsyncMock()
    channel = WeixinChannel(WeixinConfig(user_id="u", instance_id="i", bot_token="token"), handler)
    channel._lock_owner = "old"
    storage = AsyncMock()
    storage.get.return_value = "before"
    monkeypatch.setattr(channel, "_get_http", AsyncMock())
    monkeypatch.setattr(
        "src.infra.channel.weixin.provider.get_updates",
        AsyncMock(return_value=([{"sender_id": "s", "chat_id": "s", "content": "hello"}], "after")),
    )
    monkeypatch.setattr(
        "src.infra.channel.weixin.channel._renew_poll_lock", AsyncMock(return_value=False)
    )
    with pytest.raises(RuntimeError, match="lease"):
        await channel._consume_once(storage)
    handler.assert_not_awaited()
    storage.set.assert_not_awaited()
