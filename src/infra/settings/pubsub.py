# src/infra/settings/pubsub.py
"""
Settings Pub/Sub - Redis Pub/Sub for distributed settings synchronization.

When one instance updates a setting, it publishes a message to Redis.
All other instances subscribe and refresh their local in-memory settings.

Includes:
- Auto-reconnect on connection errors (with backoff)
- Instance ID filtering to skip self-published messages
"""

import json
import uuid
from typing import Any, Dict, Optional

from src.infra.logging import get_logger
from src.infra.pubsub_hub import get_pubsub_hub

from ..task.constants import SETTINGS_CHANNEL

logger = get_logger(__name__)


class SettingsPubSub:
    """
    Redis Pub/Sub listener for settings changes.

    Lightweight version of TaskPubSub — no lock/tasks needed,
    just listens for setting change notifications and refreshes local state.
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
        """Start listening for settings change notifications.

        Should be called during application startup, after initialize_settings().
        """
        if self._running:
            return

        hub = get_pubsub_hub()
        self._subscription_token = hub.subscribe(
            SETTINGS_CHANNEL,
            self._handle_message,
        )
        await hub.start()
        self._running = True
        logger.info(
            f"Settings pub/sub listening on channel: {SETTINGS_CHANNEL} (instance={self._instance_id})"
        )

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

    async def stop_listener(self) -> None:
        """Stop the settings pub/sub listener.

        Should be called during application shutdown.
        """
        self._running = False

        if self._subscription_token:
            hub = get_pubsub_hub()
            hub.unsubscribe(self._subscription_token)
            self._subscription_token = None
            await hub.stop_if_idle()

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
