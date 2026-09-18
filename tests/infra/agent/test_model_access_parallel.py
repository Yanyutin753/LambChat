from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

from src.infra.agent import model_access
from src.kernel.schemas.user import TokenPayload


def _role(name: str) -> SimpleNamespace:
    return SimpleNamespace(id=f"id-{name}", name=name, permissions=[])


class _RoleManager:
    def __init__(self, roles: dict[str, SimpleNamespace | None]) -> None:
        self._roles = roles
        self.calls: list[str] = []

    async def get_role_by_name(self, name: str) -> SimpleNamespace | None:
        self.calls.append(name)
        return self._roles.get(name)


class _Storage:
    def __init__(self, models_by_role: dict[str, list[str] | None]) -> None:
        self._models = models_by_role
        self.calls: list[str] = []

    async def get_role_models(self, role_id: str) -> list[str] | None:
        self.calls.append(role_id)
        return self._models.get(role_id)


@pytest.mark.asyncio
async def test_role_lookups_run_concurrently(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[str] = []
    all_started = asyncio.Event()

    class _SlowRoleManager(_RoleManager):
        async def get_role_by_name(self, name: str) -> SimpleNamespace | None:
            started.append(name)
            if len(started) == 2:
                all_started.set()
            await asyncio.wait_for(all_started.wait(), timeout=1.0)
            return _role(name)

    monkeypatch.setattr(
        "src.infra.agent.config_storage.get_agent_config_storage", lambda: _Storage({})
    )
    import src.infra.role.manager as role_manager_module

    monkeypatch.setattr(role_manager_module, "get_role_manager", lambda: _SlowRoleManager({}))

    result = await model_access.resolve_user_allowed_model_ids(
        TokenPayload(sub="u", username="u", roles=["admin", "user"])
    )

    assert result is None  # 无任何角色-模型配置 → 不受限


@pytest.mark.asyncio
async def test_role_model_lookups_run_concurrently(monkeypatch: pytest.MonkeyPatch) -> None:
    started: list[str] = []
    all_started = asyncio.Event()

    class _SlowStorage(_Storage):
        async def get_role_models(self, role_id: str) -> list[str] | None:
            started.append(role_id)
            if len(started) == 2:
                all_started.set()
            await asyncio.wait_for(all_started.wait(), timeout=1.0)
            return ["m"]

    monkeypatch.setattr(
        "src.infra.agent.config_storage.get_agent_config_storage", lambda: _SlowStorage({})
    )
    import src.infra.role.manager as role_manager_module

    monkeypatch.setattr(
        role_manager_module,
        "get_role_manager",
        lambda: _RoleManager(
            {
                "admin": _role("admin"),
                "user": _role("user"),
            }
        ),
    )

    result = await model_access.resolve_user_allowed_model_ids(
        TokenPayload(sub="u", username="u", roles=["admin", "user"])
    )

    assert result == ["m"]


@pytest.mark.asyncio
async def test_merge_order_and_dedup_preserved(monkeypatch: pytest.MonkeyPatch) -> None:
    storage = _Storage(
        {
            "id-admin": ["m2", "m1", "m2"],
            "id-user": ["m1", "m3"],
        }
    )
    monkeypatch.setattr("src.infra.agent.config_storage.get_agent_config_storage", lambda: storage)
    import src.infra.role.manager as role_manager_module

    monkeypatch.setattr(
        role_manager_module,
        "get_role_manager",
        lambda: _RoleManager({"admin": _role("admin"), "user": _role("user")}),
    )

    result = await model_access.resolve_user_allowed_model_ids(
        TokenPayload(sub="u", username="u", roles=["admin", "user"])
    )

    assert result == ["m2", "m1", "m3"]


@pytest.mark.asyncio
async def test_unconfigured_role_means_unrestricted(monkeypatch: pytest.MonkeyPatch) -> None:
    storage = _Storage({"id-admin": None})
    monkeypatch.setattr("src.infra.agent.config_storage.get_agent_config_storage", lambda: storage)
    import src.infra.role.manager as role_manager_module

    monkeypatch.setattr(
        role_manager_module,
        "get_role_manager",
        lambda: _RoleManager({"admin": _role("admin"), "user": None}),
    )

    result = await model_access.resolve_user_allowed_model_ids(
        TokenPayload(sub="u", username="u", roles=["admin", "user"])
    )

    assert result is None


@pytest.mark.asyncio
async def test_limit_truncation_after_dedup(monkeypatch: pytest.MonkeyPatch) -> None:
    total = model_access.ROLE_MODEL_ACCESS_LIMIT + 5
    storage = _Storage(
        {
            "id-admin": [f"m{i}" for i in range(total)],
        }
    )
    monkeypatch.setattr("src.infra.agent.config_storage.get_agent_config_storage", lambda: storage)
    import src.infra.role.manager as role_manager_module

    monkeypatch.setattr(
        role_manager_module,
        "get_role_manager",
        lambda: _RoleManager({"admin": _role("admin")}),
    )

    result = await model_access.resolve_user_allowed_model_ids(
        TokenPayload(sub="u", username="u", roles=["admin"])
    )

    assert result == [f"m{i}" for i in range(model_access.ROLE_MODEL_ACCESS_LIMIT)]
