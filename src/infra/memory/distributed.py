"""
Distributed Memory Support - Redis pub/sub for cache invalidation + distributed locks.

When a memory is modified on one instance, this publishes a Redis message so
other instances invalidate their local index cache.  A Redis-based distributed
lock prevents concurrent consolidation across instances.

Follows the same pub/sub pattern as SettingsPubSub.
"""

import json
import uuid
from typing import Any, Dict, Optional

from src.infra.logging import get_logger
from src.infra.pubsub_hub import get_pubsub_hub
from src.infra.storage.redis import get_redis_client

logger = get_logger(__name__)

# Lua script: only delete lock key if value matches instance_id (prevents releasing another instance's lock)
_RELEASE_LOCK_LUA = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
else
    return 0
end
"""

# Redis channel for memory cache invalidation
MEMORY_INVALIDATION_CHANNEL = "memory:invalidated"

# Distributed lock keys
CONSOLIDATION_LOCK_KEY = "memory:consolidation_lock:{user_id}"
CONSOLIDATION_LOCK_TTL = 120  # seconds
AUTO_CAPTURE_LOCK_KEY = "memory:auto_capture_lock:{user_id}"
AUTO_CAPTURE_LOCK_TTL = 30  # seconds

# ============================================================================
# Publisher helpers (called from NativeMemoryBackend)
# ============================================================================


async def publish_memory_invalidation(user_id: str) -> None:
    """Publish a cache invalidation message for a user.

    Called after retain, delete, and consolidate_memories so other instances
    drop stale cache entries.
    """
    try:
        redis_client = get_redis_client()
        await redis_client.publish(
            MEMORY_INVALIDATION_CHANNEL,
            json.dumps({"user_id": user_id}),
        )
    except Exception as e:
        logger.debug("[Memory] Failed to publish invalidation for %s: %s", user_id, e)


# ============================================================================
# Distributed lock for consolidation
# ============================================================================


async def acquire_consolidation_lock(user_id: str, instance_id: str) -> str:
    """Try to acquire a distributed lock for memory consolidation.

    Uses Redis SETNX with TTL.

    Returns one of:
    - "acquired": this instance owns the lock
    - "not_acquired": another instance already owns the lock
    - "unavailable": lock state could not be determined
    """
    try:
        redis_client = get_redis_client()
        lock_key = CONSOLIDATION_LOCK_KEY.format(user_id=user_id)
        acquired = await redis_client.set(lock_key, instance_id, nx=True, ex=CONSOLIDATION_LOCK_TTL)
        return "acquired" if acquired else "not_acquired"
    except Exception as e:
        logger.debug("[Memory] Failed to acquire consolidation lock for %s: %s", user_id, e)
        return "unavailable"


async def release_consolidation_lock(user_id: str, instance_id: str) -> None:
    """Release the consolidation lock (only if we own it)."""
    try:
        redis_client = get_redis_client()
        lock_key = CONSOLIDATION_LOCK_KEY.format(user_id=user_id)
        await redis_client.eval(_RELEASE_LOCK_LUA, 1, lock_key, instance_id)  # type: ignore[misc]
    except Exception as e:
        logger.debug("[Memory] Failed to release consolidation lock for %s: %s", user_id, e)


async def acquire_auto_capture_lock(user_id: str, instance_id: str) -> str:
    """Try to acquire a distributed lock for background auto memory capture."""
    try:
        redis_client = get_redis_client()
        lock_key = AUTO_CAPTURE_LOCK_KEY.format(user_id=user_id)
        acquired = await redis_client.set(lock_key, instance_id, nx=True, ex=AUTO_CAPTURE_LOCK_TTL)
        return "acquired" if acquired else "not_acquired"
    except Exception as e:
        logger.debug("[Memory] Failed to acquire auto-capture lock for %s: %s", user_id, e)
        return "unavailable"


async def release_auto_capture_lock(user_id: str, instance_id: str) -> None:
    """Release the auto-capture lock (only if we own it)."""
    try:
        redis_client = get_redis_client()
        lock_key = AUTO_CAPTURE_LOCK_KEY.format(user_id=user_id)
        await redis_client.eval(_RELEASE_LOCK_LUA, 1, lock_key, instance_id)  # type: ignore[misc]
    except Exception as e:
        logger.debug("[Memory] Failed to release auto-capture lock for %s: %s", user_id, e)


# ============================================================================
# Pub/Sub Listener
# ============================================================================


class MemoryPubSub:
    """Redis Pub/Sub listener for memory cache invalidation events.

    When another instance modifies a user's memories, this listener
    invalidates the local index cache for that user.
    """

    def __init__(self):
        self._subscription_token: Optional[str] = None
        self._running = False
        self._instance_id: str = uuid.uuid4().hex[:8]

    @property
    def instance_id(self) -> str:
        return self._instance_id

    async def start_listener(self) -> None:
        """Start listening for memory invalidation notifications."""
        if self._running:
            return

        hub = get_pubsub_hub()
        self._subscription_token = hub.subscribe(
            MEMORY_INVALIDATION_CHANNEL,
            self._handle_message,
        )
        await hub.start()
        self._running = True
        logger.info(
            "[MemoryPubSub] Listening on channel: %s (instance=%s)",
            MEMORY_INVALIDATION_CHANNEL,
            self._instance_id,
        )

    async def _handle_message(self, message: Dict[str, Any]) -> None:
        """Invalidate local index cache for the user mentioned in the message."""
        try:
            data = json.loads(message["data"])
            user_id = data.get("user_id")
            if not user_id:
                return

            from src.infra.memory.tools import _get_backend

            backend = await _get_backend()
            if backend is None or backend.name != "native":
                return

            from src.infra.memory.client.native import NativeMemoryBackend

            if not isinstance(backend, NativeMemoryBackend):
                return
            # Invalidate the index cache for this user
            backend._index_cache.pop(user_id, None)
            logger.debug("[MemoryPubSub] Invalidated index cache for user %s", user_id)

        except Exception as e:
            logger.debug("[MemoryPubSub] Error handling message: %s", e)

    async def stop_listener(self) -> None:
        """Stop the memory pub/sub listener."""
        self._running = False

        if self._subscription_token:
            hub = get_pubsub_hub()
            hub.unsubscribe(self._subscription_token)
            self._subscription_token = None
            await hub.stop_if_idle()

    @property
    def is_running(self) -> bool:
        return self._running


# Singleton instance
_memory_pubsub: Optional[MemoryPubSub] = None


def get_memory_pubsub() -> MemoryPubSub:
    """Get the global MemoryPubSub instance."""
    global _memory_pubsub
    if _memory_pubsub is None:
        _memory_pubsub = MemoryPubSub()
    return _memory_pubsub
