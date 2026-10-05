"""Opt-in receiving for chat bots, retaining legacy outbound configurations."""

from __future__ import annotations

import asyncio
import hashlib
import re
import secrets
from typing import Any

from pydantic import ConfigDict

from src.infra.channel.chat_lease import ChatLease, release_message
from src.infra.channel.outbound import OutboundChannel, OutboundChannelManager
from src.infra.logging import get_logger
from src.infra.storage.redis import get_redis_client
from src.kernel.schemas.channel import ChannelConfigBase

logger = get_logger(__name__)
MAX_PENDING_MESSAGES = 32
MAX_INBOUND_CONTENT_CHARS = 65536


class InboundConfigurationError(Exception):
    """The platform rejected configuration; retry only after the user edits it."""


class ChatConfig(ChannelConfigBase):
    model_config = ConfigDict(hide_input_in_errors=True)
    user_id: str = ""
    instance_id: str = ""
    enabled: bool = True
    default_chat_id: str = ""
    receive_enabled: bool = False
    allowed_sender_ids: str = ""
    allowed_chat_ids: str = ""


def chat_config_fields() -> list[dict[str, Any]]:
    return [
        {
            "name": "receive_enabled",
            "title": "Receive messages",
            "type": "toggle",
            "default": False,
        },
        {
            "name": "allowed_sender_ids",
            "title": "Allowed sender IDs",
            "type": "text",
            "placeholder": "Comma-separated stable user IDs; never display names",
        },
        {
            "name": "allowed_chat_ids",
            "title": "Allowed chat IDs",
            "type": "text",
            "placeholder": "Comma-separated chat IDs; both restrictions apply when provided",
        },
    ]


def _ids(value: str) -> set[str]:
    return {part for part in re.split(r"[\s,]+", value.strip()) if part}


class ChatChannel(OutboundChannel):
    """One credential-scoped reader with bounded, authorized message handling."""

    inbound_transport = True

    def __init__(self, config: Any, message_handler=None):
        super().__init__(config, message_handler)
        self._connected = False
        self._reader: asyncio.Task | None = None
        self._pending: set[asyncio.Task] = set()
        self._pending_claims: dict[asyncio.Task, tuple[Any, str, str]] = {}
        self._dispatch_failed = False
        self._admitting = 0
        self._generation = 0
        self._chat_locks: dict[tuple[str, str], asyncio.Lock] = {}

    @property
    def is_running(self) -> bool:
        return self._running and (not self.config.receive_enabled or self._connected)

    def _validate_inbound_config(self) -> bool:
        return True

    def _authorized(self, message: dict[str, Any], config: Any = None) -> bool:
        config = config if config is not None else self.config
        senders = _ids(config.allowed_sender_ids)
        chats = _ids(config.allowed_chat_ids)
        if not senders and not chats:
            chats = _ids(config.default_chat_id)
        if not senders and not chats:
            return False
        return (not senders or message["sender_id"] in senders) and (
            not chats or message["chat_id"] in chats
        )

    def _lease_key(self) -> str:
        credential = next(
            (
                str(getattr(self.config, key, ""))
                for key in ("bot_token", "app_token", "client_id", "bot_id")
                if getattr(self.config, key, "")
            ),
            f"{self.user_id}:{self.config.instance_id}",
        )
        digest = hashlib.sha256(credential.encode()).hexdigest()
        return f"channel:reader:{self.channel_type.value}:{digest}"

    @property
    def status_key(self) -> str:
        return (
            f"channel:connected:{self.channel_type.value}:{self.user_id}:{self.config.instance_id}"
        )

    async def start(self) -> bool:
        if self._running:
            return True
        if self.config.receive_enabled:
            if not (
                self.config.allowed_sender_ids.strip()
                or self.config.allowed_chat_ids.strip()
                or self.config.default_chat_id.strip()
            ):
                return False
            if not self._validate_inbound_config() or not self.message_handler:
                return False
        self._running = True
        if self.config.receive_enabled and self.inbound_transport:
            self._reader = asyncio.create_task(self._supervise())
        else:
            self._connected = True
        return True

    async def _run_inbound(self) -> None:
        raise NotImplementedError

    async def _keep_lease(self, lease: ChatLease) -> None:
        while True:
            await asyncio.sleep(10)
            if not await lease.renew():
                raise RuntimeError("Bot connection lease lost")
            if self._connected:
                await get_redis_client().set(self.status_key, lease.owner, ex=30)

    async def _supervise(self) -> None:
        delay = 1
        while self._running:
            lease = ChatLease(self._lease_key())
            tasks: list[asyncio.Task] = []
            try:
                if not await lease.acquire():
                    await asyncio.sleep(5)
                    continue
                tasks = [
                    asyncio.create_task(self._run_inbound()),
                    asyncio.create_task(self._keep_lease(lease)),
                ]
                done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                for task in done:
                    task.result()
                delay = 1
            except asyncio.CancelledError:
                raise
            except InboundConfigurationError:
                logger.warning(
                    "%s receiving stopped: invalid bot configuration", self.channel_type.value
                )
                return
            except Exception as exc:
                logger.warning(
                    "%s connection retry (%s)", self.channel_type.value, type(exc).__name__
                )
                delay = min(delay * 2, 60)
            finally:
                self._connected = False
                for task in tasks:
                    task.cancel()
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                try:
                    await lease.release()
                    await release_message(get_redis_client(), self.status_key, lease.owner)
                except Exception:
                    pass
            await asyncio.sleep(delay)

    async def enqueue_inbound(self, message: dict[str, Any]) -> bool:
        """True means accepted or deliberately ignored; False requests a retry."""
        if not self._running or not self.config.receive_enabled:
            return True
        if any(
            not isinstance(message.get(key), str) or not message[key]
            for key in ("sender_id", "chat_id", "content", "message_id")
        ):
            return True
        if not self._authorized(message):
            return True
        if len(message["content"]) > MAX_INBOUND_CONTENT_CHARS:
            return True
        if len(self._pending) + self._admitting >= MAX_PENDING_MESSAGES:
            return False
        identity = f"{self.channel_type.value}:{self.user_id}:{self.config.instance_id}:{message['message_id']}"
        key = "channel:message:" + hashlib.sha256(identity.encode()).hexdigest()
        owner = secrets.token_hex(16)
        redis = get_redis_client()
        generation = self._generation
        self._admitting += 1
        try:
            if not await redis.set(key, owner, nx=True, ex=86400):
                return True
            if not self._running or generation != self._generation:
                await release_message(redis, key, owner)
                return False
            task = asyncio.create_task(self._dispatch(message, redis, key, owner))
            self._pending.add(task)
            self._pending_claims[task] = (redis, key, owner)
            task.add_done_callback(self._forget_dispatch)
            return True
        except asyncio.CancelledError:
            # The Redis command may have succeeded before cancellation arrived.
            try:
                await release_message(redis, key, owner)
            except Exception:
                pass
            raise
        except Exception:
            return False
        finally:
            self._admitting -= 1

    def _forget_dispatch(self, task: asyncio.Task) -> None:
        self._pending.discard(task)
        self._pending_claims.pop(task, None)

    async def _dispatch(self, message: dict[str, Any], redis: Any, key: str, owner: str) -> bool:
        scope = (message["chat_id"], message["sender_id"])
        lock = self._chat_locks.setdefault(scope, asyncio.Lock())
        try:
            async with lock:
                metadata = {
                    **message.get("metadata", {}),
                    "instance_id": self.config.instance_id,
                    "message_id": message["message_id"],
                }
                if self.message_handler is None:
                    raise RuntimeError("Receiving handler is missing")
                await self.message_handler(
                    user_id=self.user_id,
                    sender_id=message["sender_id"],
                    chat_id=message["chat_id"],
                    content=message["content"],
                    metadata=metadata,
                )
            return True
        except (Exception, asyncio.CancelledError) as exc:
            self._dispatch_failed = True
            try:
                await release_message(redis, key, owner)
            except Exception:
                pass
            if isinstance(exc, asyncio.CancelledError):
                raise
            logger.warning("%s message failed (%s)", self.channel_type.value, type(exc).__name__)
            return False
        finally:
            # Keep a lock only while another message is waiting on it.
            if not lock.locked() and not getattr(lock, "_waiters", None):
                self._chat_locks.pop(scope, None)

    async def drain(self) -> bool:
        succeeded = True
        if self._pending:
            succeeded = all(await asyncio.gather(*list(self._pending)))
        succeeded = succeeded and not self._dispatch_failed
        self._dispatch_failed = False
        return succeeded

    async def stop(self) -> None:
        self._running = False
        self._generation += 1
        self._connected = False
        tasks = list(self._pending)
        claims = dict(self._pending_claims)
        if self._reader:
            tasks.append(self._reader)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        # A task cancelled before its first instruction never enters _dispatch's
        # cancellation handler; release its owner-checked claim here as well.
        for task, (redis, key, owner) in claims.items():
            if task.cancelled():
                try:
                    await release_message(redis, key, owner)
                except Exception:
                    pass
        self._pending.clear()
        self._pending_claims.clear()
        self._dispatch_failed = False
        self._reader = None
        self._chat_locks.clear()
        await super().stop()

    async def _send_reply(self, chat_id: str, content: str, **metadata: Any) -> bool:
        return await super().send_message(chat_id, content, **metadata)

    async def send_message(self, chat_id: str, content: str, **kwargs: Any) -> bool:
        if not self.config.receive_enabled:
            return await super().send_message(chat_id, content, **kwargs)
        if not content.strip():
            return False
        try:
            return await self._send_reply(chat_id or self.config.default_chat_id, content, **kwargs)
        except Exception as exc:
            logger.warning("%s reply failed (%s)", self.channel_type.value, type(exc).__name__)
            return False


class ChatChannelManager(OutboundChannelManager):
    def _build_channel(self, config_dict: dict[str, Any]) -> ChatChannel:
        from src.infra.channel.chat_handler import create_chat_message_handler
        from src.kernel.config import settings

        channel = self.channel_class(self.config_class(**config_dict))
        assert isinstance(channel, ChatChannel)
        channel.message_handler = self.message_handler or create_chat_message_handler(
            channel, settings.DEFAULT_AGENT
        )
        return channel

    async def is_connected_distributed(self, user_id: str, instance_id: str) -> bool:
        channel = self._channels.get(f"{user_id}:{instance_id}")
        if not isinstance(channel, ChatChannel):
            return False
        if channel.is_running:
            return True
        return bool(await get_redis_client().get(channel.status_key))
