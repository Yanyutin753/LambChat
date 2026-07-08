from __future__ import annotations

import pytest

from src.agents.core.base import AgentFactory
from src.kernel.extensions import (
    PluginRuntime,
    PluginUnavailableError,
    build_agent_team_plugin_manifest,
)
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


@pytest.mark.asyncio
async def test_agent_factory_rechecks_plugin_runtime_before_returning_cached_agent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.agents.core import base as base_module

    class _TeamAgent(_DummyAgent):
        pass

    runtime = PluginRuntime([build_agent_team_plugin_manifest()])
    AgentFactory._instances.clear()
    monkeypatch.setattr(base_module, "_AGENT_REGISTRY", {"team": _TeamAgent})
    base_module.set_plugin_runtime(runtime)

    try:
        agent = await AgentFactory.get("team")
        assert isinstance(agent, _TeamAgent)
        runtime.disable_plugin("agent_team")

        with pytest.raises(PluginUnavailableError):
            await AgentFactory.get("team")
    finally:
        base_module.set_plugin_runtime(None)
        AgentFactory._instances.clear()


class _SearchAgentClass:
    _agent_name = "agents.search.name"
    _description = "agents.search.description"
    _version = "1.0.0"
    _sort_order = 1
    _supports_sandbox = True
    _options = {}


class _FastAgentClass:
    _agent_name = "agents.fast.name"
    _description = "agents.fast.description"
    _version = "1.0.0"
    _sort_order = 2
    _supports_sandbox = False
    _options = {}


class _TeamAgentClass:
    _agent_name = "agents.team.name"
    _description = "agents.team.description"
    _version = "1.0.0"
    _sort_order = 20
    _supports_sandbox = False
    _options = {}


class _CatalogStorage:
    async def get_catalog_config(self) -> list[AgentCatalogConfig]:
        return [
            AgentCatalogConfig(
                id="fast",
                name="agents.fast.name",
                description="agents.fast.description",
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
        {"search": _SearchAgentClass, "fast": _FastAgentClass},
    )
    monkeypatch.setattr(
        "src.infra.agent.config_storage.get_agent_config_storage",
        lambda: _CatalogStorage(),
    )

    agents = await AgentFactory.get_filtered_agents(
        user_roles=[],
        role_agent_map={},
        default_agent_id="fast",
    )

    assert [agent["id"] for agent in agents] == ["fast"]
    assert agents[0]["icon"] == "Zap"
    assert agents[0]["labels"]["zh"]["name"] == "快速助手"


def test_list_agents_includes_effective_plugin_declared_category(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.agents.core import base as base_module

    runtime = PluginRuntime([build_agent_team_plugin_manifest()])
    monkeypatch.setattr(base_module, "_AGENT_REGISTRY", {"team": _TeamAgentClass})
    base_module.set_plugin_runtime(runtime)

    try:
        agents = AgentFactory.list_agents()
        assert len(agents) == 1
        assert agents[0]["id"] == "team"
        assert agents[0]["category"] == "agent_team:team-builder"

        runtime.disable_plugin("agent_team")
        assert AgentFactory.list_agents() == []
    finally:
        base_module.set_plugin_runtime(None)


def test_list_agents_hides_builtin_plugin_owned_agents_when_runtime_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.agents.core import base as base_module

    monkeypatch.setattr(
        base_module,
        "_AGENT_REGISTRY",
        {
            "search": _SearchAgentClass,
            "team": _TeamAgentClass,
        },
    )
    base_module.set_plugin_runtime(None)

    agents = AgentFactory.list_agents()

    assert [agent["id"] for agent in agents] == ["search"]
    assert agents[0]["category"] is None


@pytest.mark.asyncio
async def test_agent_factory_rejects_builtin_plugin_owned_agent_when_runtime_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.agents.core import base as base_module

    AgentFactory._instances.clear()
    monkeypatch.setattr(base_module, "_AGENT_REGISTRY", {"team": _TeamAgentClass})
    base_module.set_plugin_runtime(None)

    try:
        with pytest.raises(PluginUnavailableError, match="Plugin Runtime is unavailable"):
            await AgentFactory.get("team")
    finally:
        AgentFactory._instances.clear()
