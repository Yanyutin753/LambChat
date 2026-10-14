from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.infra.agent import model_access
from src.kernel.schemas.user import TokenPayload


def _role(name: str) -> SimpleNamespace:
    return SimpleNamespace(id=f"id-{name}", name=name, permissions=[])


class _RoleManager:
    def __init__(self, roles: dict[str, SimpleNamespace | None]) -> None:
        self._roles = roles
        self.calls: list[list[str]] = []

    async def get_roles_by_names(self, names):
        self.calls.append(names)
        return [self._roles[name] for name in names if self._roles.get(name) is not None]


class _Storage:
    def __init__(self, models_by_role: dict[str, list[str] | None]) -> None:
        self._models = models_by_role
        self.calls: list[list[str]] = []

    async def get_role_models_by_ids(self, role_ids):
        self.calls.append(role_ids)
        return {role_id: self._models.get(role_id) for role_id in role_ids}


@pytest.mark.asyncio
async def test_role_and_model_reads_are_batched(monkeypatch):
    roles = _RoleManager({"admin": _role("admin"), "user": _role("user")})
    storage = _Storage({"id-admin": ["m"], "id-user": ["m"]})
    monkeypatch.setattr("src.infra.agent.config_storage.get_agent_config_storage", lambda: storage)
    monkeypatch.setattr("src.infra.role.manager.get_role_manager", lambda: roles)
    result = await model_access.resolve_user_allowed_model_ids(
        TokenPayload(sub="u", username="u", roles=["admin", "user"])
    )
    assert result == ["m"]
    assert roles.calls == [["admin", "user"]]
    assert storage.calls == [["id-admin", "id-user"]]


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
