"""Channel manager for coordinating all chat channels.

Provides a unified manager that coordinates multiple channel types
and their user-specific instances.
"""

from __future__ import annotations

from typing import Any, Callable, Optional

from src.infra.channel.base import UserChannelManager
from src.infra.channel.plugin_connectors import ensure_channel_connector_available_for_type
from src.infra.channel.registry import get_registry
from src.infra.logging import get_logger
from src.kernel.extensions import PluginRuntime
from src.kernel.schemas.channel import ChannelType

logger = get_logger(__name__)


class ChannelCoordinator:
    """
    Coordinates all channel managers across different platform types.

    This is the main entry point for channel management in LambChat.
    It manages multiple UserChannelManager instances (one per channel type).
    """

    def __init__(self, message_handler: Optional[Callable] = None):
        """
        Initialize the channel coordinator.

        Args:
            message_handler: Async callback for incoming messages from all channels.
        """
        self.message_handler = message_handler
        self._managers: dict[ChannelType, UserChannelManager] = {}
        self._running = False
        self._plugin_runtime: PluginRuntime | None = None

    def set_plugin_runtime(self, runtime: PluginRuntime | None) -> None:
        """Attach Plugin Runtime so background channel sends follow connector state."""
        self._plugin_runtime = runtime

    async def start(self) -> None:
        """Start all enabled channel managers."""
        if self._running:
            return

        self._running = True
        registry = get_registry()

        for channel_type, manager_cls in registry.get_all_managers().items():
            try:
                channel_type_enum = ChannelType(channel_type)
                manager = manager_cls(message_handler=self.message_handler)
                await manager.start()
                self._managers[channel_type_enum] = manager
                logger.info(f"Started {channel_type} channel manager")
            except ValueError:
                logger.debug(f"Unknown channel type: {channel_type}")
            except Exception as e:
                logger.error(f"Failed to start {channel_type} channel manager: {e}")

    async def stop(self) -> None:
        """Stop all channel managers."""
        self._running = False

        for channel_type, manager in self._managers.items():
            try:
                await manager.stop()
                logger.info(f"Stopped {channel_type.value} channel manager")
            except Exception as e:
                logger.error(f"Error stopping {channel_type.value} channel manager: {e}")

        self._managers.clear()

    async def reload_user(self, user_id: str, channel_type: ChannelType) -> bool:
        """
        Reload a user's channel configuration.

        Args:
            user_id: The user ID.
            channel_type: The channel type to reload.

        Returns:
            True if reloaded successfully, False otherwise.
        """
        manager = self._managers.get(channel_type)
        if not manager:
            logger.warning(f"No manager for channel type: {channel_type}")
            return False

        return await manager.reload_user(user_id)

    async def send_message(
        self,
        user_id: str,
        channel_type: ChannelType,
        chat_id: str,
        content: str,
        instance_id: str | None = None,
    ) -> bool:
        """
        Send a message through a user's channel.

        Args:
            user_id: The user ID.
            channel_type: The channel type.
            chat_id: The target chat ID.
            content: The message content.
            instance_id: Optional channel instance ID.

        Returns:
            True if sent successfully, False otherwise.
        """
        if not self._is_channel_connector_available(channel_type):
            return False

        manager = self._managers.get(channel_type)
        if not manager:
            logger.warning(f"No manager for channel type: {channel_type}")
            return False

        channel = manager.get_channel(user_id, instance_id)
        if not channel:
            logger.warning(f"No {channel_type} channel for user {user_id}, instance {instance_id}")
            return False

        return await channel.send_message(chat_id, content)

    def _is_channel_connector_available(self, channel_type: ChannelType) -> bool:
        runtime = self._plugin_runtime
        available, connector_id, exc = ensure_channel_connector_available_for_type(
            channel_type,
            runtime,
        )
        if available:
            return True
        if exc is None:
            logger.warning(
                "Skipping %s channel send because Plugin Runtime is unavailable for connector %s",
                channel_type.value,
                connector_id,
            )
            return False
        logger.info("Skipping %s channel send by Plugin Runtime: %s", channel_type.value, exc)
        return False

    def is_connected(self, user_id: str, channel_type: ChannelType) -> bool:
        """Check if a user's channel is connected."""
        manager = self._managers.get(channel_type)
        if not manager:
            return False
        return manager.is_connected(user_id)

    def get_status(self) -> dict[str, Any]:
        """Get status of all channels."""
        status = {}
        for channel_type, manager in self._managers.items():
            status[channel_type.value] = {
                "connected_users": manager.get_connected_users(),
                "total_users": len(manager._channels),
            }
        return status

    def get_available_channels(self) -> list[dict]:
        """Get metadata for all available channel types."""
        registry = get_registry()
        return registry.get_channel_metadata()


# Global instance
_coordinator: Optional[ChannelCoordinator] = None


def get_channel_coordinator() -> ChannelCoordinator:
    """Get the global channel coordinator instance."""
    global _coordinator
    if _coordinator is None:
        _coordinator = ChannelCoordinator()
    return _coordinator


async def start_channels(message_handler: Optional[Callable] = None) -> None:
    """Start the channel coordinator with all enabled channels."""
    coordinator = get_channel_coordinator()
    coordinator.message_handler = message_handler
    await coordinator.start()


async def stop_channels() -> None:
    """Stop the channel coordinator."""
    global _coordinator
    if _coordinator:
        await _coordinator.stop()
        _coordinator = None
