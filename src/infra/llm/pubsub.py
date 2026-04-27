"""
Model Config Pub/Sub - Redis Pub/Sub for distributed model configuration synchronization.

When one instance updates model configs, it publishes a message to Redis.
All other instances subscribe and clear their local LLM client cache.
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from src.infra.logging import get_logger
from src.infra.pubsub_hub import get_pubsub_hub
from src.infra.storage.redis import get_redis_client

from ..task.constants import MODEL_CONFIG_CHANNEL

logger = get_logger(__name__)


class ModelConfigPubSub:
    """
    Redis Pub/Sub listener for model config changes.

    Listens for model config change notifications and clears the local
    LLM client cache when other instances make changes.
    """

    def __init__(self):
        self._subscription_token: Optional[str] = None
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

        hub = get_pubsub_hub()
        self._subscription_token = hub.subscribe(
            MODEL_CONFIG_CHANNEL,
            self._handle_message,
        )
        await hub.start()
        self._running = True
        logger.info(
            f"ModelConfig pub/sub listening on channel: {MODEL_CONFIG_CHANNEL} (instance={self._instance_id})"
        )

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

    async def stop_listener(self) -> None:
        """Stop the model config pub/sub listener.

        Should be called during application shutdown.
        """
        self._running = False

        if self._subscription_token:
            hub = get_pubsub_hub()
            hub.unsubscribe(self._subscription_token)
            self._subscription_token = None
            await hub.stop_if_idle()

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
