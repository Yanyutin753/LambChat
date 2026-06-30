from __future__ import annotations

import pytest

from src.api.routes.agent import config as config_routes
from src.kernel.schemas.agent import (
    AgentCatalogConfig,
    AgentCatalogConfigUpdate,
    AgentCatalogLocale,
    AgentConfig,
    RoleAgentAssignmentUpdate,
    RoleModelAssignmentUpdate,
)
from src.kernel.schemas.user import TokenPayload


class _CatalogStorage:
    def __init__(
        self,
        catalog: list[AgentCatalogConfig] | None = None,
        legacy_global: list[AgentConfig] | None = None,
    ) -> None:
        self.catalog = catalog or []
        self.legacy_global = legacy_global or []
        self.saved: list[AgentCatalogConfig] | None = None
        self.prune_missing: bool | None = None

    async def get_catalog_config(self) -> list[AgentCatalogConfig]:
        return self.catalog

    async def get_global_config(self) -> list[AgentConfig]:
        return self.legacy_global

    async def set_catalog_config(
        self,
        agents: list[AgentCatalogConfig],
        *,
        prune_missing: bool = True,
    ) -> list[AgentCatalogConfig]:
        self.saved = agents
        self.prune_missing = prune_missing
        self.catalog = agents
        return agents


class _RoleAssignmentStorage:
    def __init__(self, role_agents: list[str] | None = None) -> None:
        self.role_agents = role_agents or []
        self.agent_calls: list[list[str]] = []
        self.model_calls: list[list[str]] = []

    async def get_role_agents(self, role_id: str) -> list[str]:
        return self.role_agents

    async def set_role_agents(
        self,
        role_id: str,
        role_name: str,
        allowed_agents: list[str],
    ) -> list[str]:
        self.agent_calls.append(allowed_agents)
        return allowed_agents[:2]

    async def set_role_models(
        self,
        role_id: str,
        role_name: str,
        allowed_models: list[str],
    ) -> list[str]:
        self.model_calls.append(allowed_models)
        return allowed_models[:2]


class _RoleManager:
    async def get_role(self, role_id: str):
        return type("Role", (), {"id": role_id, "name": "Role"})()


def _admin() -> TokenPayload:
    return TokenPayload(sub="admin-1", username="admin", roles=["admin"])


def _registered_agents() -> list[dict]:
    return [
        {
            "id": "search",
            "name": "agents.search.name",
            "description": "agents.search.description",
            "version": "1.0.0",
            "sort_order": 1,
            "supports_sandbox": True,
            "options": {},
        },
        {
            "id": "fast",
            "name": "agents.fast.name",
            "description": "agents.fast.description",
            "version": "1.0.0",
            "sort_order": 2,
            "supports_sandbox": False,
            "options": {},
        },
    ]


def _registered_agents_with_team() -> list[dict]:
    return [
        *_registered_agents(),
        {
            "id": "team",
            "name": "agents.team.name",
            "description": "agents.team.description",
            "version": "1.0.0",
            "sort_order": 20,
            "category": "agent_team:team-builder",
            "supports_sandbox": False,
            "options": {},
        },
    ]


@pytest.mark.asyncio
async def test_get_catalog_config_seeds_registered_agents_in_dedicated_catalog(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _CatalogStorage()
    monkeypatch.setattr(config_routes, "get_agent_config_storage", lambda: storage)
    monkeypatch.setattr(config_routes.AgentFactory, "list_agents", _registered_agents)

    response = await config_routes.get_agent_catalog_config(_admin())

    assert storage.saved is not None
    assert [agent.id for agent in response.agents] == ["search", "fast"]
    assert response.agents[0].name == "agents.search.name"
    assert response.agents[0].description == "agents.search.description"
    assert response.agents[0].icon == "Bot"
    assert response.agents[0].sort_order == 1
    assert response.agents[0].labels == {}
    assert storage.prune_missing is False


@pytest.mark.asyncio
async def test_get_catalog_config_exposes_plugin_declared_agent_category(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _CatalogStorage()
    monkeypatch.setattr(config_routes, "get_agent_config_storage", lambda: storage)
    monkeypatch.setattr(config_routes.AgentFactory, "list_agents", _registered_agents_with_team)

    response = await config_routes.get_agent_catalog_config(_admin())

    team = next(agent for agent in response.agents if agent.id == "team")
    assert team.category == "agent_team:team-builder"
    assert storage.saved is not None
    saved_team = next(agent for agent in storage.saved if agent.id == "team")
    assert saved_team.category == "agent_team:team-builder"


@pytest.mark.asyncio
async def test_get_catalog_config_hides_disabled_plugin_agents_without_pruning_saved_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _CatalogStorage(
        catalog=[
            AgentCatalogConfig(
                id="team",
                name="agents.team.name",
                description="agents.team.description",
                enabled=True,
            )
        ]
    )
    monkeypatch.setattr(config_routes, "get_agent_config_storage", lambda: storage)
    monkeypatch.setattr(config_routes.AgentFactory, "list_agents", _registered_agents)

    response = await config_routes.get_agent_catalog_config(_admin())

    assert [agent.id for agent in response.agents] == ["search", "fast"]
    assert "team" not in response.available_agents
    assert storage.prune_missing is False


@pytest.mark.asyncio
async def test_get_catalog_config_migrates_legacy_global_enabled_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _CatalogStorage(
        legacy_global=[
            AgentConfig(
                id="search",
                name="agents.search.name",
                description="agents.search.description",
                enabled=False,
            )
        ]
    )
    monkeypatch.setattr(config_routes, "get_agent_config_storage", lambda: storage)
    monkeypatch.setattr(config_routes.AgentFactory, "list_agents", _registered_agents)

    response = await config_routes.get_agent_catalog_config(_admin())

    search = next(agent for agent in response.agents if agent.id == "search")
    assert search.enabled is False
    assert response.available_agents == ["fast"]


@pytest.mark.asyncio
async def test_update_catalog_config_persists_multilingual_display_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _CatalogStorage()
    monkeypatch.setattr(config_routes, "get_agent_config_storage", lambda: storage)
    monkeypatch.setattr(config_routes.AgentFactory, "list_agents", _registered_agents)

    update = AgentCatalogConfigUpdate(
        agents=[
            AgentCatalogConfig(
                id="search",
                name="agents.search.name",
                description="agents.search.description",
                enabled=True,
                icon="Search",
                sort_order=10,
                labels={
                    "zh": AgentCatalogLocale(
                        name="搜索助手",
                        description="面向检索和复杂任务",
                    ),
                    "en": AgentCatalogLocale(
                        name="Research Agent",
                        description="For research and complex tasks",
                    ),
                },
            )
        ]
    )

    response = await config_routes.update_agent_catalog_config(update, _admin())

    assert storage.saved is not None
    assert storage.saved[0].labels["zh"].name == "搜索助手"
    assert response.agents[0].icon == "Search"
    assert response.available_agents == ["search"]


@pytest.mark.asyncio
async def test_update_catalog_config_rejects_plugin_agent_hidden_by_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _CatalogStorage()
    monkeypatch.setattr(config_routes, "get_agent_config_storage", lambda: storage)
    monkeypatch.setattr(config_routes.AgentFactory, "list_agents", _registered_agents)

    with pytest.raises(Exception, match="team"):
        await config_routes.update_agent_catalog_config(
            AgentCatalogConfigUpdate(
                agents=[
                    AgentCatalogConfig(
                        id="team",
                        name="agents.team.name",
                        description="agents.team.description",
                        enabled=True,
                    )
                ]
            ),
            _admin(),
        )

    assert storage.saved is None


@pytest.mark.asyncio
async def test_update_role_agents_returns_bounded_storage_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _RoleAssignmentStorage()
    monkeypatch.setattr(config_routes, "get_agent_config_storage", lambda: storage)
    monkeypatch.setattr(config_routes, "get_role_manager", lambda: _RoleManager())
    monkeypatch.setattr(
        config_routes.AgentFactory,
        "list_agents",
        lambda: [
            {"id": "agent-1"},
            {"id": "agent-2"},
            {"id": "agent-3"},
        ],
    )

    response = await config_routes.update_role_agents(
        "role-1",
        RoleAgentAssignmentUpdate(allowed_agents=["agent-1", "agent-2", "agent-3"]),
        _admin(),
    )

    assert storage.agent_calls == [["agent-1", "agent-2", "agent-3"]]
    assert response.allowed_agents == ["agent-1", "agent-2"]


@pytest.mark.asyncio
async def test_get_role_agents_hides_plugin_agents_hidden_by_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _RoleAssignmentStorage(role_agents=["search", "team", "fast"])
    monkeypatch.setattr(config_routes, "get_agent_config_storage", lambda: storage)
    monkeypatch.setattr(config_routes, "get_role_manager", lambda: _RoleManager())
    monkeypatch.setattr(config_routes.AgentFactory, "list_agents", _registered_agents)

    response = await config_routes.get_role_agents("role-1", _admin())

    assert response.allowed_agents == ["search", "fast"]
    assert storage.role_agents == ["search", "team", "fast"]


@pytest.mark.asyncio
async def test_update_role_agents_rejects_plugin_agent_hidden_by_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _RoleAssignmentStorage()
    monkeypatch.setattr(config_routes, "get_agent_config_storage", lambda: storage)
    monkeypatch.setattr(config_routes, "get_role_manager", lambda: _RoleManager())
    monkeypatch.setattr(config_routes.AgentFactory, "list_agents", _registered_agents)

    with pytest.raises(Exception, match="team"):
        await config_routes.update_role_agents(
            "role-1",
            RoleAgentAssignmentUpdate(allowed_agents=["search", "team"]),
            _admin(),
        )

    assert storage.agent_calls == []


@pytest.mark.asyncio
async def test_update_role_models_returns_bounded_storage_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    storage = _RoleAssignmentStorage()
    monkeypatch.setattr(config_routes, "get_agent_config_storage", lambda: storage)
    monkeypatch.setattr(config_routes, "get_role_manager", lambda: _RoleManager())

    response = await config_routes.update_role_models(
        "role-1",
        RoleModelAssignmentUpdate(allowed_models=["model-1", "model-2", "model-3"]),
        _admin(),
    )

    assert storage.model_calls == [["model-1", "model-2", "model-3"]]
    assert response.allowed_models == ["model-1", "model-2"]
