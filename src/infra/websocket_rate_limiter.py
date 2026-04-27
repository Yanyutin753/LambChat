"""WebSocket 速率限制（基于 Redis）"""

from src.infra.logging import get_logger
from src.infra.storage.redis import create_redis_client

logger = get_logger(__name__)


class WebSocketRateLimiter:
    """WebSocket 连接速率限制器，仅对认证失败计数"""

    def __init__(self, max_failures: int = 5, window_seconds: int = 300):
        self.max_failures = max_failures
        self.window_seconds = window_seconds
        self._redis = None

    def _get_redis(self):
        if self._redis is None:
            self._redis = create_redis_client(isolated_pool=True)
        return self._redis

    async def check(self, client_ip: str) -> tuple[bool, int]:
        """
        检查 IP 是否被封禁（不修改计数）

        Returns:
            (是否允许连接, 剩余封禁时间秒数)
        """
        key = f"ws:auth:fail:{client_ip}"
        redis = self._get_redis()
        count_str = await redis.get(key)
        if count_str is None:
            return True, 0
        count = int(count_str)
        if count >= self.max_failures:
            ttl = await redis.ttl(key)
            return False, max(ttl, 0)
        return True, 0

    async def record_failure(self, client_ip: str) -> tuple[bool, int]:
        """
        记录一次认证失败

        Returns:
            (是否应该封禁, 当前失败次数)
        """
        key = f"ws:auth:fail:{client_ip}"
        redis = self._get_redis()
        count = await redis.incr(key)
        if count == 1:
            await redis.expire(key, self.window_seconds)
        should_block = count >= self.max_failures
        if should_block:
            logger.warning(f"[WS] IP {client_ip} blocked after {count} failures")
        return should_block, count

    async def reset(self, client_ip: str) -> None:
        """认证成功时重置失败计数"""
        await self._get_redis().delete(f"ws:auth:fail:{client_ip}")


_limiter: WebSocketRateLimiter | None = None


def get_ws_rate_limiter() -> WebSocketRateLimiter:
    global _limiter
    if _limiter is None:
        _limiter = WebSocketRateLimiter()
    return _limiter
