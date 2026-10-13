"""Apply persona tool bindings to both direct and deferred discovery."""

from typing import Any

from src.agents.core.tool_filter import filter_mcp_tools_by_server_whitelist
from src.infra.tool.deferred_manager import DeferredToolManager

_ROLE_EXCLUDED_TOOLS = {
    "search_tools",
    "search_skills",
    "search_persona_presets",
    "create_agent_team",
    "save_persona_preset",
}


def build_role_tool_scope(
    tools: list[Any],
    deferred_manager: DeferredToolManager | None,
    *,
    mcp_servers: list[str],
    scope: str,
) -> tuple[list[Any], DeferredToolManager | None]:
    direct = filter_mcp_tools_by_server_whitelist(
        [tool for tool in tools if tool.name not in _ROLE_EXCLUDED_TOOLS], mcp_servers
    )
    if deferred_manager is None:
        return direct, None
    stubs = deferred_manager.get_deferred_stubs()
    mcp = [
        tool
        for stub in stubs
        if stub.kind == "mcp" and (tool := deferred_manager.get_tool(stub.name)) is not None
    ]
    system = [
        tool
        for stub in stubs
        if stub.kind == "system"
        and stub.name not in _ROLE_EXCLUDED_TOOLS
        and (tool := deferred_manager.get_tool(stub.name)) is not None
    ]
    return direct, DeferredToolManager(
        all_deferred_tools=filter_mcp_tools_by_server_whitelist(mcp, mcp_servers),
        deferred_system_tools=system,
        session_id=scope,
        pre_discovered_names=deferred_manager.discovered_names,
        unavailable_server_names=tuple(
            name
            for name in deferred_manager.unavailable_server_names
            if not mcp_servers or name in mcp_servers
        ),
    )
