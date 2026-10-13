"""Unavailable authorized MCP servers remain visible without retrying discovery."""

import importlib
import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.agents.team_agent.role_tools import build_role_tool_scope
from src.infra.tool.deferred_manager import DeferredToolManager
from src.infra.tool.tool_search_tool import ToolSearchTool


async def test_failed_mcp_catalog_retains_sanitized_status_and_recovery_clears_it(monkeypatch):
    from src.infra.tool import mcp_client

    failed = True
    attempts = []

    async def load(*args, **kwargs):
        attempts.append(kwargs["server_name"])
        if failed:
            raise RuntimeError("https://private.test Authorization: secret-token")
        return []

    module = types.ModuleType("langchain_mcp_adapters.tools")
    module.load_mcp_tools = load
    monkeypatch.setitem(sys.modules, "langchain_mcp_adapters.tools", module)
    monkeypatch.setattr(mcp_client, "MultiServerMCPClient", lambda configs: object())
    manager = mcp_client.MCPClientManager()
    config = {
        "mcpServers": {"catalog": {"transport": "streamable_http", "url": "https://private.test"}}
    }
    await manager._create_mcp_client(config)
    assert manager.unavailable_server_names == ("catalog",)
    directory = DeferredToolManager(
        [], "s", unavailable_server_names=manager.unavailable_server_names
    )
    search = ToolSearchTool(manager=directory)
    for _ in range(3):
        result = await search._arun("catalog")
        assert "catalog: unavailable" in result
        assert "secret-token" not in result
        assert "private.test" not in result
        assert "Try different keywords" not in result
    assert attempts == ["catalog"]
    failed = False
    await manager._create_mcp_client(config)
    assert manager.unavailable_server_names == ()


@pytest.mark.parametrize("agent_name", ["fast", "search"])
@pytest.mark.parametrize("deferred_enabled", [False, True])
async def test_actual_agent_context_exposes_unavailable_servers_with_empty_catalog(
    monkeypatch, agent_name, deferred_enabled
):
    module = importlib.import_module(f"src.agents.{agent_name}_agent.context")
    context_type = getattr(
        module, "FastAgentContext" if agent_name == "fast" else "SearchAgentContext"
    )
    source = SimpleNamespace(
        unavailable_server_names=("down", "hidden", "outside"), _server_tool_policies={}
    )
    load = AsyncMock(return_value=([], source))
    monkeypatch.setattr(module, "get_global_mcp_tools", load)
    monkeypatch.setattr(module, "get_db_disabled_mcp_tool_names", AsyncMock(return_value=[]))
    monkeypatch.setattr(module.settings, "ENABLE_MCP", True)
    monkeypatch.setattr(module.settings, "ENABLE_DEFERRED_TOOL_LOADING", deferred_enabled)
    context = context_type(
        session_id="s",
        agent_id=agent_name,
        user_id="u",
        disabled_tools=["mcp:hidden"],
        enabled_mcp_servers=["down", "hidden"],
    )
    await context.get_tools()
    await context.get_tools()
    assert context.deferred_manager is not None
    text = context.deferred_manager.get_deferred_stubs_string()
    assert "down: unavailable" in text
    assert "hidden" not in text and "outside" not in text
    load.assert_awaited_once()


async def test_unavailable_catalog_fork_and_persona_scopes_do_not_leak_servers():
    parent = DeferredToolManager(
        [],
        "s",
        unavailable_server_names=("allowed", "hidden", "outside"),
        disabled_tools=["mcp:hidden"],
    )
    assert parent.unavailable_server_names == ("allowed", "outside")
    child = parent.fork_for_scope("child")
    assert child.unavailable_server_names == parent.unavailable_server_names
    _, role = build_role_tool_scope([], parent, mcp_servers=["allowed"], scope="role")
    assert role is not None
    assert role.unavailable_server_names == ("allowed",)
    result = await ToolSearchTool(manager=role)._arun("outside")
    assert "allowed: unavailable" in result
    assert "outside" not in result


async def test_unavailable_reason_does_not_hide_successful_discovery():
    from langchain_core.tools import tool

    @tool
    def available(value: str) -> str:
        """Read an available catalog value."""
        return value

    manager = DeferredToolManager([available], "s", unavailable_server_names=("down",))
    result = await ToolSearchTool(manager=manager)._arun("select:available")
    assert "## available" in result
    assert "down: unavailable" in result
    assert manager.discovered_names == ["available"]
