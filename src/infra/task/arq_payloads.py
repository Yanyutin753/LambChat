from __future__ import annotations

import json
from typing import Any

from src.infra.async_utils import run_blocking_io
from src.infra.storage.redis import get_redis_client

DEFAULT_TASK_ARQ_PAYLOAD_TTL_SECONDS = 60 * 60 * 24
TASK_ARQ_PAYLOAD_PREFIX = "task:arq:payload:"
TASK_ARQ_PAYLOAD_MAX_BYTES = 2 * 1024 * 1024
USER_MESSAGE_SEARCH_INDEX_PAYLOAD_PREFIX = "task:arq:user-message-search-index:"


class TaskArqPayloadStore:
    """Persist serializable task context for arq workers."""

    def __init__(self, redis: Any | None = None, ttl_seconds: int | None = None) -> None:
        self._redis = redis
        self._ttl_seconds = ttl_seconds or DEFAULT_TASK_ARQ_PAYLOAD_TTL_SECONDS

    @property
    def redis(self) -> Any:
        if self._redis is None:
            self._redis = get_redis_client()
        return self._redis

    async def save(self, run_id: str, payload: dict[str, Any]) -> None:
        encoded = await run_blocking_io(json.dumps, payload, ensure_ascii=False)
        size = len(encoded.encode("utf-8"))
        if size > TASK_ARQ_PAYLOAD_MAX_BYTES:
            raise ValueError(
                f"task payload too large: {size} bytes (max {TASK_ARQ_PAYLOAD_MAX_BYTES})"
            )
        await self.redis.set(
            self._key(run_id),
            encoded,
            ex=self._ttl_seconds,
        )

    async def load(self, run_id: str) -> dict[str, Any] | None:
        raw = await self.redis.get(self._key(run_id))
        if raw is None:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return await run_blocking_io(json.loads, raw)

    async def delete(self, run_id: str) -> bool:
        return bool(await self.redis.delete(self._key(run_id)))

    @staticmethod
    def _key(run_id: str) -> str:
        return f"{TASK_ARQ_PAYLOAD_PREFIX}{run_id}"


class UserMessageSearchIndexPayloadStore(TaskArqPayloadStore):
    """Persist user-message index input for a distributed ARQ worker."""

    @staticmethod
    def _key(run_id: str) -> str:
        return f"{USER_MESSAGE_SEARCH_INDEX_PAYLOAD_PREFIX}{run_id}"
