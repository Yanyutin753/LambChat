"""WeCom smart bot WebSocket protocol, separate from legacy group webhooks."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from src.infra.channel.wecom import WeComChannel, WeComConfig

pytestmark = pytest.mark.usefixtures("fake_channel_inbox")


def channel():
    return WeComChannel(
        WeComConfig(
            user_id="owner",
            receive_enabled=True,
            bot_id="bot",
            bot_secret="secret",
            allowed_sender_ids="staff",
        )
    )


def callback(**changes):
    body = {
        "msgid": "message-id",
        "aibotid": "bot",
        "chattype": "single",
        "from": {"userid": "staff"},
        "msgtype": "text",
        "text": {"content": "hello"},
    }
    body.update(changes)
    return {"cmd": "aibot_msg_callback", "headers": {"req_id": "request-id"}, "body": body}


async def test_smart_bot_inbound_maps_sender_and_keeps_request_context():
    ch = channel()
    ch.enqueue_inbound = AsyncMock(return_value=True)
    await ch._handle_ws_frame(callback())
    assert ch.enqueue_inbound.call_args.args[0] == {
        "sender_id": "staff",
        "chat_id": "staff",
        "content": "hello",
        "message_id": "message-id",
        "metadata": {"wecom_req_id": "request-id", "chat_type": "single"},
    }


@pytest.mark.parametrize(
    "changes",
    [{"aibotid": "other"}, {"from": {"userid": "bot"}}, {"msgtype": "file"}, {"chattype": "group"}],
)
async def test_smart_bot_rejects_wrong_bot_self_nontext_and_missing_group(changes):
    ch = channel()
    ch.enqueue_inbound = AsyncMock(return_value=True)
    await ch._handle_ws_frame(callback(**changes))
    ch.enqueue_inbound.assert_not_awaited()


async def test_smart_bot_reply_uses_original_request_id_and_waits_for_ack():
    ch = channel()
    ch._ws = AsyncMock()
    ch._connected = True
    task = asyncio.create_task(ch._send_reply("staff", "answer", wecom_req_id="request-id"))
    await asyncio.sleep(0)
    assert not task.done()
    payload = ch._ws.send_json.call_args.args[0]
    assert payload["cmd"] == "aibot_respond_msg"
    assert payload["headers"] == {"req_id": "request-id"}
    assert payload["body"]["stream"]["finish"] is True
    assert payload["body"]["stream"]["content"] == "answer"
    await ch._handle_ws_frame({"headers": {"req_id": "request-id"}, "errcode": 0})
    assert await task


async def test_smart_bot_proactive_send_uses_chatid_and_rejects_error_ack():
    ch = channel()
    ch._ws = AsyncMock()
    ch._connected = True
    task = asyncio.create_task(ch._send_reply("group", "notification"))
    await asyncio.sleep(0)
    payload = ch._ws.send_json.call_args.args[0]
    assert payload["cmd"] == "aibot_send_msg"
    assert payload["body"] == {
        "chatid": "group",
        "msgtype": "markdown",
        "markdown": {"content": "notification"},
    }
    await ch._handle_ws_frame({"headers": payload["headers"], "errcode": 6000})
    assert not await task


async def test_reconnect_reply_does_not_reuse_previous_socket_request():
    ch = channel()
    ch._connection_id = "new-connection"
    ch._send_reply_part = AsyncMock(return_value=True)
    assert await ch._send_reply(
        "group",
        "recovered answer",
        wecom_req_id="old-request",
        wecom_connection_id="old-connection",
    )
    assert "wecom_req_id" not in ch._send_reply_part.call_args.kwargs


async def test_smart_bot_heartbeat_requires_application_ack():
    ch = channel()
    ch._ws = AsyncMock()
    ch._connected = True
    ch.heartbeat_seconds = 0.001
    task = asyncio.create_task(ch._heartbeat())
    await asyncio.sleep(0.01)
    assert task.done()
    assert ch._ws.send_json.call_count == 2
    assert ch._ws.send_json.call_args.args[0]["cmd"] == "ping"
    ch._ws.close.assert_awaited()


async def test_smart_bot_dispatch_does_not_conflict_with_reply_ack_tracking():
    ch = channel()
    ch._running = True
    ch.message_handler = AsyncMock()
    await ch._handle_ws_frame(callback())
    await ch.drain()
    assert ch.message_handler.call_args.kwargs["content"] == "hello"


async def test_smart_bot_ping_ack_clears_missed_heartbeats():
    ch = channel()
    ch._missed_pongs = 2
    ch._ping_ids.add("ping-request")
    await ch._handle_ws_frame({"headers": {"req_id": "unrelated"}, "errcode": 0})
    assert ch._missed_pongs == 2
    await ch._handle_ws_frame({"headers": {"req_id": "ping-request"}, "errcode": 0})
    assert ch._missed_pongs == 0


async def test_smart_bot_missing_ack_fails_delivery_without_leaking_waiters():
    ch = channel()
    ch._ws = AsyncMock()
    ch._connected = True
    ch.timeout_seconds = 0.001
    assert not await ch._send_reply("staff", "answer", wecom_req_id="request-id")
    assert not ch._reply_acks


@pytest.mark.parametrize("authorized", [True, False])
async def test_smart_bot_connection_authentication_and_cleanup(monkeypatch, authorized):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    import aiohttp

    from src.infra.channel.chat import InboundConfigurationError

    ch = channel()
    ch.enqueue_inbound = AsyncMock(return_value=True)
    outgoing = []

    class Socket:
        async def send_json(self, data):
            outgoing.append(data)

        async def receive_json(self, **kwargs):
            return {"headers": outgoing[0]["headers"], "errcode": 0 if authorized else 40001}

        def __aiter__(self):
            async def frames():
                assert ch._connected
                yield SimpleNamespace(
                    type=aiohttp.WSMsgType.TEXT, data=__import__("json").dumps(callback())
                )

            return frames()

    class Session:
        @asynccontextmanager
        async def ws_connect(self, url, **kwargs):
            assert url == "wss://openws.work.weixin.qq.com"
            yield Socket()

    @asynccontextmanager
    async def session():
        yield Session()

    monkeypatch.setattr("src.infra.channel.wecom.aiohttp.ClientSession", session)
    if authorized:
        await ch._run_inbound()
        assert ch.enqueue_inbound.await_count == 1
    else:
        with pytest.raises(InboundConfigurationError):
            await ch._run_inbound()
        ch.enqueue_inbound.assert_not_awaited()
    assert outgoing[0]["cmd"] == "aibot_subscribe"
    assert outgoing[0]["body"] == {"bot_id": "bot", "secret": "secret"}
    assert ch._ws is None
    assert not ch._connected


@pytest.mark.parametrize("metadata", [{"wecom_req_id": "request-id"}, {}])
async def test_smart_bot_long_unicode_reply_splits_within_platform_byte_limits(metadata):
    ch = channel()
    ch._ws = AsyncMock()
    ch._connected = True
    sent = []

    async def acknowledge(payload):
        sent.append(payload)
        await ch._handle_ws_frame({"headers": payload["headers"], "errcode": 0})

    ch._ws.send_json.side_effect = acknowledge
    content = "研究🧪" * 3000
    assert await ch._send_reply("staff", content, **metadata)
    reconstructed = []
    for index, payload in enumerate(sent):
        if metadata and index == 0:
            assert payload["cmd"] == "aibot_respond_msg"
            assert payload["headers"]["req_id"] == "request-id"
            part = payload["body"]["stream"]["content"]
            assert len(part.encode("utf-8")) <= 20480
        else:
            assert payload["cmd"] == "aibot_send_msg"
            assert payload["body"]["chatid"] == "staff"
            part = payload["body"]["markdown"]["content"]
            assert len(part.encode("utf-8")) <= 4096
        reconstructed.append(part)
    assert "".join(reconstructed) == content
    assert len(sent) > 1
