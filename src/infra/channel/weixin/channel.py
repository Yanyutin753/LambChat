"""微信 iLink Bot 渠道实现。

长轮询收消息（Redis 分布式锁单副本消费，游标处理完才持久化）+
/sendmessage 出站发送。收到消息经 ``_handle_message`` 回调进入
agent 执行管线（见 handler.py）。
"""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from typing import Any, Callable, Optional

import httpx

from src.infra.channel.base import BaseChannel
from src.infra.channel.weixin import provider
from src.infra.logging import get_logger
from src.kernel.schemas.channel import (
    ChannelCapability,
    ChannelType,
)
from src.kernel.schemas.weixin import WeixinConfig, WeixinGroupPolicy

logger = get_logger(__name__)

POLL_LOCK_TTL_SECONDS = 150  # 需覆盖 90s 长轮询；处理期由续期任务兜住
POLL_ERROR_BACKOFF_MAX_SECONDS = 60
LOCK_RENEW_INTERVAL_SECONDS = 45
SEEN_MESSAGE_TTL_SECONDS = 3600
# iLink 消息体实测无 id 字段，退回内容指纹去重；短窗只挡跨副本双消费的
# 秒级窗口，避免误吞用户短时间连发的相同内容消息
SEEN_FINGERPRINT_TTL_SECONDS = 300
POLL_LOCK_RETRY_SECONDS = 10
POLL_ERROR_BACKOFF_SECONDS = 5


def _buf_key(user_id: str, instance_id: str) -> str:
    return f"weixin:buf:{user_id}:{instance_id}"


def _lock_key(user_id: str, instance_id: str) -> str:
    return f"weixin:poll-lock:{user_id}:{instance_id}"


def _seen_key(key: str) -> str:
    return f"weixin:seen:{key}"


def _dedup_key(message: dict[str, Any]) -> tuple[str, int]:
    """去重键：message_id 优先，缺失时退回 (chat|sender|content) 指纹。"""
    message_id = message.get("message_id")
    if message_id:
        return str(message_id), SEEN_MESSAGE_TTL_SECONDS
    fingerprint = hashlib.sha256(
        f"{message.get('chat_id', '')}|{message.get('sender_id', '')}|"
        f"{message.get('content', '')}".encode()
    ).hexdigest()
    return f"fp:{fingerprint}", SEEN_FINGERPRINT_TTL_SECONDS


async def _mark_message_seen(key: str, ttl: int = SEEN_MESSAGE_TTL_SECONDS) -> bool:
    """去重标记；已见过返回 False（锁过期被其他副本重拉时兜底）。"""
    from src.infra.storage.redis import get_redis_client

    try:
        return bool(await get_redis_client().set(_seen_key(key), "1", nx=True, ex=ttl))
    except Exception as e:
        logger.debug("weixin seen-mark failed (allowing message): %s", e)
        return True  # 去重基础设施故障时宁可重复不可丢


async def _acquire_poll_lock(
    user_id: str, instance_id: str, owner: str, client: Any = None
) -> bool:
    """SET NX + TTL 锁（值=owner 令牌）：多副本部署只有一个实例消费 getupdates 游标。"""
    from src.infra.storage.redis import get_redis_client

    try:
        redis = client or get_redis_client()
        return bool(
            await redis.set(
                _lock_key(user_id, instance_id), owner, nx=True, ex=POLL_LOCK_TTL_SECONDS
            )
        )
    except Exception as e:
        logger.warning("weixin poll lock acquire failed: %s", e)
        return False


async def _renew_poll_lock(user_id: str, instance_id: str, owner: str, client: Any = None) -> bool:
    """只有锁值仍是自己的 owner 令牌才续期；过期或被夺走返回 False。"""
    from src.infra.storage.redis import get_redis_client

    try:
        redis = client or get_redis_client()
        current = await redis.get(_lock_key(user_id, instance_id))
        if current != owner:
            return False
        await redis.expire(_lock_key(user_id, instance_id), POLL_LOCK_TTL_SECONDS)
        return True
    except Exception as e:
        logger.debug("weixin poll lock renew failed: %s", e)
        return False


async def _release_poll_lock(
    user_id: str, instance_id: str, owner: str, client: Any = None
) -> None:
    """释放锁前校验 owner：锁已易主时不动他人的锁。"""
    from src.infra.storage.redis import get_redis_client

    try:
        redis = client or get_redis_client()
        key = _lock_key(user_id, instance_id)
        if await redis.get(key) == owner:
            await redis.delete(key)
    except Exception as e:
        logger.debug("weixin poll lock release failed: %s", e)


class WeixinChannel(BaseChannel):
    """微信 iLink Bot 双向渠道。"""

    channel_type = ChannelType.WEIXIN
    display_name = "WeChat Bot"
    description = "Chat with your agent in WeChat via the official iLink bot API"
    icon = "message-circle"

    def __init__(self, config: WeixinConfig, message_handler: Optional[Callable] = None):
        super().__init__(config, message_handler)
        self._http: httpx.AsyncClient | None = None
        self._http_lock: asyncio.Lock | None = None
        self._poll_task: asyncio.Task | None = None
        self._lock_owner: str | None = None
        self._last_context_tokens: dict[str, str] = {}

    # ── 生命周期 ──

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http_lock is None:
            self._http_lock = asyncio.Lock()
        async with self._http_lock:
            if self._http is None or self._http.is_closed:
                self._http = httpx.AsyncClient(
                    timeout=httpx.Timeout(provider.GET_UPDATES_TIMEOUT_SECONDS + 10)
                )
        return self._http

    async def start(self) -> bool:
        if not self.config.bot_token:
            logger.warning("weixin bot token missing for user %s", self.user_id)
            return False
        client = await self._get_http()
        if not await provider.verify_token(client, self.config.bot_token):
            return False
        if self._poll_task is None or self._poll_task.done():
            self._poll_task = asyncio.create_task(self._poll_loop())
        self._running = True
        return True

    async def stop(self) -> None:
        self._running = False
        task, self._poll_task = self._poll_task, None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        client, self._http = self._http, None
        if client is not None and not client.is_closed:
            await client.aclose()
        if self._lock_owner:
            await _release_poll_lock(self.config.user_id, self.config.instance_id, self._lock_owner)
            self._lock_owner = None

    # ── 收消息 ──

    async def _poll_loop(self) -> None:
        """持锁长轮询；拿不到锁则以 standby 节奏重试（等其他副本让位）。

        每轮长轮询前必须确认锁仍归自己（owner 令牌续期）：空闲期连续两轮
        90s 长轮询即可耗尽 150s TTL，锁过期被其他副本夺走后若不自知，
        双副本会同时消费同一 bot 导致一条消息回答两次（生产事故复盘）。
        """
        backoff = POLL_ERROR_BACKOFF_SECONDS
        while self._running:
            owner = uuid.uuid4().hex
            locked = await _acquire_poll_lock(self.config.user_id, self.config.instance_id, owner)
            if not locked:
                await asyncio.sleep(POLL_LOCK_RETRY_SECONDS)
                continue
            self._lock_owner = owner
            try:
                while self._running:
                    if not await _renew_poll_lock(
                        self.config.user_id, self.config.instance_id, owner
                    ):
                        logger.warning(
                            "weixin poll lock lost (user %s); yielding consumption",
                            self.config.user_id,
                        )
                        break  # 锁已易主，立即让位防双消费
                    try:
                        await self._consume_once()
                        backoff = POLL_ERROR_BACKOFF_SECONDS  # 成功即重置退避
                    except asyncio.CancelledError:
                        raise
                    except Exception as e:
                        logger.warning("weixin poll error (user %s): %s", self.config.user_id, e)
                        # token 失效/网络故障时指数退避，避免 5s 空转刷接口
                        await asyncio.sleep(backoff)
                        backoff = min(backoff * 2, POLL_ERROR_BACKOFF_MAX_SECONDS)
            finally:
                await _release_poll_lock(self.config.user_id, self.config.instance_id, owner)
                self._lock_owner = None
            if self._running:
                await asyncio.sleep(POLL_LOCK_RETRY_SECONDS)

    async def _consume_once(self, storage: Any = None) -> bool:
        """拉一批消息并分发；返回是否处理了消息（供测试注入 storage）。"""
        from src.infra.storage.redis import RedisStorage

        redis = storage or RedisStorage()
        client = await self._get_http()
        buf_key = _buf_key(self.config.user_id, self.config.instance_id)
        raw_buf = await redis.get(buf_key)
        buf = str(raw_buf) if raw_buf is not None else ""
        messages, next_buf = await provider.get_updates(client, self.config.bot_token, buf)

        for message in messages:
            # 群聊消息按策略过滤（chat_id 为 room 时与发送者不同）
            if (
                self.config.group_policy == WeixinGroupPolicy.OFF
                and message["chat_id"] != message["sender_id"]
            ):
                continue
            dedup_key, dedup_ttl = _dedup_key(message)
            if not await _mark_message_seen(dedup_key, ttl=dedup_ttl):
                logger.debug("weixin duplicate message skipped: %s", dedup_key)
                continue
            await self._with_lock_renewal(self._dispatch_message(message))

        # 游标在本批消息全部处理完成后才持久化：中途失败下轮按旧游标重拉，
        # 宁可重复投递不可丢消息
        if next_buf:
            await redis.set(buf_key, next_buf)
        return bool(messages)

    async def _with_lock_renewal(self, coro: Any) -> Any:
        """agent 执行可达分钟级，远超锁 TTL；处理期间周期续期防他副本重入。"""
        renew_task = asyncio.create_task(self._renew_lock_loop())
        try:
            return await coro
        finally:
            renew_task.cancel()

    async def _renew_lock_loop(self) -> None:
        while True:
            await asyncio.sleep(LOCK_RENEW_INTERVAL_SECONDS)
            try:
                # owner 校验续期：锁已易主时不给他人的锁续命，让位由
                # _poll_loop 每轮开头的 renew 检查完成
                if self._lock_owner and not await _renew_poll_lock(
                    self.config.user_id, self.config.instance_id, self._lock_owner
                ):
                    logger.warning(
                        "weixin poll lock lost during dispatch (user %s)",
                        self.config.user_id,
                    )
            except asyncio.CancelledError:
                raise
            except Exception:
                pass  # 续期失败由外层锁语义兜底（at-least-once + 去重）

    async def _dispatch_message(self, message: dict[str, Any]) -> None:
        context_token = message.get("context_token")
        if context_token:
            self._last_context_tokens[message["chat_id"]] = context_token
        await self._handle_message(
            sender_id=message["sender_id"],
            chat_id=message["chat_id"],
            content=message["content"],
            metadata={
                "context_token": context_token,
                "message_id": message.get("message_id"),
                "display_name": message.get("display_name"),
                "instance_id": self.config.instance_id or None,
            },
        )

    # ── 发消息 ──

    async def send_message(self, chat_id: str, content: str, **kwargs: Any) -> bool:
        if not content or not content.strip():
            return False
        target = chat_id or getattr(self.config, "default_chat_id", "") or ""
        if not target:
            logger.warning("weixin send_message has no target chat (user %s)", self.user_id)
            return False
        client = await self._get_http()
        context_token = kwargs.get("context_token") or self._last_context_tokens.get(target)
        return await provider.send_bot_message(
            client,
            self.config.bot_token,
            to_user_id=target,
            text=content,
            context_token=context_token,
        )

    # ── 元数据 ──

    @classmethod
    def get_capabilities(cls) -> list[ChannelCapability]:
        return WeixinConfig.get_capabilities()

    @classmethod
    def get_config_fields(cls) -> list[dict[str, Any]]:
        return [
            {
                "name": "bot_token",
                "title": "Bot Token",
                "type": "password",
                "required": True,
                "sensitive": True,
                "placeholder": "点击「扫码登录」自动获取",
            },
            {
                "name": "default_chat_id",
                "title": "Default Chat ID",
                "type": "text",
                "required": False,
                "sensitive": False,
                "placeholder": "出站推送默认目标（微信 user id），可从对话消息日志获取",
            },
            {
                "name": "group_policy",
                "title": "Group Policy",
                "type": "select",
                "required": False,
                "sensitive": False,
                "default": "open",
                "options": [
                    {"value": "open", "label": "Respond in groups and DMs"},
                    {"value": "off", "label": "DMs only"},
                ],
            },
        ]

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        from src.infra.channel.outbound import OutboundChannel

        return OutboundChannel._build_config_schema(cls.get_config_fields())

    @classmethod
    def get_setup_guide(cls) -> list[str]:
        return [
            "Click 扫码登录 (Scan QR) and confirm on your phone",
            "The bot token is filled automatically after scanning",
            "Send a message to the bot in WeChat to start chatting",
        ]
