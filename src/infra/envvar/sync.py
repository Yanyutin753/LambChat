"""Synchronization helpers for environment variable changes."""

from __future__ import annotations

from typing import Any

from src.infra.envvar.storage import EnvVarStorage
from src.infra.logging import get_logger
from src.infra.tool.cache_pubsub import publish_tool_cache_invalidation
from src.infra.tool.env_var_prompt import invalidate_env_var_prompt_cache

logger = get_logger(__name__)


async def resolve_channel_env_vars(
    user_id: str, agent_options: dict[str, Any] | None
) -> dict[str, str]:
    """Resolve encrypted variables for this owner without persisting values in run options."""
    if "channel_runtime" not in (agent_options or {}):
        return {}
    from src.infra.channel.channel_storage import ChannelStorage
    from src.infra.channel.runtime import ChannelRuntimeConfig
    from src.kernel.schemas.channel import ChannelType

    reference = (agent_options or {})["channel_runtime"]
    error = "Channel runtime configuration unavailable"
    if not user_id or not isinstance(reference, dict):
        raise ValueError(error)
    instance_id = reference.get("instance_id")
    if not isinstance(instance_id, str) or not instance_id:
        raise ValueError(error)
    try:
        channel_type = ChannelType(reference.get("channel_type"))
    except (ValueError, TypeError):
        raise ValueError(error) from None
    try:
        config = await ChannelStorage().get_config(user_id, channel_type, instance_id)
    except Exception:
        raise ValueError(error) from None
    if not config or config.get("user_id") != user_id:
        raise ValueError(error)
    try:
        runtime = ChannelRuntimeConfig.model_validate(config.get("runtime_config") or {})
    except ValueError:
        raise ValueError(error) from None
    return dict(runtime.env_vars)


def apply_sandbox_env_overrides(backend: Any, overrides: dict[str, str]) -> None:
    """Apply variables to a run-owned delegate, never mutate a shared environment dict."""
    if not overrides:
        return
    sandbox_backend = getattr(backend, "default", backend)
    sandbox_backend._run_env_overrides = dict(overrides)
    sandbox_backend.env_vars = {**getattr(sandbox_backend, "env_vars", {}), **overrides}


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
    # Lazy cloud backends hold the run's command environment on their initialized delegate.
    sandbox_backend = getattr(sandbox_backend, "_delegate", None) or sandbox_backend
    if hasattr(sandbox_backend, "env_vars"):
        sandbox_backend.env_vars = {
            **(env_vars or {}),
            **getattr(sandbox_backend, "_run_env_overrides", {}),
        }


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
