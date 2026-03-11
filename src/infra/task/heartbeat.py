# src/infra/task/heartbeat.py
"""
Background Task Manager - Heartbeat Mechanism

Manages task heartbeat for detecting stale/failed tasks in distributed scenarios.
"""

import asyncio
import logging
from datetime import datetime

from src.infra.storage.redis import get_redis_client

from .constants import HEARTBEAT_INTERVAL, HEARTBEAT_PREFIX, HEARTBEAT_TIMEOUT

logger = logging.getLogger(__name__)


class TaskHeartbeat:
    """
    任务心跳管理类

    负责启动和停止任务的心跳机制，用于检测任务是否存活。
    """

    def __init__(self) -> None:
        self._heartbeat_tasks: dict[str, asyncio.Task] = {}  # run_id -> heartbeat Task

    async def start(self, run_id: str) -> None:
        """启动任务心跳"""
        if run_id in self._heartbeat_tasks:
            logger.warning(f"Heartbeat already exists for run_id={run_id}")
            return

        async def heartbeat_loop():
            try:
                redis_client = get_redis_client()
                while True:
                    # 设置心跳，带 TTL（超时时间的 2 倍）
                    await redis_client.set(
                        f"{HEARTBEAT_PREFIX}{run_id}",
                        datetime.now().isoformat(),
                        ex=HEARTBEAT_TIMEOUT * 2,
                    )
                    await asyncio.sleep(HEARTBEAT_INTERVAL)
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.warning(f"Heartbeat error for run_id={run_id}: {e}")

        self._heartbeat_tasks[run_id] = asyncio.create_task(heartbeat_loop())

    async def stop(self, run_id: str) -> None:
        """停止任务心跳"""
        # 取消心跳任务
        if run_id in self._heartbeat_tasks:
            task = self._heartbeat_tasks.pop(run_id)
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass

        # 删除 Redis 中的心跳 key
        try:
            redis_client = get_redis_client()
            await redis_client.delete(f"{HEARTBEAT_PREFIX}{run_id}")
        except Exception as e:
            logger.warning(f"Failed to delete heartbeat for run_id={run_id}: {e}")

    async def stop_all(self) -> None:
        """停止所有心跳任务"""
        for run_id in list(self._heartbeat_tasks.keys()):
            await self.stop(run_id)

    async def check_exists(self, run_id: str) -> bool:
        """
        检查心跳是否存在

        用于判断任务是否在其他实例上运行。
        """
        try:
            redis_client = get_redis_client()
            heartbeat_key = f"{HEARTBEAT_PREFIX}{run_id}"
            heartbeat = await redis_client.get(heartbeat_key)
            return heartbeat is not None
        except Exception as e:
            logger.warning(f"Failed to check heartbeat for run_id={run_id}: {e}")
            return False

    def is_running(self, run_id: str) -> bool:
        """检查本地心跳任务是否在运行"""
        return run_id in self._heartbeat_tasks
