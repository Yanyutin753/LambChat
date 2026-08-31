# src/infra/task/heartbeat.py
"""
Background Task Manager - Heartbeat Mechanism

Manages task heartbeat for detecting stale/failed tasks in distributed scenarios.
"""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timezone

from src.infra.logging import get_logger
from src.infra.storage.redis import get_redis_client
from src.infra.utils.datetime import utc_now_iso

from .constants import (
    HEARTBEAT_INTERVAL,
    HEARTBEAT_PREFIX,
    HEARTBEAT_STALE_THRESHOLD_SECONDS,
    HEARTBEAT_TIMEOUT,
)
from .startup_cleanup import _gather_limited

logger = get_logger(__name__)


class TaskHeartbeat:
    """
    任务心跳管理类

    负责启动和停止任务的心跳机制，用于检测任务是否存活。
    """

    def __init__(self) -> None:
        self._heartbeat_tasks: dict[str, asyncio.Task] = {}  # run_id -> heartbeat Task

    async def start(self, run_id: str, user_id: str | None = None) -> None:
        """启动任务心跳"""
        if run_id in self._heartbeat_tasks:
            logger.warning(f"Heartbeat already exists for run_id={run_id}")
            return

        async def heartbeat_loop():
            try:
                redis_client = get_redis_client()
                while True:
                    try:
                        # 设置心跳，带 TTL（超时时间的 2 倍）
                        await redis_client.set(
                            f"{HEARTBEAT_PREFIX}{run_id}",
                            utc_now_iso(),
                            ex=HEARTBEAT_TIMEOUT * 2,
                        )
                        # 刷新并发限制的 Sorted Set 分数（保持条目活跃）
                        if user_id:
                            try:
                                from src.infra.task.concurrency import get_concurrency_limiter

                                limiter = get_concurrency_limiter()
                                await limiter.refresh(user_id, run_id)
                            except Exception:
                                pass
                    except Exception as e:
                        logger.warning(f"Heartbeat write failed for run_id={run_id}: {e}")
                    await asyncio.sleep(HEARTBEAT_INTERVAL)
            except asyncio.CancelledError:
                pass
            finally:
                self._heartbeat_tasks.pop(run_id, None)

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
        run_ids = list(self._heartbeat_tasks.keys())
        stop_factories: list[Callable[[], Awaitable[None]]] = []
        for run_id in run_ids:

            async def _stop_current(run_id: str = run_id) -> None:
                await self.stop(run_id)

            stop_factories.append(_stop_current)

        await _gather_limited(stop_factories)

    async def is_stale(self, run_id: str, max_age_seconds: int | None = None) -> bool:
        """按时间戳判断心跳是否过期。

        与 check_exists（等 Redis key 120s TTL 自然消失）相比，按「距最后一次
        心跳的时长」判定可以把实例死亡后的接管检测从 ~2 分钟缩到几十秒。
        值缺失 → 过期；解析失败 → 按存活处理（避免误接管活任务）。
        恢复入口与 arq worker 侧都有同款复核兜底，短阈值不会误接管活任务。
        """
        if max_age_seconds is None:
            # settings 优先（TASK_HEARTBEAT_STALE_SECONDS，<=0 回退内置公式）
            try:
                from src.kernel.config import settings

                configured = int(
                    getattr(settings, "TASK_HEARTBEAT_STALE_SECONDS", 0) or 0
                )
            except Exception:
                configured = 0
            max_age_seconds = (
                configured
                if configured > 0
                else HEARTBEAT_STALE_THRESHOLD_SECONDS
            )
        threshold = max_age_seconds
        try:
            value = await get_redis_client().get(f"{HEARTBEAT_PREFIX}{run_id}")
        except Exception as e:
            logger.warning(f"Heartbeat read failed for run_id={run_id}: {e}")
            return False  # Redis 不可用时按存活处理，避免误接管
        if value is None:
            return True
        try:
            last_beat = datetime.fromisoformat(str(value))
        except ValueError:
            return False
        if last_beat.tzinfo is None:
            last_beat = last_beat.replace(tzinfo=timezone.utc)
        return (datetime.now(timezone.utc) - last_beat).total_seconds() > threshold

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
