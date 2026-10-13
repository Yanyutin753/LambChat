"""Helpers for deciding whether MCP tools are inline or deferred."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

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


def attach_mcp_availability(context: Any) -> None:
    """Share the authorized cached connection snapshot across all agent modes."""
    from src.infra.tool.deferred_manager import DeferredToolManager

    names = getattr(context.mcp_manager, "unavailable_server_names", ())
    if context.enabled_mcp_servers:
        allowed = set(context.enabled_mcp_servers)
        names = tuple(name for name in names if name in allowed)
    if not names:
        return
    if context.deferred_manager is None:
        context.deferred_manager = DeferredToolManager(
            [],
            context.session_id,
            disabled_tools=context.disabled_tools,
            disabled_mcp_tools=context.disabled_mcp_tools,
        )
    context.deferred_manager.set_unavailable_servers(names)
