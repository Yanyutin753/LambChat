# src/infra/task/cancellation.py
"""
Background Task Manager - Task Cancellation

Handles task interruption and cancellation logic including in-memory flags,
Redis-based distributed cancellation, and agent cleanup.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, Optional

from src.infra.session.trace_storage import get_trace_storage
from src.infra.storage.redis import get_redis_client

from .constants import CANCEL_CHANNEL, INTERRUPT_PREFIX
from .exceptions import TaskInterruptedError

logger = logging.getLogger(__name__)

# 内存中的中断标志集合（用于快速检查）
_interrupted_runs: set = set()


class TaskCancellation:
    """
    任务取消和中断管理类

    处理任务的取消、中断信号管理和清理工作。
    """

    def __init__(self, lock: asyncio.Lock, tasks: Dict[str, asyncio.Task]):
        """
        初始化任务取消管理器

        Args:
            lock: 异步锁，用于保护共享状态
            tasks: 任务字典，run_id -> asyncio.Task
        """
        self._lock = lock
        self._tasks = tasks

    async def cancel_run(
        self,
        run_id: str,
        publish: bool = True,
        user_id: Optional[str] = None,
        run_info: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        取消特定 run 的任务（支持分布式）

        Args:
            run_id: 运行 ID
            publish: 是否通过 Redis pub/sub 广播取消信号（用于分布式场景）
            user_id: 取消任务的用户 ID
            run_info: 运行信息字典 {session_id, trace_id, agent_id}

        Returns:
            {
                "success": bool,  # 中断信号是否成功设置
                "cancelled_locally": bool,  # 是否在本地实例取消
                "run_id": str,  # 被取消的 run_id
                "message": str  # 状态信息
            }
        """
        cancelled_locally = False
        interrupt_signal_set = False

        # 1. 立即设置内存中的中断标志（最快）
        _interrupted_runs.add(run_id)
        logger.info(f"Memory interrupt flag set for run_id={run_id}")

        # 2. 设置 Redis 中断信号（用于分布式场景）
        try:
            redis_client = get_redis_client()
            await redis_client.set(
                f"{INTERRUPT_PREFIX}{run_id}",
                datetime.now().isoformat(),
                ex=300,  # 5 分钟过期
            )
            interrupt_signal_set = True
            logger.info(f"Redis interrupt signal set for run_id={run_id}")
        except Exception as e:
            logger.warning(f"Failed to set interrupt signal: {e}")

        # 3. 直接更新 MongoDB trace 状态为 error（确保 trace 状态被更新）
        if run_info:
            trace_id = run_info.get("trace_id")
            if trace_id:
                try:
                    trace_storage = get_trace_storage()
                    success = await trace_storage.complete_trace(
                        trace_id,
                        status="error",
                        metadata={"cancel_reason": "Task cancelled by user"},
                    )
                    logger.info(
                        f"MongoDB trace status updated: trace_id={trace_id}, success={success}"
                    )
                except Exception as e:
                    logger.warning(f"Failed to update trace status: {e}")

        # 3.1 记录用户取消事件
        if user_id and run_info:
            session_id = run_info.get("session_id")
            trace_id = run_info.get("trace_id")
            if session_id and trace_id:
                try:
                    from src.infra.session.dual_writer import get_dual_writer

                    dual_writer = get_dual_writer()
                    await dual_writer.write_event(
                        session_id=session_id,
                        event_type="user:cancel",
                        data={
                            "user_id": user_id,
                            "run_id": run_id,
                            "timestamp": datetime.now().isoformat(),
                        },
                        trace_id=trace_id,
                        run_id=run_id,
                    )
                    logger.info(f"User cancel event recorded: user_id={user_id}, run_id={run_id}")
                except Exception as e:
                    logger.warning(f"Failed to record user cancel event: {e}")

        # 4. 调用 agent.close(run_id) 取消 graph 执行
        if run_info:
            agent_id = run_info.get("agent_id")
            if agent_id:
                try:
                    from src.agents.core.base import AgentFactory

                    agent = await AgentFactory.get(agent_id)
                    await agent.close(run_id)
                    logger.info(f"Agent.close({run_id}) called for agent={agent_id}")
                except Exception as e:
                    logger.warning(f"Failed to call agent.close: {e}")

        async with self._lock:
            if run_id in self._tasks:
                task = self._tasks[run_id]
                if not task.done():
                    task.cancel()
                    cancelled_locally = True
                    logger.info(f"Task cancelled locally: run_id={run_id}")

        # 如果本地没有这个任务，或者需要广播给其他实例
        if publish:
            try:
                redis_client = get_redis_client()
                agent_id = run_info.get("agent_id") if run_info else None
                session_id = run_info.get("session_id") if run_info else None
                trace_id = run_info.get("trace_id") if run_info else None
                import json

                await redis_client.publish(
                    CANCEL_CHANNEL,
                    json.dumps(
                        {
                            "run_id": run_id,
                            "agent_id": agent_id,
                            "session_id": session_id,
                            "trace_id": trace_id,
                            "timestamp": datetime.now().isoformat(),
                        }
                    ),
                )
                logger.info(
                    f"Published cancel signal for run_id={run_id}, agent_id={agent_id}, session_id={session_id}"
                )
            except Exception as e:
                logger.warning(f"Failed to publish cancel signal: {e}")

        # 构建返回结果
        # success: 中断信号成功设置即认为成功（即使任务在其他实例运行）
        success = interrupt_signal_set or run_id in _interrupted_runs

        if cancelled_locally:
            message = "任务已取消"
        elif success:
            message = "取消信号已发送，任务将在下次检查点中断"
        else:
            message = "取消信号设置失败"

        return {
            "success": success,
            "cancelled_locally": cancelled_locally,
            "run_id": run_id,
            "message": message,
        }

    @staticmethod
    def check_interrupt_fast(run_id: str) -> bool:
        """
        快速检查中断信号（仅内存，无 IO）

        用于高频调用的场景（如主循环），避免 Redis IO 开销。
        对于分布式场景，依赖 Redis pub/sub 将信号同步到本地内存。

        Args:
            run_id: 运行 ID

        Returns:
            True 如果任务被中断
        """
        global _interrupted_runs
        return run_id in _interrupted_runs

    @staticmethod
    async def check_interrupt(run_id: str) -> None:
        """
        检查是否有中断信号，如果有则抛出 TaskInterruptedError

        供 agent 在执行过程中调用，实现优雅中断。
        优先检查内存标志（最快），其次检查 Redis（分布式场景）。

        Args:
            run_id: 运行 ID

        Raises:
            TaskInterruptedError: 如果任务被中断
        """
        global _interrupted_runs

        # 1. 首先检查内存标志（最快，无 IO）
        if run_id in _interrupted_runs:
            logger.info(f"Memory interrupt detected for run_id={run_id}")
            raise TaskInterruptedError(f"Task interrupted: run_id={run_id}")

        # 2. 检查 Redis（分布式场景）
        try:
            redis_client = get_redis_client()
            interrupted = await redis_client.get(f"{INTERRUPT_PREFIX}{run_id}")
            if interrupted:
                logger.info(f"Redis interrupt detected for run_id={run_id}")
                raise TaskInterruptedError(f"Task interrupted: run_id={run_id}")
        except TaskInterruptedError:
            raise
        except Exception as e:
            logger.warning(f"Failed to check Redis interrupt signal: {e}")

    @staticmethod
    async def clear_interrupt(run_id: str) -> None:
        """
        清除中断信号

        Args:
            run_id: 运行 ID
        """
        global _interrupted_runs

        # 1. 清除内存标志
        _interrupted_runs.discard(run_id)

        # 2. 清除 Redis 标志
        try:
            redis_client = get_redis_client()
            await redis_client.delete(f"{INTERRUPT_PREFIX}{run_id}")
        except Exception as e:
            logger.warning(f"Failed to clear interrupt signal: {e}")
