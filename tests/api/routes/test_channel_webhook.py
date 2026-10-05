"""Tenant-safe generic webhook callback boundary."""

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi import FastAPI

from src.api.error_handlers import register_error_handlers


async def _callback(
    monkeypatch, *, config=None, payload=None, secret="a" * 32, raw=None, accepted=True
):
    from src.api.routes import channel_webhook

    config = (
        config
        if config is not None
        else {
            "user_id": "tenant-from-storage",
            "instance_id": "instance",
            "channel_type": "webhook",
            "enabled": True,
            "receive_enabled": True,
            "webhook_secret": "a" * 32,
            "allowed_sender_ids": "sender",
        }
    )
    storage = SimpleNamespace(get_config_by_instance=AsyncMock(return_value=config))
    deliveries = []

    async def receive(config, message):
        deliveries.append((config, message))
        return accepted

    manager = SimpleNamespace(receive_callback=receive)
    monkeypatch.setattr(channel_webhook.WebhookChannelManager, "get_instance", lambda: manager)
    app = FastAPI()
    from src.api.middleware.auth import AuthMiddleware

    app.add_middleware(AuthMiddleware)
    register_error_handlers(app)
    app.include_router(channel_webhook.router, prefix="/api/channels")
    app.dependency_overrides[channel_webhook.get_channel_storage] = lambda: storage
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://test"
    ) as client:
        response = await client.post(
            "/api/channels/webhook/instance/callback",
            headers={"x-lambchat-bot-secret": secret, "content-type": "application/json"},
            content=raw
            if raw is not None
            else json.dumps(
                payload
                or {
                    "sender_id": "sender",
                    "content": "hello",
                    "message_id": "msg-1",
                }
            ),
        )
    return response, deliveries


async def test_authenticated_webhook_uses_stored_owner(monkeypatch):
    response, deliveries = await _callback(monkeypatch)
    assert response.status_code == 202
    assert response.json() == {"accepted": True}
    assert deliveries[0][0]["user_id"] == "tenant-from-storage"
    assert deliveries[0][1] == {
        "sender_id": "sender",
        "chat_id": "sender",
        "content": "hello",
        "message_id": "msg-1",
    }


@pytest.mark.parametrize("secret", ["", "wrong", "a" * 31, "a" * 32 + "x"])
async def test_wrong_secret_cannot_dispatch(monkeypatch, secret):
    response, deliveries = await _callback(monkeypatch, secret=secret)
    assert response.status_code == 403
    assert not deliveries


@pytest.mark.parametrize(
    "overrides",
    [
        {"enabled": False},
        {"receive_enabled": False},
        {"webhook_secret": ""},
        {"user_id": ""},
        {"channel_type": "telegram"},
        {"instance_id": "other"},
    ],
)
async def test_disabled_or_invalid_instance_cannot_dispatch(monkeypatch, overrides):
    config = {
        "user_id": "tenant",
        "instance_id": "instance",
        "channel_type": "webhook",
        "enabled": True,
        "receive_enabled": True,
        "webhook_secret": "a" * 32,
        **overrides,
    }
    response, deliveries = await _callback(monkeypatch, config=config)
    assert response.status_code == 403
    assert not deliveries


@pytest.mark.parametrize(
    "payload",
    [
        {"sender_id": "sender", "content": "hello", "message_id": "msg-1", "user_id": "victim"},
        {"sender_id": "sender", "content": "hello", "message_id": "msg-1", "botId": "other"},
        {"sender_id": "sender", "content": "hello"},
        {"sender_id": "sender", "content": "a" * 16001, "message_id": "msg-1"},
    ],
)
async def test_untrusted_payload_cannot_override_routing(monkeypatch, payload):
    response, deliveries = await _callback(monkeypatch, payload=payload)
    assert response.status_code == 422
    assert not deliveries
    assert "victim" not in response.text


@pytest.mark.parametrize("raw,status", [("{", 422), ("{}" + " " * 65536, 413)])
async def test_invalid_or_oversized_body_never_dispatches(monkeypatch, raw, status):
    response, deliveries = await _callback(monkeypatch, raw=raw)
    assert response.status_code == status
    assert not deliveries


async def test_webhook_backpressure_requests_provider_retry(monkeypatch):
    response, deliveries = await _callback(monkeypatch, accepted=False)
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "service_unavailable"
    assert len(deliveries) == 1
