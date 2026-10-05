"""微信 iLink Bot 渠道实现。

长轮询收消息（Redis 分布式锁单副本消费，消息持久化后推进游标）+
/sendmessage 出站发送。收到消息经 ``_handle_message`` 回调进入
agent 执行管线（见 handler.py）。
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import uuid
from typing import Any, Callable, Optional

import httpx

from src.infra.channel.base import BaseChannel
from src.infra.channel.inbox import ChannelInbox
from src.infra.channel.inbox_worker import InboxWorker
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
POLL_LOCK_RETRY_SECONDS = 10
POLL_ERROR_BACKOFF_SECONDS = 5

_RENEW_LOCK_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('expire', KEYS[1], ARGV[2])
end
return 0
"""
_RELEASE_LOCK_LUA = """
if redis.call('get', KEYS[1]) == ARGV[1] then
    return redis.call('del', KEYS[1])
end
return 0
"""


def _buf_key(user_id: str, instance_id: str) -> str:
    return f"weixin:buf:{user_id}:{instance_id}"


def _lock_key(user_id: str, instance_id: str) -> str:
    return f"weixin:poll-lock:{user_id}:{instance_id}"


def _dedup_key(message: dict[str, Any], batch_cursor: str | None, index: int) -> str | None:
    """优先消息 ID；缺失时只识别同一响应批次内的同一条消息。"""
    message_id = message.get("message_id")
    if message_id:
        return f"id:{message_id}"
    if not batch_cursor:
        return None  # 没有可靠投递身份时宁可重复，不误吞正常的相同文本。
    fingerprint = hashlib.sha256(
        json.dumps(
            [
                batch_cursor,
                index,
                message.get("chat_id"),
                message.get("sender_id"),
                message.get("content"),
                message.get("context_token"),
            ],
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    return f"fp:{fingerprint}"


async def _acquire_poll_lock(
    user_id: str, instance_id: str, owner: str, client: Any = None
) -> bool:
    """SET NX + TTL 锁（值=owner 令牌）：多副本部署只有一个实例消费 getupdates 游标。"""
    from src.infra.storage.redis import get_redis_client

    try:
        redis: Any = client or get_redis_client()
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
        redis: Any = client or get_redis_client()
        return bool(
            await redis.eval(
                _RENEW_LOCK_LUA, 1, _lock_key(user_id, instance_id), owner, POLL_LOCK_TTL_SECONDS
            )
        )
    except Exception as e:
        logger.debug("weixin poll lock renew failed: %s", e)
        return False


async def _release_poll_lock(
    user_id: str, instance_id: str, owner: str, client: Any = None
) -> None:
    """释放锁前校验 owner：锁已易主时不动他人的锁。"""
    from src.infra.storage.redis import get_redis_client

    try:
        redis: Any = client or get_redis_client()
        await redis.eval(_RELEASE_LOCK_LUA, 1, _lock_key(user_id, instance_id), owner)
    except Exception as e:
        logger.debug("weixin poll lock release failed: %s", e)


class PollLeaseLostError(RuntimeError):
    """Reader ownership lost; stop execution immediately."""


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
        self._inbox_worker = InboxWorker(
            ChannelInbox(self.channel_type.value, config.user_id, config.instance_id),
            self._deliver_inbox_message,
        )
        self._inbox_task: asyncio.Task | None = None

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
        # Polling owns retries, including transient authentication failures.
        self._running = True
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
            await self._release_reader(self._lock_owner)
            self._lock_owner = None

    # ── 收消息 ──

    @property
    def _reader_scope(self) -> tuple[str, str]:
        # Provider polling is bot-global even when duplicate credentials are
        # configured under different tenants. Never put the token in Redis keys.
        return "bot", hashlib.sha256(self.config.bot_token.encode()).hexdigest()

    async def _acquire_reader(self, owner: str) -> bool:
        if not await _acquire_poll_lock(*self._reader_scope, owner):
            return False
        # Keep the legacy instance lock while older deployments are rolling out.
        # Acquire it second and release the bot lock if an old reader still owns it.
        try:
            if await _acquire_poll_lock(self.config.user_id, self.config.instance_id, owner):
                return True
        except BaseException:
            await self._release_reader(owner)
            raise
        await self._release_reader(owner)
        return False

    async def _release_reader(self, owner: str) -> None:
        await _release_poll_lock(self.config.user_id, self.config.instance_id, owner)
        await _release_poll_lock(*self._reader_scope, owner)

    async def _poll_loop(self) -> None:
        """持锁长轮询；拿不到锁则以 standby 节奏重试（等其他副本让位）。

        每轮长轮询前必须确认锁仍归自己（owner 令牌续期）：空闲期连续两轮
        90s 长轮询即可耗尽 150s TTL，锁过期被其他副本夺走后若不自知，
        双副本会同时消费同一 bot 导致一条消息回答两次（生产事故复盘）。
        """
        while self._running:
            owner = uuid.uuid4().hex
            locked = await self._acquire_reader(owner)
            if not locked:
                await asyncio.sleep(POLL_LOCK_RETRY_SECONDS)
                continue
            self._lock_owner = owner
            self._inbox_task = asyncio.create_task(self._inbox_worker.run())
            try:
                await self._with_lock_renewal(self._consume_loop())
            except PollLeaseLostError:
                logger.warning("weixin poll lease lost (user %s)", self.config.user_id)
            finally:
                await self._inbox_worker.stop()
                if self._inbox_task:
                    self._inbox_task.cancel()
                    await asyncio.gather(self._inbox_task, return_exceptions=True)
                    self._inbox_task = None
                await self._release_reader(owner)
                self._lock_owner = None
            if self._running:
                await asyncio.sleep(POLL_LOCK_RETRY_SECONDS)

    async def _consume_loop(self) -> None:
        backoff = POLL_ERROR_BACKOFF_SECONDS
        while self._running:
            await self._check_poll_owner()
            try:
                await self._consume_once()
                backoff = POLL_ERROR_BACKOFF_SECONDS
            except PollLeaseLostError:
                raise
            except Exception as exc:
                logger.warning(
                    "weixin poll error (user %s): %s", self.config.user_id, type(exc).__name__
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, POLL_ERROR_BACKOFF_MAX_SECONDS)

    async def _consume_once(self, storage: Any = None) -> bool:
        """拉一批消息并持久化；返回是否收到消息（供测试注入 storage）。"""
        from src.infra.storage.redis import RedisStorage

        redis = storage or RedisStorage()
        client = await self._get_http()
        buf_key = _buf_key(*self._reader_scope)
        raw_buf = await redis.get(buf_key)
        if raw_buf is None and self._lock_owner:
            # Import the old cursor only while both compatibility locks are held.
            await self._check_poll_owner()
            raw_buf = await redis.get(_buf_key(self.config.user_id, self.config.instance_id))
            if raw_buf is not None:
                await self._check_poll_owner()
                await redis.set(buf_key, raw_buf)
        buf = str(raw_buf) if raw_buf is not None else ""
        messages, next_buf = await provider.get_updates(client, self.config.bot_token, buf)
        await self._check_poll_owner()

        for index, message in enumerate(messages):
            # 群聊消息按策略过滤（chat_id 为 room 时与发送者不同）
            if (
                self.config.group_policy == WeixinGroupPolicy.OFF
                and message["chat_id"] != message["sender_id"]
            ):
                continue
            dedup = _dedup_key(message, next_buf, index)
            await self._check_poll_owner()
            normalized = {
                "message_id": dedup or uuid.uuid4().hex,
                "sender_id": message["sender_id"],
                "chat_id": message["chat_id"],
                "content": message["content"],
                "metadata": {
                    "context_token": message.get("context_token"),
                    "message_id": message.get("message_id"),
                    "display_name": message.get("display_name"),
                    "instance_id": self.config.instance_id or None,
                },
            }
            if not await self._inbox_worker.accept(normalized):
                raise RuntimeError("Weixin inbox acceptance failed")

        # 游标在本批消息全部持久化到 inbox 后推进：中途失败下轮按旧游标重拉，
        # 宁可重复投递不可丢消息
        if next_buf:
            await self._check_poll_owner()
            await redis.set(buf_key, next_buf)
            if self._lock_owner:
                # An older replica can regain the compatibility lock during a
                # rolling deploy; keep its cursor current for that handoff.
                await redis.set(_buf_key(self.config.user_id, self.config.instance_id), next_buf)
        return bool(messages)

    async def _check_poll_owner(self) -> None:
        if not self._lock_owner:
            return
        for scope in (self._reader_scope, (self.config.user_id, self.config.instance_id)):
            if not await _renew_poll_lock(scope[0], scope[1], self._lock_owner):
                raise PollLeaseLostError("Weixin poll lease lost")

    async def _with_lock_renewal(self, coro: Any) -> Any:
        """agent 执行可达分钟级，远超锁 TTL；处理期间周期续期防他副本重入。"""
        renew_task = asyncio.create_task(self._renew_lock_loop())
        work = asyncio.create_task(coro)
        try:
            done, _ = await asyncio.wait([work, renew_task], return_when=asyncio.FIRST_COMPLETED)
            if renew_task in done:
                renew_task.result()
            return await work
        finally:
            renew_task.cancel()
            work.cancel()
            await asyncio.gather(renew_task, work, return_exceptions=True)

    async def _renew_lock_loop(self) -> None:
        while True:
            await asyncio.sleep(LOCK_RENEW_INTERVAL_SECONDS)
            await self._check_poll_owner()

    def _context_key(self, chat_id: str) -> str:
        identity = [self.user_id, self.config.instance_id, chat_id]
        digest = hashlib.sha256(json.dumps(identity).encode()).hexdigest()
        return f"weixin:context:{digest}"

    async def _deliver_inbox_message(self, message: dict[str, Any]) -> None:
        metadata = message.get("metadata") or {}
        if message.get("outbound") is True:
            if not await self.send_message(message["chat_id"], message["content"], **metadata):
                raise RuntimeError("Weixin outbound delivery failed")
            return
        token = metadata.get("context_token")
        if token:
            self._last_context_tokens[message["chat_id"]] = token
            from src.infra.async_utils import run_long_blocking_io
            from src.infra.mcp.encryption import encrypt_value
            from src.infra.storage.redis import RedisStorage

            try:
                encrypted = await run_long_blocking_io(encrypt_value, {"value": token})
                await RedisStorage().set(self._context_key(message["chat_id"]), encrypted)
            except Exception:
                logger.warning("weixin context cache write failed (user %s)", self.user_id)
        await self._handle_message(
            sender_id=message["sender_id"],
            chat_id=message["chat_id"],
            content=message["content"],
            metadata=metadata,
        )

    async def _cached_context_token(self, chat_id: str) -> str | None:
        from src.infra.async_utils import run_long_blocking_io
        from src.infra.mcp.encryption import decrypt_value
        from src.infra.storage.redis import RedisStorage

        try:
            encrypted = await RedisStorage().get(self._context_key(chat_id))
            if encrypted:
                decoded = await run_long_blocking_io(decrypt_value, encrypted)
                token = decoded.get("value")
                if isinstance(token, str):
                    self._last_context_tokens[chat_id] = token
                    return token
        except Exception:
            logger.warning("weixin context cache read failed (user %s)", self.user_id)
        return None

    # ── 发消息 ──

    async def send_message(self, chat_id: str, content: str, **kwargs: Any) -> bool:
        if not content or not content.strip():
            return False
        target = chat_id or getattr(self.config, "default_chat_id", "") or ""
        if not target:
            logger.warning("weixin send_message has no target chat (user %s)", self.user_id)
            return False
        client = await self._get_http()
        context_token = (
            kwargs.get("context_token")
            or self._last_context_tokens.get(target)
            or await self._cached_context_token(target)
        )
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
