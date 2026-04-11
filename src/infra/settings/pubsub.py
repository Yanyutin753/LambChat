# src/infra/settings/pubsub.py
"""
Settings Pub/Sub - Redis Pub/Sub for distributed settings synchronization.

When one instance updates a setting, it publishes a message to Redis.
All other instances subscribe and refresh their local in-memory settings.

Includes:
- Auto-reconnect on connection errors (with backoff)
- Instance ID filtering to skip self-published messages
"""

import asyncio
import json
import uuid
from typing import Any, Dict, Optional

from redis.asyncio.client import PubSub

from src.infra.logging import get_logger
from src.infra.storage.redis import get_redis_client

from ..task.constants import SETTINGS_CHANNEL

logger = get_logger(__name__)

# Maximum reconnect delay (seconds)
_MAX_RECONNECT_DELAY = 30


class SettingsPubSub:
    """
    Redis Pub/Sub listener for settings changes.

    Lightweight version of TaskPubSub — no lock/tasks needed,
    just listens for setting change notifications and refreshes local state.
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
        """Start listening for settings change notifications.

        Should be called during application startup, after initialize_settings().
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
                    await self._pubsub.subscribe(SETTINGS_CHANNEL)
                    logger.info(
                        f"Settings pub/sub listening on channel: {SETTINGS_CHANNEL} (instance={self._instance_id})"
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
                    logger.error(f"Settings pub/sub listener error: {e}")
                    if not self._running:
                        break
                    # Auto-reconnect with exponential backoff
                    logger.info(f"Settings pub/sub reconnecting in {delay}s...")
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, _MAX_RECONNECT_DELAY)

            await self._cleanup()
            self._running = False
            logger.info("Settings pub/sub listener stopped")

        self._pubsub_task = asyncio.create_task(listener())

    async def _handle_message(self, message: Dict[str, Any]) -> None:
        """Handle an incoming settings change message."""
        try:
            data = json.loads(message["data"])
            key = data.get("key")
            # Skip messages published by this instance
            if data.get("instance_id") == self._instance_id:
                return
            if not key:
                return

            logger.info(f"[SettingsPubSub] Received setting change: {key}")

            # Refresh local in-memory settings
            from src.kernel.config import refresh_settings

            await refresh_settings(key)
            logger.info(f"[SettingsPubSub] Refreshed local setting: {key}")

        except json.JSONDecodeError:
            logger.warning(f"[SettingsPubSub] Invalid message format: {message['data']}")
        except Exception as e:
            logger.error(f"[SettingsPubSub] Error handling message: {e}")

    async def _cleanup(self) -> None:
        """Unsubscribe and close the pub/sub connection."""
        if self._pubsub:
            try:
                await self._pubsub.unsubscribe(SETTINGS_CHANNEL)
                await self._pubsub.close()
            except Exception as e:
                logger.warning(f"[SettingsPubSub] Cleanup error: {e}")
            finally:
                self._pubsub = None

    async def stop_listener(self) -> None:
        """Stop the settings pub/sub listener.

        Should be called during application shutdown.
        """
        self._running = False

        if self._pubsub:
            try:
                await self._pubsub.unsubscribe(SETTINGS_CHANNEL)
                await self._pubsub.close()
            except Exception as e:
                logger.warning(f"[SettingsPubSub] Stop error: {e}")
            finally:
                self._pubsub = None

        if self._pubsub_task and not self._pubsub_task.done():
            self._pubsub_task.cancel()
            try:
                await self._pubsub_task
            except asyncio.CancelledError:
                pass

        logger.info("Settings pub/sub listener stopped")

    @property
    def is_running(self) -> bool:
        return self._running


# Singleton instance
_settings_pubsub: Optional[SettingsPubSub] = None


def get_settings_pubsub() -> SettingsPubSub:
    """Get the global SettingsPubSub instance."""
    global _settings_pubsub
    if _settings_pubsub is None:
        _settings_pubsub = SettingsPubSub()
    return _settings_pubsub
