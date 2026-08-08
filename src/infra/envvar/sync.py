"""Synchronization helpers for environment variable changes."""

from __future__ import annotations

from typing import Any

from src.infra.tool.cache_pubsub import publish_tool_cache_invalidation
from src.infra.tool.env_var_prompt import invalidate_env_var_prompt_cache


async def sync_envvar_change(user_id: str, *, backend: Any | None = None) -> None:
    """Invalidate local prompt caches and broadcast the change to peer processes."""
    invalidate_env_var_prompt_cache(user_id)
    await publish_tool_cache_invalidation("env_var_prompt", user_id=user_id)
