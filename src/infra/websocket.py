"""
WebSocket Manager - WebSocket 连接管理器

管理 WebSocket 连接，用于实时推送任务完成通知。
支持 Redis Pub/Sub 实现分布式部署。
"""

import asyncio
import json
import uuid
from typing import Dict, Optional, Set

from fastapi import WebSocket

from src.infra.async_utils.blocking import run_blocking_io
from src.infra.logging import get_logger
from src.infra.pubsub_hub import get_pubsub_hub, namespaced_channel
from src.infra.storage.redis import create_redis_client

logger = get_logger(__name__)

# Redis key/channel design for distributed WebSocket delivery
WS_ROUTE_PREFIX = "ws:route"
WS_ROUTE_SET_PREFIX = "ws:routes"
WS_DELIVERY_CHANNEL_PREFIX = "ws:deliver"
WS_ROUTE_TTL_SECONDS = 60
WS_ROUTE_REFRESH_INTERVAL = 20
WS_ROUTE_SCAN_LIMIT = 100
WS_MESSAGE_MAX_BYTES = 256 * 1024


async def _json_dumps_message(message: dict) -> str:
    return await run_blocking_io(json.dumps, message, ensure_ascii=False)


async def _json_dumps_delivery(payload: dict) -> str:
    return await run_blocking_io(json.dumps, payload)


async def _json_loads_delivery(raw_value: str) -> dict:
    return await run_blocking_io(json.loads, raw_value)


def _json_size_bytes(value: str) -> int:
    return len(value.encode("utf-8"))


async def _json_dumps_message_limited(message: dict, *, label: str) -> str | None:
    serialized = await _json_dumps_message(message)
    size = _json_size_bytes(serialized)
    if size > WS_MESSAGE_MAX_BYTES:
        logger.warning(
            "Dropping oversized WebSocket %s message: %s bytes > %s",
            label,
            size,
            WS_MESSAGE_MAX_BYTES,
        )
        return None
    return serialized


async def _json_dumps_delivery_limited(payload: dict) -> str | None:
    serialized = await _json_dumps_delivery(payload)
    size = _json_size_bytes(serialized)
    if size > WS_MESSAGE_MAX_BYTES:
        logger.warning(
            "Dropping oversized WebSocket delivery payload: %s bytes > %s",
            size,
            WS_MESSAGE_MAX_BYTES,
        )
        return None
    return serialized


async def _scan_redis_keys(
    redis_client,
    pattern: str,
    *,
    count: int = 100,
    limit: int = WS_ROUTE_SCAN_LIMIT,
) -> list[str]:
    """Collect matching Redis keys with SCAN to avoid blocking Redis."""
    cursor: int | str = 0
    keys: list[str] = []
    while True:
        cursor, batch = await redis_client.scan(cursor=cursor, match=pattern, count=count)
        for key in batch:
            keys.append(str(key))
            if len(keys) >= limit:
                logger.warning("WebSocket route scan limit reached: %s", limit)
                return keys
        if int(cursor) == 0:
            return keys


class ConnectionManager:
    """
    WebSocket 连接管理器

    管理所有活跃的 WebSocket 连接，按用户 ID 分组。
    支持 Redis Pub/Sub 实现分布式部署时的跨实例广播。
    """

    def __init__(self):
        # user_id -> Set[WebSocket]
        self._connections: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()
        self._subscription_token: Optional[str] = None
        self._route_refresh_tasks: dict[str, asyncio.Task] = {}
        self._running = False
        self._instance_id = uuid.uuid4().hex
        self._redis = None

    async def connect(self, websocket: WebSocket, user_id: str, accept: bool = True) -> None:
        """用户连接 WebSocket

        Args:
            websocket: WebSocket连接
            user_id: 用户ID
            accept: 是否需要接受连接（如果已经accept过，设为False）
        """
        if accept:
            await websocket.accept()
        async with self._lock:
            if user_id not in self._connections:
                self._connections[user_id] = set()
            self._connections[user_id].add(websocket)
            connection_count = len(self._connections[user_id])
            if connection_count == 1:
                self._ensure_route_refresh_task(user_id)
        await self._sync_route_registration(user_id, connection_count)
        logger.info(f"WebSocket connected: user_id={user_id}, total={connection_count}")

    async def disconnect(self, websocket: WebSocket, user_id: str) -> None:
        """用户断开 WebSocket"""
        async with self._lock:
            connection_count = 0
            if user_id in self._connections:
                self._connections[user_id].discard(websocket)
                connection_count = len(self._connections[user_id])
                if connection_count == 0:
                    del self._connections[user_id]
                    await self._stop_route_refresh_task(user_id)
        await self._sync_route_registration(user_id, connection_count)
        logger.info(f"WebSocket disconnected: user_id={user_id}")

    async def broadcast(self, message: dict) -> int:
        """
        向所有用户广播消息

        Args:
            message: 消息内容

        Returns:
            成功发送的连接数
        """
        all_connections = []
        async with self._lock:
            for user_id, conns in self._connections.items():
                all_connections.extend([(user_id, ws) for ws in conns])

        sent_count = 0
        disconnected = set()
        json_str = (
            await _json_dumps_message_limited(message, label="broadcast") if all_connections else ""
        )
        if json_str is None:
            return 0

        for user_id, ws in all_connections:
            try:
                await ws.send_text(json_str)
                sent_count += 1
            except Exception as e:
                logger.warning(f"Failed to broadcast to WebSocket: {e}")
                disconnected.add((user_id, ws))

        # 清理断开的连接
        if disconnected:
            users_to_unregister = await self._cleanup_disconnected_connections(disconnected)
            for user_id in users_to_unregister:
                await self._sync_route_registration(user_id, 0)

        return sent_count

    def get_connection_count(self, user_id: str | None = None) -> int:
        """获取连接数量"""
        if user_id:
            return len(self._connections.get(user_id, set()))
        return sum(len(conns) for conns in self._connections.values())

    async def start_pubsub_listener(self) -> None:
        """
        启动 Redis pub/sub 监听器，用于接收跨实例广播

        应在应用启动时调用
        """
        if self._running:
            return

        hub = get_pubsub_hub()
        self._subscription_token = hub.subscribe(
            self._delivery_channel(self._instance_id),
            self._handle_pubsub_message,
        )
        await hub.start()
        self._running = True
        logger.info(
            "WebSocket: Started listening on Redis channel: %s",
            self._delivery_channel(self._instance_id),
        )

    async def stop_pubsub_listener(self) -> None:
        """
        停止 Redis pub/sub 监听器

        应在应用关闭时调用
        """
        self._running = False
        await self._cancel_all_route_refresh_tasks()
        await self._remove_all_route_registrations()
        await self._close_redis()

        if self._subscription_token:
            hub = get_pubsub_hub()
            hub.unsubscribe(self._subscription_token)
            self._subscription_token = None
            await hub.stop_if_idle()

        logger.info("WebSocket pub/sub listener stopped")

    async def _handle_pubsub_message(self, message: dict) -> None:
        try:
            data = await _json_loads_delivery(message["data"])
            await self._handle_broadcast_message(data)
        except json.JSONDecodeError:
            logger.warning(f"Invalid WebSocket broadcast message: {message['data']}")
        except Exception as e:
            logger.error(f"Error processing WebSocket broadcast: {e}")

    async def _handle_broadcast_message(self, data: dict) -> int:
        """Handle a WebSocket broadcast payload received from Redis."""
        user_id = data.get("user_id")
        msg_content = data.get("message")
        if not user_id or not msg_content:
            return 0

        return await self._send_to_user_local(user_id, msg_content)

    async def _send_to_user_local(self, user_id: str, message: dict) -> int:
        """
        仅在本地实例向指定用户发送消息（不广播到 Redis）

        Args:
            user_id: 用户 ID
            message: 消息内容

        Returns:
            成功发送的连接数
        """
        if not message:
            return 0

        json_str = await _json_dumps_message_limited(message, label="local")
        if json_str is None:
            return 0
        sent_count = 0

        async with self._lock:
            connections = self._connections.get(user_id, set()).copy()

        disconnected = set()
        for ws in connections:
            try:
                await ws.send_text(json_str)
                sent_count += 1
            except Exception as e:
                logger.warning(f"Failed to send to WebSocket: {e}")
                disconnected.add(ws)

        # 清理断开的连接
        if disconnected:
            users_to_unregister = await self._cleanup_disconnected_connections(
                {(user_id, ws) for ws in disconnected}
            )
            for target_user_id in users_to_unregister:
                await self._sync_route_registration(target_user_id, 0)

        return sent_count

    async def _cleanup_disconnected_connections(
        self,
        disconnected: set[tuple[str, WebSocket]],
    ) -> set[str]:
        """Remove disconnected sockets and fully release empty user buckets."""
        users_to_unregister: set[str] = set()
        async with self._lock:
            for user_id, ws in disconnected:
                connections = self._connections.get(user_id)
                if connections is None:
                    continue
                connections.discard(ws)
                if not connections:
                    del self._connections[user_id]
                    await self._stop_route_refresh_task(user_id)
                    users_to_unregister.add(user_id)
        return users_to_unregister

    async def send_to_user_with_broadcast(self, user_id: str, message: dict) -> int:
        """
        向指定用户发送消息（支持分布式定向投递）

        Args:
            user_id: 用户 ID
            message: 消息内容

        Returns:
            发布到的实例通道数量
        """
        try:
            redis_client = self._get_redis()
            payload = await _json_dumps_delivery_limited(
                {
                    "user_id": user_id,
                    "message": message,
                    "source_instance_id": self._instance_id,
                }
            )
            if payload is None:
                return 0
            published = 0
            instance_ids = await redis_client.smembers(self._route_set_key(user_id))
            for raw_instance_id in sorted(instance_ids)[:WS_ROUTE_SCAN_LIMIT]:
                instance_id = (
                    raw_instance_id.decode("utf-8")
                    if isinstance(raw_instance_id, bytes)
                    else str(raw_instance_id)
                )
                route_key = self._route_key_for_instance(user_id, instance_id)
                if await redis_client.get(route_key) is None:
                    await redis_client.srem(self._route_set_key(user_id), instance_id)
                    continue
                subscriber_count = await redis_client.publish(
                    namespaced_channel(self._delivery_channel(instance_id)),
                    payload,
                )
                published += int(subscriber_count or 0)

            # Fallback for edge cases where local connections exist but Redis route has
            # not been registered yet (for example after a transient Redis error).
            if published == 0:
                return await self._send_to_user_local(user_id, message)
            return published
        except Exception as e:
            logger.warning(f"Failed to route WebSocket message: {e}")
            return await self._send_to_user_local(user_id, message)

    @staticmethod
    def _delivery_channel(instance_id: str) -> str:
        return f"{WS_DELIVERY_CHANNEL_PREFIX}:{instance_id}"

    def _route_key(self, user_id: str) -> str:
        return f"{WS_ROUTE_PREFIX}:{user_id}:{self._instance_id}"

    @staticmethod
    def _route_key_for_instance(user_id: str, instance_id: str) -> str:
        return f"{WS_ROUTE_PREFIX}:{user_id}:{instance_id}"

    @staticmethod
    def _route_set_key(user_id: str) -> str:
        return f"{WS_ROUTE_SET_PREFIX}:{user_id}"

    async def _sync_route_registration(self, user_id: str, connection_count: int) -> None:
        try:
            redis_client = self._get_redis()
            route_key = self._route_key(user_id)
            route_set_key = self._route_set_key(user_id)
            if connection_count > 0:
                await redis_client.set(route_key, str(connection_count), ex=WS_ROUTE_TTL_SECONDS)
                await redis_client.sadd(route_set_key, self._instance_id)
                await redis_client.expire(route_set_key, WS_ROUTE_TTL_SECONDS)
            else:
                await redis_client.delete(route_key)
                await redis_client.srem(route_set_key, self._instance_id)
        except Exception as e:
            logger.warning("Failed to sync WebSocket route for user %s: %s", user_id, e)

    def _get_redis(self):
        if self._redis is None:
            self._redis = create_redis_client(isolated_pool=True)
        return self._redis

    async def _close_redis(self) -> None:
        if self._redis is None:
            return
        try:
            await self._redis.aclose()
        except Exception as e:
            logger.warning("Failed to close WebSocket Redis client: %s", e)
        finally:
            self._redis = None

    def _ensure_route_refresh_task(self, user_id: str) -> None:
        if user_id in self._route_refresh_tasks:
            return

        async def _refresh_loop() -> None:
            try:
                while True:
                    await asyncio.sleep(WS_ROUTE_REFRESH_INTERVAL)
                    async with self._lock:
                        connection_count = len(self._connections.get(user_id, set()))
                    if connection_count <= 0:
                        return
                    await self._sync_route_registration(user_id, connection_count)
            except asyncio.CancelledError:
                pass
            finally:
                self._route_refresh_tasks.pop(user_id, None)

        self._route_refresh_tasks[user_id] = asyncio.create_task(_refresh_loop())

    async def _stop_route_refresh_task(self, user_id: str) -> None:
        task = self._route_refresh_tasks.pop(user_id, None)
        if task and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    async def _cancel_all_route_refresh_tasks(self) -> None:
        for user_id in list(self._route_refresh_tasks.keys()):
            await self._stop_route_refresh_task(user_id)

    async def _remove_all_route_registrations(self) -> None:
        user_ids = list(self._connections.keys())
        if not user_ids:
            return
        for user_id in user_ids:
            await self._sync_route_registration(user_id, 0)


# Singleton instance
_manager: ConnectionManager | None = None


def get_connection_manager() -> ConnectionManager:
    """获取 ConnectionManager 单例"""
    global _manager
    if _manager is None:
        _manager = ConnectionManager()
    return _manager
