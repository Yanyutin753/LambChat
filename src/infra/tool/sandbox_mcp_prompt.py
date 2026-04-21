"""Sandbox Tools Prompt Builder - Injects sandbox tool descriptions into system prompt.

These are sandbox tools (managed via mcporter), NOT MCP tools.
The LLM must use the `execute` tool to invoke them.

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
# With descriptions + params, each tool uses ~60-120 tokens; 20 tools ≈ 1200-2400 tokens.
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
    # Cleanup stale cache entries periodically
    _cleanup_stale_cache()

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


def _cleanup_stale_cache() -> None:
    """Remove expired entries from the cache."""
    now = time.time()
    stale = [uid for uid, (_, _, ts) in _sandbox_mcp_prompt_cache.items() if now - ts > _CACHE_TTL]
    for uid in stale:
        del _sandbox_mcp_prompt_cache[uid]
    if stale:
        logger.debug(f"[SandboxMCP Prompt] Cleaned up {len(stale)} stale cache entries")


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
        + 'Use `execute(command="mcporter list")` to browse all available tools.\n'
    )


def _clean_description(desc: str) -> str:
    """Strip Args/COST WARNING sections, keep core one-line description."""
    if not desc:
        return ""
    # Remove Args section
    for marker in ("\n\nArgs:", "\nArgs:"):
        idx = desc.find(marker)
        if idx != -1:
            desc = desc[:idx].strip()
    # Remove COST WARNING
    for marker in ("\n\nCOST WARNING:", "\nCOST WARNING:"):
        idx = desc.find(marker)
        if idx != -1:
            desc = desc[:idx].strip()
    # Collapse multi-line to single line
    desc = " ".join(desc.split())
    # Truncate long descriptions
    if len(desc) > 200:
        desc = desc[:197] + "..."
    return desc


def _format_params(schema: Any) -> str:
    """Format inputSchema properties into a concise parameter list.

    Example output:
      Params: query (string, required), limit (integer, default: 10)
    """
    if not isinstance(schema, dict):
        return ""

    properties = schema.get("properties", {})
    required = set(schema.get("required", []))

    if not properties:
        return ""

    parts = []
    for name, info in properties.items():
        if not isinstance(info, dict):
            continue
        ptype = info.get("type", "any")
        tokens = [name, f"({ptype}"]
        if name in required:
            tokens.append(", required")
        if "default" in info:
            tokens.append(f", default: {info['default']}")
        # Add enum hint if present
        if "enum" in info and isinstance(info["enum"], list):
            enum_vals = ", ".join(str(v) for v in info["enum"][:5])
            tokens.append(f", enum: [{enum_vals}]")
        tokens.append(")")
        parts.append("".join(tokens))

    if not parts:
        return ""
    return "Params: " + ", ".join(parts)


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
        "## Sandbox Tools (NOT MCP — DO NOT call directly)",
        "",
        "⚠️ **IMPORTANT**: The tools listed below are **sandbox tools**, NOT MCP tools. "
        "You do NOT have direct access to them. Do NOT attempt to call them as MCP tools "
        "— such calls will fail.",
        "",
        "**How to use**: You MUST use the `execute` tool with `mcporter` commands. "
        "The `execute` tool is your ONLY way to invoke sandbox tools.",
        "",
        "Example — calling `server.my_tool` with arg `query=hello`:",
        "```",
        'execute(command="mcporter call server.my_tool query=hello")',
        "```",
        "",
        "**Discovery** — run via `execute`:",
        "- `mcporter list` — list all servers and tools",
        "- `mcporter list --schema` — show parameter schemas (check before first use)",
        "",
        "**Invocation** — call via `execute`: `mcporter call server.tool <args>`",
        "- Named args: `mcporter call server.tool key=value` (values with spaces MUST be quoted)",
        '- JSON payload: `mcporter call server.tool --args \'{"key": "value"}\'` (for complex params)',
        "",
        "Do NOT use `--flag value` syntax — that passes `value` as a positional arg.",
        "",
        "**Server Management**: `sandbox_mcp_add` / `sandbox_mcp_update` / `sandbox_mcp_remove` — "
        "changes are persisted and auto-restored on sandbox rebuild.",
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

            # Build tool entry with description and parameters
            full_name = f"{server_name}.{tool_name}"

            # Clean description: strip Args/COST WARNING sections, keep core description
            tool_desc = _clean_description(tool_desc)

            lines.append(f"- `{full_name}`")
            if tool_desc:
                lines.append(f"  {tool_desc}")

            # Extract and format parameters
            param_line = _format_params(tool.get("inputSchema"))
            if param_line:
                lines.append(f"  {param_line}")

            lines.append(f'  → use: `execute(command="mcporter call {full_name} <args>")`')

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
