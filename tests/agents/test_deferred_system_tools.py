from __future__ import annotations

from types import SimpleNamespace

import pytest
from langchain_core.tools import BaseTool

from src.agents.fast_agent import context as fast_context
from src.agents.fast_agent.context import FastAgentContext
from src.agents.search_agent import context as search_context
from src.agents.search_agent.context import SearchAgentContext


class _FakeTool(BaseTool):
    name: str
    description: str = ""

    def _run(self, *args, **kwargs):
        return "sync"

    async def _arun(self, *args, **kwargs):
        return "async"


@pytest.fixture
def lean_settings(monkeypatch):
    for module in (fast_context, search_context):
        monkeypatch.setattr(module.settings, "ENABLE_SKILLS", False)
        monkeypatch.setattr(module.settings, "ENABLE_MEMORY", False)
        monkeypatch.setattr(module.settings, "ENABLE_SANDBOX", False)
        monkeypatch.setattr(module.settings, "ENABLE_MCP", False)
        monkeypatch.setattr(module.settings, "ENABLE_DEFERRED_TOOL_LOADING", True)


@pytest.mark.parametrize(
    ("module", "context_type"),
    [(fast_context, FastAgentContext), (search_context, SearchAgentContext)],
)
@pytest.mark.asyncio
async def test_context_defers_system_tools_even_when_mcp_is_disabled(
    monkeypatch,
    lean_settings,
    module,
    context_type,
) -> None:
    inline = _FakeTool(name="inline_system", description="Inline system tool")
    deferred = _FakeTool(name="deferred_system", description="Deferred system tool")

    async def internal_tools(**_kwargs):
        return [inline], [deferred]

    monkeypatch.setattr(module, "get_internal_tools_by_exposure_for_user", internal_tools)
    context = context_type(session_id="session-1")

    await context.setup()
    await context.get_tools()

    assert "inline_system" in {tool.name for tool in context.tools}
    assert "deferred_system" not in {tool.name for tool in context.tools}
    assert context.deferred_manager is not None
    assert context.deferred_manager.get_tool("deferred_system") is deferred


@pytest.mark.asyncio
async def test_compatibility_registration_does_not_reinline_deferred_env_tool(
    monkeypatch,
    lean_settings,
) -> None:
    env_tool = _FakeTool(name="env_var_list", description="List environment variables")

    async def internal_tools(**_kwargs):
        return [], [env_tool]

    monkeypatch.setattr(
        fast_context,
        "get_internal_tools_by_exposure_for_user",
        internal_tools,
    )
    monkeypatch.setattr("src.infra.tool.env_var_tool.get_env_var_tools", lambda: [env_tool])
    context = FastAgentContext(session_id="session-1")

    await context.setup()

    assert "env_var_list" not in {tool.name for tool in context.tools}
    assert context.deferred_manager is not None
    assert context.deferred_manager.get_tool("env_var_list") is env_tool


@pytest.mark.asyncio
async def test_disabling_deferred_loading_inlines_all_authorized_system_tools(
    monkeypatch,
    lean_settings,
) -> None:
    monkeypatch.setattr(fast_context.settings, "ENABLE_DEFERRED_TOOL_LOADING", False)
    inline = _FakeTool(name="inline_system")
    normally_deferred = _FakeTool(name="normally_deferred")

    async def internal_tools(**_kwargs):
        return [inline], [normally_deferred]

    monkeypatch.setattr(
        fast_context,
        "get_internal_tools_by_exposure_for_user",
        internal_tools,
    )
    context = FastAgentContext(session_id="session-1")

    await context.setup()

    assert {"inline_system", "normally_deferred"}.issubset({tool.name for tool in context.tools})
    assert context.deferred_manager is None


@pytest.mark.asyncio
async def test_deferred_system_tools_do_not_force_small_mcp_set_to_defer(
    monkeypatch,
    lean_settings,
) -> None:
    monkeypatch.setattr(fast_context.settings, "ENABLE_MCP", True)
    monkeypatch.setattr(fast_context.settings, "DEFERRED_TOOL_THRESHOLD", 100)
    system = _FakeTool(name="deferred_system")
    mcp = _FakeTool(name="github:create", description="Create issue")
    object.__setattr__(mcp, "server", "github")

    async def internal_tools(**_kwargs):
        return [], [system]

    async def global_tools(_user_id):
        return [mcp], SimpleNamespace(_server_tool_policies={})

    async def no_disabled(_user_id):
        return set()

    monkeypatch.setattr(
        fast_context,
        "get_internal_tools_by_exposure_for_user",
        internal_tools,
    )
    monkeypatch.setattr(fast_context, "get_global_mcp_tools", global_tools)
    monkeypatch.setattr(fast_context, "get_db_disabled_mcp_tool_names", no_disabled)
    context = FastAgentContext(session_id="session-1", user_id="user-1")

    await context.setup()
    await context.get_tools()

    assert "github:create" in {tool.name for tool in context.tools}
    assert context.deferred_manager is not None
    assert context.deferred_manager.get_tool("deferred_system") is system
    assert context.deferred_manager.get_tool("github:create") is None
