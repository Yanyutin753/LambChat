# src/infra/task/manager.py
"""
Background Task Manager - 后台任务管理器

支持按 run_id 管理任务状态，实现多轮对话隔离。
支持分布式取消任务。
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.infra.session.storage import SessionStorage
from src.infra.session.trace_storage import get_trace_storage

from .cancellation import TaskCancellation
from .exceptions import TaskInterruptedError
from .executor import TaskExecutor
from .heartbeat import TaskHeartbeat
from .pubsub import TaskPubSub
from .status import TaskStatus

# 重导出供外部使用
__all__ = [
    "BackgroundTaskManager",
    "TaskStatus",
    "TaskInterruptedError",
    "TaskCancellation",
]

logger = logging.getLogger(__name__)


def _generate_run_id() -> str:
    """生成运行 ID"""
    return f"run_{datetime.now().strftime('%Y%m%d%H%M%S')}_{uuid.uuid4().hex[:8]}"


class BackgroundTaskManager:
    """
    后台任务管理器

    管理后台任务的生命周期：
    - 提交任务后立即返回 session_id 和 run_id
    - 任务在后台异步执行
    - 支持按 run_id 查询任务状态
    - 支持分布式取消任务（通过 Redis pub/sub）
    - 服务关闭时标记未完成任务为失败
    """

    def __init__(self):
        # 使用 run_id 作为 key 管理状态
        self._tasks: Dict[str, asyncio.Task] = {}  # run_id -> Task
        self._run_info: Dict[str, Dict[str, str]] = {}  # run_id -> {session_id, trace_id, agent_id}
        self._lock = asyncio.Lock()
        self._storage = None
        self._heartbeat = TaskHeartbeat()
        self._cancellation = TaskCancellation(self._lock, self._tasks)
        self._pubsub = TaskPubSub(self._lock, self._tasks)
        self._executor = None  # Lazy init in submit

    @property
    def storage(self) -> SessionStorage:
        """延迟加载存储"""
        if self._storage is None:
            self._storage = SessionStorage()
        return self._storage

    async def submit(
        self,
        session_id: str,
        agent_id: str,
        message: str,
        user_id: str,
        executor: Callable[[str, str, str, str], Any],
        disabled_tools: Optional[List[str]] = None,
        agent_options: Optional[Dict[str, Any]] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
    ) -> Tuple[str, str]:
        """
        提交后台任务

        Args:
            session_id: 会话 ID
            agent_id: Agent ID
            message: 用户消息
            user_id: 用户 ID
            executor: 执行函数 (session_id, agent_id, message, user_id) -> AsyncGenerator
            disabled_tools: 用户禁用的工具列表（可选）
            agent_options: Agent 选项（可选，如 enable_thinking）
            attachments: 文件附件列表（可选）

        Returns:
            (run_id, trace_id) 元组
        """
        # 确保 executor 已初始化
        if self._executor is None:
            self._executor = TaskExecutor(self.storage, self._run_info, self._heartbeat)

        # 生成 run_id
        run_id = _generate_run_id()

        async with self._lock:
            # 确保 session 记录存在
            await self._executor.ensure_session(session_id, agent_id, user_id)

            # 更新 MongoDB session 状态（包含 current_run_id）
            await self._executor._update_session_status(
                session_id, TaskStatus.PENDING, run_id=run_id
            )

            # 创建后台任务
            task = asyncio.create_task(
                self._executor.run_task(
                    session_id,
                    run_id,
                    agent_id,
                    message,
                    user_id,
                    executor,
                    disabled_tools,
                    agent_options,
                    attachments,
                )
            )
            self._tasks[run_id] = task

            # 添加完成回调
            task.add_done_callback(lambda t: self._on_task_done(run_id, t))

        logger.info(f"Task submitted: session={session_id}, run_id={run_id}, agent={agent_id}")
        # 返回 run_id，trace_id 将在 _run_task 中创建
        return run_id, ""  # trace_id 由 Presenter 生成，这里先返回空

    def _on_task_done(self, run_id: str, task: asyncio.Task) -> None:
        """任务完成回调"""
        # 清理任务引用
        if run_id in self._tasks:
            del self._tasks[run_id]

    async def get_status(self, session_id: str) -> TaskStatus:
        """获取 session 当前 run 的任务状态（向后兼容）

        直接从 MongoDB 读取，不使用本地内存缓存，支持分布式部署。
        """
        try:
            session = await self.storage.get_by_session_id(session_id)
            if session and session.metadata:
                task_status = session.metadata.get("task_status")
                if task_status:
                    return TaskStatus(task_status)
        except Exception as e:
            logger.warning(f"Failed to get status from session storage: {e}")
        return TaskStatus.PENDING

    async def get_run_status(self, session_id: str, run_id: str) -> TaskStatus:
        """获取特定 run 的任务状态

        直接从 MongoDB 读取，不使用本地内存缓存，支持分布式部署。
        """
        # 优先从 session metadata 获取（最权威，取消/失败时会更新）
        try:
            session = await self.storage.get_by_session_id(session_id)
            if session and session.metadata:
                task_status = session.metadata.get("task_status")
                if task_status:
                    return TaskStatus(task_status)
        except Exception as e:
            logger.warning(f"Failed to get run status from session storage: {e}")

        # 回退到 trace storage 获取状态
        try:
            trace_storage = get_trace_storage()
            # 查询该 run_id 的 trace
            cursor = (
                trace_storage.collection.find({"run_id": run_id}, {"status": 1, "_id": 0})
                .sort("started_at", -1)
                .limit(1)
            )
            traces = await cursor.to_list(length=1)
            if traces:
                trace_status = traces[0].get("status")
                if trace_status:
                    # 映射 trace status 到 TaskStatus
                    status_map = {
                        "running": TaskStatus.RUNNING,
                        "completed": TaskStatus.COMPLETED,
                        "error": TaskStatus.FAILED,
                    }
                    return status_map.get(trace_status, TaskStatus.PENDING)
        except Exception as e:
            logger.warning(f"Failed to get run status from trace storage: {e}")

        return TaskStatus.PENDING

    async def get_error(self, session_id: str) -> Optional[str]:
        """获取任务错误信息（向后兼容）

        直接从 MongoDB 读取，不使用本地内存缓存，支持分布式部署。
        """
        try:
            session = await self.storage.get_by_session_id(session_id)
            if session and session.metadata:
                return session.metadata.get("task_error")
        except Exception as e:
            logger.warning(f"Failed to get error from session storage: {e}")
        return None

    async def get_run_error(self, run_id: str) -> Optional[str]:
        """获取特定 run 的错误信息

        直接从 MongoDB 读取，不使用本地内存缓存，支持分布式部署。
        """
        # 从 trace storage 获取错误信息
        try:
            trace_storage = get_trace_storage()
            # 查询该 run_id 的 trace
            cursor = (
                trace_storage.collection.find(
                    {"run_id": run_id}, {"metadata": 1, "events": 1, "_id": 0}
                )
                .sort("started_at", -1)
                .limit(1)
            )
            traces = await cursor.to_list(length=1)
            if traces:
                trace = traces[0]
                # 先检查 metadata 中的错误信息
                metadata = trace.get("metadata", {})
                if metadata.get("error"):
                    return metadata.get("error")
                # 再检查 events 中是否有 error 事件
                events = trace.get("events", [])
                for event in reversed(events):  # 从后往前找最新的 error
                    if event.get("event_type") == "error":
                        data = event.get("data", {})
                        return data.get("error")
        except Exception as e:
            logger.warning(f"Failed to get run error from trace storage: {e}")

        # 如果 trace storage 没有，尝试从 session metadata 获取
        run_info = self._run_info.get(run_id)
        if run_info:
            session_id = run_info.get("session_id")
            if session_id:
                try:
                    session = await self.storage.get_by_session_id(session_id)
                    if session and session.metadata:
                        return session.metadata.get("task_error")
                except Exception as e:
                    logger.warning(f"Failed to get run error from session storage: {e}")

        return None

    def get_trace_id(self, run_id: str) -> Optional[str]:
        """获取 run 对应的 trace_id"""
        info = self._run_info.get(run_id)
        return info.get("trace_id") if info else None

    async def cancel(self, session_id: str, user_id: Optional[str] = None) -> Dict[str, Any]:
        """
        取消任务（支持分布式）

        Args:
            session_id: 会话 ID
            user_id: 取消任务的用户 ID

        Returns:
            {
                "success": bool,  # 中断信号是否成功设置
                "cancelled_locally": bool,  # 是否在本地实例取消
                "run_id": str | None,  # 被取消的 run_id
                "message": str  # 状态信息
            }
        """
        # 获取 current_run_id
        try:
            session = await self.storage.get_by_session_id(session_id)
            if session and session.metadata:
                run_id = session.metadata.get("current_run_id")
                if run_id:
                    return await self.cancel_run(run_id, user_id=user_id)
                else:
                    return {
                        "success": False,
                        "cancelled_locally": False,
                        "run_id": None,
                        "message": "没有正在运行的任务",
                    }
        except Exception as e:
            logger.warning(f"Failed to cancel session {session_id}: {e}")
        return {
            "success": False,
            "cancelled_locally": False,
            "run_id": None,
            "message": "取消失败",
        }

    async def cancel_run(
        self, run_id: str, publish: bool = True, user_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        取消特定 run 的任务（支持分布式）

        Args:
            run_id: 运行 ID
            publish: 是否通过 Redis pub/sub 广播取消信号（用于分布式场景）
            user_id: 取消任务的用户 ID

        Returns:
            {
                "success": bool,  # 中断信号是否成功设置
                "cancelled_locally": bool,  # 是否在本地实例取消
                "run_id": str,  # 被取消的 run_id
                "message": str  # 状态信息
            }
        """
        run_info = self._run_info.get(run_id)

        result = await self._cancellation.cancel_run(
            run_id=run_id,
            publish=publish,
            user_id=user_id,
            run_info=run_info,
        )

        # 更新 session 状态为 cancelled
        if result["success"] and run_info and self._executor is not None:
            session_id = run_info.get("session_id")
            if session_id:
                await self._executor._update_session_status(
                    session_id, TaskStatus.FAILED, "Task cancelled", run_id=run_id
                )

        return result

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
        return TaskCancellation.check_interrupt_fast(run_id)

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
        await TaskCancellation.check_interrupt(run_id)

    @staticmethod
    async def clear_interrupt(run_id: str) -> None:
        """
        清除中断信号

        Args:
            run_id: 运行 ID
        """
        await TaskCancellation.clear_interrupt(run_id)

    async def start_pubsub_listener(self) -> None:
        """
        启动 Redis pub/sub 监听器，用于接收分布式取消信号

        应在应用启动时调用
        """
        await self._pubsub.start_listener()

    async def stop_pubsub_listener(self) -> None:
        """
        停止 Redis pub/sub 监听器

        应在应用关闭时调用
        """
        await self._pubsub.stop_listener()

    async def cleanup_stale_tasks(self) -> None:
        """
        清理残留的运行中任务（服务启动时调用）

        只清理心跳超时的任务，说明任务所在的实例已经下线或卡死。
        心跳还在的任务说明其他实例正在运行，不应清理。
        """
        try:
            # 查找所有 task_status=running 的 session
            cursor = self.storage.collection.find(
                {"metadata.task_status": TaskStatus.RUNNING.value}
            )
            running_sessions = await cursor.to_list(length=1000)

            cleaned_count = 0
            for session in running_sessions:
                session_id = session.get("_id")
                run_id = session.get("metadata", {}).get("current_run_id")

                if not run_id:
                    continue

                # 检查心跳是否存在
                heartbeat_exists = await self._heartbeat.check_exists(run_id)

                if heartbeat_exists:
                    # 心跳存在，说明其他实例正在运行此任务，跳过
                    logger.debug(
                        f"Task still running on another instance: session={session_id}, run_id={run_id}"
                    )
                    continue

                # 心跳不存在，说明任务所在的实例已下线，清理此任务
                logger.warning(
                    f"Cleaning up stale task (no heartbeat): session={session_id}, run_id={run_id}"
                )
                if self._executor is None:
                    self._executor = TaskExecutor(self.storage, self._run_info, self._heartbeat)
                await self._executor._update_session_status(
                    session_id,
                    TaskStatus.FAILED,
                    "Task interrupted (instance unavailable)",
                    run_id=run_id,
                )
                cleaned_count += 1

            if cleaned_count > 0:
                logger.info(f"Cleaned up {cleaned_count} stale tasks without heartbeat")
        except Exception as e:
            logger.error(f"Failed to cleanup stale tasks: {e}")

    async def shutdown(self) -> None:
        """
        服务关闭时调用

        标记所有运行中的任务为失败，清理心跳
        """
        async with self._lock:
            # 停止所有心跳任务
            await self._heartbeat.stop_all()

            # 初始化 executor 如果还未初始化
            if self._executor is None:
                self._executor = TaskExecutor(self.storage, self._run_info, self._heartbeat)

            for run_id, task in self._tasks.items():
                if not task.done():
                    task.cancel()

                    # 获取 session_id 并更新状态
                    info = self._run_info.get(run_id)
                    if info:
                        session_id = info.get("session_id")
                        if session_id:
                            await self._executor._update_session_status(
                                session_id,
                                TaskStatus.FAILED,
                                "Server shutdown",
                                run_id=run_id,
                            )
                    logger.warning(f"Task marked as failed (shutdown): run_id={run_id}")

            self._tasks.clear()
            logger.info("Task manager shutdown complete")


# Singleton instance
_task_manager: Optional[BackgroundTaskManager] = None


def get_task_manager() -> BackgroundTaskManager:
    """获取 TaskManager 单例"""
    global _task_manager
    if _task_manager is None:
        _task_manager = BackgroundTaskManager()
    return _task_manager
