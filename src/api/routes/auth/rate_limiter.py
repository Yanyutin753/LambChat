"""
Rate limiting helper for auth routes
"""

import logging
import re
from typing import Optional

from redis import asyncio as aioredis

from src.kernel.config import settings

logger = logging.getLogger(__name__)


class RateLimiter:
    """Simple Redis-based rate limiter for email endpoints."""

    def __init__(self) -> None:
        self._redis: Optional[aioredis.Redis] = None

    @staticmethod
    def _safe_key_part(value: str) -> str:
        """Sanitize value for use in Redis key to prevent injection.

        Args:
            value: Raw input value (IP or email)

        Returns:
            Safe string for Redis key (alphanumeric, dots, hyphens, @ only)
        """
        # 只保留安全字符：字母、数字、点、连字符、@、下划线
        return re.sub(r"[^a-zA-Z0-9.@_-]", "", value)[:100]

    @staticmethod
    def build_key(prefix: str, identifier: str) -> str:
        """Build a safe Redis key from prefix and identifier.

        Args:
            prefix: Key prefix (e.g., "ratelimit:forgot-password:ip")
            identifier: User-provided identifier (IP or email)

        Returns:
            Safe Redis key
        """
        safe_id = RateLimiter._safe_key_part(identifier)
        return f"{prefix}:{safe_id}"

    def _get_redis(self) -> aioredis.Redis:
        """Lazy load Redis client."""
        if self._redis is None:
            self._redis = aioredis.from_url(
                settings.REDIS_URL, password=settings.REDIS_PASSWORD or None, decode_responses=True
            )
        return self._redis

    async def check_rate_limit(
        self,
        key: str,
        max_requests: int,
        window_seconds: int,
    ) -> tuple[bool, int]:
        """Check if request is within rate limit.

        Args:
            key: Redis key for rate limiting (should be built with build_key())
            max_requests: Maximum requests allowed in window
            window_seconds: Time window in seconds

        Returns:
            Tuple of (is_allowed, remaining_requests)
        """
        try:
            redis = self._get_redis()
            current = await redis.get(key)

            if current is None:
                await redis.setex(key, window_seconds, 1)
                return True, max_requests - 1

            current_count = int(current)
            if current_count >= max_requests:
                ttl = await redis.ttl(key)
                logger.warning("[RateLimiter] Rate limit exceeded for %s, TTL=%d", key, ttl)
                return False, 0

            await redis.incr(key)
            return True, max_requests - current_count - 1

        except Exception as e:
            # If Redis fails, allow the request (fail open)
            logger.error("[RateLimiter] Redis error: %s", e)
            return True, max_requests

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis is not None:
            await self._redis.close()
            self._redis = None


_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get singleton rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter
