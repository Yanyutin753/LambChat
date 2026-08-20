"""Codex 式运行中插话（steer）消息队列。

单进程内存实现：LambChat 的 agent 图（本地模式或内嵌 arq worker）与
API 路由运行在同一进程，字典 + asyncio.Lock 足够。消息由
``SteerMiddleware`` 在下一次模型调用时取出注入并持久化到图状态；
若运行在取出前结束，残留消息会在该会话的下一次运行的首次模型调用时
送达（排队语义，不丢失）。
"""

from __future__ import annotations

import asyncio
from typing import Dict, List

from src.infra.logging import get_logger

logger = get_logger(__name__)


class SteerQueue:
    """按会话隔离的插话消息队列（FIFO）。"""

    def __init__(self) -> None:
        self._pending: Dict[str, List[str]] = {}
        self._lock = asyncio.Lock()

    async def enqueue(self, session_id: str, message: str) -> int:
        """入队一条插话消息，返回该会话当前排队数。"""
        async with self._lock:
            queue = self._pending.setdefault(session_id, [])
            queue.append(message)
            logger.info("[Steer] session=%s queued message (%d pending)", session_id, len(queue))
            return len(queue)

    async def drain(self, session_id: str) -> List[str]:
        """取出并清空该会话的全部排队消息（FIFO）。"""
        async with self._lock:
            messages = self._pending.pop(session_id, [])
            if messages:
                logger.info("[Steer] session=%s draining %d message(s)", session_id, len(messages))
            return messages

    async def requeue_front(self, session_id: str, messages: List[str]) -> None:
        """把消息放回队首（用于注入失败后恢复排队，保持 FIFO 送达顺序）。"""
        if not messages:
            return
        async with self._lock:
            queue = self._pending.setdefault(session_id, [])
            queue[:0] = messages
            logger.info(
                "[Steer] session=%s requeued %d message(s) after failed delivery",
                session_id,
                len(messages),
            )

    def pending_count(self, session_id: str) -> int:
        """该会话当前排队数（只读，用于观测）。"""
        return len(self._pending.get(session_id, []))

    async def remove(self, session_id: str, message: str) -> bool:
        """移除该会话中排队的第一条相同内容消息（用户取消插话）。"""
        async with self._lock:
            queue = self._pending.get(session_id)
            if not queue:
                return False
            for index, queued in enumerate(queue):
                if queued == message:
                    del queue[index]
                    logger.info("[Steer] session=%s cancelled one queued message", session_id)
                    return True
            return False


_steer_queue: SteerQueue | None = None


def get_steer_queue() -> SteerQueue:
    """进程内单例。"""
    global _steer_queue
    if _steer_queue is None:
        _steer_queue = SteerQueue()
    return _steer_queue
