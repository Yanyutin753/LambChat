"""
Redis 存储实现
"""

import json
from functools import lru_cache
from typing import Any, Optional

import redis.asyncio as redis
from redis.asyncio import Redis

from src.infra.async_utils import run_long_blocking_io
from src.infra.logging import get_logger
from src.infra.storage.base import StorageBase
from src.kernel.config import settings

logger = get_logger(__name__)
_UNSET = object()
REDIS_STORAGE_KEYS_LIMIT = 1000


def _parse_stream_fields_sync(fields: dict) -> dict:
    parsed = {}
    for key, value in fields.items():
        try:
            parsed[key] = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            parsed[key] = value
    return parsed


def _parse_stream_entries_sync(entries: list[tuple[str, dict]]) -> list[tuple[str, dict]]:
    return [(entry_id, _parse_stream_fields_sync(fields)) for entry_id, fields in entries]


def _parse_stream_read_result_sync(
    result: list[tuple[str, list[tuple[str, dict]]]],
) -> list[tuple[str, list[tuple[str, dict]]]]:
    return [(stream_key, _parse_stream_entries_sync(entries)) for stream_key, entries in result]


def _redis_pool_kwargs(
    *, decode_responses: bool = True, socket_timeout: Any = _UNSET
) -> dict[str, Any]:
    kwargs = {
        "encoding": "utf-8",
        "decode_responses": decode_responses,
        "max_connections": 50,
        "socket_timeout": 10,
        "socket_connect_timeout": 5,
        "retry_on_timeout": True,
    }
    if settings.REDIS_PASSWORD:
        kwargs["password"] = settings.REDIS_PASSWORD
    if socket_timeout is not _UNSET:
        kwargs["socket_timeout"] = socket_timeout
    return kwargs


@lru_cache
def get_redis_connection_pool():
    """Get the shared Redis connection pool for this process."""
    return redis.ConnectionPool.from_url(settings.REDIS_URL, **_redis_pool_kwargs())


@lru_cache
def get_binary_redis_connection_pool():
    """二进制安全连接池（decode_responses=False）：沙箱帧通道专用。

    共享池 decode_responses=True 在读取时把任意 bytes 按 UTF-8 解码，而
    帧通道（sandbox:stream / sandbox:upblob list）存的是裸二进制帧——任何
    非 UTF-8 的真实文件内容都会在 lpop 时抛 UnicodeDecodeError（2026-09-07
    生产事故：本地沙箱 reveal_file/artifact 全线误报 file_not_found_or_empty）。
    """
    return redis.ConnectionPool.from_url(
        settings.REDIS_URL, **_redis_pool_kwargs(decode_responses=False)
    )


def create_redis_client(*, isolated_pool: bool = False, socket_timeout: Any = _UNSET) -> Redis:
    """Create a Redis client with the project's standard connection settings."""
    if isolated_pool:
        return Redis(
            connection_pool=redis.ConnectionPool.from_url(
                settings.REDIS_URL,
                **_redis_pool_kwargs(socket_timeout=socket_timeout),
            ),
            auto_close_connection_pool=True,
        )
    return Redis(connection_pool=get_redis_connection_pool())


def get_redis_client() -> Redis:
    """Get a Redis client backed by the shared connection pool."""
    return create_redis_client()


def get_binary_redis_client() -> Redis:
    """Get a binary-safe Redis client (decode_responses=False) for frame channels."""
    return Redis(connection_pool=get_binary_redis_connection_pool())


async def close_redis_client() -> None:
    """关闭 Redis 连接池"""
    try:
        pools: list = []
        if get_redis_connection_pool.cache_info().currsize > 0:
            pools.append(get_redis_connection_pool())
        if get_binary_redis_connection_pool.cache_info().currsize > 0:
            pools.append(get_binary_redis_connection_pool())
        if not pools:
            return
        for pool in pools:
            await pool.aclose()
        get_redis_connection_pool.cache_clear()
        get_binary_redis_connection_pool.cache_clear()
        logger.info("Redis connection pool closed")
    except Exception as e:
        logger.warning(f"Error closing Redis client: {e}")


class RedisStorage(StorageBase):
    """
    Redis 存储实现
    """

    def __init__(self):
        self._client = None

    @property
    def client(self):
        """延迟加载 Redis 客户端"""
        if self._client is None:
            self._client = get_redis_client()
        return self._client

    async def get(self, key: str) -> Optional[Any]:
        """获取数据"""
        value = await self.client.get(key)
        if value is None:
            return None
        try:
            # json.loads 是微秒级纯 CPU 调用，走线程池的开销远大于收益，直接内联
            return json.loads(value)
        except json.JSONDecodeError:
            return value

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """设置数据"""
        if isinstance(value, (dict, list)):
            # 微秒级纯 CPU 序列化，内联执行避免线程池往返
            value = json.dumps(value)
        await self.client.set(key, value, ex=ttl)

    async def delete(self, key: str) -> bool:
        """删除数据"""
        result = await self.client.delete(key)
        return result > 0

    async def exists(self, key: str) -> bool:
        """检查键是否存在"""
        return await self.client.exists(key) > 0

    async def keys(self, pattern: str) -> list[str]:
        """获取匹配的键列表，使用 SCAN 且限制结果数量避免阻塞和内存膨胀。"""
        cursor: int | str = 0
        keys: list[str] = []
        while True:
            cursor, batch = await self.client.scan(cursor=cursor, match=pattern, count=100)
            remaining = REDIS_STORAGE_KEYS_LIMIT - len(keys)
            keys.extend(str(key) for key in batch[:remaining])
            if len(keys) >= REDIS_STORAGE_KEYS_LIMIT:
                return keys
            if int(cursor) == 0:
                return keys

    async def expire(self, key: str, ttl: int) -> bool:
        """设置过期时间"""
        return await self.client.expire(key, ttl)

    async def ttl(self, key: str) -> int:
        """获取剩余过期时间"""
        return await self.client.ttl(key)

    async def incr(self, key: str) -> int:
        """自增"""
        return await self.client.incr(key)

    async def decr(self, key: str) -> int:
        """自减"""
        return await self.client.decr(key)

    async def xadd(
        self,
        stream_key: str,
        fields: dict,
        maxlen: Optional[int] = None,
    ) -> str:
        """
        Add entry to Redis Stream

        Args:
            stream_key: Stream key name
            fields: Dictionary of field-value pairs
            maxlen: Maximum stream length (approximate)

        Returns:
            Entry ID
        """
        # Serialize dict values
        serialized = {}
        for k, v in fields.items():
            if isinstance(v, dict):
                # 微秒级纯 CPU 序列化，内联执行避免线程池往返
                serialized[k] = json.dumps(v)
            else:
                serialized[k] = str(v)

        if maxlen:
            return await self.client.xadd(stream_key, serialized, maxlen=maxlen)
        return await self.client.xadd(stream_key, serialized)

    async def xrange(
        self,
        stream_key: str,
        start: str = "-",
        end: str = "+",
        count: Optional[int] = None,
        *,
        min: Optional[str] = None,  # Alias for start (redis-py compatibility)
        max: Optional[str] = None,  # Alias for end (redis-py compatibility)
    ) -> list[tuple[str, dict]]:
        """
        Read entries from Redis Stream by range

        Args:
            stream_key: Stream key name
            start: Start ID (default: "-")
            end: End ID (default: "+")
            count: Maximum number of entries
            min: Alias for start (redis-py compatibility)
            max: Alias for end (redis-py compatibility)

        Returns:
            List of (id, fields) tuples
        """
        # Support both start/end and min/max parameter names
        actual_start = min if min is not None else start
        actual_end = max if max is not None else end
        # redis-py uses 'min' and 'max' as parameter names
        entries = await self.client.xrange(
            stream_key, min=actual_start, max=actual_end, count=count
        )
        return await run_long_blocking_io(_parse_stream_entries_sync, entries)

    async def xread(
        self,
        streams: dict[str, str],
        count: Optional[int] = None,
        block: Optional[int] = None,
    ) -> list[tuple[str, list[tuple[str, dict]]]]:
        """
        Read from multiple streams

        Args:
            streams: Dict of {stream_key: last_id}
            count: Maximum entries per stream
            block: Block timeout in milliseconds

        Returns:
            List of (stream_key, [(id, fields), ...])
        """
        # Validate streams dict is not empty
        if not streams:
            return []

        # Filter out empty keys - redis-py requires streams as keyword arg with dict
        filtered_streams = {k: v for k, v in streams.items() if k and v}
        if not filtered_streams:
            return []

        try:
            if block:
                result = await self.client.xread(
                    streams=filtered_streams,
                    count=count,
                    block=block,  # type: ignore[arg-type]
                )
            else:
                result = await self.client.xread(streams=filtered_streams, count=count)  # type: ignore[arg-type]
        except Exception as e:
            # Handle case where stream doesn't exist
            if "no such key" in str(e).lower() or "doesn't exist" in str(e).lower():
                return []
            raise

        return await run_long_blocking_io(_parse_stream_read_result_sync, result or [])

    async def xdel(self, stream_key: str, entry_id: str) -> int:
        """Delete entry from stream"""
        return await self.client.xdel(stream_key, entry_id)

    async def xlen(self, stream_key: str) -> int:
        """Get stream length"""
        return await self.client.xlen(stream_key)
