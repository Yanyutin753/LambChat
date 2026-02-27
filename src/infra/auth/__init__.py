"""
认证授权模块

提供 JWT 认证、密码处理和 RBAC 权限控制。
"""

from src.infra.auth.jwt import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_token,
)
from src.infra.auth.password import (
    hash_password,
    verify_password,
)
from src.infra.auth.rbac import (
    check_permission,
    get_user_permissions,
    require_permissions,
)

__all__ = [
    # JWT
    "create_access_token",
    "create_refresh_token",
    "decode_token",
    "verify_token",
    # Password
    "hash_password",
    "verify_password",
    # RBAC
    "check_permission",
    "get_user_permissions",
    "require_permissions",
]
