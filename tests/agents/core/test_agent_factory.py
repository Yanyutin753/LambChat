from __future__ import annotations

import pytest

from src.agents.core.base import AgentFactory
from src.kernel.schemas.agent import AgentCatalogConfig, AgentCatalogLocale


class _DummyAgent:
    def __init__(self) -> None:
        self.initialized = False

    async def initialize(self) -> None:
        self.initialized = True


@pytest.mark.asyncio
async def test_agent_factory_get_discovers_agents_when_registry_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.agents.core import base as base_module

    AgentFactory._instances.clear()
    monkeypatch.setattr(base_module, "_AGENT_REGISTRY", {})

    def _fake_discover_agents() -> None:
        base_module._AGENT_REGISTRY["dummy"] = _DummyAgent

    monkeypatch.setattr("src.agents.discover_agents", _fake_discover_agents)

    agent = await AgentFactory.get("dummy")

    assert isinstance(agent, _DummyAgent)
    assert agent.initialized is True


class _SearchAgentClass:
    _agent_name = "agents.search.name"
    _description = "agents.search.description"
    _version = "1.0.0"
    _sort_order = 1
    _supports_sandbox = True
    _options = {}


class _QuickAgentClass:
    _agent_name = "agents.quick.name"
    _description = "agents.quick.description"
    _version = "1.0.0"
    _sort_order = 2
    _supports_sandbox = False
    _options = {}


class _CatalogStorage:
    async def get_catalog_config(self) -> list[AgentCatalogConfig]:
        return [
            AgentCatalogConfig(
                id="quick",
                name="agents.quick.name",
                description="agents.quick.description",
                enabled=True,
                icon="Zap",
                sort_order=5,
                labels={
                    "zh": AgentCatalogLocale(
                        name="快速助手",
                        description="日常对话",
                    )
                },
            ),
            AgentCatalogConfig(
                id="search",
                name="agents.search.name",
                description="agents.search.description",
                enabled=False,
                icon="Search",
                sort_order=10,
                labels={},
            ),
        ]

    async def get_global_config(self) -> list:
        raise AssertionError("catalog config should replace legacy global config")


@pytest.mark.asyncio
async def test_filtered_agents_use_catalog_enabled_state_and_display_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.agents.core import base as base_module

    monkeypatch.setattr(
        base_module,
        "_AGENT_REGISTRY",
        {"search": _SearchAgentClass, "quick": _QuickAgentClass},
    )
    monkeypatch.setattr(
        "src.infra.agent.config_storage.get_agent_config_storage",
        lambda: _CatalogStorage(),
    )

    agents = await AgentFactory.get_filtered_agents(
        user_roles=[],
        role_agent_map={},
        default_agent_id="quick",
    )

    assert [agent["id"] for agent in agents] == ["quick"]
    assert agents[0]["icon"] == "Zap"
    assert agents[0]["labels"]["zh"]["name"] == "快速助手"


@pytest.mark.asyncio
async def test_legacy_fast_uses_the_search_instance(monkeypatch):
    from src.agents.core import base as base_module

    monkeypatch.setattr(base_module, "_AGENT_REGISTRY", {"search": _DummyAgent})
    monkeypatch.setattr(AgentFactory, "_instances", {})
    legacy = await AgentFactory.get("fast")
    search = await AgentFactory.get("search")
    assert legacy is search
    assert legacy.initialized
    assert base_module.get_agent_class("fast") is _DummyAgent


def test_discovery_exposes_search_quick_and_team_only():
    from src.agents import discover_agents
    from src.agents.core import base as base_module

    discover_agents()
    assert set(base_module._AGENT_REGISTRY) == {"search", "quick", "team"}


@pytest.mark.asyncio
async def test_legacy_fast_catalog_and_role_allow_search(monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from src.agents.core import base as base_module

    monkeypatch.setattr(base_module, "_AGENT_REGISTRY", {"search": _SearchAgentClass})
    storage = SimpleNamespace(
        get_catalog_config=AsyncMock(
            return_value=[
                AgentCatalogConfig(id="fast", name="Fast", description="Legacy", enabled=True),
            ]
        )
    )
    monkeypatch.setattr("src.infra.agent.config_storage.get_agent_config_storage", lambda: storage)
    agents = await AgentFactory.get_filtered_agents(
        user_roles=["member"],
        role_agent_map={"member": ["fast"]},
        default_agent_id="fast",
    )
    assert [agent["id"] for agent in agents] == ["search"]
    assert agents[0]["name"] == "agents.search.name"


@pytest.mark.asyncio
async def test_disabled_search_is_not_enabled_by_legacy_fast_catalog(monkeypatch):
    from src.agents.core import base as base_module

    monkeypatch.setattr(base_module, "_AGENT_REGISTRY", {"search": _SearchAgentClass})

    class Storage(_CatalogStorage):
        async def get_catalog_config(self):
            configs = await super().get_catalog_config()
            return [
                *configs,
                AgentCatalogConfig(id="fast", name="Fast", description="Legacy", enabled=True),
            ]

    monkeypatch.setattr(
        "src.infra.agent.config_storage.get_agent_config_storage", lambda: Storage()
    )
    assert await AgentFactory.get_filtered_agents(user_roles=[], role_agent_map={}) == []


def test_legacy_fast_recovery_keeps_search_even_if_default_is_quick(monkeypatch):
    from types import SimpleNamespace

    from src.infra.task import recovery

    monkeypatch.setattr(recovery, "_registered_agent_ids", lambda: {"search", "quick", "team"})
    monkeypatch.setattr(recovery.settings, "DEFAULT_AGENT", "quick")
    assert recovery._resolve_recovery_agent_id({"agent_id": "fast"}, SimpleNamespace()) == "search"
