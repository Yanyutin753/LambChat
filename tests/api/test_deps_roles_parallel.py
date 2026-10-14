from types import SimpleNamespace

import pytest

from src.api import deps


@pytest.mark.parametrize("names", [["admin", "user"], ["ghost", "admin", "user", "admin"]])
async def test_authority_batches_roles_preserving_order_duplicates_and_permissions(
    monkeypatch, names
):
    calls = []

    class Manager:
        async def get_roles_by_names(self, role_names):
            calls.append(role_names)
            return [
                SimpleNamespace(name=name, permissions=[f"{name}:read", "shared:perm"])
                for name in role_names
                if name != "ghost"
            ]

    monkeypatch.setattr(deps, "RoleManager", Manager)
    roles, permissions = await deps._get_user_roles_and_permissions(names)
    assert roles == [name for name in names if name != "ghost"]
    assert set(permissions) == {"admin:read", "user:read", "shared:perm"}
    assert calls == [names]


async def test_authority_does_not_cache_role_permissions_in_process(monkeypatch):
    permissions = ["old:read"]

    class Manager:
        async def get_roles_by_names(self, names):
            return [SimpleNamespace(name=name, permissions=list(permissions)) for name in names]

    monkeypatch.setattr(deps, "RoleManager", Manager)
    assert await deps._get_user_roles_and_permissions(["user"]) == (["user"], ["old:read"])
    permissions[:] = ["new:read"]
    assert await deps._get_user_roles_and_permissions(["user"]) == (["user"], ["new:read"])
