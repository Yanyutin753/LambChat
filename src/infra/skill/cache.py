"""
Skill cache mixin for Redis caching operations
"""

import json
import logging
from typing import Any, Optional

from src.infra.skill.constants import (
    MCP_TOOLS_METADATA_CACHE_TTL,
    MCP_TOOLS_METADATA_KEY_PREFIX,
    SKILLS_CACHE_KEY_PREFIX,
)
from src.infra.storage.redis import get_redis_client

logger = logging.getLogger(__name__)


class SkillCacheMixin:
    """
    Mixin providing Redis caching functionality for skills.

    This mixin handles:
    - User skills cache invalidation
    - MCP tools metadata caching
    """

    async def _invalidate_user_skills_cache(self, user_id: str) -> None:
        """Invalidate skills Redis cache for a specific user"""
        cache_key = f"{SKILLS_CACHE_KEY_PREFIX}{user_id}"
        try:
            redis_client = get_redis_client()
            result = await redis_client.delete(cache_key)
            if result > 0:
                logger.info(f"[Skills Cache] Invalidated Redis cache for user {user_id}")
        except Exception as e:
            logger.warning(f"[Skills Cache] Redis delete failed for user {user_id}: {e}")

    async def _invalidate_all_skills_cache(self) -> None:
        """Invalidate all skills Redis cache (system config changed)"""
        try:
            redis_client = get_redis_client()
            keys = await redis_client.keys(f"{SKILLS_CACHE_KEY_PREFIX}*")
            if keys:
                deleted = 0
                for key in keys:
                    if await redis_client.delete(key) > 0:
                        deleted += 1
                logger.info(f"[Skills Cache] Invalidated {deleted} Redis cache entries")
        except Exception as e:
            logger.warning(f"[Skills Cache] Redis keys/delete failed: {e}")

    async def get_mcp_tools(
        self,
        user_id: str,
        fetch_func,
        cache_key_suffix: Optional[str] = None,
        ttl: int = MCP_TOOLS_METADATA_CACHE_TTL,
    ) -> list[dict[str, Any]]:
        """
        Get MCP tools (with Redis cache)

        Check Redis cache first, return if cached, otherwise call fetch_func
        and cache the result.

        Args:
            user_id: User ID
            fetch_func: Async function to fetch MCP tools, signature: async def fetch_func() -> list[dict]
            cache_key_suffix: Cache key suffix (optional, for different tool types)
            ttl: Cache expiration time in seconds, default 30 minutes

        Returns:
            MCP tools list
        """
        # Build cache key
        cache_key = f"{MCP_TOOLS_METADATA_KEY_PREFIX}{user_id}"
        if cache_key_suffix:
            cache_key = f"{cache_key}:{cache_key_suffix}"

        # Try to get from Redis cache
        try:
            redis_client = get_redis_client()
            cached_data = await redis_client.get(cache_key)

            if cached_data:
                tools = json.loads(cached_data)
                logger.info(f"[MCP Tools Cache] Hit for user {user_id}, {len(tools)} tools")
                return tools
        except Exception as e:
            logger.warning(f"[MCP Tools Cache] Redis get failed for user {user_id}: {e}")

        # Cache miss, call fetch_func to get data
        logger.info(f"[MCP Tools Cache] Miss for user {user_id}")
        tools = await fetch_func()

        # Store in Redis cache
        try:
            redis_client = get_redis_client()
            await redis_client.set(cache_key, json.dumps(tools), ex=ttl)
            logger.info(f"[MCP Tools Cache] Cached {len(tools)} tools for user {user_id}")
        except Exception as e:
            logger.warning(f"[MCP Tools Cache] Redis set failed for user {user_id}: {e}")

        return tools

    async def invalidate_mcp_tools_cache(
        self, user_id: str, cache_key_suffix: Optional[str] = None
    ) -> bool:
        """
        Invalidate MCP tools cache

        Args:
            user_id: User ID
            cache_key_suffix: Cache key suffix (optional)

        Returns:
            Whether cache was successfully deleted
        """
        cache_key = f"{MCP_TOOLS_METADATA_KEY_PREFIX}{user_id}"
        if cache_key_suffix:
            cache_key = f"{cache_key}:{cache_key_suffix}"

        try:
            redis_client = get_redis_client()
            result = await redis_client.delete(cache_key)
            if result > 0:
                logger.info(f"[MCP Tools Cache] Invalidated cache for user {user_id}")
                return True
        except Exception as e:
            logger.warning(f"[MCP Tools Cache] Redis delete failed for user {user_id}: {e}")

        return False
