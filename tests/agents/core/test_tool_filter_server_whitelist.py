from __future__ import annotations

from types import SimpleNamespace

from src.agents.core.tool_filter import filter_mcp_tools_by_server_whitelist


def _tool(name: str, server: str | None = None) -> SimpleNamespace:
    ns = SimpleNamespace()
    ns.name = name
    if server is not None:
        ns.server = server
    return ns


def test_whitelist_keeps_only_attributed_servers() -> None:
    tools = [
        _tool("arxiv:search", "arxiv"),
        _tool("weather:lookup", "weather"),
        _tool("builtin_tool"),
    ]
    filtered = filter_mcp_tools_by_server_whitelist(tools, ["arxiv"])
    assert [t.name for t in filtered] == ["arxiv:search", "builtin_tool"]


def test_whitelist_matches_name_prefix_without_server_attr() -> None:
    tools = [_tool("arxiv:search"), _tool("weather:lookup")]
    filtered = filter_mcp_tools_by_server_whitelist(tools, ["weather"])
    assert [t.name for t in filtered] == ["weather:lookup"]


def test_empty_whitelist_is_noop() -> None:
    tools = [_tool("arxiv:search", "arxiv")]
    assert filter_mcp_tools_by_server_whitelist(tools, None) == tools
    assert filter_mcp_tools_by_server_whitelist(tools, []) == tools
