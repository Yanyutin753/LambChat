"""Synchronization helpers for environment variable changes."""

from __future__ import annotations

from typing import Any

from src.infra.envvar.storage import EnvVarStorage
from src.infra.logging import get_logger
from src.infra.tool.cache_pubsub import publish_tool_cache_invalidation
from src.infra.tool.env_var_prompt import invalidate_env_var_prompt_cache

logger = get_logger(__name__)


def get_session_sandbox_manager():
    from src.infra.sandbox.session_manager import get_session_sandbox_manager as _get_manager

    return _get_manager()


async def sync_sandbox_env_vars(backend: Any, user_id: str) -> None:
    """Refresh per-execution sandbox environment variables from encrypted storage."""
    try:
        env_vars = await EnvVarStorage().get_decrypted_vars(user_id)
    except Exception as e:
        logger.warning("Failed to load sandbox environment variables for user %s: %s", user_id, e)
        return

    sandbox_backend = getattr(backend, "default", backend)
    if hasattr(sandbox_backend, "env_vars"):
        sandbox_backend.env_vars = env_vars or {}


async def sync_envvar_change(user_id: str, *, backend: Any | None = None) -> None:
    """Invalidate prompt caches and refresh the active sandbox backend."""
    invalidate_env_var_prompt_cache(user_id)
    await publish_tool_cache_invalidation("env_var_prompt", user_id=user_id)

    if backend is None:
        try:
            backend = get_session_sandbox_manager().get_cached_backend(user_id)
        except Exception:
            backend = None

    if backend is not None:
        await sync_sandbox_env_vars(backend, user_id)
