"""Helpers for deciding whether MCP tools are inline or deferred."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from src.kernel.schemas.mcp import MCPToolPolicy

if TYPE_CHECKING:
    from langchain_core.tools import BaseTool


def _server_for_tool(tool: "BaseTool") -> str:
    server = getattr(tool, "server", "")
    if isinstance(server, str) and server:
        return server
    name = getattr(tool, "name", "")
    return name.split(":", 1)[0] if ":" in name else ""


def _raw_name_for_tool(tool: "BaseTool", server_name: str) -> str:
    name = getattr(tool, "name", "")
    if server_name and name.startswith(f"{server_name}:"):
        return name[len(server_name) + 1 :]
    return name


def split_mcp_tools_for_exposure(
    tools: list["BaseTool"],
    policies_by_server: Mapping[str, Mapping[str, MCPToolPolicy]],
) -> tuple[list["BaseTool"], list["BaseTool"]]:
    """Split MCP tools into directly exposed tools and deferred tools."""
    inline_tools: list["BaseTool"] = []
    deferred_tools: list["BaseTool"] = []

    for tool in tools:
        server_name = _server_for_tool(tool)
        raw_name = _raw_name_for_tool(tool, server_name)
        policy = policies_by_server.get(server_name, {}).get(raw_name)
        if policy and policy.inline_exposure:
            inline_tools.append(tool)
        else:
            deferred_tools.append(tool)

    return inline_tools, deferred_tools
