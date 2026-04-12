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

from src.infra.logging import get_logger
from src.kernel.config import settings

logger = get_logger(__name__)

# Redis cache key and TTL
_MODELS_CACHE_KEY = "models:available"
_MODELS_CACHE_TTL = 300  # 5 minutes default TTL

# In-memory cache (per-process)
_memory_cache: Optional[list[dict[str, Any]]] = None

# In-process api_key cache (per-process, not shared via Redis)
_api_key_cache: dict[str, str] = {}


def set_memory_cache(models: list[dict[str, Any]]) -> None:
    """Update the in-memory cache directly."""
    global _memory_cache
    _memory_cache = models


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
    """Store api_key in the in-process cache."""
    _api_key_cache[model_value] = api_key


async def get_default_model(allowed_models: Optional[list[str]] = None) -> str:
    """Return the first available model's value, or empty string.

    Args:
        allowed_models: If provided, only consider models in this list
                       (can be model values or model IDs).
    """
    models = await get_available_models()
    if allowed_models is not None:
        allowed_set = set(allowed_models)
        for m in models:
            # 支持按 value 或 id 匹配
            if m.get("value") in allowed_set or m.get("id") in allowed_set:
                return m.get("value", "")
        return ""
    if models:
        return models[0].get("value", "")
    return ""


async def get_default_model_id(allowed_models: Optional[list[str]] = None) -> str:
    """Return the first available model's ID, or empty string.

    Args:
        allowed_models: If provided, only consider models in this list
                       (model IDs).
    """
    models = await get_available_models()
    if allowed_models is not None:
        allowed_set = set(allowed_models)
        for m in models:
            if m.get("id") in allowed_set or m.get("value") in allowed_set:
                return m.get("id", "")
        return ""
    if models:
        return models[0].get("id", "")
    return ""


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
            model_list = json.loads(cached)
            _memory_cache = model_list
            return model_list
    except Exception as e:
        logger.debug(f"[LLMModels] Redis read failed: {e}")

    # 3. DB
    return await _fetch_from_db()


def _strip_api_keys(model_list: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Remove api_key from model dicts before caching.

    Returns new dicts to avoid mutating the caller's data.
    """
    return [{**m, "api_key": None} for m in model_list]


async def _write_to_caches(model_list: list[dict[str, Any]]) -> None:
    """Write model list to memory and Redis caches (api_keys stripped)."""
    global _memory_cache

    stripped = _strip_api_keys(model_list)
    _memory_cache = stripped

    try:
        from src.infra.storage.redis import get_redis_client

        redis_client = get_redis_client()
        ttl = getattr(settings, "LLM_MODELS_CACHE_TTL", _MODELS_CACHE_TTL)
        await redis_client.set(_MODELS_CACHE_KEY, json.dumps(stripped), ex=ttl)
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
        for m, raw in zip(models, model_list):
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
