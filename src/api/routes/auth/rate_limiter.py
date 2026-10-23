"""
Rate limiting helper for auth routes
"""

import re
from collections.abc import Awaitable
from typing import cast

from src.infra.logging import get_logger
from src.infra.storage.redis import get_redis_client

logger = get_logger(__name__)


class RateLimiter:
    """Simple Redis-based rate limiter for email endpoints."""

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
            redis = get_redis_client()
            current_count = int(
                await cast(
                    Awaitable[str],
                    redis.eval(
                        "local n = redis.call('INCR', KEYS[1]); "
                        "if n == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end; return n",
                        1,
                        key,
                        str(window_seconds),
                    ),
                )
            )
            return current_count <= max_requests, max(0, max_requests - current_count)
        except Exception as e:
            from src.kernel.errors import AppError, ErrorCode

            logger.error("[RateLimiter] Redis error: %s", e)
            raise AppError(ErrorCode.SERVICE_UNAVAILABLE) from e

    async def close(self) -> None:
        """No-op: Redis client is managed by get_redis_client() singleton."""
        pass


_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    """Get singleton rate limiter instance."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


async def close_rate_limiter() -> None:
    """Release the singleton rate limiter without creating it during shutdown."""
    global _rate_limiter
    limiter = _rate_limiter
    _rate_limiter = None
    if limiter is not None:
        await limiter.close()
