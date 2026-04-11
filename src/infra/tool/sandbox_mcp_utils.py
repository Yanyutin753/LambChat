"""Shared utilities for sandbox MCP operations.

Provides common helpers used by both the LLM tools (sandbox_mcp_tool.py)
and the sandbox session manager (session_manager.py) to avoid code
duplication.
"""

import shlex


async def build_env_flags(user_id: str, env_key_names: list[str]) -> str:
    """Build --env KEY=VALUE flags for mcporter commands.

    Resolves actual values from the user's encrypted env var storage.

    Args:
        user_id: User ID to look up env vars for.
        env_key_names: List of env var key names to include.

    Returns:
        A string of "--env KEY=VALUE" flags, or empty string if no keys.
    """
    if not env_key_names:
        return ""
    from src.infra.envvar.storage import EnvVarStorage

    storage = EnvVarStorage()
    env_vars = await storage.get_decrypted_vars(user_id)
    parts = []
    for key in env_key_names:
        val = env_vars.get(key, "")
        parts.append(f" --env {shlex.quote(key)}={shlex.quote(val)}")
    return "".join(parts)
