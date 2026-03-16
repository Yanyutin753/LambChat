"""
Feishu channel manager for managing multiple user bot connections.
"""

import logging
from typing import Any, Callable, Optional

from src.infra.channel.base import UserChannelManager
from src.infra.channel.channel_storage import ChannelStorage
from src.infra.channel.feishu.channel import FEISHU_AVAILABLE, FeishuChannel
from src.kernel.schemas.channel import ChannelType
from src.kernel.schemas.feishu import FeishuConfig, FeishuGroupPolicy

logger = logging.getLogger(__name__)


class FeishuChannelManager(UserChannelManager):
    """
    Manager for all user Feishu channels.

    Manages multiple Feishu bot connections, one per user.
    """

    channel_type = ChannelType.FEISHU
    config_class = FeishuConfig

    def __init__(self, message_handler: Optional[Callable] = None):
        super().__init__(message_handler)
        self._storage = ChannelStorage()
        self._message_handler: Optional[Callable] = message_handler

    @classmethod
    def get_instance(cls) -> "FeishuChannelManager":
        """Get the singleton instance, consistent with get_feishu_channel_manager()."""
        return get_feishu_channel_manager()

    def _dict_to_config(
        self,
        user_id: str,
        config_dict: dict[str, Any],
        instance_id: Optional[str] = None,
    ) -> FeishuConfig:
        """Convert a config dict to FeishuConfig."""
        # Use explicit instance_id, fallback to config_dict's instance_id, then empty string
        resolved_instance_id = instance_id or config_dict.get("instance_id") or ""
        return FeishuConfig(
            user_id=user_id,
            instance_id=resolved_instance_id,
            app_id=config_dict.get("app_id") or "",
            app_secret=config_dict.get("app_secret") or "",
            encrypt_key=config_dict.get("encrypt_key") or "",
            verification_token=config_dict.get("verification_token") or "",
            react_emoji=config_dict.get("react_emoji") or "THUMBSUP",
            group_policy=FeishuGroupPolicy(config_dict.get("group_policy") or "mention"),
            enabled=config_dict.get("enabled", True),
        )

    async def start(self) -> None:
        """Start all enabled Feishu channels."""
        if not FEISHU_AVAILABLE:
            logger.warning("Feishu SDK not installed. Run: pip install lark-oapi")
            return

        self._running = True

        # Load all enabled configs from ChannelStorage
        config_dicts = await self._storage.list_enabled_configs(ChannelType.FEISHU)
        logger.info(f"Found {len(config_dicts)} enabled Feishu configurations")

        for config_dict in config_dicts:
            try:
                user_id = config_dict.get("user_id")
                if not user_id:
                    logger.warning("Skipping config without user_id")
                    continue

                # Check if required fields are present (decryption may have failed)
                app_id = config_dict.get("app_id") or ""
                app_secret = config_dict.get("app_secret") or ""

                if not app_id or not app_secret:
                    logger.warning(
                        f"Skipping Feishu config for user {user_id}: "
                        "missing app_id or app_secret (decryption may have failed). "
                        "Please re-save the channel configuration."
                    )
                    continue

                config = self._dict_to_config(user_id, config_dict)
                await self._start_user_client(config)
            except Exception as e:
                logger.error(
                    f"Failed to start Feishu client for user {config_dict.get('user_id')}: {e}"
                )

    async def stop(self) -> None:
        """Stop all Feishu channels."""
        self._running = False

        for user_id, client in list(self._channels.items()):
            try:
                await client.stop()
            except Exception as e:
                logger.error(f"Error stopping Feishu client for user {user_id}: {e}")

        self._channels.clear()
        await self._storage.close()

    async def _start_user_client(self, config: FeishuConfig) -> bool:
        """Start a user's Feishu client."""
        # Use instance_id if available, otherwise use user_id for backward compatibility
        channel_key = (
            f"{config.user_id}:{config.instance_id}" if config.instance_id else config.user_id
        )

        if channel_key in self._channels:
            await self._channels[channel_key].stop()

        client = FeishuChannel(config, self._message_handler)
        success = await client.start()

        if success:
            self._channels[channel_key] = client
            return True
        return False

    async def reload_user(self, user_id: str, instance_id: Optional[str] = None) -> bool:
        """Reload a user's Feishu configuration and restart the client.

        Args:
            user_id: The user ID
            instance_id: Optional specific instance ID to reload. If None, reloads all instances.
        """
        # If instance_id is provided, stop only that specific instance
        if instance_id:
            # Check if this specific instance has an active connection
            channel_key = f"{user_id}:{instance_id}"
            if channel_key in self._channels:
                await self._channels[channel_key].stop()
                del self._channels[channel_key]
                logger.info(f"Stopped Feishu client for {channel_key}")

            # Check if there's still config for this instance
            config_dict = await self._storage.get_config(user_id, ChannelType.FEISHU, instance_id)
            if config_dict and config_dict.get("enabled", True):
                config = self._dict_to_config(user_id, config_dict, instance_id)
                return await self._start_user_client(config)
            return True

        # Legacy behavior: reload all instances for user
        config_list = await self._storage.list_user_configs(user_id)
        feishu_configs = [c for c in config_list if c.get("channel_type") == "feishu"]

        # Stop all existing clients
        for key in list(self._channels.keys()):
            if key.startswith(user_id):
                await self._channels[key].stop()
                del self._channels[key]

        # Start all enabled clients
        for config_dict in feishu_configs:
            if config_dict.get("enabled", True):
                inst_id = config_dict.get("instance_id")
                config = self._dict_to_config(user_id, config_dict, inst_id)
                await self._start_user_client(config)

        return True

    def _find_channel(
        self, user_id: str, instance_id: Optional[str] = None
    ) -> Optional[FeishuChannel]:
        """Find a channel by user_id, with fallback to prefix match.

        Lookup order:
        1. Exact match: "user_id:instance_id" (if instance_id provided)
        2. Exact match: "user_id"
        3. Prefix match: first key starting with "user_id:"
        """
        if instance_id:
            channel = self._channels.get(f"{user_id}:{instance_id}")
            if channel:
                return channel

        channel = self._channels.get(user_id)
        if channel:
            return channel

        # Fallback: find first channel whose key starts with "user_id:"
        prefix = f"{user_id}:"
        for key, ch in self._channels.items():
            if key.startswith(prefix):
                logger.debug(
                    f"[Feishu] _find_channel fallback: matched key '{key}' for user '{user_id}'"
                )
                return ch

        return None

    async def send_message(self, user_id: str, chat_id: str, content: str) -> bool:
        """Send a message through a user's Feishu bot."""
        client = self._find_channel(user_id)
        if not client:
            logger.warning(f"No Feishu client for user {user_id}")
            return False

        return await client.send_message(chat_id, content)

    def is_connected(self, user_id: str, instance_id: Optional[str] = None) -> bool:
        """Check if a user's Feishu bot is connected."""
        channel = self._find_channel(user_id, instance_id)
        return channel is not None and channel._running


# Global instance
_feishu_channel_manager: Optional[FeishuChannelManager] = None


def get_feishu_channel_manager() -> FeishuChannelManager:
    """Get the global Feishu channel manager instance."""
    global _feishu_channel_manager
    if _feishu_channel_manager is None:
        _feishu_channel_manager = FeishuChannelManager()
    return _feishu_channel_manager


async def start_feishu_channels(message_handler=None) -> None:
    """Start the Feishu channel manager with all enabled user bots."""
    manager = get_feishu_channel_manager()
    manager._message_handler = message_handler
    await manager.start()


async def stop_feishu_channels() -> None:
    """Stop the Feishu channel manager."""
    global _feishu_channel_manager
    if _feishu_channel_manager:
        await _feishu_channel_manager.stop()
        _feishu_channel_manager = None
