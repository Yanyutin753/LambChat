"""Bounded durable delivery with independently fenced inbox and conversation leases."""

from __future__ import annotations

import asyncio
import secrets
from collections.abc import Awaitable, Callable
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any

from src.infra.channel.chat_lease import ChatLease
from src.infra.channel.inbox import LEASE_SECONDS, ChannelInbox, conversation_key
from src.infra.logging import get_logger

logger = get_logger(__name__)
HEARTBEAT_SECONDS = LEASE_SECONDS / 3
POLL_SECONDS = 1.0
MAX_CONCURRENT = 32


@dataclass
class DeliveryContext:
    inbox: ChannelInbox
    key: str
    owner: str
    checkpoint: dict[str, Any] = field(default_factory=dict)

    async def save(self, **values: Any) -> None:
        await self.inbox.checkpoint(self.key, self.owner, values)
        self.checkpoint.update(values)


current_delivery: ContextVar[DeliveryContext | None] = ContextVar("current_delivery", default=None)


class InboxWorker:
    def __init__(self, inbox: ChannelInbox, handler: Callable[[dict[str, Any]], Awaitable[None]]):
        self.inbox = inbox
        self.handler = handler
        self._wake = asyncio.Event()
        self._stop_lock = asyncio.Lock()
        self._stopped = False
        self._tasks: dict[str, tuple[asyncio.Task[bool], str]] = {}
        self._retry: dict[str, tuple[int, float]] = {}

    async def accept(self, message: dict[str, Any]) -> bool:
        try:
            await self.inbox.accept(message)
        except Exception as exc:
            logger.warning("Channel inbox acceptance failed: %s", type(exc).__name__)
            return False
        self._wake.set()
        return True

    def _chat_key(self, message: dict[str, Any]) -> str:
        return f"channel:inbox:chat:{conversation_key(self.inbox.scope, message)}"

    def _reap(self) -> bool:
        succeeded = True
        for key, (task, _) in list(self._tasks.items()):
            if not task.done():
                continue
            self._tasks.pop(key)
            ok = not task.cancelled() and task.result()
            if ok:
                self._retry.pop(key, None)
            else:
                succeeded = False
                attempts = min(self._retry.get(key, (0, 0))[0] + 1, 6)
                self._retry[key] = (attempts, asyncio.get_running_loop().time() + 2**attempts)
        return succeeded

    async def _schedule(self) -> None:
        active_chats = {chat for _, chat in self._tasks.values()}
        now = asyncio.get_running_loop().time()
        for row in await self.inbox.pending(limit=MAX_CONCURRENT * 4):
            if self._stopped or len(self._tasks) >= MAX_CONCURRENT:
                break
            key = row["_id"]
            chat = self._chat_key(row["message"])
            if key in self._tasks or chat in active_chats:
                continue
            active_chats.add(chat)
            if self._retry.get(key, (0, 0))[1] > now:
                continue
            task = asyncio.create_task(self._process(key, chat))
            self._tasks[key] = (task, chat)
            task.add_done_callback(lambda _: self._wake.set())

    async def run(self) -> None:
        self._stopped = False
        try:
            while not self._stopped:
                self._wake.clear()
                self._reap()
                try:
                    await self._schedule()
                except Exception as exc:
                    logger.warning("Channel inbox scan failed: %s", type(exc).__name__)
                try:
                    await asyncio.wait_for(self._wake.wait(), POLL_SECONDS)
                except TimeoutError:
                    pass
        finally:
            await self.stop()

    async def drain(self) -> bool:
        """Attempt pending inputs, returning false when any delivery remains pending."""
        while not self._stopped:
            succeeded = self._reap()
            if not succeeded:
                return False
            await self._schedule()
            if not self._tasks:
                return not bool(await self.inbox.pending(limit=1))
            await asyncio.gather(
                *(task for task, _ in self._tasks.values()), return_exceptions=True
            )
        return False

    async def stop(self) -> None:
        self._stopped = True
        self._wake.set()
        async with self._stop_lock:
            tasks = [task for task, _ in self._tasks.values()]
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            self._tasks.clear()

    async def _process(self, key: str, chat: str) -> bool:
        owner = secrets.token_hex(16)
        lease = ChatLease(chat)
        acquired = False
        dispatch: asyncio.Task[None] | None = None
        heartbeat: asyncio.Task[None] | None = None

        async def renew() -> None:
            while True:
                await asyncio.sleep(HEARTBEAT_SECONDS)
                if not await self.inbox.renew(key, owner):
                    raise RuntimeError("Inbox ownership lost")
                if acquired and not await lease.renew():
                    raise RuntimeError("Conversation ownership lost")

        async def deliver(row: dict[str, Any]) -> None:
            nonlocal acquired
            while not await lease.acquire():
                await asyncio.sleep(POLL_SECONDS)
            acquired = True
            # Recheck both order and fencing after waiting for the conversation lock.
            if not await self.inbox.is_head(key):
                raise RuntimeError("Earlier conversation input still pending")
            if not await self.inbox.renew(key, owner):
                raise RuntimeError("Inbox ownership lost")
            context = DeliveryContext(self.inbox, key, owner, dict(row.get("checkpoint", {})))
            token = current_delivery.set(context)
            try:
                await self.handler(row["message"])
            finally:
                current_delivery.reset(token)

        try:
            row = await self.inbox.claim(key, owner)
            if row is None:
                return True
            heartbeat = asyncio.create_task(renew())
            dispatch = asyncio.create_task(deliver(row))
            finished, _ = await asyncio.wait(
                (dispatch, heartbeat), return_when=asyncio.FIRST_COMPLETED
            )
            if heartbeat in finished:
                await heartbeat
            await dispatch
            return await self.inbox.complete(key, owner)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning("Channel inbox delivery failed: %s", type(exc).__name__)
            return False
        finally:
            helpers = [task for task in (heartbeat, dispatch) if task is not None]
            for task in helpers:
                task.cancel()
            await asyncio.gather(*helpers, return_exceptions=True)
            # Release even after cancelled acquire: the server may already own it.
            results = await asyncio.gather(
                lease.release(), self.inbox.release(key, owner), return_exceptions=True
            )
            for result in results:
                if isinstance(result, Exception):
                    logger.warning("Channel inbox release failed: %s", type(result).__name__)
