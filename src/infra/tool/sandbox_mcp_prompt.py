"""Sandbox MCP Prompt Builder - Injects sandbox MCP tool descriptions into system prompt.

Caches mcporter list output per-user to maximize KV cache hit rate.
The prompt section is appended at the END of the system prompt so that
changes only invalidate the tail of the KV cache, not the stable prefix.
"""

import json
import time
from typing import Any

from src.infra.logging import get_logger

logger = get_logger(__name__)

# Cache: user_id -> (prompt_string, timestamp)
_sandbox_mcp_prompt_cache: dict[str, tuple[str, float]] = {}

# Cache TTL in seconds
_CACHE_TTL = 1800  # 30 minutes

# mcporter timeout
_MCPORTER_TIMEOUT = 15


async def build_sandbox_mcp_prompt(
    backend: Any,
    user_id: str,
    force_refresh: bool = False,
) -> str:
    """Build a prompt section describing available sandbox MCP tools.

    Args:
        backend: The sandbox backend (CompositeBackend) to run mcporter on.
        user_id: User ID for cache keying.
        force_refresh: If True, bypass cache and refresh.

    Returns:
        Formatted prompt string, or empty string if no tools available.
    """
    # Check cache
    if not force_refresh and user_id in _sandbox_mcp_prompt_cache:
        prompt, ts = _sandbox_mcp_prompt_cache[user_id]
        if time.time() - ts < _CACHE_TTL:
            logger.debug(f"[SandboxMCP Prompt] Cache hit for user {user_id}")
            return prompt

    # Fetch from mcporter
    prompt = await _fetch_and_format(backend)

    # Update cache (even if empty — avoids repeated mcporter calls when no servers exist)
    _sandbox_mcp_prompt_cache[user_id] = (prompt, time.time())
    logger.info(
        f"[SandboxMCP Prompt] {'Cache miss' if not force_refresh else 'Force refresh'} "
        f"for user {user_id}, prompt length={len(prompt)}"
    )

    return prompt


def invalidate_sandbox_mcp_prompt_cache(user_id: str) -> None:
    """Invalidate the cached prompt for a user.

    Call this after sandbox_mcp_add/update/remove operations.
    """
    if user_id in _sandbox_mcp_prompt_cache:
        del _sandbox_mcp_prompt_cache[user_id]
        logger.debug(f"[SandboxMCP Prompt] Cache invalidated for user {user_id}")


def _format_tools_list(data: Any) -> str:
    """Format mcporter list JSON output into a readable prompt section.

    Actual mcporter list --json format:
    {
      "mode": "list",
      "servers": [
        {
          "name": "server_name",
          "status": "ok",
          "tools": [
            {
              "name": "tool_name",
              "description": "...",
              "inputSchema": { ... }
            }
          ]
        }
      ]
    }
    """
    if not isinstance(data, dict):
        return ""

    # mcporter returns servers as a list under "servers" key
    servers = data.get("servers", [])
    if not isinstance(servers, list):
        return ""

    lines = ["## Sandbox MCP Tools", ""]
    lines.append(
        "The following MCP tools are registered in your sandbox. "
        "Use them via bash with `mcporter call`:"
    )
    lines.append("")

    tool_count = 0

    for server in servers:
        if not isinstance(server, dict):
            continue

        server_name = server.get("name", "")
        tools = server.get("tools", [])
        if not tools:
            continue

        for tool in tools:
            tool_name = tool.get("name", "")
            description = tool.get("description", "")
            input_schema = tool.get("inputSchema", {})

            if not tool_name:
                continue

            tool_count += 1

            # Tool header
            lines.append(f"- **{tool_name}** (from `{server_name}`)")
            if description:
                lines.append(f"  {description}")

            # Parameters from inputSchema
            properties = input_schema.get("properties", {})
            required = set(input_schema.get("required", []))

            if properties:
                param_parts = []
                for param_name, param_info in properties.items():
                    req = "required" if param_name in required else "optional"
                    param_desc = param_info.get("description", "")
                    param_parts.append(
                        f"`{param_name}` ({req}{': ' + param_desc if param_desc else ''})"
                    )

                lines.append(f"  Parameters: {', '.join(param_parts)}")

            # Usage example
            if properties:
                required_params = [p for p in properties if p in required]
                if required_params:
                    args_example = " ".join(f'{p}="<value>"' for p in required_params[:3])
                else:
                    first_param = next(iter(properties), "")
                    args_example = f'{first_param}="<value>"' if first_param else ""
                lines.append(f"  Usage: `mcporter call {server_name}.{tool_name} {args_example}`")
            else:
                lines.append(f"  Usage: `mcporter call {server_name}.{tool_name}`")

            lines.append("")

    if tool_count == 0:
        return ""

    return "\n".join(lines)


async def _fetch_and_format(backend: Any) -> str:
    """Run mcporter list and format the output."""
    try:
        result = await backend.aexecute("mcporter list --json", timeout=_MCPORTER_TIMEOUT)
        if result.exit_code != 0:
            logger.warning(f"[SandboxMCP Prompt] mcporter list failed: {result.output}")
            return ""

        try:
            data = json.loads(result.output)
            logger.debug(f"[SandboxMCP Prompt] mcporter list output: {data}")
        except json.JSONDecodeError:
            logger.warning("[SandboxMCP Prompt] mcporter list returned invalid JSON")
            return ""

        return _format_tools_list(data)

    except Exception as e:
        logger.warning(f"[SandboxMCP Prompt] Failed to fetch tools: {e}")
        return ""
