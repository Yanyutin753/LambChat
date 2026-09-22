"""
LLM Models Service - Model fetching utilities with distributed caching.

Three-tier cache: memory → Redis → DB.
Supports distributed deployments with pub/sub invalidation.

API keys are cached in-process only (not in Redis) for security.
This eliminates the per-request DB fallback while keeping keys out of
shared caches.
"""

from __future__ import annotations

import json
from typing import Any, Optional

from src.infra.async_utils import run_long_blocking_io
from src.infra.logging import get_logger
from src.kernel.config import settings

logger = get_logger(__name__)

# Redis cache key and TTL
_MODELS_CACHE_KEY = "models:available"
_MODELS_CACHE_TTL = 300  # 5 minutes default TTL
_MODELS_CACHE_MAX_SIZE = 500

# In-memory cache (per-process)
_memory_cache: Optional[list[dict[str, Any]]] = None

# In-process api_key cache (per-process, not shared via Redis)
_api_key_cache: dict[str, str] = {}
_API_KEY_CACHE_MAX_SIZE = 500  # Prevent unbounded growth


def set_memory_cache(models: list[dict[str, Any]]) -> None:
    """Update the in-memory cache directly."""
    global _memory_cache
    _memory_cache = models[:_MODELS_CACHE_MAX_SIZE]


def clear_memory_cache() -> None:
    """Clear the in-memory cache only (sync, no I/O)."""
    global _memory_cache
    _memory_cache = None


def clear_api_key_cache() -> None:
    """Clear the in-process api_key cache (sync, no I/O)."""
    _api_key_cache.clear()


def get_cached_api_key(model_value: str) -> Optional[str]:
    """Get api_key from the in-process cache."""
    return _api_key_cache.get(model_value)


def set_cached_api_key(model_value: str, api_key: str) -> None:
    """Store api_key in the in-process cache with a max-size guard."""
    if len(_api_key_cache) >= _API_KEY_CACHE_MAX_SIZE and model_value not in _api_key_cache:
        # Evict oldest entries by clearing and letting them reload on next access
        _api_key_cache.clear()
    _api_key_cache[model_value] = api_key


def _matches_allowed(model: dict[str, Any], allowed_set: set[str] | None) -> bool:
    if allowed_set is None:
        return True
    return model.get("value") in allowed_set or model.get("id") in allowed_set


def select_default_model(
    models: list[dict[str, Any]], allowed_models: Optional[list[str]] = None
) -> dict[str, Any] | None:
    """Select the effective default model from already-available models."""
    allowed_set = set(allowed_models) if allowed_models is not None else None
    admin_default_id = getattr(settings, "DEFAULT_MODEL_ID", "") or ""

    if admin_default_id:
        for model in models:
            if not _matches_allowed(model, allowed_set):
                continue
            if model.get("id") == admin_default_id or model.get("value") == admin_default_id:
                return model

    for model in models:
        if _matches_allowed(model, allowed_set):
            return model
    return None


async def get_default_model(allowed_models: Optional[list[str]] = None) -> str:
    """Return the first available model's value, or empty string.

    Args:
        allowed_models: If provided, only consider models in this list
                       (can be model values or model IDs).
    """
    model = select_default_model(await get_available_models(), allowed_models)
    return model.get("value", "") if model else ""


async def get_default_model_id(allowed_models: Optional[list[str]] = None) -> str:
    """Return the first available model's ID, or empty string.

    Args:
        allowed_models: If provided, only consider models in this list
                       (model IDs).
    """
    model = select_default_model(await get_available_models(), allowed_models)
    return model.get("id", "") if model else ""


async def resolve_model_reference(reference: str | None) -> tuple[str | None, str | None]:
    """Resolve a setting value that may be a model config ID or legacy model value.

    Returns ``(model_id, model)`` for ``LLMClient.get_model``. Empty values return
    ``(None, None)`` so the client falls back to the configured default model.
    """
    value = (reference or "").strip()
    if not value:
        return None, None

    available_models = await get_available_models()
    for model in available_models:
        if model.get("id") == value:
            return value, None

    return None, value


async def get_available_models() -> list[dict[str, Any]]:
    """Get available models — memory → Redis → DB."""
    global _memory_cache

    # 1. Memory cache
    if _memory_cache is not None:
        return _memory_cache

    # 2. Redis cache
    try:
        from src.infra.storage.redis import get_redis_client

        redis_client = get_redis_client()
        cached = await redis_client.get(_MODELS_CACHE_KEY)
        if cached:
            logger.debug("[LLMModels] Cache hit: Redis")
            model_list = await run_long_blocking_io(json.loads, cached)
            set_memory_cache(model_list)
            return _memory_cache or []
    except Exception as e:
        logger.debug(f"[LLMModels] Redis read failed: {e}")

    # 3. DB
    return await _fetch_from_db()


def _strip_api_keys(model_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove api_key from model dicts before caching.

    Returns new dicts to avoid mutating the caller's data.
    """
    return [{**m, "api_key": None} for m in model_list[:_MODELS_CACHE_MAX_SIZE]]


async def _write_to_caches(model_list: list[dict[str, Any]]) -> None:
    """Write model list to memory and Redis caches (api_keys stripped)."""
    global _memory_cache

    stripped = _strip_api_keys(model_list)
    _memory_cache = stripped

    try:
        from src.infra.storage.redis import get_redis_client

        redis_client = get_redis_client()
        ttl = getattr(settings, "LLM_MODELS_CACHE_TTL", _MODELS_CACHE_TTL)
        serialized = await run_long_blocking_io(json.dumps, stripped)
        await redis_client.set(_MODELS_CACHE_KEY, serialized, ex=ttl)
        logger.debug(f"[LLMModels] Cached {len(stripped)} models (TTL={ttl}s)")
    except Exception as e:
        logger.debug(f"[LLMModels] Redis write failed: {e}")


async def _fetch_from_db(*, raise_on_error: bool = True) -> list[dict[str, Any]]:
    """Query DB, write results into memory + Redis caches.

    Args:
        raise_on_error: If True, re-raise exceptions. If False, return [].
    """
    try:
        from src.infra.agent.model_storage import get_model_storage

        storage = get_model_storage()
        models = await storage.list_models(include_disabled=False)
        if not models:
            return []

        model_list = [m.model_dump() for m in models]

        # Populate in-process api_key cache from DB results
        for m in models[:_MODELS_CACHE_MAX_SIZE]:
            if m.api_key:
                _api_key_cache[m.value] = m.api_key

        await _write_to_caches(model_list)
        return _strip_api_keys(model_list)
    except Exception as e:
        msg = f"[LLMModels] DB query failed: {e}"
        if raise_on_error:
            logger.error(msg)
            raise
        logger.debug(msg)
        return []


# ---------------------------------------------------------------------------
# Cache invalidation
# ---------------------------------------------------------------------------


async def invalidate_cache(*, publish: bool = True) -> None:
    """Invalidate all cache layers.

    Args:
        publish: If True, publish a pub/sub event to notify other instances.
                 Set to False when called from a pub/sub handler to avoid
                 infinite cross-instance bouncing.
    """
    clear_memory_cache()
    clear_api_key_cache()

    try:
        from src.infra.storage.redis import get_redis_client

        redis_client = get_redis_client()
        await redis_client.delete(_MODELS_CACHE_KEY)
        logger.debug("[LLMModels] Deleted Redis cache")
    except Exception as e:
        logger.warning(f"[LLMModels] Redis delete failed: {e}")

    if publish:
        try:
            from src.infra.llm.pubsub import publish_model_config_changed

            await publish_model_config_changed()
        except Exception as e:
            logger.warning(f"[LLMModels] Pub/sub publish failed: {e}")


async def refresh_models() -> list[dict[str, Any]]:
    """Refresh models from DB, update memory + Redis caches."""
    return await _fetch_from_db(raise_on_error=False)
