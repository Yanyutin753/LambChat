"""Distributed channel configuration synchronization."""

from __future__ import annotations

import json
import uuid
from typing import Any, Optional

from src.infra.async_utils import run_blocking_io
from src.infra.channel.plugin_connectors import ensure_channel_connector_available_for_type
from src.infra.channel.registry import get_registry
from src.infra.logging import get_logger
from src.infra.pubsub_hub import get_pubsub_hub
from src.infra.storage.redis import get_redis_client
from src.kernel.extensions import PluginRuntime
from src.kernel.schemas.channel import ChannelType

logger = get_logger(__name__)

CHANNEL_CONFIG_CHANNEL = "channel:config:changed"


class ChannelConfigPubSub:
    """Listen for cross-instance channel configuration changes."""

    def __init__(self) -> None:
        self._subscription_token: Optional[str] = None
        self._running = False
        self._instance_id = uuid.uuid4().hex[:8]
        self._plugin_runtime: PluginRuntime | None = None

    @property
    def instance_id(self) -> str:
        return self._instance_id

    def set_plugin_runtime(self, runtime: PluginRuntime | None) -> None:
        self._plugin_runtime = runtime

    async def start_listener(self) -> None:
        if self._running:
            return

        hub = get_pubsub_hub()
        self._subscription_token = hub.subscribe(CHANNEL_CONFIG_CHANNEL, self._handle_message)
        await hub.start()
        self._running = True
        logger.info(
            "ChannelConfig pub/sub listening on channel: %s (instance=%s)",
            CHANNEL_CONFIG_CHANNEL,
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

            user_id = data.get("user_id")
            channel_type_value = data.get("channel_type")
            instance_id = data.get("channel_instance_id")
            if not user_id or not channel_type_value:
                return

            try:
                channel_type = ChannelType(channel_type_value)
            except ValueError:
                logger.warning("Unknown channel type from pub/sub event: %s", channel_type_value)
                return

            available, connector_id, exc = ensure_channel_connector_available_for_type(
                channel_type,
                self._plugin_runtime,
            )
            if not available and self._plugin_runtime is None:
                logger.info(
                    "Applying %s channel config reload without Plugin Runtime for connector %s",
                    channel_type.value,
                    connector_id,
                )
                available = True
            if not available:
                if exc is None:
                    logger.info(
                        "Skipped %s channel config reload because Plugin Runtime is unavailable for connector %s",
                        channel_type.value,
                        connector_id,
                    )
                else:
                    logger.info(
                        "Skipped %s channel config reload by Plugin Runtime: %s",
                        channel_type.value,
                        exc,
                    )
                return

            manager_class = get_registry().get_manager_class(channel_type)
            if not manager_class:
                return

            manager = manager_class.get_instance()
            await manager.reload_user(user_id, instance_id)
            logger.info(
                "Applied distributed channel config change: user=%s channel=%s instance=%s",
                user_id,
                channel_type_value,
                instance_id,
            )
        except Exception as e:
            logger.error("Failed to handle distributed channel config change: %s", e)

    @property
    def is_running(self) -> bool:
        return self._running


_channel_config_pubsub: ChannelConfigPubSub | None = None


def get_channel_config_pubsub() -> ChannelConfigPubSub:
    global _channel_config_pubsub
    if _channel_config_pubsub is None:
        _channel_config_pubsub = ChannelConfigPubSub()
    return _channel_config_pubsub


async def close_channel_config_pubsub() -> None:
    """Stop and release the global ChannelConfigPubSub instance if it exists."""
    global _channel_config_pubsub
    pubsub = _channel_config_pubsub
    _channel_config_pubsub = None
    if pubsub is not None:
        await pubsub.stop_listener()


async def publish_channel_config_changed(
    *,
    user_id: str,
    channel_type: str,
    channel_instance_id: str | None,
    action: str,
) -> None:
    try:
        redis_client = get_redis_client()
        pubsub = get_channel_config_pubsub()
        payload = await run_blocking_io(
            json.dumps,
            {
                "instance_id": pubsub.instance_id,
                "user_id": user_id,
                "channel_type": channel_type,
                "channel_instance_id": channel_instance_id,
                "action": action,
            },
        )
        await redis_client.publish(CHANNEL_CONFIG_CHANNEL, payload)
    except Exception as e:
        logger.warning("Failed to publish channel config change: %s", e)
