"""Distributed, throttled session search backfill worker."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

from src.infra.logging import get_logger
from src.infra.session.storage import SessionStorage
from src.infra.storage.redis import create_redis_client

logger = get_logger(__name__)

BACKFILL_LOCK_KEY = "session:search_backfill:lock"
CONVERSATION_BACKFILL_LOCK_KEY = "conversation:search_backfill:lock"
BACKFILL_LOCK_TTL_SECONDS = 30
BACKFILL_BATCH_SIZE = 20
BACKFILL_BATCH_DELAY_SECONDS = 0.25
BACKFILL_LOCK_RENEW_INTERVAL_SECONDS = BACKFILL_LOCK_TTL_SECONDS / 3

_RELEASE_LOCK_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("del", KEYS[1])
else
    return 0
end
"""

_RENEW_LOCK_LUA = """
if redis.call("get", KEYS[1]) == ARGV[1] then
    return redis.call("expire", KEYS[1], ARGV[2])
else
    return 0
end
"""


class SessionSearchBackfillWorker:
    """Backfill stale session search indexes one batch at a time."""

    def __init__(
        self,
        *,
        storage: SessionStorage | None = None,
        redis_client: Any | None = None,
        batch_size: int = BACKFILL_BATCH_SIZE,
        batch_delay_seconds: float = BACKFILL_BATCH_DELAY_SECONDS,
        lock_ttl_seconds: int = BACKFILL_LOCK_TTL_SECONDS,
        renew_interval_seconds: float = BACKFILL_LOCK_RENEW_INTERVAL_SECONDS,
    ) -> None:
        self._storage = storage or SessionStorage()
        self._redis = redis_client
        self._batch_size = batch_size
        self._batch_delay_seconds = batch_delay_seconds
        self._lock_ttl_seconds = lock_ttl_seconds
        self._renew_interval_seconds = renew_interval_seconds
        self._lock_key = BACKFILL_LOCK_KEY
        self._lock_value: str | None = None
        self._instance_id = str(uuid.uuid4())
        self._renew_task: asyncio.Task[None] | None = None

    async def run_once(self) -> int:
        """Backfill a single batch if this instance owns the distributed lock."""
        acquired = await self._acquire_lock()
        if not acquired:
            return 0

        self._start_lock_renewal()
        try:
            return await self._run_batch()
        finally:
            await self._stop_lock_renewal()
            await self._release_lock()

    async def run_until_complete(self) -> int:
        """Run batches until no stale sessions remain."""
        rebuilt = 0
        while True:
            batch_count = await self.run_once()
            if batch_count <= 0:
                return rebuilt
            rebuilt += batch_count
            await asyncio.sleep(self._batch_delay_seconds)

    async def close(self) -> None:
        await self._stop_lock_renewal()
        redis_client = self._redis
        self._redis = None
        if redis_client is not None:
            try:
                await redis_client.aclose()
            except Exception:
                return

    async def _run_batch(self) -> int:
        return await self._storage.backfill_search_indexes(batch_size=self._batch_size)

    async def _acquire_lock(self) -> bool:
        redis_client = self._get_redis()
        try:
            self._lock_value = self._instance_id
            acquired = await redis_client.set(
                self._lock_key,
                self._lock_value,
                nx=True,
                ex=self._lock_ttl_seconds,
            )
            return bool(acquired)
        except Exception as exc:
            logger.warning("Failed to acquire session backfill lock: %s", exc)
            return False

    def _start_lock_renewal(self) -> None:
        if self._renew_interval_seconds <= 0:
            return
        if self._renew_task is None or self._renew_task.done():
            self._renew_task = asyncio.create_task(self._renew_lock_loop())

    async def _stop_lock_renewal(self) -> None:
        renew_task = self._renew_task
        self._renew_task = None
        if renew_task is None:
            return
        renew_task.cancel()
        try:
            await renew_task
        except asyncio.CancelledError:
            pass

    async def _renew_lock_loop(self) -> None:
        try:
            while True:
                await asyncio.sleep(self._renew_interval_seconds)
                await self._renew_lock()
        except asyncio.CancelledError:
            return

    async def _renew_lock(self) -> None:
        redis_client = self._redis
        lock_value = self._lock_value
        if redis_client is None or not lock_value:
            return
        try:
            renewed = await redis_client.eval(
                _RENEW_LOCK_LUA,
                1,
                self._lock_key,
                lock_value,
                self._lock_ttl_seconds,
            )  # type: ignore[misc]
            if not renewed:
                logger.warning("Session backfill lock was lost before renewal")
        except Exception as exc:
            logger.warning("Failed to renew session backfill lock: %s", exc)

    async def _release_lock(self) -> None:
        redis_client = self._redis
        lock_value = self._lock_value
        self._lock_value = None
        if redis_client is None or not lock_value:
            return
        try:
            await redis_client.eval(_RELEASE_LOCK_LUA, 1, self._lock_key, lock_value)  # type: ignore[misc]
        except Exception as exc:
            logger.warning("Failed to release session backfill lock: %s", exc)

    def _get_redis(self):
        if self._redis is None:
            self._redis = create_redis_client(isolated_pool=True)
        return self._redis


class ConversationHistoryBackfillWorker(SessionSearchBackfillWorker):
    """Backfill versioned per-run conversation search projections."""

    def __init__(self, *, service: Any | None = None, **kwargs: Any) -> None:
        from src.infra.session.conversation_history import ConversationHistoryService

        self._service = service or ConversationHistoryService()
        super().__init__(**kwargs)
        self._lock_key = CONVERSATION_BACKFILL_LOCK_KEY

    async def _run_batch(self) -> int:
        return await self._service.backfill_indexes(batch_size=self._batch_size)
