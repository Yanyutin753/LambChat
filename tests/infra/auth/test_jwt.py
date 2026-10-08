"""JWT 令牌处理测试。

覆盖：签发/验证往返、过期、篡改、错误密钥、缺失声明、刷新令牌。
"""

from datetime import timedelta

import jwt
import pytest

from src.infra.auth.jwt import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_token,
)
from src.infra.utils.datetime import utc_now
from src.kernel.config import settings
from src.kernel.errors import AppError


@pytest.fixture
def jwt_settings(monkeypatch):
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", "test-jwt-secret-key-with-32-bytes-minimum")
    monkeypatch.setattr(settings, "JWT_ALGORITHM", "HS256")
    monkeypatch.setattr(settings, "ACCESS_TOKEN_EXPIRE_HOURS", 1)
    monkeypatch.setattr(settings, "REFRESH_TOKEN_EXPIRE_DAYS", 7)


class TestAccessToken:
    def test_create_and_verify_access_token(self, jwt_settings):
        token = create_access_token("user-123")
        payload = verify_token(token)
        assert payload.sub == "user-123"
        assert payload.exp is not None
        assert payload.iat is not None

    def test_access_token_missing_sub_rejected(self, jwt_settings):
        now = utc_now()
        token = jwt.encode(
            {"exp": now + timedelta(hours=1), "iat": now},
            settings.JWT_SECRET_KEY,
            algorithm="HS256",
        )
        with pytest.raises(AppError, match="sub"):
            verify_token(token)

    def test_expired_token_rejected(self, jwt_settings):
        token = create_access_token("user-123", expires_delta=timedelta(seconds=-1))
        with pytest.raises(AppError):
            verify_token(token)

    def test_tampered_token_rejected(self, jwt_settings):
        token = create_access_token("user-123")
        tampered = token[:-4] + "AAAA"
        with pytest.raises(AppError):
            verify_token(tampered)

    def test_wrong_secret_rejected(self, jwt_settings, monkeypatch):
        token = create_access_token("user-123")
        monkeypatch.setattr(
            settings, "JWT_SECRET_KEY", "different-secret-key-with-32-bytes-minimum"
        )
        with pytest.raises(AppError):
            verify_token(token)


class TestRefreshToken:
    def test_create_and_decode_refresh_token(self, jwt_settings):
        token = create_refresh_token("user-123", "alice")
        payload = decode_token(token)
        assert payload["sub"] == "user-123"
        assert payload["username"] == "alice"
        assert payload["type"] == "refresh"

    def test_refresh_token_missing_sub_rejected_by_verify(self, jwt_settings):
        now = utc_now()
        token = jwt.encode(
            {"exp": now + timedelta(days=1), "iat": now, "type": "refresh"},
            settings.JWT_SECRET_KEY,
            algorithm="HS256",
        )
        with pytest.raises(AppError, match="sub"):
            verify_token(token)


@pytest.mark.parametrize("token_type", ["refresh", "reset", "mfa", "step_up"])
async def test_nonaccess_token_cannot_authenticate_an_ordinary_api(
    jwt_settings, monkeypatch, token_type
):
    from fastapi import Depends, FastAPI
    from httpx import ASGITransport, AsyncClient

    from src.api import deps
    from src.api.error_handlers import register_error_handlers
    from src.kernel.schemas.user import TokenPayload

    async def user_payload(user_id, payload=None):
        return payload or TokenPayload(sub=user_id, username="alice")

    monkeypatch.setattr(deps, "_load_user_payload", user_payload)
    deps.clear_auth_cache()
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/ordinary-api")
    async def ordinary_api(user=Depends(deps.get_current_user_required)):
        return {"sub": user.sub}

    now = utc_now()
    token = (
        create_refresh_token("user-123", "alice")
        if token_type == "refresh"
        else jwt.encode(
            {"sub": "user-123", "iat": now, "exp": now + timedelta(minutes=5), "type": token_type},
            settings.JWT_SECRET_KEY,
            algorithm="HS256",
        )
    )
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/ordinary-api", headers={"Authorization": f"Bearer {token}"}
            )
        assert response.status_code == 401
        assert response.json()["detail"]["code"] == "invalid_token"
    finally:
        deps.clear_auth_cache()


def test_new_access_tokens_explicitly_declare_their_type(jwt_settings):
    assert decode_token(create_access_token("user-123"))["type"] == "access"


def test_only_original_access_claim_shape_is_accepted_without_type(jwt_settings):
    now = utc_now()
    legacy = jwt.encode(
        {"sub": "user-123", "exp": now + timedelta(hours=1), "iat": now},
        settings.JWT_SECRET_KEY,
        algorithm="HS256",
    )
    assert verify_token(legacy).sub == "user-123"


@pytest.mark.parametrize(
    "extra",
    [
        {"type": None},
        {"type": ""},
        {"purpose": "reset"},
        {"username": "alice"},
        {"challenge_id": "pending-mfa"},
    ],
)
def test_ambiguous_or_purpose_marked_untyped_tokens_are_rejected(jwt_settings, extra):
    now = utc_now()
    token = jwt.encode(
        {"sub": "user-123", "exp": now + timedelta(hours=1), "iat": now, **extra},
        settings.JWT_SECRET_KEY,
        algorithm="HS256",
    )
    with pytest.raises(AppError):
        verify_token(token)
