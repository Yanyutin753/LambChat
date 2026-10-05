"""DingTalk Stream protocol boundaries, independent from real credentials."""

import json
import time
from unittest.mock import AsyncMock

import httpx
import pytest

from src.infra.channel.dingtalk import DingTalkChannel, DingTalkConfig


def channel(**kwargs):
    return DingTalkChannel(
        DingTalkConfig(
            user_id="owner",
            receive_enabled=True,
            client_id="app",
            client_secret="secret",
            corp_id="corp",
            allowed_sender_ids="staff",
            **kwargs,
        )
    )


def callback(**changes):
    body = {
        "msgId": "business-id",
        "msgtype": "text",
        "text": {"content": "hello"},
        "senderStaffId": "staff",
        "senderId": "external-user",
        "senderCorpId": "corp",
        "chatbotCorpId": "corp",
        "conversationId": "group",
        "conversationType": "2",
        "isInAtList": True,
        "sessionWebhook": "https://oapi.dingtalk.com/robot/sendBySession?session=secret",
        "sessionWebhookExpiredTime": int(time.time() * 1000) + 60000,
    }
    body.update(changes)
    return {
        "type": "CALLBACK",
        "headers": {
            "messageId": "transport-id",
            "topic": "/v1.0/im/bot/messages/get",
        },
        "data": json.dumps(body),
    }


async def test_stream_callback_preserves_per_message_reply_context_and_acks():
    ch = channel()
    ch.enqueue_inbound = AsyncMock(return_value=True)
    ws = AsyncMock()
    await ch._handle_stream_frame(ws, callback())
    message = ch.enqueue_inbound.call_args.args[0]
    assert {k: message[k] for k in ("sender_id", "chat_id", "content", "message_id")} == {
        "sender_id": "staff",
        "chat_id": "group",
        "content": "hello",
        "message_id": "business-id",
    }
    assert message["metadata"]["session_webhook"].startswith("https://oapi.dingtalk.com/")
    ack = ws.send_json.call_args.args[0]
    assert ack["code"] == 200
    assert ack["headers"]["messageId"] == "transport-id"


@pytest.mark.parametrize(
    "changes",
    [
        {"senderCorpId": "other"},
        {"chatbotCorpId": "other"},
        {"senderStaffId": ""},
        {"msgtype": "picture"},
        {"isInAtList": False},
    ],
)
async def test_stream_rejects_wrong_tenant_or_unsupported_sender_message(changes):
    ch = channel()
    ch.enqueue_inbound = AsyncMock(return_value=True)
    await ch._handle_stream_frame(AsyncMock(), callback(**changes))
    ch.enqueue_inbound.assert_not_awaited()


async def test_stream_backpressure_does_not_ack_success():
    ch = channel()
    ch.enqueue_inbound = AsyncMock(return_value=False)
    ws = AsyncMock()
    await ch._handle_stream_frame(ws, callback())
    assert ws.send_json.call_args.args[0]["code"] != 200


async def test_stream_ping_echoes_opaque_without_enqueue():
    ch = channel()
    ch.enqueue_inbound = AsyncMock()
    ws = AsyncMock()
    await ch._handle_stream_frame(
        ws,
        {
            "type": "SYSTEM",
            "headers": {"topic": "ping", "messageId": "ping-id"},
            "data": '{"opaque":"opaque-value"}',
        },
    )
    assert json.loads(ws.send_json.call_args.args[0]["data"]) == {"opaque": "opaque-value"}
    ch.enqueue_inbound.assert_not_awaited()


@pytest.mark.parametrize(
    "url",
    [
        "http://oapi.dingtalk.com/robot/sendBySession",
        "https://evil.test/x",
        "https://oapi.dingtalk.com@127.0.0.1/x",
    ],
)
async def test_session_reply_refuses_untrusted_url(url):
    ch = channel()
    ch._post = AsyncMock()
    assert not await ch._send_reply("group", "answer", session_webhook=url)
    ch._post.assert_not_awaited()


async def test_session_reply_checks_expiry_and_platform_error():
    ch = channel()
    ch._http = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, json={"errcode": 310000}))
    )
    try:
        assert not await ch._send_reply(
            "group",
            "answer",
            session_webhook="https://oapi.dingtalk.com/robot/sendBySession?session=secret",
            session_webhook_expired_time=1,
        )
        assert not await ch._send_reply(
            "group",
            "answer",
            session_webhook="https://oapi.dingtalk.com/robot/sendBySession?session=secret",
        )
    finally:
        await ch._http.aclose()


async def test_expired_session_reply_after_restart_uses_authenticated_target():
    ch = channel()
    requests = []

    def respond(request):
        requests.append(request)
        if request.url.path.endswith("accessToken"):
            return httpx.Response(200, json={"accessToken": "fresh"})
        return httpx.Response(200, json={"processQueryKey": "accepted"})

    ch._http = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    try:
        assert await ch._send_reply(
            "group",
            "recovered answer",
            chat_type="group",
            session_webhook="https://oapi.dingtalk.com/robot/sendBySession?session=old",
            session_webhook_expired_time=1,
        )
        assert len(requests) == 2
        assert json.loads(requests[1].content)["openConversationId"] == "group"
        assert all("sendBySession" not in str(request.url) for request in requests)
    finally:
        await ch._http.aclose()


async def test_stream_ticket_request_uses_credentials_and_robot_topic():
    ch = channel()
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(
            200,
            json={"endpoint": "wss://wss-open-connection.dingtalk.com/connect", "ticket": "a+b"},
        )

    ch._http = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    try:
        assert (
            await ch._open_stream_url()
            == "wss://wss-open-connection.dingtalk.com/connect?ticket=a%2Bb"
        )
        body = json.loads(requests[0].content)
        assert body["clientId"] == "app"
        assert body["clientSecret"] == "secret"
        assert body["subscriptions"] == [{"type": "CALLBACK", "topic": "/v1.0/im/bot/messages/get"}]
    finally:
        await ch._http.aclose()


@pytest.mark.parametrize(
    "target,metadata,path,key,value",
    [
        ("group", {}, "groupMessages/send", "openConversationId", "group"),
        ("staff", {"chat_type": "single"}, "oToMessages/batchSend", "userIds", ["staff"]),
        ("user:staff", {}, "oToMessages/batchSend", "userIds", ["staff"]),
    ],
)
async def test_proactive_robot_send_authenticates_and_selects_group_or_direct(
    target, metadata, path, key, value
):
    ch = channel()
    requests = []

    def respond(request):
        requests.append(request)
        if request.url.path.endswith("accessToken"):
            return httpx.Response(200, json={"accessToken": "token", "expireIn": 7200})
        return httpx.Response(200, json={"processQueryKey": "delivery-id"})

    ch._http = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    try:
        assert await ch._send_reply(target, "answer", **metadata)
        assert str(requests[-1].url).endswith(path)
        assert requests[-1].headers["x-acs-dingtalk-access-token"] == "token"
        payload = json.loads(requests[-1].content)
        assert payload[key] == value
        assert payload["robotCode"] == "app"
        assert json.loads(payload["msgParam"]) == {"content": "answer"}
    finally:
        await ch._http.aclose()


async def test_stream_disconnect_closes_transport():
    ch = channel()
    ws = AsyncMock()
    await ch._handle_stream_frame(
        ws, {"type": "SYSTEM", "headers": {"topic": "disconnect"}, "data": '{"reason":"expired"}'}
    )
    ws.close.assert_awaited_once()


async def test_stream_connection_consumes_text_frames_and_clears_status(monkeypatch):
    from contextlib import asynccontextmanager
    from types import SimpleNamespace

    import aiohttp

    ch = channel()
    ch._open_stream_url = AsyncMock(
        return_value="wss://wss-open-connection.dingtalk.com/connect?ticket=example"
    )
    ch.enqueue_inbound = AsyncMock(return_value=True)
    outgoing = []

    class Socket:
        async def send_json(self, data):
            outgoing.append(data)

        def __aiter__(self):
            async def frames():
                assert ch._connected
                yield SimpleNamespace(type=aiohttp.WSMsgType.TEXT, data=json.dumps(callback()))

            return frames()

    class Session:
        @asynccontextmanager
        async def ws_connect(self, url, **kwargs):
            assert url.endswith("ticket=example")
            yield Socket()

    @asynccontextmanager
    async def session():
        yield Session()

    monkeypatch.setattr("src.infra.channel.dingtalk.aiohttp.ClientSession", session)
    await ch._run_inbound()
    assert outgoing[0]["code"] == 200
    assert ch.enqueue_inbound.await_count == 1
    assert not ch._connected


async def test_bot_direct_reply_does_not_leak_to_retained_group_webhook():
    ch = channel(webhook_url="https://oapi.dingtalk.com/robot/send?access_token=old-group")
    requests = []

    def respond(request):
        requests.append(request)
        if request.url.path.endswith("accessToken"):
            return httpx.Response(200, json={"accessToken": "token"})
        return httpx.Response(200, json={"processQueryKey": "sent", "errcode": 0})

    ch._http = httpx.AsyncClient(transport=httpx.MockTransport(respond))
    try:
        assert await ch._send_reply("staff", "private answer", chat_type="single")
        assert requests[-1].url.path == "/v1.0/robot/oToMessages/batchSend"
        assert json.loads(requests[-1].content)["userIds"] == ["staff"]
        assert all(request.url.host == "api.dingtalk.com" for request in requests)
    finally:
        await ch._http.aclose()
