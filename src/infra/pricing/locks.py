"""Pricing 分布式锁：同步与回填的多副本互斥。

Redis SET NX EX 获取 + Lua 比较删除释放（同 scheduler/locks 模式）。
Redis 不可用时由调用方决定退化行为（单机场景不应中断主流程）。
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable
from typing import Any, Optional, cast

from src.infra.logging import get_logger
from src.infra.storage.redis import get_redis_client

logger = get_logger(__name__)

# Lua: 只释放自己持有的锁
_RELEASE_LOCK_LUA = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
else
    return 0
end
"""


async def acquire_pricing_lock(lock_key: str, ttl: int) -> Optional[str]:
    """尝试获取锁；成功返回 token，被其他副本持有时返回 None。

    Redis 异常向上抛出，由调用方决定是否退化为本地执行。
    """
    redis = get_redis_client()
    token = f"{uuid.uuid4().hex[:16]}"
    acquired = await redis.set(lock_key, token, nx=True, ex=ttl)
    if acquired:
        logger.debug("[PricingLock] acquired %s", lock_key)
        return token
    logger.debug("[PricingLock] contended %s", lock_key)
    return None


async def release_pricing_lock(lock_key: str, token: str) -> None:
    """释放锁（best-effort，持锁过期也能自动释放）。"""
    try:
        redis = get_redis_client()
        await cast(Awaitable[Any], redis.eval(_RELEASE_LOCK_LUA, 1, lock_key, token))
    except Exception as e:
        logger.warning(f"[PricingLock] 释放 {lock_key} 失败: {e}")
