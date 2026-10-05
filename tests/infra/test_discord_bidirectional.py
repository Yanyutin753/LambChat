"""Discord Gateway protocol and bot reply contracts."""

import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest

from src.infra.channel.discord import DiscordChannel, DiscordConfig


def message(**changes):
    data = {
        "id": "M1",
        "channel_id": "C1",
        "guild_id": "G1",
        "author": {"id": "U1", "bot": False},
        "content": "<@BOT> hello",
        "mentions": [{"id": "BOT"}],
        "type": 0,
    }
    data.update(changes)
    return {"op": 0, "s": 4, "t": "MESSAGE_CREATE", "d": data}


async def test_gateway_message_preserves_reply_identity_and_sequence():
    channel = DiscordChannel(DiscordConfig(bot_token="test", receive_enabled=True))
    channel._bot_user_id = "BOT"
    channel.enqueue_inbound = AsyncMock(return_value=True)
    assert await channel._handle_gateway_event(AsyncMock(), message())
    channel.enqueue_inbound.assert_awaited_once_with(
        {
            "sender_id": "U1",
            "chat_id": "C1",
            "content": "hello",
            "message_id": "M1",
            "metadata": {"reply_message_id": "M1"},
        }
    )
    assert channel._gateway_seq == 4


async def test_gateway_rejected_delivery_does_not_advance_resume_sequence():
    channel = DiscordChannel(DiscordConfig())
    channel._bot_user_id = "BOT"
    channel._gateway_seq = 3
    channel.enqueue_inbound = AsyncMock(return_value=False)
    with pytest.raises(RuntimeError):
        await channel._handle_gateway_event(AsyncMock(), message())
    assert channel._gateway_seq == 3


@pytest.mark.parametrize(
    "changes",
    [
        {"author": {"id": "U1", "bot": True}},
        {"webhook_id": "WH1"},
        {"author": {"id": "BOT"}},
        {"content": "no mention", "mentions": []},
        {"type": 7},
    ],
)
async def test_gateway_ignores_bots_system_messages_and_unmentioned_group_text(changes):
    channel = DiscordChannel(DiscordConfig())
    channel._bot_user_id = "BOT"
    channel.enqueue_inbound = AsyncMock()
    assert await channel._handle_gateway_event(AsyncMock(), message(**changes))
    channel.enqueue_inbound.assert_not_awaited()


async def test_gateway_private_messages_do_not_require_mention():
    channel = DiscordChannel(DiscordConfig())
    channel.enqueue_inbound = AsyncMock(return_value=True)
    packet = message(content="private", mentions=[])
    del packet["d"]["guild_id"]
    await channel._handle_gateway_event(AsyncMock(), packet)
    assert channel.enqueue_inbound.await_args.args[0]["content"] == "private"


async def test_gateway_ready_saves_resume_state_and_marks_authenticated():
    channel = DiscordChannel(DiscordConfig())
    await channel._handle_gateway_event(
        AsyncMock(),
        {
            "op": 0,
            "s": 1,
            "t": "READY",
            "d": {
                "session_id": "S1",
                "resume_gateway_url": "wss://gateway.discord.gg",
                "user": {"id": "BOT"},
            },
        },
    )
    assert channel._session_id == "S1"
    assert channel._resume_gateway_url == "wss://gateway.discord.gg"
    assert channel._connected


async def test_gateway_invalid_session_discards_resume_credentials():
    channel = DiscordChannel(DiscordConfig())
    channel._session_id = "S1"
    channel._gateway_seq = 4
    assert not await channel._handle_gateway_event(AsyncMock(), {"op": 9, "d": False})
    assert channel._session_id is None
    assert channel._gateway_seq is None


async def test_gateway_session_start_limit_is_retryable_after_reset():
    from src.infra.channel.chat import InboundConfigurationError

    channel = DiscordChannel(DiscordConfig(bot_token="test"))
    channel._http = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "url": "wss://gateway.discord.gg",
                    "shards": 1,
                    "session_start_limit": {"remaining": 0, "reset_after": 60000},
                },
            )
        )
    )
    try:
        with pytest.raises(RuntimeError) as failure:
            await channel._run_inbound()
        assert not isinstance(failure.value, InboundConfigurationError)
    finally:
        await channel.stop()


async def test_gateway_server_heartbeat_request_gets_current_sequence():
    channel = DiscordChannel(DiscordConfig())
    channel._gateway_seq = 4
    ws = AsyncMock()
    assert await channel._handle_gateway_event(ws, {"op": 1})
    ws.send_json.assert_awaited_once_with({"op": 1, "d": 4})


async def test_discord_reply_uses_reference_and_disables_mentions():
    channel = DiscordChannel(DiscordConfig(bot_token="test", receive_enabled=True))
    channel._post = AsyncMock(return_value=httpx.Response(200, json={"id": "M2"}))
    assert await channel._send_reply("C1", "answer", reply_message_id="M1")
    channel._post.assert_awaited_once_with(
        "https://discord.com/api/v10/channels/C1/messages",
        headers={"Authorization": "Bot test"},
        json={
            "content": "answer",
            "allowed_mentions": {"parse": [], "replied_user": False},
            "message_reference": {"message_id": "M1", "fail_if_not_exists": False},
        },
    )


async def test_existing_discord_webhook_remains_outbound_without_bot_token():
    channel = DiscordChannel(DiscordConfig(webhook_url="https://discord.com/api/webhooks/test"))
    channel._post = AsyncMock(return_value=httpx.Response(204))
    assert await channel.send_message("", "answer")
    assert channel._post.await_args.args == ("https://discord.com/api/webhooks/test",)
    assert not getattr(channel.config, "receive_enabled", True)


async def test_gateway_identify_requests_only_message_intents_by_default():
    channel = DiscordChannel(DiscordConfig(bot_token="test"))
    ws = AsyncMock()
    await channel._identify_or_resume(ws)
    assert ws.send_json.await_args.args[0] == {
        "op": 2,
        "d": {
            "token": "test",
            "intents": 4608,
            "properties": {"os": "linux", "browser": "lambchat", "device": "lambchat"},
        },
    }


async def test_gateway_resume_uses_saved_sequence_without_identifying():
    channel = DiscordChannel(DiscordConfig(bot_token="test"))
    channel._session_id = "S1"
    channel._gateway_seq = 4
    ws = AsyncMock()
    await channel._identify_or_resume(ws)
    ws.send_json.assert_awaited_once_with(
        {"op": 6, "d": {"token": "test", "session_id": "S1", "seq": 4}}
    )


async def test_gateway_missing_heartbeat_ack_closes_connection_for_resume(monkeypatch):
    channel = DiscordChannel(DiscordConfig())
    channel._gateway_seq = 4
    monkeypatch.setattr("random.random", lambda: 0)
    ws = AsyncMock()
    ws.closed = False
    await asyncio.wait_for(channel._heartbeat(ws, 0.001), timeout=1)
    ws.send_json.assert_awaited_once_with({"op": 1, "d": 4})
    ws.close.assert_awaited_once_with(code=4000)


async def test_discord_replies_split_without_silently_truncating():
    channel = DiscordChannel(DiscordConfig(bot_token="test"))
    channel._post = AsyncMock(return_value=httpx.Response(200, json={"id": "M2"}))
    assert await channel._send_reply("C1", "a" * 2001)
    assert [len(call.kwargs["json"]["content"]) for call in channel._post.await_args_list] == [
        2000,
        1,
    ]


async def test_discord_retries_rate_limited_reply():
    channel = DiscordChannel(DiscordConfig(bot_token="test"))
    channel._post = AsyncMock(
        side_effect=[
            httpx.Response(429, json={"retry_after": 0}),
            httpx.Response(200, json={"id": "M2"}),
        ]
    )
    assert await channel._send_reply("C1", "answer")
    assert channel._post.await_count == 2


async def test_gateway_transport_preserves_session_for_server_reconnect(monkeypatch):
    import aiohttp

    channel = DiscordChannel(DiscordConfig(bot_token="test"))
    channel._http = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: httpx.Response(
                200,
                json={
                    "url": "wss://gateway.discord.gg",
                    "shards": 1,
                    "session_start_limit": {"remaining": 100},
                },
            )
        )
    )
    packets = [
        {
            "op": 0,
            "s": 1,
            "t": "READY",
            "d": {
                "session_id": "S1",
                "resume_gateway_url": "wss://resume.discord.gg",
                "user": {"id": "BOT"},
            },
        },
        {"op": 7, "d": None},
    ]
    ws = AsyncMock()
    ws.closed = False
    ws.close_code = 4000
    ws.receive_json.return_value = {"op": 10, "d": {"heartbeat_interval": 45000}}

    async def close(**kwargs):
        ws.closed = True

    async def frames(*args):
        for packet in packets:
            yield type(
                "Frame", (), {"type": aiohttp.WSMsgType.TEXT, "json": lambda self, p=packet: p}
            )()

    ws.close.side_effect = close
    ws.__aiter__ = frames
    socket_context = AsyncMock()
    socket_context.__aenter__.return_value = ws
    session = type("Session", (), {"ws_connect": lambda self, url, **kwargs: socket_context})()
    session_context = AsyncMock()
    session_context.__aenter__.return_value = session
    monkeypatch.setattr(aiohttp, "ClientSession", lambda: session_context)
    try:
        await channel._run_inbound()
        assert ws.send_json.await_args_list[0].args[0]["op"] == 2
        ws.close.assert_awaited_once_with(code=4000)
        assert channel._session_id == "S1"
        assert channel._gateway_seq == 1
        assert not channel._connected
    finally:
        await channel.stop()
