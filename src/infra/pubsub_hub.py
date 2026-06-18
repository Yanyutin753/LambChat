"""
Shared Redis pub/sub hub.

Keeps a single Redis pub/sub connection per process and fan-outs messages to
channel-specific async handlers. This reduces idle connections and background
listener tasks for distributed features that only need lightweight broadcasts.
"""

from __future__ import annotations

import asyncio
import inspect
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from redis.exceptions import ConnectionError as RedisConnectionError

from src.infra.logging import get_logger

if TYPE_CHECKING:
    from src.kernel.extensions import PluginRuntime

logger = get_logger(__name__)

PubSubHandler = Callable[[dict[str, Any]], Awaitable[None] | None]
_MAX_RECONNECT_DELAY = 30
_DEFAULT_MAX_HANDLER_TASKS = 128
_DEFAULT_MAX_MESSAGE_BYTES = 256 * 1024


@dataclass(frozen=True, slots=True)
class PubSubSubscription:
    handler: PubSubHandler
    plugin_listener_id: str | None = None


def create_redis_client(*, isolated_pool: bool = False, socket_timeout: Any = None) -> Any:
    """Create Redis client lazily to avoid import cycles at module import time."""
    from src.infra.storage.redis import create_redis_client as _create_redis_client

    return _create_redis_client(
        isolated_pool=isolated_pool,
        socket_timeout=socket_timeout,
    )


def _message_data_size(data: Any) -> int:
    if isinstance(data, bytes):
        return len(data)
    if isinstance(data, str):
        return len(data.encode("utf-8"))
    try:
        return len(data)
    except TypeError:
        return 0


class RedisPubSubHub:
    """Multiplex Redis pub/sub channels over a single shared listener."""

    def __init__(
        self,
        *,
        max_handler_tasks: int = _DEFAULT_MAX_HANDLER_TASKS,
        max_message_bytes: int = _DEFAULT_MAX_MESSAGE_BYTES,
    ) -> None:
        self._subscriptions: dict[str, dict[str, PubSubSubscription]] = defaultdict(dict)
        self._lock = asyncio.Lock()
        self._listener_task: asyncio.Task | None = None
        self._pubsub: Any | None = None
        self._running = False
        self._ready_event: asyncio.Event | None = None
        self._expected_disconnects: set[int] = set()
        self._handler_tasks: set[asyncio.Task[None]] = set()
        self._resubscribe_task: asyncio.Task[None] | None = None
        self._handler_semaphore = asyncio.Semaphore(max(1, max_handler_tasks))
        self._max_message_bytes = max(1, int(max_message_bytes))
        self._plugin_runtime: PluginRuntime | None = None

    def set_plugin_runtime(self, runtime: PluginRuntime | None) -> None:
        """Attach the active Plugin Runtime for plugin-owned listener guards."""
        self._plugin_runtime = runtime

    def subscribe(
        self,
        channel: str,
        handler: PubSubHandler,
        *,
        plugin_listener_id: str | None = None,
    ) -> str:
        """Register a handler for a Redis channel."""
        token = uuid.uuid4().hex
        self._subscriptions[channel][token] = PubSubSubscription(
            handler=handler,
            plugin_listener_id=plugin_listener_id,
        )
        if self._running:
            self._schedule_resubscribe()
        return token

    def unsubscribe(self, token: str) -> None:
        """Remove a previously registered handler."""
        empty_channels: list[str] = []
        for channel, handlers in self._subscriptions.items():
            if token in handlers:
                del handlers[token]
                if not handlers:
                    empty_channels.append(channel)
                break

        for channel in empty_channels:
            del self._subscriptions[channel]

        if self._running:
            self._schedule_resubscribe()

    async def start(self) -> None:
        """Start the shared listener if it is not running already."""
        if self._running:
            return

        self._running = True
        self._ready_event = asyncio.Event()
        self._listener_task = asyncio.create_task(self._listener_loop())
        await self._ready_event.wait()

    async def stop(self) -> None:
        """Stop the shared listener and close the current Redis pub/sub."""
        self._running = False
        pubsub = self._pubsub
        if pubsub is not None:
            await self._close_pubsub(pubsub)

        if self._listener_task and not self._listener_task.done():
            self._listener_task.cancel()
            try:
                await self._listener_task
            except asyncio.CancelledError:
                pass

        await self._cancel_resubscribe_task()
        await self._cancel_handler_tasks()

        self._listener_task = None
        self._ready_event = None

    async def stop_if_idle(self) -> None:
        """Stop the listener when no channels remain subscribed."""
        if self.subscription_count == 0:
            await self.stop()

    @property
    def subscription_count(self) -> int:
        return sum(len(handlers) for handlers in self._subscriptions.values())

    def describe_state(self) -> dict[str, Any]:
        channels = {
            channel: len(handlers) for channel, handlers in sorted(self._subscriptions.items())
        }
        return {
            "channel_count": len(channels),
            "subscription_count": sum(channels.values()),
            "channels": channels,
        }

    async def _listener_loop(self) -> None:
        delay = 1

        try:
            while self._running:
                channels = sorted(self._subscriptions.keys())
                if not channels:
                    if self._ready_event is not None and not self._ready_event.is_set():
                        self._ready_event.set()
                    await asyncio.sleep(0.05)
                    continue

                pubsub = None
                redis_client = None
                try:
                    redis_client = create_redis_client(
                        isolated_pool=True,
                        socket_timeout=None,
                    )
                    pubsub = redis_client.pubsub()
                    async with self._lock:
                        self._pubsub = pubsub

                    await pubsub.subscribe(*channels)
                    snapshot = self.describe_state()
                    logger.info(
                        "Pub/sub hub listening on %s channels (%s subscriptions): %s",
                        snapshot["channel_count"],
                        snapshot["subscription_count"],
                        ", ".join(channels),
                    )
                    if self._ready_event is not None and not self._ready_event.is_set():
                        self._ready_event.set()
                    delay = 1

                    async for message in pubsub.listen():
                        if not self._running:
                            break
                        if message.get("type") != "message":
                            continue
                        await self._dispatch_message(message)
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    if not self._running:
                        break
                    if pubsub is not None and self._is_expected_disconnect(pubsub, e):
                        delay = 1
                        logger.debug("Pub/sub hub restarting listener after resubscribe")
                        continue
                    if self._ready_event is not None and not self._ready_event.is_set():
                        self._ready_event.set()
                    logger.error("Pub/sub hub listener error: %s", e)
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, _MAX_RECONNECT_DELAY)
                finally:
                    await self._detach_pubsub(pubsub)
                    await self._close_redis_client(redis_client)
        except asyncio.CancelledError:
            logger.info("Pub/sub hub listener cancelled")
        finally:
            self._running = False
            logger.info("Pub/sub hub listener stopped")

    async def _dispatch_message(self, message: dict[str, Any]) -> None:
        channel = message.get("channel")
        if not isinstance(channel, str):
            return
        data_size = _message_data_size(message.get("data"))
        if data_size > self._max_message_bytes:
            logger.warning(
                "Dropping oversized pub/sub message on channel %s: %s bytes > %s",
                channel,
                data_size,
                self._max_message_bytes,
            )
            return

        subscriptions = list(self._subscriptions.get(channel, {}).values())
        for subscription in subscriptions:
            await self._handler_semaphore.acquire()
            task = asyncio.create_task(
                self._run_handler(channel, subscription, dict(message)),
                name=f"pubsub-handler:{channel}",
            )
            self._handler_tasks.add(task)
            task.add_done_callback(self._on_handler_task_done)

    def _on_handler_task_done(self, task: asyncio.Task[None]) -> None:
        self._handler_tasks.discard(task)
        self._handler_semaphore.release()

    async def _run_handler(
        self,
        channel: str,
        subscription: PubSubSubscription,
        message: dict[str, Any],
    ) -> None:
        try:
            if not self._is_plugin_listener_available(subscription):
                return
            result = subscription.handler(message)
            if inspect.isawaitable(result):
                await result
        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error("Pub/sub hub handler failed for channel %s: %s", channel, e)

    def _is_plugin_listener_available(self, subscription: PubSubSubscription) -> bool:
        listener_id = subscription.plugin_listener_id
        if not listener_id:
            return True
        if self._plugin_runtime is None:
            logger.warning(
                "Skipping plugin pub/sub listener %s because Plugin Runtime is unavailable",
                listener_id,
            )
            return False
        try:
            self._plugin_runtime.ensure_listener_available(listener_id)
        except Exception as e:  # noqa: BLE001 - plugin listener dispatch must fail closed
            logger.info("Skipping plugin pub/sub listener %s: %s", listener_id, e)
            return False
        return True

    async def _cancel_handler_tasks(self) -> None:
        tasks = list(self._handler_tasks)
        if not tasks:
            return
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self._handler_tasks.clear()

    def _schedule_resubscribe(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        if self._resubscribe_task is not None and not self._resubscribe_task.done():
            return
        self._resubscribe_task = loop.create_task(self._poke_listener())
        self._resubscribe_task.add_done_callback(self._on_resubscribe_task_done)

    def _on_resubscribe_task_done(self, task: asyncio.Task[None]) -> None:
        if self._resubscribe_task is task:
            self._resubscribe_task = None
        if task.cancelled():
            return
        try:
            task.result()
        except Exception as e:
            logger.warning("Pub/sub hub resubscribe poke failed: %s", e)

    async def _poke_listener(self) -> None:
        pubsub = self._pubsub
        if pubsub is not None:
            await self._close_pubsub(pubsub)

    async def _cancel_resubscribe_task(self) -> None:
        task = self._resubscribe_task
        if task is None:
            return
        self._resubscribe_task = None
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def _detach_pubsub(self, pubsub: Any | None) -> None:
        if pubsub is None:
            return

        await self._close_pubsub(pubsub)
        self._expected_disconnects.discard(id(pubsub))
        async with self._lock:
            if self._pubsub is pubsub:
                self._pubsub = None

    async def _close_pubsub(self, pubsub: Any) -> None:
        self._expected_disconnects.add(id(pubsub))
        try:
            await pubsub.close()
        except Exception as e:
            logger.warning("Failed to close shared pub/sub connection: %s", e)

    async def _close_redis_client(self, redis_client: Any | None) -> None:
        if redis_client is None:
            return
        try:
            await redis_client.aclose()
        except Exception as e:
            logger.warning("Failed to close shared pub/sub Redis client: %s", e)

    def _is_expected_disconnect(self, pubsub: Any, error: Exception) -> bool:
        if id(pubsub) not in self._expected_disconnects:
            return False
        return (
            isinstance(error, RedisConnectionError) and str(error) == "Connection closed by server."
        )


_pubsub_hub: RedisPubSubHub | None = None


def get_pubsub_hub() -> RedisPubSubHub:
    global _pubsub_hub
    if _pubsub_hub is None:
        _pubsub_hub = RedisPubSubHub()
    return _pubsub_hub


async def close_pubsub_hub() -> None:
    """Stop and release the process-local pub/sub hub without creating it."""
    global _pubsub_hub
    hub = _pubsub_hub
    _pubsub_hub = None
    if hub is not None:
        await hub.stop()
