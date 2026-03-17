"""
依赖注入

提供 FastAPI 依赖项。
"""

import json
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.infra.auth.jwt import verify_token
from src.infra.logging import get_logger
from src.infra.role.storage import RoleStorage
from src.infra.storage.redis import get_redis_client
from src.infra.user.manager import UserManager
from src.infra.user.storage import UserStorage
from src.kernel.schemas.user import TokenPayload

security = HTTPBearer(auto_error=False)

logger = get_logger(__name__)

# 角色权限缓存 key 前缀和 TTL（按角色名缓存，所有用户共享）
_ROLE_PERMS_CACHE_PREFIX = "role:perms:"
_ROLE_PERMS_VERSION_PREFIX = "role:perms_ver:"
_ROLE_PERMS_CACHE_TTL = 300  # 5 分钟


async def _get_role_permissions(role_name: str) -> tuple[list[str], bool]:
    """
    从 Redis 缓存或数据库获取单个角色的权限列表

    使用版本号机制，分布式集群友好（不依赖 KEYS 命令）。

    Args:
        role_name: 角色名称

    Returns:
        (权限列表, 角色是否存在)
    """
    version: str = "0"

    try:
        redis_client = get_redis_client()
        raw = await redis_client.get(f"{_ROLE_PERMS_VERSION_PREFIX}{role_name}")
        version = raw or "0"
        cache_key = f"{_ROLE_PERMS_CACHE_PREFIX}{role_name}:v{version}"

        cached = await redis_client.get(cache_key)
        if cached:
            logger.debug(f"[Auth Cache] Hit for role {role_name}")
            return json.loads(cached), True
    except Exception as e:
        logger.warning(f"[Auth Cache] Redis get failed for role {role_name}: {e}")

    # 缓存未命中，从数据库查询
    logger.debug(f"[Auth Cache] Miss for role {role_name}")
    role_storage = RoleStorage()
    role = await role_storage.get_by_name(role_name)

    permissions: list[str] = []
    if role:
        for perm in role.permissions:
            permissions.append(perm if isinstance(perm, str) else perm.value)

    # 写入 Redis 缓存（CAS: 写入前重新检查版本号，避免 TOCTOU）
    try:
        redis_client = get_redis_client()
        current_version = await redis_client.get(f"{_ROLE_PERMS_VERSION_PREFIX}{role_name}")
        current_version = current_version or "0"
        # 版本号未变才写入，防止用旧数据覆盖已被 invalidate 的新 key
        if current_version == version:
            cache_key = f"{_ROLE_PERMS_CACHE_PREFIX}{role_name}:v{current_version}"
            await redis_client.set(
                cache_key,
                json.dumps(permissions),
                ex=_ROLE_PERMS_CACHE_TTL,
            )
        else:
            logger.debug(f"[Auth Cache] Version changed for role {role_name}, skip stale write")
    except Exception as e:
        logger.warning(f"[Auth Cache] Redis set failed for role {role_name}: {e}")

    return permissions, role is not None


async def _get_user_roles_and_permissions(user_roles: list[str]) -> tuple[list[str], list[str]]:
    """
    获取用户角色列表和合并后的权限列表

    每个角色的权限独立缓存，变更某角色只失效该角色的缓存。

    Args:
        user_roles: 用户角色列表（从 token 中获取）

    Returns:
        (角色列表, 权限列表)
    """
    roles = []
    permissions = set()

    for role_name in user_roles:
        perms, exists = await _get_role_permissions(role_name)
        if exists:
            roles.append(role_name)
            permissions.update(perms)

    return roles, list(permissions)


async def invalidate_role_permissions_cache(role_name: str) -> None:
    """
    清除指定角色的权限缓存（分布式集群友好）

    通过递增版本号使旧缓存 key 失效，无需 KEYS 扫描。
    当角色权限变更时应调用此方法。

    Args:
        role_name: 需要失效的角色名称
    """
    try:
        redis_client = get_redis_client()
        version_key = f"{_ROLE_PERMS_VERSION_PREFIX}{role_name}"
        await redis_client.incr(version_key)
        # 不设置 TTL，防止版本 key 过期导致版本号回退到 0
        logger.info(f"[Auth Cache] Invalidated cache for role {role_name} (version bumped)")
    except Exception as e:
        logger.warning(f"[Auth Cache] Redis incr failed for role {role_name}: {e}")


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[TokenPayload]:
    """
    获取当前用户（可选）

    从 JWT token 中解析用户信息。
    """
    if not credentials:
        return None

    try:
        token = credentials.credentials
        payload = verify_token(token)
        return payload
    except Exception:
        return None


# Alias for clarity
get_current_user_optional = get_current_user


async def get_current_user_required(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> TokenPayload:
    """
    获取当前用户（必需）

    如果未认证则抛出异常。
    用户信息从数据库动态获取，确保权限变更立即生效。
    """
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证信息",
        )

    try:
        token = credentials.credentials
        payload = verify_token(token)
        user_id = payload.sub

        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的 Token",
            )

        # 从数据库获取用户信息
        user_storage = UserStorage()
        user = await user_storage.get_by_id(user_id)

        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户不存在",
            )

        # 从缓存/数据库动态获取角色和权限
        roles, permissions = await _get_user_roles_and_permissions(user.roles)

        # 更新 payload
        payload.username = user.username
        payload.roles = roles
        payload.permissions = permissions

        return payload
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )


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
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证信息",
        )

    try:
        payload = verify_token(token)
        user_id = payload.sub

        if not user_id:
            logger.warning("[WebSocket] Invalid token: no user_id")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的 Token",
            )

        # 从数据库获取用户信息
        user_storage = UserStorage()
        user = await user_storage.get_by_id(user_id)

        if not user:
            logger.warning(f"[WebSocket] User not found: {user_id}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="用户不存在",
            )

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

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"[WebSocket] Auth error: {e}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
        )


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
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail=f"缺少权限: {perm}",
                )
        return user

    return checker
