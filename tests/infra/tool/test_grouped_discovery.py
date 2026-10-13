"""Large discovery directories stay compact without reducing search coverage."""

from types import SimpleNamespace

import pytest

from src.infra.tool.deferred_manager import DeferredToolManager
from src.infra.tool.tool_search_tool import ToolSearchTool


def _tools(count: int) -> list:
    return [
        SimpleNamespace(
            name=f"database:query_{index:03d}",
            description=f"Query relational records in table {index}",
            server="database",
            args_schema={"type": "object", "properties": {"sql": {"type": "string"}}},
        )
        for index in range(count)
    ]


@pytest.mark.parametrize("count", [20, 40, 41, 100, 500])
async def test_tool_directory_groups_only_large_inventories_and_keeps_exact_search(count) -> None:
    tools = _tools(count)
    manager = DeferredToolManager(tools, "session")
    directory = manager.get_deferred_stubs_string()
    if count <= 40:
        assert all(tool.name in directory for tool in tools)
    else:
        assert f"database ({count} tools)" in directory
        assert "Query relational records" in directory
        assert all(tool.name not in directory for tool in tools)
        assert len(directory) < 800
    assert len(manager.get_deferred_stubs()) == count
    search = ToolSearchTool(manager=manager)
    result = await search._arun(f"select:{tools[-1].name}")
    assert f"## {tools[-1].name}\n" in result
    assert '"sql"' in result
    assert manager.discovered_names == [tools[-1].name]
    assert manager.get_deferred_stubs_string() == directory


async def test_grouped_tool_lexical_search_and_disabled_server_never_leak() -> None:
    tools = _tools(100)
    hidden = SimpleNamespace(name="secret:query", description="Query secrets", server="secret")
    manager = DeferredToolManager(
        tools + [hidden], "session", disabled_tools=[tools[0].name, "mcp:secret"]
    )
    directory = manager.get_deferred_stubs_string()
    assert "database (99 tools)" in directory
    assert "secret" not in directory
    search = ToolSearchTool(manager=manager, search_limit=1)
    result = await search._arun("relational records")
    assert "## database:query_" in result
    assert "No tools found" in await search._arun("select:secret:query")
    assert "No tools found" in await search._arun(f"select:{tools[0].name}")


def test_system_business_domains_and_unknown_tools_have_searchable_groups() -> None:
    system = [
        SimpleNamespace(name=f"memory_delete_{index}", description="Delete saved memories")
        for index in range(41)
    ] + [SimpleNamespace(name="odd_operation", description="Unclassified operation")]
    manager = DeferredToolManager([], "session", deferred_system_tools=system)
    directory = manager.get_deferred_stubs_string()
    assert "memory (41 tools)" in directory
    assert "other (1 tools)" in directory
    assert "odd_operation" not in directory
    assert manager.get_tool("odd_operation") is system[-1]


def test_grouped_directory_restart_fork_and_duplicate_names_preserve_isolation() -> None:
    tools = _tools(100)
    parent = DeferredToolManager(tools + [tools[0]], "session")
    directory = parent.get_deferred_stubs_string()
    parent.discover_tools([tools[-1].name, tools[3].name])
    child = parent.fork_for_scope("child")
    child.discover_tools([tools[7].name])
    assert parent.discovered_names == [tools[-1].name, tools[3].name]
    parent.discover_tools([tools[9].name, tools[1].name])
    assert child.discovered_names == [
        tools[-1].name,
        tools[3].name,
        tools[7].name,
        tools[9].name,
        tools[1].name,
    ]
    restored = DeferredToolManager(
        list(reversed(tools)), "session", pre_discovered_names=parent.discovered_names
    )
    assert restored.discovered_names == parent.discovered_names
    assert restored.get_deferred_stubs_string() == directory == child.get_deferred_stubs_string()
    revoked = DeferredToolManager(
        tools,
        "session",
        disabled_tools=[tools[-1].name],
        pre_discovered_names=parent.discovered_names,
    )
    assert tools[-1].name not in revoked.discovered_names
    assert revoked.get_tool(tools[-1].name) is None
