"""daemon 连接注册表：Redis hash + TTL 心跳判活（spec §3.2）。同用户仅一个活跃连接。

版本地基（M2 终审）：hash value 存 ``node_id``（旧格式/未上报版本）或
``node_id|version``——daemon connect URL 带 ``?version=``，channel 注册与
心跳时写入，``/api/sandbox/status`` 用 :func:`parse_daemon_version` 反解成
``daemon_version`` 暴露。无 version 的调用方（旧格式写入方）保持纯 node_id，
向后兼容。
"""

from src.infra.storage.redis import get_redis_client

_TTL_SECONDS = 35


def _key(user_id: str) -> str:
    return f"sandbox:clients:{user_id}"


def encode_node_value(node_id: str, version: str = "") -> str:
    """hash value 编码：有版本时 ``node_id|version``，无版本保持纯 node_id。"""
    return f"{node_id}|{version}" if version else node_id


def parse_daemon_version(value: str) -> str:
    """hash value 反解 daemon 版本；旧格式（无 ``|`` 分隔）返回空串。"""
    _, sep, version = value.partition("|")
    return version if sep else ""


class SandboxClientRegistry:
    def _redis(self):
        return get_redis_client()

    async def register(
        self, user_id: str, client_id: str, node_id: str, *, version: str = ""
    ) -> None:
        redis = self._redis()
        await redis.delete(_key(user_id))  # 后连踢前连
        await redis.hset(_key(user_id), client_id, encode_node_value(node_id, version))
        await redis.expire(_key(user_id), _TTL_SECONDS)

    async def heartbeat(
        self, user_id: str, client_id: str, node_id: str, *, version: str = ""
    ) -> None:
        redis = self._redis()
        await redis.hset(_key(user_id), client_id, encode_node_value(node_id, version))
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
