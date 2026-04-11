"""
LLM Models Service - Model fetching utilities with distributed caching.

Three-tier cache: memory → Redis → DB.
Supports distributed deployments with pub/sub invalidation.

IMPORTANT: API keys are NOT stored in the cache for security.
At inference time, LLMClient.get_model() does a direct DB lookup
for api_key when needed.
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


def set_memory_cache(models: list[dict[str, Any]]) -> None:
    """Update the in-memory cache directly."""
    global _memory_cache
    _memory_cache = models


def clear_memory_cache() -> None:
    """Clear the in-memory cache only (sync, no I/O)."""
    global _memory_cache
    _memory_cache = None


async def get_default_model(allowed_models: Optional[list[str]] = None) -> str:
    """Return the first available model's id, or empty string.

    Args:
        allowed_models: If provided, only consider models in this list
                       (role-based access control, stores model ids now).
    """
    models = await get_available_models()
    if allowed_models is not None:
        allowed_set = set(allowed_models)
        for m in models:
            if m.get("id") in allowed_set:
                return m.get("id", "")
        return ""
    if models:
        return models[0].get("id", "")
    return ""


async def get_model_by_id(model_id: str) -> Optional[dict[str, Any]]:
    """Get full model config by id (including api_key).

    Used by LLM client to get complete config for inference.
    Falls through: memory cache → Redis → DB.
    """
    # 1. Memory cache
    global _memory_cache
    if _memory_cache is not None:
        for m in _memory_cache:
            if m.get("id") == model_id:
                # Cache may not have api_key, fetch from DB
                try:
                    from src.infra.agent.model_storage import get_model_storage

                    db_model = await get_model_storage().get(model_id)
                    if db_model:
                        full = db_model.model_dump()
                        return full
                except Exception:
                    pass
                return m

    # 2. Redis cache
    try:
        from src.infra.storage.redis import get_redis_client

        redis_client = get_redis_client()
        cached = await redis_client.get(_MODELS_CACHE_KEY)
        if cached:
            model_list = json.loads(cached)
            _memory_cache = model_list
            for m in model_list:
                if m.get("id") == model_id:
                    try:
                        from src.infra.agent.model_storage import get_model_storage

                        db_model = await get_model_storage().get(model_id)
                        if db_model:
                            return db_model.model_dump()
                    except Exception:
                        pass
                    return m
    except Exception:
        pass

    # 3. DB
    try:
        from src.infra.agent.model_storage import get_model_storage

        db_model = await get_model_storage().get(model_id)
        if db_model:
            return db_model.model_dump()
    except Exception as e:
        logger.error(f"[LLMModels] DB query failed for model_id {model_id}: {e}")

    return None


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

    API keys are sensitive and should not be stored in Redis or process memory.
    They are fetched on-demand from DB at inference time.
    """
    for m in model_list:
        m["api_key"] = None
    return model_list


async def _fetch_from_db() -> list[dict[str, Any]]:
    """Query DB, write results into memory + Redis caches."""
    global _memory_cache

    try:
        from src.infra.agent.model_storage import get_model_storage

        storage = get_model_storage()
        models = await storage.list_models(include_disabled=False)
        if not models:
            return []

        model_list = [m.model_dump() for m in models]
        _strip_api_keys(model_list)
        _memory_cache = model_list

        try:
            from src.infra.storage.redis import get_redis_client

            redis_client = get_redis_client()
            ttl = getattr(settings, "LLM_MODELS_CACHE_TTL", _MODELS_CACHE_TTL)
            await redis_client.set(_MODELS_CACHE_KEY, json.dumps(model_list), ex=ttl)
            logger.debug(f"[LLMModels] Cached {len(model_list)} models in Redis (TTL={ttl}s)")
        except Exception as e:
            logger.debug(f"[LLMModels] Redis write failed: {e}")

        return model_list
    except Exception as e:
        logger.error(f"[LLMModels] DB query failed: {e}")
        # Re-raise to caller so it doesn't silently use stale data
        raise


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
    global _memory_cache

    try:
        from src.infra.agent.model_storage import get_model_storage

        storage = get_model_storage()
        models = await storage.list_models(include_disabled=False)
        if models:
            logger.info(f"[LLMModels] Refreshed {len(models)} models from database")
            model_list = [m.model_dump() for m in models]
            _strip_api_keys(model_list)
            _memory_cache = model_list
            try:
                from src.infra.storage.redis import get_redis_client

                redis_client = get_redis_client()
                ttl = getattr(settings, "LLM_MODELS_CACHE_TTL", _MODELS_CACHE_TTL)
                await redis_client.set(_MODELS_CACHE_KEY, json.dumps(model_list), ex=ttl)
            except Exception as e:
                logger.debug(f"[LLMModels] Redis write failed: {e}")
            return model_list
    except Exception as e:
        logger.debug(f"[LLMModels] DB query failed: {e}")

    return []
