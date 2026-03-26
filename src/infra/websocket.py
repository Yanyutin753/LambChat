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

from src.infra.logging import get_logger

logger = get_logger(__name__)

# Redis channel for WebSocket broadcast
WS_BROADCAST_CHANNEL = "ws:broadcast"


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
        self._pubsub_task: Optional[asyncio.Task] = None
        self._pubsub = None
        self._running = False
        self._instance_id = uuid.uuid4().hex

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
        logger.info(
            f"WebSocket connected: user_id={user_id}, total={len(self._connections[user_id])}"
        )

    async def disconnect(self, websocket: WebSocket, user_id: str) -> None:
        """用户断开 WebSocket"""
        async with self._lock:
            if user_id in self._connections:
                self._connections[user_id].discard(websocket)
                if not self._connections[user_id]:
                    del self._connections[user_id]
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

        for user_id, ws in all_connections:
            try:
                await ws.send_text(json.dumps(message, ensure_ascii=False))
                sent_count += 1
            except Exception as e:
                logger.warning(f"Failed to broadcast to WebSocket: {e}")
                disconnected.add((user_id, ws))

        # 清理断开的连接
        if disconnected:
            async with self._lock:
                for user_id, ws in disconnected:
                    if user_id in self._connections:
                        self._connections[user_id].discard(ws)

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

        self._running = True

        async def listener():
            try:
                from src.infra.storage.redis import get_redis_client

                redis_client = get_redis_client()
                self._pubsub = redis_client.pubsub()
                await self._pubsub.subscribe(WS_BROADCAST_CHANNEL)
                logger.info(
                    f"WebSocket: Started listening on Redis channel: {WS_BROADCAST_CHANNEL}"
                )

                async for message in self._pubsub.listen():
                    if not self._running:
                        break

                    if message["type"] == "message":
                        try:
                            data = json.loads(message["data"])
                            await self._handle_broadcast_message(data)
                        except json.JSONDecodeError:
                            logger.warning(
                                f"Invalid WebSocket broadcast message: {message['data']}"
                            )
                        except Exception as e:
                            logger.error(f"Error processing WebSocket broadcast: {e}")

            except asyncio.CancelledError:
                logger.info("WebSocket pub/sub listener cancelled")
            except Exception as e:
                logger.error(f"WebSocket pub/sub listener error: {e}")
            finally:
                if self._pubsub:
                    try:
                        await self._pubsub.unsubscribe(WS_BROADCAST_CHANNEL)
                        await self._pubsub.close()
                    except Exception as e:
                        logger.warning(f"Failed to close WebSocket pubsub: {e}")
                    finally:
                        self._pubsub = None
                self._running = False
                logger.info("WebSocket pub/sub listener stopped")

        self._pubsub_task = asyncio.create_task(listener())

    async def stop_pubsub_listener(self) -> None:
        """
        停止 Redis pub/sub 监听器

        应在应用关闭时调用
        """
        self._running = False

        if self._pubsub:
            try:
                await self._pubsub.unsubscribe(WS_BROADCAST_CHANNEL)
                await self._pubsub.close()
            except Exception as e:
                logger.warning(f"Failed to close WebSocket pubsub: {e}")
            finally:
                self._pubsub = None

        if self._pubsub_task and not self._pubsub_task.done():
            self._pubsub_task.cancel()
            try:
                await self._pubsub_task
            except asyncio.CancelledError:
                pass

        logger.info("WebSocket pub/sub listener stopped")

    async def _handle_broadcast_message(self, data: dict) -> int:
        """Handle a WebSocket broadcast payload received from Redis."""
        if data.get("source_instance_id") == self._instance_id:
            return 0

        user_id = data.get("user_id")
        msg_content = data.get("message")
        if not user_id or not msg_content:
            return 0

        # Only deliver locally here; rebroadcasting would create a loop.
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

        json_str = json.dumps(message, ensure_ascii=False)
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
            async with self._lock:
                for ws in disconnected:
                    if user_id in self._connections:
                        self._connections[user_id].discard(ws)

        return sent_count

    async def send_to_user_with_broadcast(self, user_id: str, message: dict) -> int:
        """
        向指定用户发送消息（支持分布式广播）

        先在本地发送，然后通过 Redis 广播到其他实例。

        Args:
            user_id: 用户 ID
            message: 消息内容

        Returns:
            本地成功发送的连接数
        """
        # 本地发送
        sent_count = await self._send_to_user_local(user_id, message)

        # 广播到其他实例
        try:
            from src.infra.storage.redis import get_redis_client

            redis_client = get_redis_client()
            await redis_client.publish(
                WS_BROADCAST_CHANNEL,
                json.dumps(
                    {
                        "user_id": user_id,
                        "message": message,
                        "source_instance_id": self._instance_id,
                    }
                ),
            )
        except Exception as e:
            logger.warning(f"Failed to broadcast WebSocket message: {e}")

        return sent_count


# Singleton instance
_manager: ConnectionManager | None = None


def get_connection_manager() -> ConnectionManager:
    """获取 ConnectionManager 单例"""
    global _manager
    if _manager is None:
        _manager = ConnectionManager()
    return _manager
