"""daemon 连接注册表：Redis hash + TTL 心跳判活（spec §3.2）。同用户仅一个活跃连接。"""

from src.infra.storage.redis import get_redis_client

_TTL_SECONDS = 35


def _key(user_id: str) -> str:
    return f"sandbox:clients:{user_id}"


class SandboxClientRegistry:
    def _redis(self):
        return get_redis_client()

    async def register(self, user_id: str, client_id: str, node_id: str) -> None:
        redis = self._redis()
        await redis.delete(_key(user_id))  # 后连踢前连
        await redis.hset(_key(user_id), client_id, node_id)
        await redis.expire(_key(user_id), _TTL_SECONDS)

    async def heartbeat(self, user_id: str, client_id: str, node_id: str) -> None:
        redis = self._redis()
        await redis.hset(_key(user_id), client_id, node_id)
        await redis.expire(_key(user_id), _TTL_SECONDS)

    async def unregister(self, user_id: str, client_id: str) -> None:
        redis = self._redis()
        await redis.hdel(_key(user_id), client_id)
        if not await redis.hgetall(_key(user_id)):
            await redis.delete(_key(user_id))

    async def is_online(self, user_id: str) -> bool:
        return bool(await self._redis().exists(_key(user_id)))

    async def get_active(self, user_id: str) -> tuple[str, str] | None:
        fields = await self._redis().hgetall(_key(user_id))
        if not fields:
            return None
        client_id = next(iter(fields))
        return client_id, fields[client_id]
