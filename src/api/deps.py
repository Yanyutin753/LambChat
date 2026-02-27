"""
依赖注入

提供 FastAPI 依赖项。
"""

from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from src.infra.auth.jwt import verify_token
from src.infra.role.storage import RoleStorage
from src.infra.user.manager import UserManager
from src.infra.user.storage import UserStorage
from src.kernel.schemas.user import TokenPayload

security = HTTPBearer(auto_error=False)


async def _get_user_roles_and_permissions(user_roles: list[str]) -> tuple[list[str], list[str]]:
    """
    从数据库获取用户最新的角色和权限

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
                if isinstance(perm, str):
                    permissions.add(perm)
                else:
                    permissions.add(perm.value)

    return roles, list(permissions)


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

        # 从数据库动态获取角色和权限
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
