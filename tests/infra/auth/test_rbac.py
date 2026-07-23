"""RBAC 权限校验测试。

覆盖：权限检查、require_permissions 装饰器（通过/拒绝/未认证/多权限）、
RBACManager（权限校验、默认角色层级）。
"""

import pytest

from src.infra.auth.rbac import (
    RBACManager,
    check_permission,
    require_permissions,
)
from src.kernel.exceptions import AuthorizationError
from src.kernel.types import Permission


class TestCheckPermission:
    def test_has_permission(self):
        perm = Permission.CHAT_READ.value
        assert check_permission([perm, "other"], perm) is True

    def test_missing_permission(self):
        assert check_permission([Permission.CHAT_READ.value], Permission.CHAT_WRITE.value) is False

    def test_empty_permissions(self):
        assert check_permission([], Permission.CHAT_READ.value) is False


class TestRequirePermissionsDecorator:
    @pytest.mark.asyncio
    async def test_allows_when_user_has_permission(self):
        perm = Permission.CHAT_READ.value

        @require_permissions(perm)
        async def view(current_user):
            return "ok"

        assert await view(current_user={"permissions": [perm]}) == "ok"

    @pytest.mark.asyncio
    async def test_denies_when_permission_missing(self):
        @require_permissions(Permission.CHAT_WRITE.value)
        async def write(current_user):
            return "ok"

        with pytest.raises(AuthorizationError, match=Permission.CHAT_WRITE.value):
            await write(current_user={"permissions": [Permission.CHAT_READ.value]})

    @pytest.mark.asyncio
    async def test_denies_when_no_current_user(self):
        @require_permissions(Permission.CHAT_READ.value)
        async def view(current_user=None):
            return "ok"

        with pytest.raises(AuthorizationError, match="未认证"):
            await view()

    @pytest.mark.asyncio
    async def test_requires_all_listed_permissions(self):
        @require_permissions(Permission.CHAT_READ.value, Permission.CHAT_WRITE.value)
        async def view(current_user):
            return "ok"

        with pytest.raises(AuthorizationError):
            await view(current_user={"permissions": [Permission.CHAT_READ.value]})


class TestRBACManager:
    def test_validate_permission_valid(self):
        manager = RBACManager()
        assert manager.validate_permission(Permission.CHAT_READ.value) is True

    def test_validate_permission_invalid(self):
        manager = RBACManager()
        assert manager.validate_permission("nonexistent:perm") is False

    def test_default_roles_hierarchy(self):
        manager = RBACManager()
        roles = {r["name"]: r for r in manager.get_default_roles()}
        assert {"admin", "user", "guest"} <= set(roles)
        # admin 拥有全部权限
        assert len(roles["admin"]["permissions"]) == len(list(Permission))
        # guest 权限是 user 的子集（只读 ⊂ 读写）
        assert set(roles["guest"]["permissions"]).issubset(set(roles["user"]["permissions"]))
