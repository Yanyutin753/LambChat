# src/infra/task/pubsub.py
"""
Background Task Manager - Redis Pub/Sub

Handles Redis pub/sub for distributed task cancellation signals.
"""

import asyncio
import json
from typing import Any, Callable, Dict, Optional

from src.infra.logging import get_logger
from src.infra.pubsub_hub import get_pubsub_hub

from .constants import CANCEL_CHANNEL

logger = get_logger(__name__)


class TaskPubSub:
    """
    Redis Pub/Sub 管理类

    处理任务取消信号的发布和订阅。
    """

    def __init__(self, lock: asyncio.Lock, tasks: Dict[str, asyncio.Task]):
        """
        初始化 Pub/Sub 管理器

        Args:
            lock: 异步锁，用于保护共享状态
            tasks: 任务字典，run_id -> asyncio.Task
        """
        self._lock = lock
        self._tasks = tasks
        self._subscription_token: Optional[str] = None
        self._on_message: Optional[Callable[[Dict[str, Any]], None]] = None
        self._running = False

    async def start_listener(
        self,
        on_message: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        """
        启动 Redis pub/sub 监听器，用于接收分布式取消信号

        应在应用启动时调用

        Args:
            on_message: 消息回调函数，接收解析后的消息字典
        """
        if self._running:
            return

        self._on_message = on_message
        hub = get_pubsub_hub()
        self._subscription_token = hub.subscribe(
            CANCEL_CHANNEL,
            self._handle_hub_message,
        )
        await hub.start()
        self._running = True
        logger.info(f"Started listening on Redis channel: {CANCEL_CHANNEL}")

    async def _handle_hub_message(self, message: Dict[str, Any]) -> None:
        await self._handle_cancel_message(message, self._on_message)

    async def _handle_cancel_message(
        self,
        message: Dict[str, Any],
        on_message: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> None:
        """处理取消消息"""
        try:
            data = json.loads(message["data"])
            run_id = data.get("run_id")
            agent_id = data.get("agent_id")
            session_id = data.get("session_id")
            trace_id = data.get("trace_id")
            if run_id:
                logger.info(
                    f"Received cancel signal for run_id={run_id}, agent_id={agent_id}, session_id={session_id}"
                )

                # 调用自定义回调
                if on_message:
                    try:
                        await on_message(data)  # type: ignore[misc]
                    except Exception as e:
                        logger.warning(f"Error in on_message callback: {e}")

                # 更新 MongoDB trace 状态为 error（确保 trace 状态被更新）
                if trace_id:
                    try:
                        from src.infra.session.trace_storage import get_trace_storage

                        trace_storage = get_trace_storage()
                        success = await trace_storage.complete_trace(
                            trace_id,
                            status="error",
                            metadata={"cancel_reason": "Task cancelled via pub/sub"},
                        )
                        logger.info(
                            f"MongoDB trace status updated via pub/sub: trace_id={trace_id}, success={success}"
                        )
                    except Exception as e:
                        logger.warning(f"Failed to update trace status via pub/sub: {e}")

                # 调用 agent.close(run_id) 取消 graph
                if agent_id:
                    try:
                        from src.agents.core.base import AgentFactory

                        agent = await AgentFactory.get(agent_id)
                        await agent.close(run_id)
                        logger.info(
                            f"Agent.close({run_id}) called via pub/sub for agent={agent_id}"
                        )
                    except Exception as e:
                        logger.warning(f"Failed to call agent.close via pub/sub: {e}")

                # 尝试本地取消 asyncio Task
                async with self._lock:
                    if run_id in self._tasks:
                        task = self._tasks[run_id]
                        if not task.done():
                            task.cancel()
                            logger.info(f"Task cancelled via pub/sub: run_id={run_id}")
        except json.JSONDecodeError:
            logger.warning(f"Invalid cancel message format: {message['data']}")
        except Exception as e:
            logger.error(f"Error processing cancel message: {e}")

    async def stop_listener(self) -> None:
        """
        停止 Redis pub/sub 监听器

        应在应用关闭时调用
        """
        self._running = False
        self._on_message = None

        if self._subscription_token:
            hub = get_pubsub_hub()
            hub.unsubscribe(self._subscription_token)
            self._subscription_token = None
            await hub.stop_if_idle()

        logger.info("Pub/sub listener stopped")

    @property
    def is_running(self) -> bool:
        """检查监听器是否正在运行"""
        return self._running
