# src/infra/model/pubsub.py
"""
Model Config Pub/Sub - Redis Pub/Sub for distributed model config synchronization.

When one worker updates provider/model/role config, it publishes to Redis.
All other workers clear their LLM model cache in response.
"""

import asyncio
import json
import uuid
from typing import Optional

from redis.asyncio.client import PubSub

from src.infra.logging import get_logger
from src.infra.storage.redis import get_redis_client
from src.infra.task.constants import MODEL_CONFIG_CHANNEL

logger = get_logger(__name__)

_MAX_RECONNECT_DELAY = 30


class ModelConfigPubSub:
    """Redis Pub/Sub listener for model config changes."""

    def __init__(self):
        self._pubsub_task: Optional[asyncio.Task] = None
        self._pubsub: Optional["PubSub"] = None
        self._running = False
        self._instance_id: str = uuid.uuid4().hex[:8]

    async def start_listener(self) -> None:
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
                        f"Model config pub/sub listening on {MODEL_CONFIG_CHANNEL} (instance={self._instance_id})"
                    )
                    delay = 1

                    async for message in self._pubsub.listen():
                        if not self._running:
                            break
                        if message["type"] == "message":
                            await self._handle_message(message)

                except asyncio.CancelledError:
                    break
                except Exception as e:
                    logger.error(f"Model config pub/sub error: {e}")
                    if not self._running:
                        break
                    logger.info(f"Model config pub/sub reconnecting in {delay}s...")
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, _MAX_RECONNECT_DELAY)

            await self._cleanup()
            self._running = False

        self._pubsub_task = asyncio.create_task(listener())

    async def _handle_message(self, message: dict) -> None:
        try:
            data = json.loads(message["data"])
            if data.get("instance_id") == self._instance_id:
                return

            action = data.get("action", "unknown")
            logger.info(f"[ModelConfigPubSub] Received: {action}")

            from src.infra.llm.client import LLMClient

            cleared = LLMClient.clear_cache_by_model()
            logger.info(f"[ModelConfigPubSub] Cleared {cleared} LLM cache entries after '{action}'")
        except Exception as e:
            logger.error(f"[ModelConfigPubSub] Error: {e}")

    async def _cleanup(self) -> None:
        if self._pubsub:
            try:
                await self._pubsub.unsubscribe(MODEL_CONFIG_CHANNEL)
                await self._pubsub.close()
            except Exception:
                pass
            finally:
                self._pubsub = None

    async def stop_listener(self) -> None:
        self._running = False
        if self._pubsub:
            try:
                await self._pubsub.unsubscribe(MODEL_CONFIG_CHANNEL)
                await self._pubsub.close()
            except Exception:
                pass
            finally:
                self._pubsub = None
        if self._pubsub_task and not self._pubsub_task.done():
            self._pubsub_task.cancel()
            try:
                await self._pubsub_task
            except asyncio.CancelledError:
                pass


# Singleton
_model_config_pubsub: Optional[ModelConfigPubSub] = None


def get_model_config_pubsub() -> ModelConfigPubSub:
    global _model_config_pubsub
    if _model_config_pubsub is None:
        _model_config_pubsub = ModelConfigPubSub()
    return _model_config_pubsub


async def publish_model_config_change(action: str) -> None:
    """Publish a model config change notification to all workers."""
    from src.infra.model.pubsub import get_model_config_pubsub

    pubsub = get_model_config_pubsub()
    try:
        redis_client = get_redis_client()
        await redis_client.publish(
            MODEL_CONFIG_CHANNEL,
            json.dumps(
                {
                    "action": action,
                    "instance_id": pubsub._instance_id,
                }
            ),
        )
    except Exception as e:
        logger.warning(f"Failed to publish model config change: {e}")
