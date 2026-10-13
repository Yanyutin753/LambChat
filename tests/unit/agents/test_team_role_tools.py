from types import SimpleNamespace

from src.agents.team_agent.role_tools import build_role_tool_scope
from src.infra.tool.deferred_manager import DeferredToolManager


def test_role_mcp_whitelist_applies_to_direct_and_deferred_tools():
    a = SimpleNamespace(name="a:read", server="a", description="Read A")
    b = SimpleNamespace(name="b:read", server="b", description="Read B")
    save = SimpleNamespace(name="save_persona_preset", description="Save role")
    parent_search = SimpleNamespace(name="search_tools", description="Search all tools")
    manager = DeferredToolManager(
        all_deferred_tools=[a, b], deferred_system_tools=[save], session_id="s"
    )
    tools, scoped = build_role_tool_scope(
        [a, b, save, parent_search], manager, mcp_servers=["a"], scope="s:role:p1"
    )
    assert tools == [a]
    assert scoped.get_tool("a:read") is a
    assert scoped.get_tool("b:read") is None
    assert scoped.get_tool("save_persona_preset") is None
    assert manager.get_tool("b:read") is b


def test_empty_role_mcp_whitelist_preserves_existing_inheritance():
    a = SimpleNamespace(name="a:read", server="a", description="Read A")
    tools, scoped = build_role_tool_scope([a], None, mcp_servers=[], scope="s:role:p1")
    assert tools == [a]
    assert scoped is None
