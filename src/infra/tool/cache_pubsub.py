"""Distributed invalidation for process-local tool prompt caches."""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from src.infra.async_utils import run_blocking_io
from src.infra.logging import get_logger
from src.infra.pubsub_hub import get_pubsub_hub
from src.infra.storage.redis import get_redis_client
from src.infra.tool.env_var_prompt import invalidate_env_var_prompt_cache

logger = get_logger(__name__)

TOOL_CACHE_INVALIDATION_CHANNEL = "tool:cache:invalidate"


class ToolCachePubSub:
    """Synchronize prompt cache invalidation across instances."""

    def __init__(self) -> None:
        self._subscription_token: Optional[str] = None
        self._running = False
        self._instance_id = uuid.uuid4().hex[:8]

    @property
    def instance_id(self) -> str:
        return self._instance_id

    async def start_listener(self) -> None:
        if self._running:
            return

        hub = get_pubsub_hub()
        self._subscription_token = hub.subscribe(
            TOOL_CACHE_INVALIDATION_CHANNEL, self._handle_message
        )
        await hub.start()
        self._running = True
        logger.info(
            "ToolCache pub/sub listening on channel: %s (instance=%s)",
            TOOL_CACHE_INVALIDATION_CHANNEL,
            self._instance_id,
        )

    async def stop_listener(self) -> None:
        self._running = False
        if self._subscription_token:
            hub = get_pubsub_hub()
            hub.unsubscribe(self._subscription_token)
            self._subscription_token = None
            await hub.stop_if_idle()

    async def _handle_message(self, message: dict[str, Any]) -> None:
        try:
            data = await run_blocking_io(json.loads, message["data"])
            if data.get("instance_id") == self._instance_id:
                return

            cache = data.get("cache")
            user_id = data.get("user_id")
            if not cache or not user_id:
                return

            if cache == "env_var_prompt":
                invalidate_env_var_prompt_cache(user_id)
            else:
                logger.debug("Ignoring unknown tool cache invalidation key: %s", cache)
                return

            logger.debug("Applied distributed tool cache invalidation: %s user=%s", cache, user_id)
        except Exception as e:
            logger.error("Failed to handle distributed tool cache invalidation: %s", e)

    @property
    def is_running(self) -> bool:
        return self._running


_tool_cache_pubsub: ToolCachePubSub | None = None


def get_tool_cache_pubsub() -> ToolCachePubSub:
    global _tool_cache_pubsub
    if _tool_cache_pubsub is None:
        _tool_cache_pubsub = ToolCachePubSub()
    return _tool_cache_pubsub


async def close_tool_cache_pubsub() -> None:
    """Stop and release the tool cache pub/sub singleton without creating it."""
    global _tool_cache_pubsub
    pubsub = _tool_cache_pubsub
    _tool_cache_pubsub = None
    if pubsub is not None:
        await pubsub.stop_listener()


async def publish_tool_cache_invalidation(cache: str, *, user_id: str | None = None) -> None:
    try:
        redis_client = get_redis_client()
        pubsub = get_tool_cache_pubsub()
        payload = await run_blocking_io(
            json.dumps,
            {
                "instance_id": pubsub.instance_id,
                "cache": cache,
                "user_id": user_id,
            },
        )
        await redis_client.publish(TOOL_CACHE_INVALIDATION_CHANNEL, payload)
    except Exception as e:
        logger.warning("Failed to publish tool cache invalidation: %s", e)
