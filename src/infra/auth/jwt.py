"""
JWT Token 处理

提供 JWT token 的创建、验证和解码功能。
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

import jwt

from src.kernel.config import settings
from src.kernel.exceptions import AuthenticationError
from src.kernel.schemas.user import TokenPayload


def create_access_token(
    user_id: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    创建访问令牌

    Args:
        user_id: 用户ID
        expires_delta: 过期时间增量

    Returns:
        JWT 访问令牌（用户信息从 API 动态获取）
    """
    if expires_delta is None:
        expires_delta = timedelta(hours=settings.ACCESS_TOKEN_EXPIRE_HOURS)

    now = datetime.now(timezone.utc)
    expire = now + expires_delta

    payload = {
        "sub": user_id,
        "exp": expire,
        "iat": now,
    }

    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def create_refresh_token(
    user_id: str,
    username: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    """
    创建刷新令牌

    Args:
        user_id: 用户ID
        username: 用户名
        expires_delta: 过期时间增量

    Returns:
        JWT 刷新令牌
    """
    if expires_delta is None:
        expires_delta = timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)

    now = datetime.now(timezone.utc)
    expire = now + expires_delta

    payload = {
        "sub": user_id,
        "username": username,
        "type": "refresh",
        "exp": expire,
        "iat": now,
    }

    return jwt.encode(
        payload,
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )


def decode_token(token: str) -> Dict[str, Any]:
    """
    解码 JWT token

    Args:
        token: JWT token

    Returns:
        解码后的 payload

    Raises:
        AuthenticationError: token 无效或过期
    """
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise AuthenticationError("Token 已过期")
    except jwt.InvalidTokenError as e:
        raise AuthenticationError(f"无效的 Token: {str(e)}")


def verify_token(token: str) -> TokenPayload:
    """
    验证并解析 token

    Args:
        token: JWT token

    Returns:
        TokenPayload 对象

    Raises:
        AuthenticationError: token 无效或过期
    """
    payload = decode_token(token)

    return TokenPayload(
        sub=payload.get("sub", ""),
        username=payload.get("username", ""),
        roles=payload.get("roles", []),
        permissions=payload.get("permissions", []),
        exp=datetime.fromtimestamp(payload.get("exp", 0), tz=timezone.utc),
        iat=datetime.fromtimestamp(payload.get("iat", 0), tz=timezone.utc),
    )
