"""
Redis 存储实现
"""

import json
from functools import lru_cache
from typing import Any, Optional

import redis.asyncio as redis

from src.infra.storage.base import StorageBase
from src.kernel.config import settings


@lru_cache
def get_redis_client():
    """获取 Redis 客户端（单例）"""
    return redis.from_url(
        settings.REDIS_URL,
        password=settings.REDIS_PASSWORD,
        encoding="utf-8",
        decode_responses=True,
    )


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
            return json.loads(value)
        except json.JSONDecodeError:
            return value

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """设置数据"""
        if isinstance(value, (dict, list)):
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
        """获取匹配的键列表"""
        return await self.client.keys(pattern)

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
        result = []
        for entry_id, fields in entries:
            parsed = {}
            for k, v in fields.items():
                try:
                    parsed[k] = json.loads(v)
                except (json.JSONDecodeError, TypeError):
                    parsed[k] = v
            result.append((entry_id, parsed))
        return result

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

        parsed_result = []
        for stream_key, entries in result or []:
            parsed_entries = []
            for entry_id, fields in entries:
                parsed = {}
                for k, v in fields.items():
                    try:
                        parsed[k] = json.loads(v)
                    except (json.JSONDecodeError, TypeError):
                        parsed[k] = v
                parsed_entries.append((entry_id, parsed))
            parsed_result.append((stream_key, parsed_entries))

        return parsed_result

    async def xdel(self, stream_key: str, entry_id: str) -> int:
        """Delete entry from stream"""
        return await self.client.xdel(stream_key, entry_id)

    async def xlen(self, stream_key: str) -> int:
        """Get stream length"""
        return await self.client.xlen(stream_key)
