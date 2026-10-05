"""微信渠道 manager：加载 enabled 配置并持有渠道实例。"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from src.infra.channel.base import UserChannelManager
from src.infra.channel.weixin.channel import WeixinChannel
from src.infra.logging import get_logger
from src.kernel.schemas.channel import ChannelType
from src.kernel.schemas.weixin import WeixinConfig

logger = get_logger(__name__)


class WeixinChannelManager(UserChannelManager):
    channel_type = ChannelType.WEIXIN
    config_class = WeixinConfig

    @classmethod
    def get_instance(cls) -> "WeixinChannelManager":
        """复用全局单例：路由/pubsub/coordinator 都经 get_instance() 取实例，
        若默认实现另建一个无 message_handler 的 manager，会抢轮询锁吞消息。"""
        return get_weixin_channel_manager()

    def __init__(self, message_handler=None):
        super().__init__(message_handler)
        self._storage: Any = None
        self._config_snapshots: dict[str, dict[str, Any]] = {}

    def _get_storage(self) -> Any:
        if self._storage is None:
            from src.infra.channel.channel_storage import ChannelStorage

            self._storage = ChannelStorage()
        return self._storage

    def _build_channel(self, config_dict: dict[str, Any]) -> WeixinChannel:
        return WeixinChannel(WeixinConfig(**config_dict), self.message_handler)

    async def start(self) -> None:
        async with self._lifecycle_lock:
            await self._start_locked()

    async def _start_locked(self) -> None:
        self._stopping = False
        self._running = True
        self._ensure_reconcile_task(self._reconcile_enabled_configs)
        try:
            await self._reconcile_enabled_configs()
        except Exception as exc:
            logger.error("Failed to load %s configs: %s", self.channel_type.value, exc)

    async def _reconcile_enabled_configs(self) -> None:
        desired: set[str] = set()
        async for config in self._get_storage().iter_enabled_configs(self.channel_type):
            key = f"{config.get('user_id', '')}:{config.get('instance_id', '')}"
            desired.add(key)
            channel = self._channels.get(key)
            if (
                channel is None
                or not channel.is_running
                or self._config_snapshots.get(key) != config
            ):
                await self._start_instance(config)
            elif self.message_handler is not None:
                channel.message_handler = self.message_handler
        for key in list(self._channels):
            if key not in desired:
                await self._channels.pop(key).stop()
                self._config_snapshots.pop(key, None)

    async def _start_instance(self, config_dict: dict[str, Any]) -> Optional[WeixinChannel]:
        key = f"{config_dict.get('user_id', '')}:{config_dict.get('instance_id', '')}"
        old = self._channels.pop(key, None)
        self._config_snapshots.pop(key, None)
        if old is not None:
            await old.stop()
        channel = self._build_channel(config_dict)
        try:
            if not await channel.start():
                logger.warning("Failed to start weixin channel for %s (token invalid?)", key)
                await channel.stop()
                return None
        except asyncio.CancelledError:
            await channel.stop()
            raise
        except Exception as e:
            logger.error("Error starting weixin channel for %s: %s", key, e)
            await channel.stop()
            return None
        self._config_snapshots[key] = dict(config_dict)
        self._channels[key] = channel
        return channel

    async def stop(self) -> None:
        async with self._lifecycle_lock:
            await self._stop_locked()

    async def _stop_locked(self) -> None:
        self._stopping = True
        self._running = False
        await self._cancel_reconcile_task()
        for channel in list(self._channels.values()):
            try:
                await channel.stop()
            except Exception as e:
                logger.error("Error stopping weixin channel: %s", e)
        self._channels.clear()
        self._config_snapshots.clear()

    async def reload_user(self, user_id: str, instance_id: Optional[str] = None) -> bool:
        async with self._lifecycle_lock:
            if self._stopping:
                return False
            return await self._reload_user_locked(user_id, instance_id)

    async def _reload_user_locked(self, user_id: str, instance_id: Optional[str] = None) -> bool:
        configs = await self._get_storage().list_user_configs_by_type(user_id, ChannelType.WEIXIN)
        # 路由契约：disable/delete 先落库再 reload_user 停止运行中的实例。
        # 停止范围=目标实例（instance_id 指定时）或该用户全部实例。
        prefix = f"{user_id}:"
        keys_to_stop = [
            key
            for key in list(self._channels)
            if key.startswith(prefix) and (not instance_id or key == f"{user_id}:{instance_id}")
        ]
        matched = [
            cfg
            for cfg in configs
            if cfg.get("enabled", True)
            and (not instance_id or cfg.get("instance_id") == instance_id)
        ]
        if not keys_to_stop and not matched:
            return False
        for key in keys_to_stop:
            stopped = self._channels.pop(key, None)
            self._config_snapshots.pop(key, None)
            if stopped is not None:
                await stopped.stop()
        for config_dict in matched:
            await self._start_instance(config_dict)
        return True

    async def send_message(
        self,
        user_id: str,
        chat_id: str,
        content: str,
        instance_id: Optional[str] = None,
        context_token: Optional[str] = None,
    ) -> bool:
        """handler 回复用：直接路由到对应实例（带 context_token）。"""
        channel = self.get_channel(user_id, instance_id)
        if not channel:
            logger.warning("No weixin channel for user %s instance %s", user_id, instance_id)
            return False
        return await channel.send_message(chat_id, content, context_token=context_token)


# 全局实例（setup_weixin_handler 用，与 feishu manager 模式一致）
_weixin_channel_manager: Optional[WeixinChannelManager] = None


def get_weixin_channel_manager() -> WeixinChannelManager:
    global _weixin_channel_manager
    if _weixin_channel_manager is None:
        _weixin_channel_manager = WeixinChannelManager()
    return _weixin_channel_manager


async def setup_weixin_handler(default_agent: str) -> None:
    """启动微信渠道（main.py 生命周期调用）。"""
    manager = get_weixin_channel_manager()
    from src.infra.channel.weixin.handler import create_weixin_message_handler

    manager.message_handler = create_weixin_message_handler(manager, default_agent)
    await manager.start()


async def stop_weixin_channels() -> None:
    global _weixin_channel_manager
    if _weixin_channel_manager is not None:
        await _weixin_channel_manager.stop()
        _weixin_channel_manager = None
    from src.infra.channel.weixin.provider import close_client

    await close_client()
