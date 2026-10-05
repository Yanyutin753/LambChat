"""Generic webhook authentication, outbound wire contract and SSRF regression tests."""

import json
from unittest.mock import AsyncMock

import httpx
import pytest
from pydantic import ValidationError


def test_webhook_requires_nonempty_strong_secret():
    from src.infra.channel.webhook import WebhookConfig

    for secret in ("", "short", "a" * 15, "secret\n" + "a" * 30):
        with pytest.raises(ValidationError):
            WebhookConfig(webhook_secret=secret)


def test_webhook_normalizes_provider_actor_without_accepting_tenant_id():
    from src.infra.channel.webhook import WebhookInbound

    inbound = WebhookInbound.model_validate(
        {"userId": "external-user", "text": "/new", "messageId": "msg-1"}
    )
    assert inbound.to_message() == {
        "sender_id": "external-user",
        "chat_id": "external-user",
        "content": "/new",
        "message_id": "msg-1",
    }
    with pytest.raises(ValidationError):
        WebhookInbound.model_validate(
            {
                "sender_id": "external-user",
                "content": "hello",
                "message_id": "msg-1",
                "user_id": "victim",
            }
        )


@pytest.mark.parametrize(
    "updates",
    [
        {"content": " "},
        {"content": "a" * 16001},
        {"message_id": ""},
        {"sender_id": " "},
        {"chat_id": ""},
        {"message_id": None},
    ],
)
def test_webhook_rejects_invalid_message_fields(updates):
    from src.infra.channel.webhook import WebhookInbound

    with pytest.raises(ValidationError):
        WebhookInbound.model_validate(
            {
                "sender_id": "sender",
                "content": "hello",
                "message_id": "msg-1",
                **updates,
            }
        )


@pytest.mark.parametrize(
    "receiving,content",
    [(False, "answer"), (True, "answer" + "x" * 16000)],
    ids=["notification", "full-chat-reply"],
)
async def test_webhook_reply_pins_public_ip_preserves_tls_host_and_secret(
    monkeypatch, receiving, content
):
    from src.infra.channel.webhook import WebhookChannel, WebhookConfig

    channel = WebhookChannel(
        WebhookConfig(
            webhook_url="https://receiver.example/callback",
            webhook_secret="a" * 32,
            user_id="tenant",
            instance_id="instance",
            receive_enabled=receiving,
        )
    )
    requests = []

    def receive(request):
        requests.append(request)
        return httpx.Response(200)

    monkeypatch.setattr(
        "src.infra.channel.webhook.resolve_webhook_addresses",
        AsyncMock(return_value=["93.184.216.34"]),
    )
    channel._http = httpx.AsyncClient(transport=httpx.MockTransport(receive))
    try:
        assert await channel.send_message("room-1", content)
        request = requests[0]
        assert request.url.host == "93.184.216.34"
        assert request.headers["host"] == "receiver.example"
        assert request.extensions["sni_hostname"] == "receiver.example"
        assert request.headers["x-lambchat-bot-secret"] == "a" * 32
        body = json.loads(request.content)
        assert body["type"] == "lambchat.bot.message"
        assert body["botId"] == "instance"
        assert body["chatId"] == "room-1"
        assert body["text"] == content
        assert "tenant" not in request.content.decode()
    finally:
        await channel.stop()


@pytest.mark.parametrize(
    "url,addresses",
    [
        ("http://receiver.example/callback", ["93.184.216.34"]),
        ("https://user:password@receiver.example/callback", ["93.184.216.34"]),
        ("https://receiver.example/callback", ["127.0.0.1"]),
        ("https://receiver.example/callback", ["93.184.216.34", "10.0.0.1"]),
        ("https://receiver.example/callback", ["::ffff:127.0.0.1"]),
        ("https://receiver.example/callback", ["224.0.0.1"]),
        ("https://receiver.example/callback", []),
    ],
)
async def test_webhook_never_sends_secret_to_unsafe_destination(monkeypatch, url, addresses):
    from src.infra.channel.webhook import WebhookChannel, WebhookConfig

    channel = WebhookChannel(WebhookConfig(webhook_secret="a" * 32, webhook_url=url))
    requests = []
    monkeypatch.setattr(
        "src.infra.channel.webhook.resolve_webhook_addresses", AsyncMock(return_value=addresses)
    )
    channel._http = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: requests.append(request) or httpx.Response(200)
        )
    )
    try:
        assert not await channel.send_message("room", "answer")
        assert not requests
    finally:
        await channel.stop()


async def test_webhook_redirect_is_not_followed(monkeypatch):
    from src.infra.channel.webhook import WebhookChannel, WebhookConfig

    channel = WebhookChannel(
        WebhookConfig(
            webhook_secret="a" * 32,
            webhook_url="https://receiver.example/callback",
        )
    )
    requests = []
    monkeypatch.setattr(
        "src.infra.channel.webhook.resolve_webhook_addresses",
        AsyncMock(return_value=["93.184.216.34"]),
    )
    channel._http = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: (
                requests.append(request)
                or httpx.Response(302, headers={"location": "http://127.0.0.1/private"})
            )
        )
    )
    try:
        assert not await channel.send_message("room", "answer")
        assert len(requests) == 1
    finally:
        await channel.stop()


async def test_webhook_callbacks_on_two_replicas_share_dedupe_and_tenant_binding(monkeypatch):
    from src.infra.channel.webhook import WebhookChannelManager

    seen = set()
    handled = []

    async def claim(key, value, *, nx, ex):
        if key in seen:
            return False
        seen.add(key)
        return True

    async def handle(**message):
        handled.append(message)

    redis = AsyncMock()
    redis.set.side_effect = claim
    monkeypatch.setattr("src.infra.channel.chat.get_redis_client", lambda: redis)
    first = WebhookChannelManager(message_handler=handle)
    second = WebhookChannelManager(message_handler=handle)
    config = {
        "user_id": "owner",
        "instance_id": "one",
        "webhook_secret": "a" * 32,
        "allowed_sender_ids": "sender",
    }
    message = {"sender_id": "sender", "chat_id": "room", "content": "/new", "message_id": "msg-1"}
    try:
        assert await first.receive_callback(config, message)
        assert await second.receive_callback(config, message)
        await first.get_channel("owner", "one").drain()
        await second.get_channel("owner", "one").drain()
        assert len(handled) == 1
        assert handled[0]["user_id"] == "owner"
        assert handled[0]["content"] == "/new"
        assert handled[0]["metadata"]["instance_id"] == "one"
        assert first.get_channel("owner", "one")._reader is None
        assert second.get_channel("owner", "one")._reader is None
        # Identical platform message IDs in another tenant are independent.
        assert await second.receive_callback({**config, "user_id": "another"}, message)
        await second.get_channel("another", "one").drain()
        assert [item["user_id"] for item in handled] == ["owner", "another"]
    finally:
        await first.stop()
        await second.stop()


async def test_webhook_applies_fresh_allowlist_without_restarting_pending_messages(monkeypatch):
    from src.infra.channel.webhook import WebhookChannelManager

    handled = []
    redis = AsyncMock()
    redis.set.return_value = True
    monkeypatch.setattr("src.infra.channel.chat.get_redis_client", lambda: redis)

    async def handle(**message):
        handled.append(message)

    manager = WebhookChannelManager(message_handler=handle)
    config = {
        "user_id": "owner",
        "instance_id": "one",
        "webhook_secret": "a" * 32,
        "allowed_sender_ids": "first",
    }
    try:
        await manager.receive_callback(
            config,
            {
                "sender_id": "first",
                "chat_id": "room",
                "content": "hello",
                "message_id": "1",
            },
        )
        channel = manager.get_channel("owner", "one")
        await channel.drain()
        await manager.receive_callback(
            {**config, "allowed_sender_ids": "second"},
            {
                "sender_id": "first",
                "chat_id": "room",
                "content": "blocked",
                "message_id": "2",
            },
        )
        await channel.drain()
        assert [item["content"] for item in handled] == ["hello"]
        assert manager.get_channel("owner", "one") is channel
    finally:
        await manager.stop()


def test_webhook_validation_errors_do_not_echo_secret():
    from src.infra.channel.webhook import WebhookConfig

    secret = "secret-value-with-newline\n"
    with pytest.raises(ValidationError) as exc:
        WebhookConfig(webhook_secret=secret)
    assert "secret-value-with-newline" not in str(exc.value)
