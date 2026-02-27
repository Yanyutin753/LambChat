"""
基于角色的访问控制 (RBAC)

提供权限检查和角色管理功能。
"""

from __future__ import annotations

from functools import wraps
from typing import TYPE_CHECKING, Callable, List, Set

from src.kernel.exceptions import AuthorizationError
from src.kernel.types import Permission

if TYPE_CHECKING:
    from src.kernel.schemas.role import Role


def check_permission(
    user_permissions: List[str],
    required_permission: str,
) -> bool:
    """
    检查用户是否拥有指定权限

    Args:
        user_permissions: 用户权限列表
        required_permission: 需要的权限

    Returns:
        是否拥有权限
    """
    return required_permission in user_permissions


def get_user_permissions(
    roles: List["Role"],
) -> Set[str]:
    """
    获取用户的所有权限（合并所有角色的权限）

    Args:
        roles: 用户的角色列表

    Returns:
        权限集合
    """
    permissions: Set[str] = set()
    for role in roles:
        for perm in role.permissions:
            permissions.add(perm.value)
    return permissions


def require_permissions(
    *required_permissions: str,
) -> Callable:
    """
    权限检查装饰器

    用法:
        @require_permissions("chat:read", "chat:write")
        async def chat_endpoint(...):
            ...

    Args:
        required_permissions: 需要的权限列表

    Returns:
        装饰器函数
    """

    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 从 kwargs 中获取当前用户
            current_user = kwargs.get("current_user")
            if not current_user:
                raise AuthorizationError("未认证的用户")

            user_permissions = set(current_user.get("permissions", []))

            for perm in required_permissions:
                if perm not in user_permissions:
                    raise AuthorizationError(f"缺少权限: {perm}")

            return await func(*args, **kwargs)

        return wrapper

    return decorator


class RBACManager:
    """
    RBAC 管理器

    提供角色和权限的管理功能。
    """

    def __init__(self):
        self._role_cache: dict = {}

    def validate_permission(self, permission: str) -> bool:
        """
        验证权限是否有效

        Args:
            permission: 权限字符串

        Returns:
            是否有效
        """
        try:
            Permission(permission)
            return True
        except ValueError:
            return False

    def get_default_roles(self) -> List[dict]:
        """
        获取默认角色配置

        Returns:
            默认角色列表
        """
        return [
            {
                "name": "admin",
                "description": "系统管理员 - 拥有所有权限",
                "permissions": [p.value for p in Permission],
                "is_system": True,
            },
            {
                "name": "user",
                "description": "普通用户 - 可使用聊天、会话、技能和MCP功能",
                "permissions": [
                    # Chat
                    Permission.CHAT_READ.value,
                    Permission.CHAT_WRITE.value,
                    # Session
                    Permission.SESSION_READ.value,
                    Permission.SESSION_WRITE.value,
                    Permission.SESSION_DELETE.value,
                    # Skill
                    Permission.SKILL_READ.value,
                    Permission.SKILL_WRITE.value,
                    Permission.SKILL_DELETE.value,
                    # MCP
                    Permission.MCP_READ.value,
                    Permission.MCP_WRITE.value,
                    Permission.MCP_DELETE.value,
                ],
                "is_system": False,
            },
            {
                "name": "guest",
                "description": "访客 - 只读访问",
                "permissions": [
                    Permission.CHAT_READ.value,
                    Permission.SESSION_READ.value,
                    Permission.SKILL_READ.value,
                    Permission.MCP_READ.value,
                ],
                "is_system": False,
            },
        ]
