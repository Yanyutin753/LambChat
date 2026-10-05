"""Socket Mode contracts: accepted delivery, thread routing and webhook compatibility."""

from unittest.mock import AsyncMock

import httpx
import pytest

from src.infra.channel.slack import SlackChannel, SlackConfig


def envelope(**changes):
    event = {
        "type": "app_mention",
        "user": "U1",
        "channel": "C1",
        "text": "<@BOT> hello",
        "ts": "1.1",
        "thread_ts": "1.0",
    }
    event.update(changes)
    return {
        "type": "events_api",
        "envelope_id": "envelope-1",
        "payload": {"team_id": "T1", "event_id": "Ev1", "event": event},
    }


async def test_socket_mode_enqueues_thread_reply_before_ack():
    channel = SlackChannel(
        SlackConfig(bot_token="xoxb-test", app_token="xapp-test", receive_enabled=True)
    )
    channel._bot_user_id = "BOT"
    channel.enqueue_inbound = AsyncMock(return_value=True)
    ws = AsyncMock()
    await channel._handle_envelope(ws, envelope())
    channel.enqueue_inbound.assert_awaited_once_with(
        {
            "sender_id": "U1",
            "chat_id": "C1",
            "content": "hello",
            "message_id": "T1:C1:1.1",
            "metadata": {"thread_ts": "1.0"},
        }
    )
    ws.send_json.assert_awaited_once_with({"envelope_id": "envelope-1"})


async def test_socket_mode_does_not_ack_when_queue_rejects_delivery():
    channel = SlackChannel(SlackConfig())
    channel.enqueue_inbound = AsyncMock(return_value=False)
    ws = AsyncMock()
    await channel._handle_envelope(ws, envelope())
    ws.send_json.assert_not_awaited()


async def test_plain_direct_messages_keep_one_conversation_without_creating_threads():
    from src.infra.channel.chat_handler import session_scope

    channel = SlackChannel(SlackConfig(user_id="owner", instance_id="bot"))
    channel._bot_user_id = "BOT"
    channel.enqueue_inbound = AsyncMock(return_value=True)
    scopes = []
    for timestamp in ("1.1", "2.1"):
        packet = envelope(type="message", channel_type="im", channel="D1", ts=timestamp)
        packet["payload"]["event"].pop("thread_ts")
        await channel._handle_envelope(AsyncMock(), packet)
        parsed = channel.enqueue_inbound.await_args.args[0]
        scopes.append(
            session_scope(channel, parsed["sender_id"], parsed["chat_id"], parsed["metadata"])
        )
    assert scopes[0] == scopes[1]
    assert "thread_ts" not in parsed["metadata"]


@pytest.mark.parametrize(
    "changes",
    [
        {"bot_id": "B1"},
        {"subtype": "message_changed"},
        {"user": "BOT"},
        {"type": "message", "channel_type": "channel", "text": "no mention"},
    ],
)
async def test_socket_mode_acks_ignored_messages_without_running_agent(changes):
    channel = SlackChannel(SlackConfig())
    channel._bot_user_id = "BOT"
    channel.enqueue_inbound = AsyncMock()
    ws = AsyncMock()
    await channel._handle_envelope(ws, envelope(**changes))
    channel.enqueue_inbound.assert_not_awaited()
    ws.send_json.assert_awaited_once_with({"envelope_id": "envelope-1"})


async def test_slack_reply_uses_bot_api_and_thread():
    channel = SlackChannel(SlackConfig(bot_token="xoxb-test", receive_enabled=True))
    channel._post = AsyncMock(return_value=httpx.Response(200, json={"ok": True}))
    assert await channel._send_reply("C1", "answer", thread_ts="1.0")
    channel._post.assert_awaited_once_with(
        "https://slack.com/api/chat.postMessage",
        headers={"Authorization": "Bearer xoxb-test"},
        json={
            "channel": "C1",
            "text": "answer",
            "unfurl_links": False,
            "unfurl_media": False,
            "thread_ts": "1.0",
        },
    )


async def test_slack_api_ok_false_is_send_failure():
    channel = SlackChannel(SlackConfig(bot_token="xoxb-test", receive_enabled=True))
    channel._post = AsyncMock(
        return_value=httpx.Response(200, json={"ok": False, "error": "not_in_channel"})
    )
    assert not await channel._send_reply("C1", "answer")


async def test_existing_slack_webhook_remains_outbound_without_bot_tokens():
    channel = SlackChannel(SlackConfig(webhook_url="https://hooks.slack.com/services/test"))
    channel._post = AsyncMock(return_value=httpx.Response(200, text="ok"))
    assert await channel.send_message("", "answer")
    assert channel._post.await_args.args == ("https://hooks.slack.com/services/test",)
    assert not getattr(channel.config, "receive_enabled", True)


def test_slack_receive_requires_both_tokens():
    channel = SlackChannel(SlackConfig(bot_token="xoxb-test", receive_enabled=True))
    assert not channel._validate_inbound_config()


async def test_slack_retries_rate_limited_reply():
    channel = SlackChannel(SlackConfig(bot_token="xoxb-test"))
    channel._post = AsyncMock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "0"}),
            httpx.Response(200, json={"ok": True}),
        ]
    )
    assert await channel._send_reply("C1", "answer")
    assert channel._post.await_count == 2


async def test_slack_temporary_auth_endpoint_outage_is_not_fatal():
    from src.infra.channel.chat import InboundConfigurationError

    channel = SlackChannel(SlackConfig(bot_token="xoxb-test", app_token="xapp-test"))
    channel._http = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(503, json={"ok": False}))
    )
    try:
        with pytest.raises(RuntimeError) as error:
            await channel._run_inbound()
        assert not isinstance(error.value, InboundConfigurationError)
    finally:
        await channel.stop()


async def test_slack_socket_authenticates_and_acks_message_before_refresh(monkeypatch):
    import aiohttp

    channel = SlackChannel(SlackConfig(bot_token="xoxb-test", app_token="xapp-test"))
    channel.enqueue_inbound = AsyncMock(return_value=True)
    requests = []

    def respond(request):
        requests.append(request)
        if request.url.path.endswith("auth.test"):
            return httpx.Response(200, json={"ok": True, "user_id": "BOT"})
        return httpx.Response(200, json={"ok": True, "url": "wss://slack.test/socket"})

    channel._http = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    packets = [{"type": "hello"}, envelope(), {"type": "disconnect", "reason": "refresh_requested"}]
    ws = AsyncMock()

    async def frames(*args):
        for packet in packets:
            yield type(
                "Frame", (), {"type": aiohttp.WSMsgType.TEXT, "json": lambda self, p=packet: p}
            )()

    ws.__aiter__ = frames
    socket_context = AsyncMock()
    socket_context.__aenter__.return_value = ws
    session = type("Session", (), {"ws_connect": lambda self, url, **kwargs: socket_context})()
    session_context = AsyncMock()
    session_context.__aenter__.return_value = session
    monkeypatch.setattr(aiohttp, "ClientSession", lambda: session_context)
    try:
        await channel._run_inbound()
        assert [request.headers["Authorization"] for request in requests] == [
            "Bearer xoxb-test",
            "Bearer xapp-test",
        ]
        ws.send_json.assert_awaited_once_with({"envelope_id": "envelope-1"})
        assert not channel._connected
    finally:
        await channel.stop()
