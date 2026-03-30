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

# Cache: user_id -> (prompt_string, total_tool_count, timestamp)
_sandbox_mcp_prompt_cache: dict[str, tuple[str, int, float]] = {}

# Cache TTL in seconds
_CACHE_TTL = 1800  # 30 minutes

# Max tools to inject into system prompt (beyond this, LLM uses bash to discover more)
# With one-line descriptions, each tool uses ~30-50 tokens; 20 tools ≈ 600-1000 tokens.
_MAX_TOOLS_IN_PROMPT = 20

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
        prompt, total_count, ts = _sandbox_mcp_prompt_cache[user_id]
        if time.time() - ts < _CACHE_TTL:
            logger.debug(f"[SandboxMCP Prompt] Cache hit for user {user_id}")
            return _maybe_append_overflow_hint(prompt, total_count)

    # Fetch from mcporter
    prompt, total_count = await _fetch_and_format(backend)

    # Update cache (even if empty — avoids repeated mcporter calls when no servers exist)
    _sandbox_mcp_prompt_cache[user_id] = (prompt, total_count, time.time())
    logger.info(
        f"[SandboxMCP Prompt] {'Cache miss' if not force_refresh else 'Force refresh'} "
        f"for user {user_id}, prompt length={len(prompt)}, total_tools={total_count}"
    )

    return _maybe_append_overflow_hint(prompt, total_count)


def invalidate_sandbox_mcp_prompt_cache(user_id: str) -> None:
    """Invalidate the cached prompt for a user.

    Call this after sandbox_mcp_add/update/remove operations.
    """
    if user_id in _sandbox_mcp_prompt_cache:
        del _sandbox_mcp_prompt_cache[user_id]
        logger.debug(f"[SandboxMCP Prompt] Cache invalidated for user {user_id}")


def _maybe_append_overflow_hint(prompt: str, total_count: int) -> str:
    """Append overflow hint to prompt if tools were truncated."""
    if not prompt or total_count <= _MAX_TOOLS_IN_PROMPT:
        return prompt

    return (
        prompt
        + f"> **Note:** Only {_MAX_TOOLS_IN_PROMPT} of {total_count} tools are shown above. "
        + "Run `mcporter list` to browse all available tools.\n"
    )


def _format_tools_list(data: Any) -> tuple[str, int]:
    """Format mcporter list JSON output into a readable prompt section.

    Returns:
        Tuple of (formatted_prompt, total_tool_count).

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
        return "", 0

    # mcporter returns servers as a list under "servers" key
    servers = data.get("servers", [])
    if not isinstance(servers, list):
        return "", 0

    lines = [
        "## Sandbox MCP Tools",
        "",
        "MCP (Model Context Protocol) tools available in your sandbox environment, "
        "managed via `mcporter`:",
        "",
        "**Discovery & Invocation**",
        "- `mcporter list` — list all registered servers and tools",
        "- `mcporter call server.tool` — invoke a specific tool",
        "- `mcporter list --schema` — show detailed parameter schemas for tools",
        "",
        "**Server Management**",
        "- `sandbox_mcp_add` / `sandbox_mcp_update` / `sandbox_mcp_remove` — "
        "manage MCP servers. Changes are persisted and auto-restored on sandbox rebuild.",
        "",
    ]

    tool_count = 0
    total_count = 0

    for server in servers:
        if not isinstance(server, dict):
            continue

        server_name = server.get("name", "")
        server_status = server.get("status", "")
        tools = server.get("tools", [])
        if not tools:
            continue

        # Server header
        status_tag = f" ({server_status})" if server_status and server_status != "ok" else ""
        lines.append(f"### {server_name}{status_tag}")

        for tool in tools:
            total_count += 1

            if tool_count >= _MAX_TOOLS_IN_PROMPT:
                continue

            tool_name = tool.get("name", "")
            tool_desc = tool.get("description", "")

            if not tool_name:
                continue

            tool_count += 1

            # Clean description: strip Args section, preserve COST WARNING
            args_idx = tool_desc.find("\n\nArgs:")
            if args_idx != -1:
                tool_desc = tool_desc[:args_idx].strip()
            else:
                # Fallback: strip inline Args:
                args_idx = tool_desc.find("Args:")
                if args_idx != -1:
                    tool_desc = tool_desc[:args_idx].strip()

            # Build tool entry
            full_name = f"{server_name}.{tool_name}"

            if not tool_desc:
                lines.append(f"- **{full_name}**")
            else:
                lines.append(f"- **{full_name}**")
                # Indent description on the next line for readability
                for desc_line in tool_desc.split("\n"):
                    stripped = desc_line.strip()
                    if stripped:
                        lines.append(f"  {stripped}")

        lines.append("")

    return "\n".join(lines), total_count


async def _fetch_and_format(backend: Any) -> tuple[str, int]:
    """Run mcporter list and format the output."""
    try:
        result = await backend.aexecute("mcporter list --json", timeout=_MCPORTER_TIMEOUT)
        if result.exit_code != 0:
            logger.warning(f"[SandboxMCP Prompt] mcporter list failed: {result.output}")
            return "", 0

        try:
            data = json.loads(result.output)
            logger.debug(f"[SandboxMCP Prompt] mcporter list output: {data}")
        except json.JSONDecodeError:
            logger.warning("[SandboxMCP Prompt] mcporter list returned invalid JSON")
            return "", 0

        return _format_tools_list(data)

    except Exception as e:
        logger.warning(f"[SandboxMCP Prompt] Failed to fetch tools: {e}")
        return "", 0
