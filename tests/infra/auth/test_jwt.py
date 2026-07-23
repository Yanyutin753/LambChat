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
from src.kernel.exceptions import AuthenticationError


@pytest.fixture
def jwt_settings(monkeypatch):
    monkeypatch.setattr(settings, "JWT_SECRET_KEY", "test-jwt-secret-key")
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
        with pytest.raises(AuthenticationError, match="sub"):
            verify_token(token)

    def test_expired_token_rejected(self, jwt_settings):
        token = create_access_token("user-123", expires_delta=timedelta(seconds=-1))
        with pytest.raises(AuthenticationError, match="过期"):
            verify_token(token)

    def test_tampered_token_rejected(self, jwt_settings):
        token = create_access_token("user-123")
        tampered = token[:-4] + "AAAA"
        with pytest.raises(AuthenticationError):
            verify_token(tampered)

    def test_wrong_secret_rejected(self, jwt_settings, monkeypatch):
        token = create_access_token("user-123")
        monkeypatch.setattr(settings, "JWT_SECRET_KEY", "different-secret")
        with pytest.raises(AuthenticationError):
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
        with pytest.raises(AuthenticationError, match="sub"):
            verify_token(token)
