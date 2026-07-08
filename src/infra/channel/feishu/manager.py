"""
Feishu channel manager for managing multiple user bot connections.
"""

import asyncio
import hashlib
import uuid
from typing import Any, Callable, Optional, cast

from redis.asyncio import Redis

from src.infra.channel.base import UserChannelManager
from src.infra.channel.channel_storage import ChannelStorage
from src.infra.channel.feishu.channel import FEISHU_AVAILABLE, FeishuChannel
from src.infra.logging import get_logger
from src.infra.storage.redis import create_redis_client
from src.kernel.extensions import PluginRuntime
from src.kernel.schemas.channel import ChannelType
from src.kernel.schemas.feishu import (
    DEFAULT_AUDIO_TRANSCRIBE_PROMPT,
    FeishuConfig,
    FeishuGroupPolicy,
)

logger = get_logger(__name__)
_FEISHU_LEASE_PREFIX = "feishu:lease"
_FEISHU_NODE_PREFIX = "feishu:nodes"
_FEISHU_LEASE_TTL_SECONDS = 60
_FEISHU_NODE_TTL_SECONDS = 60
_FEISHU_LEASE_REFRESH_INTERVAL = 20
_FEISHU_REBALANCE_INTERVAL = 20
_RELEASE_LEASE_LUA = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("DEL", KEYS[1])
else
    return 0
end
"""
_REFRESH_LEASE_LUA = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
    return redis.call("EXPIRE", KEYS[1], ARGV[2])
else
    return 0
end
"""


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
        # Track active app_ids to prevent duplicate bot connections
        self._active_app_ids: dict[str, str] = {}  # app_id -> channel_key
        self._instance_id = uuid.uuid4().hex
        self._lease_tasks: dict[str, asyncio.Task] = {}
        self._lease_redis: Redis | None = None
        self._rebalance_task: asyncio.Task | None = None
        self._plugin_runtime: PluginRuntime | None = None

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
            stream_reply=config_dict.get("stream_reply", True),
            auto_transcribe_audio=config_dict.get("auto_transcribe_audio", True),
            audio_transcribe_prompt=config_dict.get("audio_transcribe_prompt")
            or DEFAULT_AUDIO_TRANSCRIBE_PROMPT,
            enabled=config_dict.get("enabled", True),
        )

    def set_plugin_runtime(self, runtime: PluginRuntime | None) -> None:
        """Attach Plugin Runtime used by Feishu execution guards and options."""
        self._plugin_runtime = runtime

    @property
    def plugin_runtime(self) -> PluginRuntime | None:
        return self._plugin_runtime

    async def start(self) -> None:
        """Start all enabled Feishu channels."""
        if not FEISHU_AVAILABLE:
            logger.warning("Feishu SDK not installed. Run: pip install lark-oapi")
            return

        self._running = True

        started, skipped = await self._reconcile_enabled_configs()
        self._ensure_rebalance_task()
        logger.info(
            "Feishu startup processed enabled configurations: started=%s skipped=%s",
            started,
            skipped,
        )

    async def stop(self) -> None:
        """Stop all Feishu channels."""
        self._running = False
        await self._cancel_rebalance_task()

        for user_id, client in list(self._channels.items()):
            try:
                await client.stop()
            except Exception as e:
                logger.error(f"Error stopping Feishu client for user {user_id}: {e}")

        await self._release_all_leases()
        await self._unregister_node()
        await self._close_lease_redis()
        self._channels.clear()
        self._active_app_ids.clear()
        await self._storage.close()

    async def _reconcile_enabled_configs(self) -> tuple[int, int]:
        """Start only configs assigned to this node and stop unassigned local channels."""
        if not await self._refresh_node_membership():
            return 0, 0

        node_ids = await self._list_active_node_ids()
        if self._instance_id not in node_ids:
            node_ids.append(self._instance_id)
            node_ids.sort()

        started = 0
        skipped = 0
        desired_local_keys: set[str] = set()

        async for config_dict in self._storage.iter_enabled_configs(ChannelType.FEISHU):
            try:
                user_id = config_dict.get("user_id")
                if not user_id:
                    logger.warning("Skipping config without user_id")
                    skipped += 1
                    continue

                app_id = config_dict.get("app_id") or ""
                app_secret = config_dict.get("app_secret") or ""

                if not app_id or not app_secret:
                    logger.warning(
                        f"Skipping Feishu config for user {user_id}: "
                        "missing app_id or app_secret (decryption may have failed). "
                        "Please re-save the channel configuration."
                    )
                    skipped += 1
                    continue

                channel_key = self._channel_key(
                    user_id,
                    config_dict.get("instance_id") or "",
                )
                if self._preferred_owner(app_id, node_ids) != self._instance_id:
                    await self._stop_channel_by_key(channel_key)
                    skipped += 1
                    continue

                desired_local_keys.add(channel_key)
                config = self._dict_to_config(user_id, config_dict)
                if await self._start_user_client(config, replace_existing=False):
                    started += 1
                else:
                    skipped += 1
            except Exception as e:
                logger.error(
                    f"Failed to reconcile Feishu client for user {config_dict.get('user_id')}: {e}"
                )
                skipped += 1

        for channel_key in list(self._channels.keys()):
            if channel_key not in desired_local_keys:
                await self._stop_channel_by_key(channel_key)

        return started, skipped

    async def _refresh_node_membership(self) -> bool:
        try:
            redis = self._get_lease_redis()
            await redis.set(
                self._node_key(self._instance_id),
                self._instance_id,
                ex=_FEISHU_NODE_TTL_SECONDS,
            )
            return True
        except Exception as e:
            logger.warning("[Feishu] Failed to refresh node membership: %s", e)
            return False

    async def _list_active_node_ids(self) -> list[str]:
        redis = self._get_lease_redis()
        pattern = self._node_key("*")
        cursor: int | str = 0
        node_ids: set[str] = set()
        while True:
            cursor, keys = await redis.scan(cursor=cursor, match=pattern, count=100)
            for key in keys:
                key_text = key.decode() if isinstance(key, bytes) else str(key)
                node_id = key_text.rsplit(":", 1)[-1]
                if node_id:
                    node_ids.add(node_id)
            if int(cursor) == 0:
                return sorted(node_ids)

    async def _unregister_node(self) -> None:
        try:
            redis = self._get_lease_redis()
            await redis.delete(self._node_key(self._instance_id))
        except Exception as e:
            logger.warning("[Feishu] Failed to unregister node membership: %s", e)

    def _ensure_rebalance_task(self) -> None:
        if self._rebalance_task and not self._rebalance_task.done():
            return
        self._rebalance_task = asyncio.create_task(self._rebalance_loop())

    async def _rebalance_loop(self) -> None:
        try:
            while self._running:
                await asyncio.sleep(_FEISHU_REBALANCE_INTERVAL)
                await self._reconcile_enabled_configs()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("[Feishu] Rebalance loop stopped unexpectedly: %s", e)
        finally:
            self._rebalance_task = None

    async def _cancel_rebalance_task(self) -> None:
        task = self._rebalance_task
        self._rebalance_task = None
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    @staticmethod
    def _node_key(instance_id: str) -> str:
        return f"{_FEISHU_NODE_PREFIX}:{instance_id}"

    @staticmethod
    def _channel_key(user_id: str, instance_id: str | None = None) -> str:
        return f"{user_id}:{instance_id}" if instance_id else user_id

    @staticmethod
    def _preferred_owner(app_id: str, node_ids: list[str]) -> str | None:
        if not node_ids:
            return None
        return max(
            node_ids,
            key=lambda node_id: hashlib.sha256(f"{app_id}:{node_id}".encode()).hexdigest(),
        )

    async def _start_user_client(
        self,
        config: FeishuConfig,
        *,
        replace_existing: bool = True,
    ) -> bool:
        """Start a user's Feishu client."""
        # Use instance_id if available, otherwise use user_id for backward compatibility
        channel_key = self._channel_key(config.user_id, config.instance_id)

        existing_channel = self._channels.get(channel_key)
        existing_app_id = (
            getattr(existing_channel.config, "app_id", None) if existing_channel else None
        )
        existing_running = bool(
            getattr(existing_channel, "is_running", getattr(existing_channel, "_running", False))
        )
        if (
            existing_channel
            and not replace_existing
            and existing_app_id == config.app_id
            and existing_running
        ):
            existing_channel.message_handler = self._message_handler
            self._active_app_ids[config.app_id] = channel_key
            self._ensure_lease_refresh_task(config.app_id)
            return True

        # Prevent duplicate bot connections: same app_id should only have one active channel
        app_id = config.app_id
        if app_id in self._active_app_ids:
            existing_key = self._active_app_ids[app_id]
            if existing_key != channel_key and existing_key in self._channels:
                logger.warning(
                    f"[Feishu] Duplicate bot detected: app_id={app_id} already active "
                    f"as '{existing_key}', skipping '{channel_key}'"
                )
                return False

        if not await self._acquire_lease(app_id):
            logger.info(
                "[Feishu] Lease for app_id=%s is held by another instance, skipping '%s'",
                app_id,
                channel_key,
            )
            return False

        try:
            if channel_key in self._channels:
                await self._channels[channel_key].stop()
                # Clean up old app_id tracking
                old_app_id = getattr(self._channels[channel_key].config, "app_id", None)
                if old_app_id and old_app_id in self._active_app_ids:
                    del self._active_app_ids[old_app_id]

            client = FeishuChannel(config, self._message_handler)
            success = await client.start()

            if success:
                self._channels[channel_key] = client
                self._active_app_ids[app_id] = channel_key
                self._ensure_lease_refresh_task(app_id)
                return True
            await self._release_lease(app_id)
            return False
        except BaseException:
            await self._release_lease(app_id)
            raise

    async def reload_user(self, user_id: str, instance_id: Optional[str] = None) -> bool:
        """Reload a user's Feishu configuration and restart the client.

        Args:
            user_id: The user ID
            instance_id: Optional specific instance ID to reload. If None, reloads all instances.
        """
        # If instance_id is provided, stop only that specific instance
        if instance_id:
            # Check if this specific instance has an active connection
            channel_key = self._channel_key(user_id, instance_id)
            if channel_key in self._channels:
                await self._stop_channel_by_key(channel_key)
                logger.info(f"Stopped Feishu client for {channel_key}")

            # Check if there's still config for this instance
            config_dict = await self._storage.get_config(user_id, ChannelType.FEISHU, instance_id)
            if config_dict and config_dict.get("enabled", True):
                if await self._refresh_node_membership():
                    nodes = await self._list_active_node_ids()
                    if self._instance_id not in nodes:
                        nodes.append(self._instance_id)
                    app_id = config_dict.get("app_id") or ""
                    if self._preferred_owner(app_id, sorted(nodes)) != self._instance_id:
                        return True
                config = self._dict_to_config(user_id, config_dict, instance_id)
                return await self._start_user_client(config)
            return True

        # Legacy behavior: reload all instances for user
        feishu_configs = await self._storage.list_user_configs_by_type(user_id, ChannelType.FEISHU)

        # Stop all existing clients
        for key in list(self._channels.keys()):
            if key.startswith(user_id):
                await self._stop_channel_by_key(key)

        # Start all enabled clients
        for config_dict in feishu_configs:
            if config_dict.get("enabled", True):
                inst_id = config_dict.get("instance_id")
                app_id = config_dict.get("app_id") or ""
                if await self._refresh_node_membership():
                    nodes = await self._list_active_node_ids()
                    if self._instance_id not in nodes:
                        nodes.append(self._instance_id)
                    if self._preferred_owner(app_id, sorted(nodes)) != self._instance_id:
                        continue
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
                return cast(FeishuChannel, channel)

        channel = self._channels.get(user_id)
        if channel:
            return cast(FeishuChannel, channel)

        # Fallback: find first channel whose key starts with "user_id:"
        prefix = f"{user_id}:"
        for key, ch in self._channels.items():
            if key.startswith(prefix):
                logger.debug(
                    f"[Feishu] _find_channel fallback: matched key '{key}' for user '{user_id}'"
                )
                return cast(FeishuChannel, ch)

        return None

    async def send_message(
        self,
        user_id: str,
        chat_id: str,
        content: str,
        instance_id: Optional[str] = None,
    ) -> bool:
        """Send a message through a user's Feishu bot."""
        client = self._find_channel(user_id, instance_id)
        if not client:
            logger.warning(f"No Feishu client for user {user_id}, instance {instance_id}")
            return False

        return await client.send_message(chat_id, content)

    async def send_card_message_with_id(
        self,
        user_id: str,
        chat_id: str,
        card_content: str,
        instance_id: Optional[str] = None,
        reply_to_id: str | None = None,
    ) -> tuple[bool, str | None]:
        """Send an interactive card through a user's Feishu bot."""
        logger.info("[Feishu] Sending card user=%s chat=%s", user_id, chat_id)
        client = self._find_channel(user_id, instance_id)
        if not client:
            logger.warning(f"No Feishu client for user {user_id}, instance {instance_id}")
            return False, None
        receive_id_type, receive_id = client._resolve_receive_id(chat_id)
        success, message_id = await client._send_card_message_internal(
            receive_id_type,
            receive_id,
            card_content,
            reply_to_id,
        )
        logger.info(
            "[Feishu] Card sent ok=%s message_id=%s user=%s chat=%s",
            success,
            message_id,
            user_id,
            chat_id,
        )
        return success, message_id

    async def add_reaction(
        self,
        user_id: str,
        message_id: str,
        emoji_type: str,
        instance_id: Optional[str] = None,
    ) -> str | None:
        """Add a reaction emoji to a message via a user's Feishu bot."""
        client = self._find_channel(user_id, instance_id)
        if not client:
            return None
        return await client._add_reaction(message_id, emoji_type)

    async def delete_reaction(
        self,
        user_id: str,
        message_id: str,
        reaction_id: str,
        instance_id: Optional[str] = None,
    ) -> bool:
        """Delete a reaction emoji from a message via a user's Feishu bot."""
        client = self._find_channel(user_id, instance_id)
        if not client:
            return False
        return await client._delete_reaction(message_id, reaction_id)

    def is_connected(self, user_id: str, instance_id: Optional[str] = None) -> bool:
        """Check if a user's Feishu bot is connected."""
        channel = self._find_channel(user_id, instance_id)
        return channel is not None and channel._running

    async def is_connected_distributed(
        self, user_id: str, instance_id: Optional[str] = None
    ) -> bool:
        """Check whether a Feishu bot is connected anywhere in the cluster."""
        if self.is_connected(user_id, instance_id):
            return True

        if instance_id:
            config = await self._storage.get_config(user_id, ChannelType.FEISHU, instance_id)
            return await self._has_cluster_lease(config)

        configs = await self._storage.list_user_configs_by_type(user_id, ChannelType.FEISHU)
        for config in configs:
            if not config.get("enabled", True):
                continue
            config_instance_id = config.get("instance_id")
            if config_instance_id and self.is_connected(user_id, config_instance_id):
                return True
            if await self._has_cluster_lease(config):
                return True
        return False

    async def _stop_channel_by_key(self, channel_key: str) -> None:
        channel = self._channels.pop(channel_key, None)
        if not channel:
            return

        old_app_id = getattr(channel.config, "app_id", None)
        if old_app_id and self._active_app_ids.get(old_app_id) == channel_key:
            del self._active_app_ids[old_app_id]

        try:
            await channel.stop()
        except Exception as e:
            logger.error(f"Error stopping Feishu client {channel_key}: {e}")

        if old_app_id:
            await self._release_lease(old_app_id)

    async def _has_cluster_lease(self, config: dict[str, Any] | None) -> bool:
        if not config or not config.get("enabled", True):
            return False
        app_id = config.get("app_id") or ""
        if not app_id:
            return False
        try:
            redis = self._get_lease_redis()
            return bool(await redis.get(self._lease_key(app_id)))
        except Exception as e:
            logger.warning("[Feishu] Failed to read lease for app_id=%s: %s", app_id, e)
            return False

    @staticmethod
    def _lease_key(app_id: str) -> str:
        return f"{_FEISHU_LEASE_PREFIX}:{app_id}"

    async def _acquire_lease(self, app_id: str) -> bool:
        try:
            redis = self._get_lease_redis()
            claimed = await redis.set(
                self._lease_key(app_id),
                self._instance_id,
                nx=True,
                ex=_FEISHU_LEASE_TTL_SECONDS,
            )
            return bool(claimed)
        except Exception as e:
            logger.warning("[Feishu] Failed to acquire lease for app_id=%s: %s", app_id, e)
            return False

    def _ensure_lease_refresh_task(self, app_id: str) -> None:
        if app_id in self._lease_tasks:
            return

        async def _refresh() -> None:
            try:
                redis = self._get_lease_redis()
                while True:
                    await asyncio.sleep(_FEISHU_LEASE_REFRESH_INTERVAL)
                    if app_id not in self._active_app_ids:
                        return
                    refreshed = await redis.eval(
                        _REFRESH_LEASE_LUA,
                        1,
                        self._lease_key(app_id),
                        self._instance_id,
                        _FEISHU_LEASE_TTL_SECONDS,
                    )
                    if not refreshed:
                        logger.warning(
                            "[Feishu] Lost lease refresh for app_id=%s on instance=%s",
                            app_id,
                            self._instance_id,
                        )
                        await self._stop_channel_after_lost_lease(app_id)
                        return
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.warning("[Feishu] Lease refresh failed for app_id=%s: %s", app_id, e)
                await self._stop_channel_after_lost_lease(app_id)
            finally:
                self._lease_tasks.pop(app_id, None)

        self._lease_tasks[app_id] = asyncio.create_task(_refresh())

    async def _stop_channel_after_lost_lease(self, app_id: str) -> None:
        channel_key = self._active_app_ids.pop(app_id, None)
        if not channel_key:
            return

        channel = self._channels.pop(channel_key, None)
        if not channel:
            return

        try:
            await channel.stop()
            logger.warning(
                "[Feishu] Stopped local channel '%s' after losing lease for app_id=%s",
                channel_key,
                app_id,
            )
        except Exception as e:
            logger.error(
                "[Feishu] Failed to stop channel '%s' after losing lease for app_id=%s: %s",
                channel_key,
                app_id,
                e,
            )

    async def _release_lease(self, app_id: str) -> None:
        task = self._lease_tasks.pop(app_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        try:
            redis = self._get_lease_redis()
            await redis.eval(_RELEASE_LEASE_LUA, 1, self._lease_key(app_id), self._instance_id)
        except Exception as e:
            logger.warning("[Feishu] Failed to release lease for app_id=%s: %s", app_id, e)

    def _cancel_all_lease_tasks(self) -> None:
        for app_id in list(self._lease_tasks.keys()):
            task = self._lease_tasks.pop(app_id, None)
            if task and not task.done():
                task.cancel()

    async def _release_all_leases(self) -> None:
        for app_id in list(self._active_app_ids.keys()):
            await self._release_lease(app_id)

    def _get_lease_redis(self):
        if self._lease_redis is None:
            self._lease_redis = create_redis_client(isolated_pool=True)
        return self._lease_redis

    async def _close_lease_redis(self) -> None:
        if self._lease_redis is None:
            return
        try:
            await self._lease_redis.aclose()
        except Exception as e:
            logger.warning("[Feishu] Failed to close lease redis client: %s", e)
        finally:
            self._lease_redis = None


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
    from src.infra.channel.feishu.registration import close_registration_sessions

    close_registration_sessions()
