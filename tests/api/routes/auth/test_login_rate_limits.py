"""Exercise login throttling through ASGI without network or Redis services."""

from collections import Counter
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api.error_handlers import register_error_handlers
from src.api.routes.auth import core
from src.infra.auth import two_factor


@pytest.fixture
def login_app(monkeypatch):
    login = AsyncMock(return_value=None)
    monkeypatch.setattr(core, "UserManager", lambda: SimpleNamespace(login=login))
    monkeypatch.setattr(
        core, "get_turnstile_service", lambda: SimpleNamespace(require_on_login=False)
    )
    app = FastAPI()
    register_error_handlers(app)
    app.include_router(core.router, prefix="/api/auth")
    return app, login


@pytest.mark.parametrize("scope,allowed", [("account", 10), ("ip", 30)])
async def test_wrong_password_attempts_are_throttled_before_authentication(
    monkeypatch, login_app, scope, allowed
):
    counters = Counter()

    async def increment(script, numkeys, key, ttl):
        assert numkeys == 1
        assert int(ttl) > 0
        counters[key] += 1
        return counters[key]

    monkeypatch.setattr(two_factor, "get_redis_client", lambda: SimpleNamespace(eval=increment))
    app, login = login_app
    transport = ASGITransport(app=app, client=("203.0.113.8", 1234))
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        for attempt in range(allowed + 1):
            username = (
                ("Owner" if attempt % 2 else "owner")
                if scope == "account"
                else f"account-{attempt}"
            )
            response = await client.post(
                "/api/auth/login",
                json={"username": username, "password": "incorrect"},
                headers={"X-Forwarded-For": f"198.51.100.{attempt + 1}"},
            )
            if attempt < allowed:
                assert response.status_code == 401
                assert response.json()["detail"]["code"] == "invalid_credentials"
            else:
                assert response.status_code == 429
                assert response.json()["detail"]["code"] == "too_many_requests"
    assert login.await_count == allowed


@pytest.mark.parametrize("successful_counters", [0, 1])
async def test_login_fails_closed_when_either_rate_counter_is_unavailable(
    monkeypatch, login_app, successful_counters
):
    redis = SimpleNamespace(
        eval=AsyncMock(side_effect=[1] * successful_counters + [ConnectionError("offline")])
    )
    monkeypatch.setattr(two_factor, "get_redis_client", lambda: redis)
    app, login = login_app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/auth/login", json={"username": "owner", "password": "incorrect"}
        )
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "two_factor_unavailable"
    login.assert_not_awaited()
