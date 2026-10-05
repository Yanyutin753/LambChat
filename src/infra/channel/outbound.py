"""出站推送渠道共享基类。

面向「只发不收」的通知渠道（钉钉/企微/Telegram/Slack/Discord/ntfy/Bark/
Gotify/Pushover/Server酱/PushPlus 等）：无长连接、无入站消息回调，
``start()`` 即就绪，``send_message()`` 全异步发送。共享能力：

- 每实例懒建一个 ``httpx.AsyncClient``（同实例多次发送复用连接池），stop 关闭；
- 统一超时（默认 10s）、内容截断、标题提取（首行清洗，供不支持
  title 概念的平台或默认展示使用）；
- 网络异常/非 2xx 不抛出，统一返回 False 并记日志（投递方按布尔处理）。
"""

from __future__ import annotations

import asyncio
from abc import abstractmethod
from typing import Any, Callable, Optional

import httpx

from src.infra.channel.base import BaseChannel, UserChannelManager
from src.infra.logging import get_logger
from src.kernel.schemas.channel import ChannelCapability

logger = get_logger(__name__)


def _redact_url(url: str) -> str:
    """只保留主机；bot token/webhook secret 也可能位于 path 或 userinfo。"""
    from urllib.parse import urlsplit

    try:
        parts = urlsplit(url)
        return parts.hostname or "<invalid-url>"
    except Exception:
        return "<invalid-url>"


_DEFAULT_TITLE_FALLBACK = "LambChat"


def default_title(content: str) -> str:
    """取内容首行、去掉 Markdown 前缀符号，作为通知标题（≤40 字符）。"""
    first = content.lstrip().splitlines()[0] if content.strip() else ""
    cleaned = first.lstrip("#*>- ").strip()
    return (cleaned or _DEFAULT_TITLE_FALLBACK)[:40]


class OutboundChannel(BaseChannel):
    """出站推送渠道基类：子类只需实现 ``_send`` 与配置模型。"""

    capabilities: tuple[ChannelCapability, ...] = (ChannelCapability.SEND_MESSAGE,)

    # 子类按平台限制覆盖（Telegram 4096 / Discord 2000 / 企微 markdown 4096 字节…）
    max_content_chars: int = 3800
    timeout_seconds: float = 10.0

    def __init__(self, config: Any, message_handler: Optional[Callable] = None):
        super().__init__(config, message_handler)
        self._http: Optional[httpx.AsyncClient] = None
        self._http_lock: Optional[asyncio.Lock] = None

    # ── 生命周期 ──

    async def start(self) -> bool:
        self._running = True
        return True

    async def stop(self) -> None:
        self._running = False
        client, self._http = self._http, None
        if client is not None and not client.is_closed:
            await client.aclose()

    async def _get_http(self) -> httpx.AsyncClient:
        """懒建共享 client；意外关闭后自愈重建。"""
        if self._http_lock is None:
            self._http_lock = asyncio.Lock()
        async with self._http_lock:
            if self._http is None or self._http.is_closed:
                self._http = httpx.AsyncClient(timeout=self.timeout_seconds)
        return self._http

    # ── 发送 ──

    async def send_message(self, chat_id: str, content: str, **kwargs: Any) -> bool:
        if not content or not content.strip():
            return False
        title = str(kwargs.get("title") or default_title(content))
        target = chat_id or self._default_target()
        trimmed = content[: self.max_content_chars]
        try:
            return await self._send(title=title, content=trimmed, target=target)
        except Exception as e:
            logger.warning(
                "%s send failed for user %s: %s",
                self.channel_type.value,
                self.user_id,
                type(e).__name__,
            )
            return False

    def _default_target(self) -> str:
        """未显式指定 chat_id 时的目标（默认取配置里的 default_chat_id）。"""
        return str(getattr(self.config, "default_chat_id", "") or "")

    @abstractmethod
    async def _send(self, *, title: str, content: str, target: str) -> bool:
        """把消息投递到平台；成功返回 True，失败返回 False（勿抛异常）。"""

    async def _post(
        self,
        url: str,
        *,
        json: Any = None,
        data: Any = None,
        content: Any = None,
        headers: Any = None,
    ) -> Optional[httpx.Response]:
        """POST 并吞掉网络错误；返回 None 表示请求未送达。"""
        client = await self._get_http()
        try:
            response = await client.post(
                url, json=json, data=data, content=content, headers=headers
            )
        except httpx.HTTPError as e:
            # Exception text can itself embed the full credential-bearing URL.
            logger.warning(
                "%s request failed (%s): %s",
                self.channel_type.value,
                _redact_url(url),
                type(e).__name__,
            )
            return None
        return response

    @classmethod
    def get_capabilities(cls) -> list[ChannelCapability]:
        return list(cls.capabilities)

    @classmethod
    def _build_config_schema(cls, fields: list[dict[str, Any]]) -> dict[str, Any]:
        """由 config_fields 程序化生成 JSON Schema，避免双份手工维护。"""
        properties: dict[str, Any] = {}
        required: list[str] = []
        for field in fields:
            name = field.get("name", "")
            field_type = field.get("type", "text")
            properties[name] = {
                "type": "string" if field_type != "toggle" else "boolean",
                "description": field.get("title", name),
            }
            if field.get("default") is not None:
                properties[name]["default"] = field.get("default")
            if field.get("required"):
                required.append(name)
        return {"type": "object", "properties": properties, "required": required}


class OutboundChannelManager(UserChannelManager):
    """出站渠道通用 manager：加载 enabled 配置、按 user:instance 持有实例。

    无长连接即无「接管」问题，不需要 Redis lease——任何实例发消息都是
    无状态 HTTP 调用，多副本部署天然安全。

    子类需显式声明 ``channel_type`` / ``channel_class`` / ``config_class``
    （channel_type 必须是类属性——registry 按 ``cls.channel_type.value`` 访问）。
    """

    channel_class: type[OutboundChannel]
    config_class: type

    def __init__(self, message_handler: Optional[Callable] = None):
        super().__init__(message_handler)
        self._storage: Any = None
        self._config_snapshots: dict[str, dict[str, Any]] = {}

    def _get_storage(self) -> Any:
        if self._storage is None:
            from src.infra.channel.channel_storage import ChannelStorage

            self._storage = ChannelStorage()
        return self._storage

    def _build_channel(self, config_dict: dict[str, Any]) -> OutboundChannel:
        # 展平的存储 dict（含 user_id/instance_id 等元数据）直接喂给
        # pydantic 配置模型，未知字段默认忽略。
        return self.channel_class(self.config_class(**config_dict))

    async def _start_instance(self, config_dict: dict[str, Any]) -> Optional[OutboundChannel]:
        key = self._channel_key(config_dict)
        old = self._channels.pop(key, None)
        self._config_snapshots.pop(key, None)
        if old is not None:
            await old.stop()
        channel = self._build_channel(config_dict)
        try:
            if not await channel.start():
                logger.warning("Failed to start %s channel for %s", self.channel_type.value, key)
                await channel.stop()
                return None
        except asyncio.CancelledError:
            await channel.stop()
            raise
        except Exception as e:
            logger.error("Error starting %s channel for %s: %s", self.channel_type.value, key, e)
            await channel.stop()
            return None
        self._config_snapshots[key] = dict(config_dict)
        self._channels[key] = channel
        return channel

    @staticmethod
    def _channel_key(config_dict: dict[str, Any]) -> str:
        return f"{config_dict.get('user_id', '')}:{config_dict.get('instance_id', '')}"

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
                logger.error("Error stopping %s channel: %s", self.channel_type.value, e)
        self._channels.clear()
        self._config_snapshots.clear()

    async def reload_user(self, user_id: str, instance_id: Optional[str] = None) -> bool:
        async with self._lifecycle_lock:
            if self._stopping:
                return False
            return await self._reload_user_locked(user_id, instance_id)

    async def _reload_user_locked(self, user_id: str, instance_id: Optional[str] = None) -> bool:
        configs = await self._get_storage().list_user_configs_by_type(user_id, self.channel_type)
        # 路由契约：disable/delete 靠 reload_user 停止运行中实例（先停再按需重启）
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


async def start_outbound_channels() -> None:
    """启动注册表发现的全部出站渠道 manager（幂等，应用启动时调用）。"""
    from src.infra.channel.registry import discover_all_managers

    for slug, manager_cls in discover_all_managers().items():
        if not issubclass(manager_cls, OutboundChannelManager):
            continue
        try:
            manager = manager_cls.get_instance()
            await manager.start()
            logger.info("Started %s outbound channel manager", slug)
        except Exception as e:
            logger.error("Failed to start %s outbound channel manager: %s", slug, e)


async def stop_outbound_channels() -> None:
    """停掉全部出站渠道 manager 单例（应用关停时调用，不影响飞书）。"""
    from src.infra.channel.base import UserChannelManager as _BaseManager

    outbound_instances = [
        (cls, inst)
        for cls, inst in _BaseManager._instances.items()
        if isinstance(inst, OutboundChannelManager)
    ]
    for cls, inst in outbound_instances:
        _BaseManager._instances.pop(cls, None)
        try:
            await inst.stop()
        except Exception as e:
            logger.warning("Error stopping %s outbound manager: %s", cls.__name__, e)
