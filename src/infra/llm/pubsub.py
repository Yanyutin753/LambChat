"""
Model Config Pub/Sub - Redis Pub/Sub for distributed model configuration synchronization.

When one instance updates model configs, it publishes a message to Redis.
All other instances subscribe and clear their local LLM client cache.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any, Optional

from redis.asyncio.client import PubSub

from src.infra.logging import get_logger
from src.infra.storage.redis import get_redis_client

from ..task.constants import MODEL_CONFIG_CHANNEL

logger = get_logger(__name__)

# Maximum reconnect delay (seconds)
_MAX_RECONNECT_DELAY = 30


class ModelConfigPubSub:
    """
    Redis Pub/Sub listener for model config changes.

    Listens for model config change notifications and clears the local
    LLM client cache when other instances make changes.
    """

    def __init__(self):
        self._pubsub_task: Optional[asyncio.Task] = None
        self._pubsub: Optional["PubSub"] = None
        self._running = False
        # Unique ID for this instance — used to skip self-published messages
        self._instance_id: str = uuid.uuid4().hex[:8]

    @property
    def instance_id(self) -> str:
        return self._instance_id

    async def start_listener(self) -> None:
        """Start listening for model config change notifications.

        Should be called during application startup.
        """
        if self._running:
            return

        self._running = True

        async def listener():
            delay = 1
            while self._running:
                try:
                    redis_client = get_redis_client()
                    self._pubsub = redis_client.pubsub()
                    await self._pubsub.subscribe(MODEL_CONFIG_CHANNEL)
                    logger.info(
                        f"ModelConfig pub/sub listening on channel: {MODEL_CONFIG_CHANNEL} (instance={self._instance_id})"
                    )
                    delay = 1  # reset on successful connection

                    async for message in self._pubsub.listen():
                        if not self._running:
                            break

                        if message["type"] == "message":
                            await self._handle_message(message)

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"ModelConfig pub/sub listener error: {e}")
                    if not self._running:
                        break
                    # Clean up old pubsub connection before reconnecting
                    await self._cleanup()
                    # Auto-reconnect with exponential backoff
                    logger.info(f"ModelConfig pub/sub reconnecting in {delay}s...")
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, _MAX_RECONNECT_DELAY)

            await self._cleanup()
            self._running = False
            logger.info("ModelConfig pub/sub listener stopped")

        self._pubsub_task = asyncio.create_task(listener())

    async def _handle_message(self, message: dict[str, Any]) -> None:
        """Handle an incoming model config change message."""
        try:
            data = json.loads(message["data"])
            # Skip messages published by this instance
            if data.get("instance_id") == self._instance_id:
                return

            logger.info("[ModelConfigPubSub] Received model config change notification")

            # Clear the LLM client cache and model caches (no re-publish to avoid bouncing)
            from src.infra.llm.client import LLMClient
            from src.infra.llm.models_service import clear_api_key_cache, invalidate_cache

            await invalidate_cache(publish=False)
            clear_api_key_cache()
            count = LLMClient.clear_cache_by_model()
            logger.info(
                f"[ModelConfigPubSub] Cleared {count} LLM cache entries (local invalidation)"
            )

        except json.JSONDecodeError:
            logger.warning(f"[ModelConfigPubSub] Invalid message format: {message['data']}")
        except Exception as e:
            logger.error(f"[ModelConfigPubSub] Error handling message: {e}")

    async def _cleanup(self) -> None:
        """Unsubscribe and close the pub/sub connection."""
        if self._pubsub:
            try:
                await self._pubsub.unsubscribe(MODEL_CONFIG_CHANNEL)
                await self._pubsub.close()
            except Exception as e:
                logger.warning(f"[ModelConfigPubSub] Cleanup error: {e}")
            finally:
                self._pubsub = None

    async def stop_listener(self) -> None:
        """Stop the model config pub/sub listener.

        Should be called during application shutdown.
        """
        self._running = False

        if self._pubsub_task and not self._pubsub_task.done():
            self._pubsub_task.cancel()
            try:
                await self._pubsub_task
            except asyncio.CancelledError:
                pass
        # _cleanup() is called by the listener coroutine on exit,
        # so we don't need to unsubscribe/close here to avoid double-close.

        logger.info("ModelConfig pub/sub listener stopped")

    @property
    def is_running(self) -> bool:
        return self._running


# Singleton instance
_model_config_pubsub: Optional[ModelConfigPubSub] = None


def get_model_config_pubsub() -> ModelConfigPubSub:
    """Get the global ModelConfigPubSub instance."""
    global _model_config_pubsub
    if _model_config_pubsub is None:
        _model_config_pubsub = ModelConfigPubSub()
    return _model_config_pubsub


async def publish_model_config_changed() -> None:
    """Publish a model config change notification to Redis.

    Call this after create/update/delete/toggle/reorder operations.
    """
    try:
        redis_client = get_redis_client()
        pubsub = get_model_config_pubsub()
        message = json.dumps({"instance_id": pubsub.instance_id})
        await redis_client.publish(MODEL_CONFIG_CHANNEL, message)
        logger.debug(f"[ModelConfigPubSub] Published model config change: {message}")
    except Exception as e:
        logger.warning(f"[ModelConfigPubSub] Failed to publish model config change: {e}")
