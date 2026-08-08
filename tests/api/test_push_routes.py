from __future__ import annotations

import logging

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api import deps as api_deps
from src.api.routes import push as push_route
from src.kernel.schemas.user import TokenPayload


def _fake_user() -> TokenPayload:
    return TokenPayload(
        sub="user-1",
        username="tester",
        roles=["user"],
        permissions=["chat:write"],
    )


def _subscription(
    sub_id: str = "sub-1",
    user_id: str = "user-1",
    endpoint: str = "https://push.example.com/sub/123",
) -> dict:
    return {
        "id": sub_id,
        "user_id": user_id,
        "endpoint": endpoint,
        "keys": {"p256dh": "key", "auth": "auth"},
        "user_agent": "Mozilla/5.0",
        "created_at": "2026-01-15T00:00:00",
        "last_used_at": None,
    }


# ── VAPID public key endpoint ──


@pytest.mark.asyncio
async def test_vapid_public_key_returns_key_when_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(push_route.settings, "VAPID_PUBLIC_KEY", "BM...test-key")

    app = FastAPI()
    app.include_router(push_route.router, prefix="/api/push")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/api/push/vapid-public-key")

    assert resp.status_code == 200
    assert resp.json() == {"public_key": "BM...test-key"}


@pytest.mark.asyncio
async def test_vapid_public_key_returns_503_when_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(push_route.settings, "VAPID_PUBLIC_KEY", "")

    app = FastAPI()
    app.include_router(push_route.router, prefix="/api/push")

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/api/push/vapid-public-key")

    assert resp.status_code == 503


# ── Subscribe endpoint ──


@pytest.mark.asyncio
async def test_subscribe_saves_subscription_and_returns_it() -> None:
    calls: list[tuple[str, dict, str]] = []

    class _FakeManager:
        async def save_subscription(self, user_id: str, data: dict, user_agent: str = "") -> dict:
            calls.append((user_id, data, user_agent))
            return _subscription()

    app = FastAPI()
    app.include_router(push_route.router, prefix="/api/push")
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_user
    app.dependency_overrides[push_route.get_push_manager] = lambda: _FakeManager()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post(
            "/api/push/subscribe",
            json={
                "endpoint": "https://push.example.com/sub/123",
                "keys": {"p256dh": "key", "auth": "auth"},
                "user_agent": "Mozilla/5.0",
            },
        )

    assert resp.status_code == 200
    assert calls[0][0] == "user-1"
    assert calls[0][1]["endpoint"] == "https://push.example.com/sub/123"
    assert resp.json()["id"] == "sub-1"


@pytest.mark.asyncio
async def test_subscribe_log_omits_subscription_endpoint(
    caplog: pytest.LogCaptureFixture,
) -> None:
    endpoint = "https://push.example.com/sub/private-token"

    class _FakeManager:
        async def save_subscription(self, user_id: str, data: dict, user_agent: str = "") -> dict:
            return _subscription(endpoint=endpoint)

    app = FastAPI()
    app.include_router(push_route.router, prefix="/api/push")
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_user
    app.dependency_overrides[push_route.get_push_manager] = lambda: _FakeManager()

    with caplog.at_level(logging.INFO):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as client:
            response = await client.post(
                "/api/push/subscribe",
                json={
                    "endpoint": endpoint,
                    "keys": {"p256dh": "key", "auth": "auth"},
                },
            )

    assert response.status_code == 200
    assert endpoint not in caplog.text
    assert "user-1" in caplog.text


@pytest.mark.asyncio
async def test_subscribe_rejects_non_https_endpoint() -> None:
    app = FastAPI()
    app.include_router(push_route.router, prefix="/api/push")
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post(
            "/api/push/subscribe",
            json={
                "endpoint": "http://insecure.example.com/sub",
                "keys": {"p256dh": "key", "auth": "auth"},
            },
        )

    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_subscribe_rejects_empty_keys() -> None:
    app = FastAPI()
    app.include_router(push_route.router, prefix="/api/push")
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post(
            "/api/push/subscribe",
            json={
                "endpoint": "https://push.example.com/sub/123",
                "keys": {"p256dh": "", "auth": ""},
            },
        )

    assert resp.status_code == 400


# ── Unsubscribe endpoint ──


@pytest.mark.asyncio
async def test_unsubscribe_removes_subscription() -> None:
    calls: list[str] = []

    class _FakeManager:
        async def remove_subscription(self, endpoint: str) -> bool:
            calls.append(endpoint)
            return True

    app = FastAPI()
    app.include_router(push_route.router, prefix="/api/push")
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_user
    app.dependency_overrides[push_route.get_push_manager] = lambda: _FakeManager()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post(
            "/api/push/unsubscribe",
            json={
                "endpoint": "https://push.example.com/sub/123",
            },
        )

    assert resp.status_code == 200
    assert resp.json()["status"] == "unsubscribed"
    assert calls == ["https://push.example.com/sub/123"]


# ── Delete all subscriptions endpoint ──


@pytest.mark.asyncio
async def test_delete_all_subscriptions_removes_for_user() -> None:
    calls: list[str] = []

    class _FakeManager:
        async def remove_all_for_user(self, user_id: str) -> int:
            calls.append(user_id)
            return 3

    app = FastAPI()
    app.include_router(push_route.router, prefix="/api/push")
    app.dependency_overrides[api_deps.get_current_user_required] = _fake_user
    app.dependency_overrides[push_route.get_push_manager] = lambda: _FakeManager()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.delete("/api/push/subscriptions")

    assert resp.status_code == 200
    assert resp.json()["count"] == 3
    assert calls == ["user-1"]
