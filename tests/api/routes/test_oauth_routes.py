from __future__ import annotations

from urllib.parse import urlparse

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api.routes.auth import oauth as oauth_routes
from src.api.routes.auth import utils as auth_utils
from src.kernel.schemas.user import Token


class _FakeOAuthService:
    async def handle_callback(self, provider, code: str, state: str, redirect_uri: str):
        assert code == "apple-code"
        assert state == "state-123"
        assert redirect_uri == "https://lambchat.com/api/auth/oauth/apple/callback"
        return Token(access_token="access.jwt", refresh_token="refresh.jwt", expires_in=3600)


@pytest.mark.asyncio
async def test_apple_form_post_callback_redirects_to_frontend_fragment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = FastAPI()
    app.include_router(oauth_routes.router, prefix="/api/auth")

    monkeypatch.setattr(oauth_routes, "_get_frontend_url", lambda request: "https://lambchat.com")
    monkeypatch.setattr(oauth_routes, "_get_client_ip", lambda request: "203.0.113.10")
    monkeypatch.setattr(oauth_routes, "_verify_oauth_state", lambda provider, state, ip: True)

    import src.infra.auth.oauth as oauth_service_module

    monkeypatch.setattr(oauth_service_module, "get_oauth_service", lambda: _FakeOAuthService())

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://lambchat.com",
        follow_redirects=False,
    ) as client:
        response = await client.post(
            "/api/auth/oauth/apple/callback",
            data={"code": "apple-code", "state": "state-123"},
        )

    assert response.status_code == 302
    location = response.headers["location"]
    parsed = urlparse(location)
    assert parsed.scheme == "https"
    assert parsed.netloc == "lambchat.com"
    assert parsed.path == "/auth/callback"
    assert "access_token=access.jwt" in parsed.fragment
    assert "refresh_token=refresh.jwt" in parsed.fragment
    assert "expires_in=3600" in parsed.fragment


def test_frontend_url_prefers_configured_app_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(auth_utils.settings, "APP_BASE_URL", "https://lambchat.com/")

    request = type(
        "Request",
        (),
        {
            "headers": {
                "host": "127.0.0.1:8000",
                "x-forwarded-proto": "http",
            },
            "base_url": "http://127.0.0.1:8000/",
        },
    )()

    assert auth_utils._get_frontend_url(request) == "https://lambchat.com"


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.deleted: list[str] = []

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self.values[key] = value

    async def get(self, key: str) -> str | None:
        return self.values.get(key)

    async def delete(self, key: str) -> None:
        self.deleted.append(key)
        self.values.pop(key, None)


@pytest.mark.asyncio
async def test_oauth_state_is_keyed_by_state_not_client_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    redis = _FakeRedis()

    import src.infra.storage.redis as redis_module

    monkeypatch.setattr(redis_module, "get_redis_client", lambda: redis)

    await auth_utils._store_oauth_state("github", "state-abc", "203.0.113.1")

    assert "oauth:state:github:state-abc" in redis.values
    assert await auth_utils._verify_oauth_state("github", "state-abc", "203.0.113.99")
    assert redis.deleted == ["oauth:state:github:state-abc"]


@pytest.mark.parametrize(
    "email,url", [("support@example.test", "https://example.test/support"), ("", "")]
)
async def test_public_auth_config_exposes_only_contact_fields_without_unlocking_settings(
    monkeypatch: pytest.MonkeyPatch, email: str, url: str
) -> None:
    from types import SimpleNamespace

    import src.infra.auth.oauth as oauth_service_module
    from src.api.middleware.auth import AuthMiddleware

    monkeypatch.setattr(
        oauth_service_module,
        "get_oauth_service",
        lambda: SimpleNamespace(is_provider_enabled=lambda provider: False),
    )
    monkeypatch.setattr(
        oauth_routes,
        "settings",
        SimpleNamespace(
            ENABLE_REGISTRATION=True,
            ADMIN_CONTACT_EMAIL=email,
            ADMIN_CONTACT_URL=url,
            JWT_SECRET_KEY="private-test-jwt",
            OAUTH_GOOGLE_CLIENT_SECRET="private-test-oauth",
        ),
    )
    monkeypatch.setattr(
        oauth_routes,
        "get_turnstile_service",
        lambda: SimpleNamespace(
            is_enabled=False,
            site_key="",
            require_on_login=False,
            require_on_register=False,
            require_on_password_change=False,
            secret_key="private-test-turnstile",
        ),
    )
    app = FastAPI()
    app.add_middleware(AuthMiddleware)
    app.include_router(oauth_routes.router, prefix="/api/auth")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/api/auth/oauth/providers", headers={"accept": "application/json"}
        )
        protected = await client.get("/api/settings", headers={"accept": "application/json"})
    assert response.status_code == 200
    assert response.json() == {
        "providers": [],
        "registration_enabled": True,
        "admin_contact": {"email": email, "url": url},
        "turnstile": {
            "enabled": False,
            "site_key": "",
            "require_on_login": False,
            "require_on_register": False,
            "require_on_password_change": False,
        },
    }
    assert protected.status_code == 401
