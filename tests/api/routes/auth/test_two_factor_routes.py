from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from src.api import deps
from src.api.error_handlers import register_error_handlers
from src.api.middleware.auth import AuthMiddleware
from src.api.routes.auth import core, oauth, two_factor
from src.infra.auth import two_factor as mfa
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.user import TokenPayload, TwoFactorChallenge, User, UserCreate


@pytest.mark.parametrize("channel", ["jwt", "cached-jwt", "websocket"])
async def test_old_login_version_is_rejected_in_every_interactive_channel(monkeypatch, channel):
    deps.clear_auth_cache()
    payload = TokenPayload(sub="owner", username="a", auth_version="old")
    user = SimpleNamespace(username="a", roles=[], is_active=True, auth_version="new")
    monkeypatch.setattr(
        deps, "UserStorage", lambda: SimpleNamespace(get_by_id=AsyncMock(return_value=user))
    )
    monkeypatch.setattr(deps, "_verify_token_async", AsyncMock(return_value=payload))
    monkeypatch.setattr(deps, "_get_user_roles_and_permissions", AsyncMock(return_value=([], [])))
    if channel == "cached-jwt":
        deps._set_cached_user("token", payload)
    from fastapi.security import HTTPAuthorizationCredentials

    with pytest.raises(AppError) as failure:
        if channel == "websocket":
            await deps.get_current_user_from_websocket("token")
        else:
            await deps.get_current_user_required(
                SimpleNamespace(state=SimpleNamespace()),
                HTTPAuthorizationCredentials(scheme="Bearer", credentials="token"),
            )
    assert failure.value.error_code is ErrorCode.INVALID_TOKEN
    deps.clear_auth_cache()


async def test_old_refresh_token_cannot_bypass_enrollment(monkeypatch):
    monkeypatch.setattr(
        core, "decode_token", lambda _: {"sub": "owner", "username": "a", "type": "refresh"}
    )
    monkeypatch.setattr(
        core,
        "UserManager",
        lambda: SimpleNamespace(
            storage=SimpleNamespace(
                get_by_id=AsyncMock(
                    return_value=SimpleNamespace(is_active=True, auth_version="new")
                )
            )
        ),
    )
    with pytest.raises(AppError) as failure:
        await core.refresh_token(
            SimpleNamespace(json=AsyncMock(return_value={"refresh_token": "old"}))
        )
    assert failure.value.error_code is ErrorCode.REFRESH_TOKEN_INVALID


@pytest.mark.parametrize("method", ["get", "form", "json"])
async def test_oauth_returns_only_challenge_until_second_factor_passes(monkeypatch, method):
    async def exchange(*_):
        return "https://lambchat.com", TwoFactorChallenge(challenge_token="opaque-challenge")

    monkeypatch.setattr(oauth, "_exchange_oauth_token", exchange)
    monkeypatch.setattr(oauth, "_verify_state", AsyncMock(return_value=True))
    monkeypatch.setattr(oauth, "_get_frontend_url", lambda _: "https://lambchat.com")
    app = FastAPI()
    app.include_router(oauth.router, prefix="/api/auth")
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        if method == "get":
            result = await client.get(
                "/api/auth/oauth/google/callback", params={"code": "c", "state": "s"}
            )
        elif method == "form":
            result = await client.post(
                "/api/auth/oauth/apple/callback", data={"code": "c", "state": "s"}
            )
        else:
            result = await client.post(
                "/api/auth/oauth/github/callback", json={"code": "c", "state": "s"}
            )
    if method == "json":
        assert result.json() == {"two_factor_required": True, "challenge_token": "opaque-challenge"}
    else:
        assert parse_qs(urlparse(result.headers["location"]).fragment) == {
            "challenge_token": ["opaque-challenge"]
        }
    assert "access_token" not in result.text
    assert "refresh_token" not in result.text


async def test_second_factor_endpoint_is_public_but_pairing_requires_access_token(monkeypatch):
    app = FastAPI()
    register_error_handlers(app)
    app.add_middleware(AuthMiddleware)
    app.include_router(two_factor.router, prefix="/api/auth")
    verify = AsyncMock(side_effect=AppError(ErrorCode.TWO_FACTOR_INVALID))
    monkeypatch.setattr(two_factor, "rate_limit", AsyncMock())
    monkeypatch.setattr(
        two_factor, "TwoFactorService", lambda: SimpleNamespace(complete_login=verify)
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/auth/2fa/verify", json={"challenge_token": "x" * 43, "code": "123456"}
        )
        assert response.status_code == 400
        assert response.json()["detail"]["code"] == "two_factor_invalid"
        for action in ("setup", "enable", "disable", "recovery-codes"):
            response = await client.post(
                f"/api/auth/2fa/{action}", json={"password": "p", "code": "123456"}
            )
            assert response.status_code == 401
        response = await client.post(
            "/api/auth/2fa/setup",
            json={"password": "p"},
            headers={"Authorization": "Bearer " + "x" * 43},
        )
        assert response.status_code == 401
    assert verify.await_count == 1


async def test_public_registration_discards_privileged_fields(monkeypatch):
    monkeypatch.setattr(core.settings, "ENABLE_REGISTRATION", True)
    monkeypatch.setattr(core.settings, "REQUIRE_EMAIL_VERIFICATION", False)
    monkeypatch.setattr(
        core, "get_turnstile_service", lambda: SimpleNamespace(require_on_register=False)
    )
    create = AsyncMock(return_value=User(id="owner", username="a", email="a@example.com"))
    monkeypatch.setattr(core, "UserManager", lambda: SimpleNamespace(register=create))
    body = UserCreate(
        username="a",
        email="a@example.com",
        password="secret",
        roles=["admin"],
        skip_verification=True,
        oauth_provider="github",
        oauth_id="attacker",
    )
    await core.register(body, SimpleNamespace())
    actual = create.call_args.args[0]
    assert actual.roles == []
    assert actual.skip_verification is False
    assert actual.oauth_id is None
    assert actual.oauth_provider is None


async def test_password_login_never_returns_tokens_for_an_enabled_account(monkeypatch):
    from src.infra.user.manager import UserManager
    from src.kernel.schemas.user import UserInDB

    user = UserInDB(
        id="owner",
        username="a",
        email="a@example.com",
        password_hash="hash",
        email_verified=True,
        two_factor_enabled=True,
        auth_version="v1",
    )
    manager = UserManager()
    manager.storage = SimpleNamespace(authenticate=AsyncMock(return_value=user))
    monkeypatch.setattr(mfa, "get_redis_client", lambda: SimpleNamespace(set=AsyncMock()))
    result = await manager.login("a", "secret")
    assert isinstance(result, TwoFactorChallenge)


async def test_pairing_response_disables_http_caching(monkeypatch):
    app = FastAPI()
    app.include_router(two_factor.router, prefix="/api/auth")
    app.dependency_overrides[deps.get_current_user_required] = lambda: TokenPayload(
        sub="owner", username="a"
    )
    monkeypatch.setattr(
        two_factor,
        "TwoFactorService",
        lambda: SimpleNamespace(
            get_user=AsyncMock(return_value="user"),
            setup=AsyncMock(return_value={"secret": "secret", "otpauth_uri": "uri"}),
        ),
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/api/auth/2fa/setup", json={"password": "secret"})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
