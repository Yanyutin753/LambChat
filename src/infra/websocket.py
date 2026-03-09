"""
WebSocket Manager - WebSocket 连接管理器

管理 WebSocket 连接，用于实时推送任务完成通知。
"""

import asyncio
import json
import logging
from typing import Dict, Set

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    WebSocket 连接管理器

    管理所有活跃的 WebSocket 连接，按用户 ID 分组。
    """

    def __init__(self):
        # user_id -> Set[WebSocket]
        self._connections: Dict[str, Set[WebSocket]] = {}
        self._lock = asyncio.Lock()

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

    async def send_to_user(self, user_id: str, message: dict) -> int:
        """
        向指定用户发送消息

        Args:
            user_id: 用户 ID
            message: 消息内容（dict，会被序列化为 JSON）

        Returns:
            成功发送的连接数
        """
        if not message:
            return 0

        json_str = json.dumps(message, ensure_ascii=False)
        sent_count = 0

        logger.info(
            f"[WebSocket] send_to_user: user_id={user_id}, connections={list(self._connections.keys())}"
        )

        async with self._lock:
            connections = self._connections.get(user_id, set()).copy()

        logger.info(f"[WebSocket] Sending to {len(connections)} connections: {json_str}")

        # 遍历副本以避免在发送时修改集合
        disconnected = set()
        for ws in connections:
            try:
                await ws.send_text(json_str)
                sent_count += 1
                logger.info("[WebSocket] Sent successfully to one connection")
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


# Singleton instance
_manager: ConnectionManager | None = None


def get_connection_manager() -> ConnectionManager:
    """获取 ConnectionManager 单例"""
    global _manager
    if _manager is None:
        _manager = ConnectionManager()
    return _manager
