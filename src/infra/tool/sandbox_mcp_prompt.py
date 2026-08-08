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

from src.infra.async_utils import run_blocking_io
from src.infra.logging import get_logger

logger = get_logger(__name__)

# Cache: user_id -> (prompt_sections, total_tool_count, timestamp)
_sandbox_mcp_prompt_cache: dict[str, tuple[tuple[str, ...], int, float]] = {}

# Cache TTL in seconds
_CACHE_TTL = 1800  # 30 minutes
_MAX_PROMPT_CACHE_ENTRIES = 500

_DESCRIPTION_THRESHOLD = 20

# mcporter timeout
_MCPORTER_TIMEOUT = 15
_MCPORTER_CHECK_TIMEOUT = 5


async def build_sandbox_mcp_prompt(
    backend: Any,
    user_id: str,
    force_refresh: bool = False,
) -> str:
    """Build a prompt section describing available sandbox MCP tools."""
    return "\n\n".join(await build_sandbox_mcp_prompt_sections(backend, user_id, force_refresh))


async def build_sandbox_mcp_prompt_sections(
    backend: Any,
    user_id: str,
    force_refresh: bool = False,
) -> tuple[str, ...]:
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
        prompt_sections, total_count, ts = _sandbox_mcp_prompt_cache[user_id]
        if time.time() - ts < _CACHE_TTL:
            logger.debug(f"[SandboxMCP Prompt] Cache hit for user {user_id}")
            return prompt_sections

    # Fetch from mcporter
    prompt_sections, total_count = await _fetch_and_format(backend)

    # Update cache (even if empty — avoids repeated mcporter calls when no servers exist)
    _sandbox_mcp_prompt_cache[user_id] = (prompt_sections, total_count, time.time())
    logger.info(
        f"[SandboxMCP Prompt] {'Cache miss' if not force_refresh else 'Force refresh'} "
        f"for user {user_id}, prompt length={sum(len(section) for section in prompt_sections)}, total_tools={total_count}"
    )

    return prompt_sections


def _cleanup_stale_cache() -> None:
    """Remove expired entries from the cache."""
    now = time.time()
    stale = [uid for uid, (_, _, ts) in _sandbox_mcp_prompt_cache.items() if now - ts > _CACHE_TTL]
    for uid in stale:
        del _sandbox_mcp_prompt_cache[uid]
    if stale:
        logger.debug(f"[SandboxMCP Prompt] Cleaned up {len(stale)} stale cache entries")
    removed = _cleanup_excess_prompt_cache_entries()
    if removed:
        logger.debug(f"[SandboxMCP Prompt] Cleaned up {removed} excess cache entries")


def _cleanup_excess_prompt_cache_entries() -> int:
    max_entries = max(int(_MAX_PROMPT_CACHE_ENTRIES), 1)
    if len(_sandbox_mcp_prompt_cache) <= max_entries:
        return 0

    to_remove = len(_sandbox_mcp_prompt_cache) - max_entries
    oldest = sorted(
        _sandbox_mcp_prompt_cache.items(),
        key=lambda item: item[1][2],
    )[:to_remove]
    for user_id, _entry in oldest:
        _sandbox_mcp_prompt_cache.pop(user_id, None)
    return len(oldest)


def invalidate_sandbox_mcp_prompt_cache(user_id: str) -> None:
    """Invalidate the cached prompt for a user.

    Call this after sandbox_mcp_add/update/remove operations.
    """
    if user_id in _sandbox_mcp_prompt_cache:
        del _sandbox_mcp_prompt_cache[user_id]
        logger.debug(f"[SandboxMCP Prompt] Cache invalidated for user {user_id}")


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


def _format_tools_list(data: Any) -> tuple[str, int]:
    """Backward-compatible string formatter for sandbox tool prompt."""
    sections, total_count = _format_tools_list_sections(data)
    return "\n\n".join(sections), total_count


def _format_tools_list_sections(data: Any) -> tuple[tuple[str, ...], int]:
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
        return (), 0

    # mcporter returns servers as a list under "servers" key
    servers = data.get("servers", [])
    if not isinstance(servers, list):
        return (), 0

    intro = (
        "## Sandbox Tools (use through `execute`)\n\n"
        "These are not direct/MCP tools and `search_tools` cannot load them. Before "
        "the first call, run `mcporter list` and `mcporter list <service> --schema`; "
        "then run `mcporter call server.tool <args>`. Manage servers with "
        "`sandbox_mcp_add`, `sandbox_mcp_update`, or `sandbox_mcp_remove`."
    )
    entries: list[tuple[str, str]] = []

    for server in servers:
        if not isinstance(server, dict):
            continue

        server_name = server.get("name", "")
        tools = server.get("tools", [])
        if not server_name or not isinstance(tools, list):
            continue

        for tool in tools:
            if not isinstance(tool, dict):
                continue
            tool_name = str(tool.get("name") or "").strip()
            if not tool_name:
                continue
            full_name = f"{server_name}.{tool_name}"
            entries.append((full_name, _clean_description(str(tool.get("description") or ""))))

    entries.sort(key=lambda item: (item[0].lower(), item[0]))
    if not entries:
        return (), 0
    if len(entries) <= _DESCRIPTION_THRESHOLD:
        inventory = "\n".join(
            f"- `{name}`: {description}" if description else f"- `{name}`"
            for name, description in entries
        )
    else:
        inventory = "\n".join(f"- `{name}`" for name, _description in entries)
    return (intro, inventory), len(entries)


async def _fetch_and_format(backend: Any) -> tuple[tuple[str, ...], int]:
    """Run mcporter list and format the output."""
    try:
        if not await _is_mcporter_available(backend):
            return (), 0

        result = await backend.aexecute("mcporter list --json", timeout=_MCPORTER_TIMEOUT)
        if result.exit_code != 0:
            logger.warning(f"[SandboxMCP Prompt] mcporter list failed: {result.output}")
            return (), 0

        try:
            data = await run_blocking_io(json.loads, result.output)
            logger.debug(f"[SandboxMCP Prompt] mcporter list output: {data}")
        except json.JSONDecodeError:
            logger.warning("[SandboxMCP Prompt] mcporter list returned invalid JSON")
            return (), 0

        return _format_tools_list_sections(data)

    except Exception as e:
        logger.warning(f"[SandboxMCP Prompt] Failed to fetch tools: {e}")
        return (), 0


async def _is_mcporter_available(backend: Any) -> bool:
    """Check whether mcporter is installed in the current sandbox."""
    try:
        result = await backend.aexecute("mcporter --version", timeout=_MCPORTER_CHECK_TIMEOUT)
    except Exception as e:
        logger.info(f"[SandboxMCP Prompt] Failed to check mcporter availability: {e}")
        return False

    if result.exit_code != 0:
        logger.info(
            f"[SandboxMCP Prompt] mcporter not available (exit={result.exit_code}, output={result.output})"
        )
        return False

    return True
