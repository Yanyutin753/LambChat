"""FastAPI dependencies."""

from __future__ import annotations

import time
from typing import Optional

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.infra.async_utils import run_blocking_io
from src.infra.auth.jwt import verify_token
from src.infra.logging import get_logger
from src.infra.role.storage import RoleStorage
from src.infra.user.manager import UserManager
from src.infra.user.storage import UserStorage
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.user import TokenPayload

security = HTTPBearer(auto_error=False)

logger = get_logger(__name__)

_AUTH_CACHE_TTL_SECONDS = 45.0
_AUTH_CACHE_MAX_ENTRIES = 2048
_auth_cache: dict[str, tuple[float, TokenPayload]] = {}


def clear_auth_cache() -> None:
    """Clear per-process authenticated user cache after user/role changes."""
    _auth_cache.clear()


def _get_cached_user(token: str) -> TokenPayload | None:
    cached = _auth_cache.get(token)
    if not cached:
        return None

    expires_at, payload = cached
    if expires_at <= time.monotonic():
        _auth_cache.pop(token, None)
        return None
    return payload.model_copy(deep=True)


def _set_cached_user(token: str, payload: TokenPayload) -> None:
    if len(_auth_cache) >= _AUTH_CACHE_MAX_ENTRIES:
        now = time.monotonic()
        expired = [key for key, (expires_at, _) in _auth_cache.items() if expires_at <= now]
        for key in expired:
            _auth_cache.pop(key, None)
        while len(_auth_cache) >= _AUTH_CACHE_MAX_ENTRIES:
            _auth_cache.pop(next(iter(_auth_cache)))

    _auth_cache[token] = (time.monotonic() + _AUTH_CACHE_TTL_SECONDS, payload.model_copy(deep=True))


async def _get_user_roles_and_permissions(user_roles: list[str]) -> tuple[list[str], list[str]]:
    """
    获取用户角色列表和合并后的权限列表

    角色数据通过 RoleStorage 的 Redis 缓存获取，无需额外缓存层。

    Args:
        user_roles: 用户角色列表（从 token 中获取）

    Returns:
        (角色列表, 权限列表)
    """
    role_storage = RoleStorage()
    roles = []
    permissions = set()

    for role_name in user_roles:
        role = await role_storage.get_by_name(role_name)
        if role:
            roles.append(role.name)
            for perm in role.permissions:
                permissions.add(perm if isinstance(perm, str) else perm.value)

    return roles, list(permissions)


async def _verify_token_async(token: str) -> TokenPayload:
    return await run_blocking_io(verify_token, token)


async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[TokenPayload]:
    """
    获取当前用户（可选）

    从 JWT token 中解析用户信息。
    """
    if not credentials:
        return None

    try:
        cached = getattr(request.state, "current_user", None)
        if isinstance(cached, TokenPayload):
            return cached.model_copy(deep=True)

        token = credentials.credentials
        parsed = getattr(request.state, "auth_payload", None)
        payload = (
            parsed.model_copy(deep=True)
            if isinstance(parsed, TokenPayload)
            else await _verify_token_async(token)
        )
        return payload
    except Exception:
        return None


# Alias for clarity
get_current_user_optional = get_current_user


async def get_current_user_required(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> TokenPayload:
    """
    获取当前用户（必需）

    如果未认证则抛出异常。
    用户信息从数据库动态获取，确保权限变更立即生效。
    """
    if not credentials:
        raise AppError(ErrorCode.AUTH_MISSING)

    try:
        token = credentials.credentials
        cached_user = getattr(request.state, "current_user", None)
        if isinstance(cached_user, TokenPayload):
            return cached_user.model_copy(deep=True)

        cached = _get_cached_user(token)
        if cached is not None:
            request.state.current_user = cached.model_copy(deep=True)
            return cached

        parsed = getattr(request.state, "auth_payload", None)
        payload = (
            parsed.model_copy(deep=True)
            if isinstance(parsed, TokenPayload)
            else await _verify_token_async(token)
        )
        user_id = payload.sub

        if not user_id:
            raise AppError(ErrorCode.INVALID_TOKEN)

        # 从数据库获取用户信息
        user_storage = UserStorage()
        user = await user_storage.get_by_id(user_id)

        if not user:
            raise AppError(ErrorCode.USER_NOT_FOUND)

        # 从缓存/数据库动态获取角色和权限
        roles, permissions = await _get_user_roles_and_permissions(user.roles)

        # 更新 payload
        payload.username = user.username
        payload.roles = roles
        payload.permissions = permissions

        _set_cached_user(token, payload)
        request.state.current_user = payload.model_copy(deep=True)

        return payload
    except AppError:
        raise
    except Exception as e:
        raise AppError(ErrorCode.INVALID_TOKEN, message=str(e)) from e


async def get_current_user_from_websocket(
    token: str,
) -> TokenPayload:
    """
    从 WebSocket 查询参数获取当前用户

    用于 WebSocket 连接的认证。
    """
    from src.infra.logging import get_logger

    logger = get_logger(__name__)

    if not token:
        logger.warning("[WebSocket] No token provided")
        raise AppError(ErrorCode.AUTH_MISSING)

    try:
        payload = await _verify_token_async(token)
        user_id = payload.sub

        if not user_id:
            logger.warning("[WebSocket] Invalid token: no user_id")
            raise AppError(ErrorCode.INVALID_TOKEN)

        # 从数据库获取用户信息
        user_storage = UserStorage()
        user = await user_storage.get_by_id(user_id)

        if not user:
            logger.warning(f"[WebSocket] User not found: {user_id}")
            raise AppError(ErrorCode.USER_NOT_FOUND)

        # 从缓存/数据库动态获取角色和权限
        roles, permissions = await _get_user_roles_and_permissions(user.roles)

        # 创建新的 TokenPayload，返回用户信息
        return TokenPayload(
            sub=payload.sub,
            username=user.username,
            roles=roles,
            permissions=permissions,
            exp=payload.exp,
            iat=payload.iat,
        )

    except AppError:
        raise
    except Exception as e:
        logger.error(f"[WebSocket] Auth error: {e}")
        raise AppError(ErrorCode.INVALID_TOKEN, message=str(e)) from e


async def get_user_manager() -> UserManager:
    """获取用户管理器"""
    return UserManager()


def require_permissions(*permissions: str):
    """
    权限检查依赖

    用法:
        @router.get("/", dependencies=[Depends(require_permissions("user:read"))])
    """

    async def checker(
        user: TokenPayload = Depends(get_current_user_required),
    ) -> TokenPayload:
        user_permissions = set(user.permissions)
        for perm in permissions:
            if perm not in user_permissions:
                raise AppError(ErrorCode.PERMISSION_MISSING, args={"permission": perm})
        return user

    return checker
