"""Ownership-checked Redis leases for outbound bot connections."""

from __future__ import annotations

import secrets
from typing import Any

from src.infra.storage.redis import get_redis_client

_COMPARE_EXPIRE = """
if redis.call('get', KEYS[1]) == ARGV[1] then
 return redis.call('expire', KEYS[1], ARGV[2])
end
return 0
"""
_COMPARE_DELETE = """
if redis.call('get', KEYS[1]) == ARGV[1] then
 return redis.call('del', KEYS[1])
end
return 0
"""


class ChatLease:
    def __init__(self, key: str, ttl: int = 90):
        self.key = key
        self.ttl = ttl
        self.owner = secrets.token_hex(16)

    async def acquire(self) -> bool:
        return bool(await get_redis_client().set(self.key, self.owner, nx=True, ex=self.ttl))

    async def renew(self) -> bool:
        client: Any = get_redis_client()
        return bool(await client.eval(_COMPARE_EXPIRE, 1, self.key, self.owner, self.ttl))

    async def release(self) -> None:
        client: Any = get_redis_client()
        await client.eval(_COMPARE_DELETE, 1, self.key, self.owner)


async def release_message(redis: Any, key: str, owner: str) -> None:
    await redis.eval(_COMPARE_DELETE, 1, key, owner)
