"""
基于角色的访问控制 (RBAC)

提供权限检查和角色管理功能。
"""

from __future__ import annotations

from functools import wraps
from typing import TYPE_CHECKING, Callable, List, Set

from src.kernel.errors import ErrorCode
from src.kernel.exceptions import AuthorizationError
from src.kernel.types import Permission

if TYPE_CHECKING:
    from src.kernel.schemas.role import Role


RETIRED_PERMISSIONS = {"chat:read", "session:admin", "skill:admin", "role:manage"}
PERMISSION_MIGRATION = "permission_boundaries_v1"


def migrate_permission_grants(permissions: list[str]) -> list[str]:
    """Expand historical grants once during storage migration, never during authorization."""
    expanded = {
        "chat:read": ["session:read"],
        "user:write": [
            "user:create",
            "user:status",
            "user:reset_password",
            "user:assign_roles",
            "role:read",
        ],
        "role:manage": [
            "role:read",
            "role:write",
            "role:delete",
            "role:grant",
            "usage:quota_manage",
        ],
        "model:admin": [
            "model:read",
            "model:delete",
            "model:assign",
            "pricing:manage",
            "role:read",
        ],
        "agent:admin": ["agent:config_read", "agent:assign", "role:read"],
        "mcp:admin": ["mcp:system_read", "mcp:system_delete", "mcp:policy_manage", "mcp:export"],
        "settings:manage": ["settings:read", "settings:security", "settings:reset"],
        "usage:admin": ["usage:read", "usage:quota_manage"],
        "notification:manage": ["notification:read", "notification:delete"],
        "persona_preset:write": ["persona_preset:delete"],
        "envvar:read": ["envvar:reveal"],
        "session:read": ["project:read", "memory:read", "file:read", "sandbox:read"],
        "session:write": ["project:write"],
        "session:delete": ["project:delete"],
        "chat:write": [
            "memory:read",
            "memory:write",
            "memory:delete",
            "memory:export",
            "sandbox:execute",
            "sandbox:manage",
            "envvar:read",
            "envvar:write",
            "envvar:delete",
            "envvar:reveal",
            "file:read",
        ],
    }
    values = list(dict.fromkeys(permissions))
    for permission in values:
        for addition in expanded.get(permission, []):
            if addition not in values:
                values.append(addition)
        if permission.startswith("file:upload") and "file:delete" not in values:
            values.append("file:delete")
    return [value for value in values if value not in RETIRED_PERMISSIONS]


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
                raise AuthorizationError(ErrorCode.UNAUTHENTICATED)

            user_permissions = set(current_user.get("permissions", []))

            for perm in required_permissions:
                if perm not in user_permissions:
                    raise AuthorizationError(
                        ErrorCode.PERMISSION_MISSING, args={"permission": perm}
                    )

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
                "permissions": [p.value for p in Permission if p.value not in RETIRED_PERMISSIONS],
                "unrestricted_models": True,
                "limits": None,  # 无限制
                "is_system": True,
            },
            {
                "name": "user",
                "description": "普通用户 - 可使用聊天、会话、技能、MCP、反馈功能",
                "permissions": [
                    # Chat
                    Permission.CHAT_WRITE.value,
                    # Session
                    Permission.SESSION_READ.value,
                    Permission.SESSION_WRITE.value,
                    Permission.SESSION_DELETE.value,
                    Permission.SESSION_SHARE.value,
                    # Skill
                    Permission.SKILL_READ.value,
                    Permission.SKILL_WRITE.value,
                    Permission.SKILL_DELETE.value,
                    # MCP
                    Permission.MCP_READ.value,
                    Permission.MCP_WRITE_SSE.value,
                    Permission.MCP_WRITE_HTTP.value,
                    Permission.MCP_DELETE.value,
                    # Feedback
                    Permission.FEEDBACK_WRITE.value,
                    # Channel
                    Permission.CHANNEL_READ.value,
                    Permission.CHANNEL_WRITE.value,
                    Permission.CHANNEL_DELETE.value,
                    # Agent
                    Permission.AGENT_READ.value,
                    # Team
                    Permission.TEAM_READ.value,
                    Permission.TEAM_WRITE.value,
                    Permission.TEAM_DELETE.value,
                    # Marketplace
                    Permission.MARKETPLACE_READ.value,
                    Permission.MARKETPLACE_PUBLISH.value,
                    # Persona Preset
                    Permission.PERSONA_PRESET_READ.value,
                    Permission.PERSONA_PRESET_WRITE.value,
                    # Scheduled Task
                    Permission.SCHEDULED_TASK_READ.value,
                    Permission.SCHEDULED_TASK_WRITE.value,
                    Permission.SCHEDULED_TASK_DELETE.value,
                    # Usage
                    Permission.USAGE_READ.value,
                    Permission.PROJECT_READ.value,
                    Permission.PROJECT_WRITE.value,
                    Permission.PROJECT_DELETE.value,
                    Permission.FILE_READ.value,
                    Permission.MEMORY_READ.value,
                    Permission.MEMORY_WRITE.value,
                    Permission.MEMORY_DELETE.value,
                    Permission.MEMORY_EXPORT.value,
                    Permission.SANDBOX_READ.value,
                    Permission.SANDBOX_EXECUTE.value,
                    Permission.SANDBOX_MANAGE.value,
                    Permission.ENVVAR_READ.value,
                    Permission.ENVVAR_WRITE.value,
                    Permission.ENVVAR_DELETE.value,
                    Permission.ENVVAR_REVEAL.value,
                    Permission.PERSONA_PRESET_DELETE.value,
                ],
                "limits": {"max_channels": 10},
                "is_system": False,
            },
            {
                "name": "guest",
                "description": "访客 - 只读访问",
                "permissions": [
                    Permission.SESSION_READ.value,
                    Permission.SKILL_READ.value,
                    Permission.MCP_READ.value,
                    # Channel - read only
                    Permission.CHANNEL_READ.value,
                    # Agent
                    Permission.AGENT_READ.value,
                    # Team
                    Permission.TEAM_READ.value,
                    # Marketplace
                    Permission.MARKETPLACE_READ.value,
                    # Persona Preset
                    Permission.PERSONA_PRESET_READ.value,
                    Permission.PROJECT_READ.value,
                    Permission.MEMORY_READ.value,
                    Permission.FILE_READ.value,
                    Permission.SANDBOX_READ.value,
                ],
                "limits": {"max_channels": 0},  # 不能创建渠道
                "is_system": False,
            },
        ]
