"""Base channel interface for chat platforms.

Provides abstract base class for implementing various chat platform channels
(Feishu, WeChat, DingTalk, Slack, etc.) with a unified interface.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any, Callable, Optional

from src.kernel.schemas.channel import ChannelCapability, ChannelType

logger = logging.getLogger(__name__)


class BaseChannel(ABC):
    """
    Abstract base class for chat channel implementations.

    Each channel (Feishu, WeChat, DingTalk, etc.) should implement this interface
    to integrate with the LambChat message system.

    Attributes:
        channel_type: The channel type enum value.
        display_name: Human-readable name for UI display.
        description: Brief description of the channel.
        icon: Lucide icon name for UI.
    """

    channel_type: ChannelType
    display_name: str = "Base Channel"
    description: str = "Base channel implementation"
    icon: str = "message-circle"

    def __init__(self, config: Any, message_handler: Optional[Callable] = None):
        """
        Initialize the channel.

        Args:
            config: Channel-specific configuration (e.g., FeishuConfig).
            message_handler: Async callback for incoming messages.
        """
        self.config = config
        self.message_handler = message_handler
        self._running = False

    @classmethod
    @abstractmethod
    def get_capabilities(cls) -> list[ChannelCapability]:
        """Get the capabilities of this channel type."""
        pass

    @classmethod
    @abstractmethod
    def get_config_schema(cls) -> dict[str, Any]:
        """Get JSON schema for channel configuration."""
        pass

    @classmethod
    @abstractmethod
    def get_setup_guide(cls) -> list[str]:
        """Get setup guide steps for this channel."""
        pass

    @classmethod
    def get_config_fields(cls) -> list[dict[str, Any]]:
        """Get configuration fields for UI rendering.

        Returns a list of field definitions that the frontend can use
        to dynamically render the configuration form.

        Each field should have:
        - name: Field name (key in config)
        - title: Human-readable label
        - type: Field type (text, password, toggle, select)
        - required: Whether the field is required
        - sensitive: Whether the field contains sensitive data
        - placeholder: Optional placeholder text
        - default: Optional default value
        - options: For select type, list of {value, label} objects
        """
        return []

    @classmethod
    def get_metadata(cls) -> dict[str, Any]:
        """Get full metadata for this channel type."""
        from src.kernel.schemas.channel import ChannelMetadata

        return ChannelMetadata(
            channel_type=cls.channel_type,
            display_name=cls.display_name,
            description=cls.description,
            icon=cls.icon,
            capabilities=cls.get_capabilities(),
            config_schema=cls.get_config_schema(),
            setup_guide=cls.get_setup_guide(),
            config_fields=cls.get_config_fields(),
        ).model_dump()

    @abstractmethod
    async def start(self) -> bool:
        """
        Start the channel and begin listening for messages.

        Returns:
            True if started successfully, False otherwise.
        """
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop the channel and clean up resources."""
        pass

    @abstractmethod
    async def send_message(self, chat_id: str, content: str, **kwargs) -> bool:
        """
        Send a message through this channel.

        Args:
            chat_id: The target chat/conversation ID.
            content: The message content.
            **kwargs: Channel-specific options.

        Returns:
            True if sent successfully, False otherwise.
        """
        pass

    @property
    def is_running(self) -> bool:
        """Check if the channel is running."""
        return self._running

    @property
    def user_id(self) -> str:
        """Get the user ID this channel belongs to."""
        return getattr(self.config, "user_id", "unknown")

    async def _handle_message(
        self,
        sender_id: str,
        chat_id: str,
        content: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> None:
        """
        Handle an incoming message from the chat platform.

        This method forwards the message to the registered message handler.

        Args:
            sender_id: The sender's identifier.
            chat_id: The chat/conversation identifier.
            content: Message text content.
            metadata: Optional channel-specific metadata.
        """
        if not self.message_handler:
            logger.warning(f"No message handler registered for {self.channel_type} channel")
            return

        try:
            await self.message_handler(
                user_id=self.user_id,
                sender_id=sender_id,
                chat_id=chat_id,
                content=content,
                metadata=metadata or {},
            )
        except Exception as e:
            logger.error(f"Error handling message on {self.channel_type}: {e}")


class UserChannelManager(ABC):
    """
    Abstract base class for managing user-specific channel instances.

    Each channel type should implement a manager that handles multiple
    user configurations and their corresponding channel instances.
    """

    channel_type: ChannelType
    config_class: type
    _instances: dict[type, "UserChannelManager"] = {}

    def __init__(self, message_handler: Optional[Callable] = None):
        """
        Initialize the channel manager.

        Args:
            message_handler: Async callback for incoming messages.
        """
        self.message_handler = message_handler
        self._channels: dict[str, BaseChannel] = {}
        self._running = False

    @classmethod
    def get_instance(cls) -> "UserChannelManager":
        """Get the singleton instance for this channel manager type."""
        if cls not in cls._instances:
            cls._instances[cls] = cls()
        return cls._instances[cls]

    @abstractmethod
    async def start(self) -> None:
        """Start all enabled channels for all users."""
        pass

    @abstractmethod
    async def stop(self) -> None:
        """Stop all channels."""
        pass

    @abstractmethod
    async def reload_user(self, user_id: str) -> bool:
        """Reload a user's channel configuration."""
        pass

    def get_channel(self, user_id: str) -> Optional[BaseChannel]:
        """Get a user's channel instance."""
        return self._channels.get(user_id)

    def is_connected(self, user_id: str) -> bool:
        """Check if a user's channel is connected."""
        channel = self._channels.get(user_id)
        return channel is not None and channel.is_running

    def get_connected_users(self) -> list[str]:
        """Get list of users with connected channels."""
        return [user_id for user_id, channel in self._channels.items() if channel.is_running]
