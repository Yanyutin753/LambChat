from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from src.api import deps


def _role(name: str, permissions: list[str]) -> SimpleNamespace:
    return SimpleNamespace(id=f"id-{name}", name=name, permissions=permissions)


@pytest.mark.asyncio
async def test_role_lookups_run_concurrently(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[str] = []
    all_started = asyncio.Event()

    class _RoleStorage:
        async def get_by_name(self, name: str) -> SimpleNamespace | None:
            started.append(name)
            if len(started) == 2:
                all_started.set()
            # 串行实现下第二个查询永远等不到第一个完成，超时即失败
            await asyncio.wait_for(all_started.wait(), timeout=1.0)
            return _role(name, [f"{name}:read"]) if name != "ghost" else None

    monkeypatch.setattr(deps, "RoleStorage", _RoleStorage)
    deps.clear_auth_cache()

    roles, permissions = await deps._get_user_roles_and_permissions(["admin", "user"])

    assert roles == ["admin", "user"]
    assert set(permissions) == {"admin:read", "user:read"}


@pytest.mark.asyncio
async def test_missing_roles_are_skipped_and_merge_order_kept(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _RoleStorage:
        async def get_by_name(self, name: str) -> SimpleNamespace | None:
            if name == "ghost":
                return None
            return _role(name, [f"{name}:read", "shared:perm"])

    monkeypatch.setattr(deps, "RoleStorage", _RoleStorage)
    deps.clear_auth_cache()

    roles, permissions = await deps._get_user_roles_and_permissions(
        ["ghost", "admin", "user", "ghost"]
    )

    assert roles == ["admin", "user"]
    assert set(permissions) == {"admin:read", "user:read", "shared:perm"}


@pytest.mark.asyncio
async def test_no_process_level_role_cache_keeps_permission_changes_immediate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """角色查询不加进程内 TTL 缓存：每次请求都走 RoleStorage（其自身有全局失效缓存），
    保证角色权限变更（Redis 失效广播）即时生效。"""
    calls: list[str] = []

    class _RoleStorage:
        async def get_by_name(self, name: str) -> SimpleNamespace | None:
            calls.append(name)
            return _role(name, [f"{name}:read"])

    monkeypatch.setattr(deps, "RoleStorage", _RoleStorage)

    await deps._get_user_roles_and_permissions(["admin", "user"])
    await deps._get_user_roles_and_permissions(["admin", "user"])

    # 每次请求都查库，无进程级缓存窗口
    assert sorted(calls) == ["admin", "admin", "user", "user"]
