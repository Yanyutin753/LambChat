"""Sandbox MCP Tools - Manage MCP servers inside the sandbox via mcporter CLI.

Exposes three independent tools so the LLM can manage MCP servers:
  - sandbox_mcp_add:      Register a new MCP server (persists to MongoDB)
  - sandbox_mcp_update:   Update an existing MCP server's command/env (persists to MongoDB)
  - sandbox_mcp_remove:   Unregister an MCP server (persists to MongoDB)

Note: sandbox_mcp_list and sandbox_mcp_call were removed. The LLM discovers
tools via the system prompt and calls/discovers them directly via bash + mcporter.
"""

import json
import shlex
import sys
from typing import TYPE_CHECKING, Annotated, Any, Optional

from langchain_core.tools import BaseTool, InjectedToolArg, StructuredTool
from pydantic import BaseModel, Field

from src.infra.tool.sandbox_mcp_utils import build_env_flags

# ToolRuntime moved to langchain.tools in langchain_core >= 1.2.20.
# Must be a real runtime import (not TYPE_CHECKING) because InjectedToolArg
# needs to inspect the actual type annotation at runtime.
if TYPE_CHECKING:
    from langchain.tools import ToolRuntime
else:
    try:
        from langchain.tools import ToolRuntime  # type: ignore[assignment]
    except ImportError:  # pragma: no cover
        _mod = type(sys)("langchain.tools")  # type: ignore[assignment]
        _mod.ToolRuntime = Any  # type: ignore[assignment]
        sys.modules.setdefault("langchain.tools", _mod)
        from langchain.tools import ToolRuntime  # type: ignore[assignment]

from src.infra.logging import get_logger
from src.infra.tool.backend_utils import (
    get_backend_from_runtime,
    get_user_id_from_runtime,
)
from src.infra.tool.sandbox_mcp_prompt import invalidate_sandbox_mcp_prompt_cache

logger = get_logger(__name__)

# mcporter command timeout (seconds)
_MCPORTER_TIMEOUT = 60


# ── Args schemas ────────────────────────────────────────────────


class _AddInput(BaseModel):
    server_name: str = Field(..., description="MCP server name to register")
    command: str = Field(..., description="stdio command, e.g. 'npx @anthropic/mcp-server-fetch'")
    env_keys: Optional[str] = Field(
        None,
        description="Comma-separated list of environment variable KEY names to inject "
        "(must be pre-defined in user's environment variables settings)",
    )


class _UpdateInput(BaseModel):
    server_name: str = Field(..., description="Name of the MCP server to update")
    command: Optional[str] = Field(
        None, description="New stdio command (leave unchanged if omitted)"
    )
    env_keys: Optional[str] = Field(
        None,
        description="Comma-separated list of environment variable KEY names to inject "
        "(leave unchanged if omitted)",
    )


class _RemoveInput(BaseModel):
    server_name: str = Field(..., description="MCP server name to remove")


# ── MongoDB persistence helpers ───────────────────────────────


async def _persist_server_to_mongodb(
    user_id: str,
    server_name: str,
    command: str,
    env_keys: list[str],
) -> bool:
    """Create or update a sandbox MCP server in MongoDB."""
    from src.infra.mcp.storage import MCPStorage
    from src.kernel.schemas.mcp import MCPServerCreate, MCPTransport

    storage = MCPStorage()
    existing = await storage.get_user_server(server_name, user_id)
    if existing:
        # Update existing
        from src.kernel.schemas.mcp import MCPServerUpdate

        update = MCPServerUpdate(command=command, env_keys=env_keys if env_keys else None)
        result = await storage.update_user_server(server_name, update, user_id)
        if result:
            logger.info(f"[sandbox_mcp] Updated MongoDB server '{server_name}' for user {user_id}")
            return True
        return False
    else:
        # Create new
        create = MCPServerCreate(
            name=server_name,
            transport=MCPTransport.SANDBOX,
            command=command,
            env_keys=env_keys if env_keys else None,
        )
        server = await storage.create_user_server(create, user_id)
        if server:
            logger.info(f"[sandbox_mcp] Created MongoDB server '{server_name}' for user {user_id}")
            return True
        return False


async def _delete_server_from_mongodb(user_id: str, server_name: str) -> bool:
    """Delete a sandbox MCP server from MongoDB."""
    from src.infra.mcp.storage import MCPStorage

    storage = MCPStorage()
    deleted = await storage.delete_user_server(server_name, user_id)
    if deleted:
        logger.info(f"[sandbox_mcp] Deleted MongoDB server '{server_name}' for user {user_id}")
    return deleted


# ── Tool implementations ───────────────────────────────────────


# build_env_flags removed — use src.infra.tool.sandbox_mcp_utils.build_env_flags instead


async def _mcporter_add(
    runtime: Annotated[ToolRuntime, InjectedToolArg],
    server_name: str,
    command: str,
    env_keys: Optional[str] = None,
) -> str:
    """Add a new MCP server to the sandbox and persist to MongoDB."""
    backend = get_backend_from_runtime(runtime)
    if backend is None:
        return json.dumps({"error": "No sandbox backend available"})

    user_id = get_user_id_from_runtime(runtime) or "unknown"
    env_key_list = [k.strip() for k in env_keys.split(",") if k.strip()] if env_keys else []

    # Register in sandbox
    env_flags = await build_env_flags(user_id, env_key_list)
    cmd = (
        f"mcporter config add {shlex.quote(server_name)} --stdio {shlex.quote(command)}{env_flags}"
    )
    result = await backend.aexecute(cmd, timeout=_MCPORTER_TIMEOUT)
    if result.exit_code != 0:
        return json.dumps({"error": f"mcporter failed: {result.output}"})

    # Persist to MongoDB
    ok = await _persist_server_to_mongodb(user_id, server_name, command, env_key_list)
    if not ok:
        return json.dumps(
            {"error": "Server registered in sandbox but failed to persist to database"}
        )

    invalidate_sandbox_mcp_prompt_cache(user_id)
    return json.dumps(
        {
            "success": True,
            "message": f"Server '{server_name}' added to sandbox and saved",
            "server_name": server_name,
            "command": command,
            "env_keys": env_key_list,
        }
    )


async def _mcporter_update(
    runtime: Annotated[ToolRuntime, InjectedToolArg],
    server_name: str,
    command: Optional[str] = None,
    env_keys: Optional[str] = None,
) -> str:
    """Update an existing MCP server's command/env_keys in the sandbox and MongoDB."""
    backend = get_backend_from_runtime(runtime)
    if backend is None:
        return json.dumps({"error": "No sandbox backend available"})

    user_id = get_user_id_from_runtime(runtime) or "unknown"
    env_key_list = [k.strip() for k in env_keys.split(",") if k.strip()] if env_keys else None

    # We need to know the current command to rebuild mcporter config.
    # Read from MongoDB first.
    from src.infra.mcp.storage import MCPStorage

    storage = MCPStorage()
    existing = await storage.get_user_server(server_name, user_id)
    if not existing:
        return json.dumps({"error": f"Server '{server_name}' not found in database"})

    resolved_command = command or existing.command or ""
    resolved_env_keys = env_key_list if env_key_list is not None else (existing.env_keys or [])

    # Remove old config from mcporter, add new one
    await backend.aexecute(
        f"mcporter config remove {shlex.quote(server_name)}", timeout=_MCPORTER_TIMEOUT
    )
    # remove may fail if server wasn't in mcporter yet, that's ok

    env_flags = await build_env_flags(user_id, resolved_env_keys)
    add_cmd = f"mcporter config add {shlex.quote(server_name)} --stdio {shlex.quote(resolved_command)}{env_flags}"
    result = await backend.aexecute(add_cmd, timeout=_MCPORTER_TIMEOUT)
    if result.exit_code != 0:
        # Try to restore the old one if possible
        old_env = await build_env_flags(user_id, existing.env_keys or [])
        restore_cmd = f"mcporter config add {shlex.quote(server_name)} --stdio {shlex.quote(existing.command or '')}{old_env}"
        await backend.aexecute(restore_cmd, timeout=_MCPORTER_TIMEOUT)
        return json.dumps({"error": f"mcporter update failed: {result.output}"})

    # Persist to MongoDB
    from src.kernel.schemas.mcp import MCPServerUpdate

    update = MCPServerUpdate(
        command=resolved_command,
        env_keys=resolved_env_keys,
    )
    updated = await storage.update_user_server(server_name, update, user_id)
    if not updated:
        return json.dumps({"error": "mcporter updated but failed to persist to database"})

    invalidate_sandbox_mcp_prompt_cache(user_id)
    return json.dumps(
        {
            "success": True,
            "message": f"Server '{server_name}' updated in sandbox and saved",
            "server_name": server_name,
            "command": resolved_command,
            "env_keys": resolved_env_keys,
        }
    )


async def _mcporter_remove(
    runtime: Annotated[ToolRuntime, InjectedToolArg],
    server_name: str,
) -> str:
    """Remove an MCP server from the sandbox and MongoDB."""
    backend = get_backend_from_runtime(runtime)
    if backend is None:
        return json.dumps({"error": "No sandbox backend available"})

    user_id = get_user_id_from_runtime(runtime) or "unknown"

    # Unregister from mcporter
    cmd = f"mcporter config remove {shlex.quote(server_name)}"
    result = await backend.aexecute(cmd, timeout=_MCPORTER_TIMEOUT)

    # Persist removal to MongoDB (even if mcporter remove failed, e.g. server wasn't registered)
    deleted = await _delete_server_from_mongodb(user_id, server_name)

    if result.exit_code != 0 and deleted:
        invalidate_sandbox_mcp_prompt_cache(user_id)
        return json.dumps(
            {
                "success": True,
                "message": f"Server '{server_name}' removed from database (was not in sandbox)",
            }
        )

    if result.exit_code != 0:
        return json.dumps({"error": f"mcporter failed: {result.output}"})

    invalidate_sandbox_mcp_prompt_cache(user_id)
    return json.dumps(
        {
            "success": True,
            "message": f"Server '{server_name}' removed from sandbox and database",
            "server_name": server_name,
        }
    )


# ── Public API ─────────────────────────────────────────────────


def get_sandbox_mcp_tools() -> list[BaseTool]:
    """Get all sandbox MCP management tools.

    Returns three independent LangChain StructuredTools so the LLM can
    manage MCP servers:
      - sandbox_mcp_add:      register a new server (persists to MongoDB)
      - sandbox_mcp_update:   update server command/env_keys (persists to MongoDB)
      - sandbox_mcp_remove:   unregister a server (persists to MongoDB)
    """
    return [
        StructuredTool(
            name="sandbox_mcp_add",
            description=(
                "Register a new MCP server in the sandbox and persist it to the database. "
                "Provide server_name and the stdio command (e.g. 'npx @anthropic/mcp-server-fetch'). "
                "Optionally pass env_keys as comma-separated KEY names to inject "
                "(these must be pre-defined in user's environment variable settings). "
                "The server will be automatically restored when the sandbox is rebuilt."
            ),
            args_schema=_AddInput,
            func=None,
            coroutine=_mcporter_add,
        ),
        StructuredTool(
            name="sandbox_mcp_update",
            description=(
                "Update an existing sandbox MCP server's command or environment variables. "
                "Provide server_name and optionally the new command and/or env_keys. "
                "Changes are persisted to the database and applied to the sandbox."
            ),
            args_schema=_UpdateInput,
            func=None,
            coroutine=_mcporter_update,
        ),
        StructuredTool(
            name="sandbox_mcp_remove",
            description=(
                "Remove an MCP server from the sandbox and delete it from the database. "
                "The server will no longer be restored when the sandbox is rebuilt."
            ),
            args_schema=_RemoveInput,
            func=None,
            coroutine=_mcporter_remove,
        ),
    ]


# Backwards compatibility alias
def get_sandbox_mcp_tool() -> BaseTool:
    """Get a single sandbox MCP management tool (deprecated, use get_sandbox_mcp_tools)."""
    return get_sandbox_mcp_tools()[0]
