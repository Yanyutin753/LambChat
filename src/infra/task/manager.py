# src/infra/task/manager.py
"""
Background Task Manager - 后台任务管理器

支持按 run_id 管理任务状态，实现多轮对话隔离。
支持分布式取消任务。
"""

import asyncio
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.infra.logging import get_logger
from src.infra.session.storage import SessionStorage

from .cancellation import TaskCancellation
from .exceptions import TaskInterruptedError
from .executor import TaskExecutor
from .heartbeat import TaskHeartbeat
from .pubsub import TaskPubSub
from .recovery import TaskRecoveryService
from .run_ids import generate_run_id
from .startup_cleanup import TaskStartupCleanupService
from .status import TaskStatus
from .status_queries import TaskStatusQueries

# 重导出供外部使用
__all__ = [
    "BackgroundTaskManager",
    "TaskStatus",
    "TaskInterruptedError",
    "TaskCancellation",
]

logger = get_logger(__name__)


def _generate_run_id() -> str:
    """Backward-compatible alias for older imports."""
    return generate_run_id()


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
        self._run_info: Dict[
            str, Dict[str, Any]
        ] = {}  # run_id -> {session_id, trace_id, agent_id, user_id, ...}
        self._pending_tasks: Dict[str, Dict[str, Any]] = {}  # run_id -> task context (queued tasks)
        self._lock = asyncio.Lock()
        self._storage = None
        self._heartbeat = TaskHeartbeat()
        self._cancellation = TaskCancellation(self._lock, self._tasks)
        self._pubsub = TaskPubSub(self._lock, self._tasks)
        self._executor: Optional[TaskExecutor] = None  # Lazy init in submit

    @property
    def storage(self) -> SessionStorage:
        """延迟加载存储"""
        if self._storage is None:
            self._storage = SessionStorage()
        return self._storage

    def _ensure_executor(self) -> TaskExecutor:
        """Ensure a task executor exists for local dispatch and recovery."""
        if self._executor is None:
            self._executor = TaskExecutor(self.storage, self._run_info, self._heartbeat)
        return self._executor

    def _status_queries(self) -> TaskStatusQueries:
        return TaskStatusQueries(storage=self.storage, run_info=self._run_info)

    def _recovery_service(self) -> TaskRecoveryService:
        return TaskRecoveryService(
            storage=self.storage,
            run_info=self._run_info,
            heartbeat=self._heartbeat,
            ensure_executor=self._ensure_executor,
            submit_task=self.submit,
            mark_run_failed=self._mark_run_failed,
        )

    def _startup_cleanup_service(self) -> TaskStartupCleanupService:
        return TaskStartupCleanupService(
            storage=self.storage,
            heartbeat=self._heartbeat,
            ensure_executor=self._ensure_executor,
            load_session_record=self._load_session_record,
            resume_interrupted_run=self._resume_interrupted_run,
        )

    async def _mark_run_failed(self, run_id: str, reason: str, session: Any) -> None:
        await self._recovery_service().mark_run_failed(run_id, reason, session)

    async def _mark_run_recoverable_failure(
        self,
        session_id: str,
        run_id: str,
        error_message: str,
        error_code: str = "server_restart",
    ) -> None:
        await self._recovery_service().mark_run_recoverable_failure(
            session_id,
            run_id,
            error_message,
            error_code=error_code,
        )

    async def _submit_recovery_run(
        self,
        session: Any,
        source_run_id: str,
        reason: str,
    ) -> Dict[str, Any]:
        return await self._recovery_service().submit_recovery_run(session, source_run_id, reason)

    async def _resume_interrupted_run(
        self,
        session: Any,
        source_run_id: str,
        reason: str,
    ) -> Dict[str, Any]:
        return await self._recovery_service().resume_interrupted_run(
            session,
            source_run_id,
            reason,
        )

    async def _load_session_record(self, raw_session: dict[str, Any]) -> Any | None:
        """Load a normalized session model from a raw MongoDB session document."""
        session_id = raw_session.get("session_id") or str(raw_session.get("_id"))
        session = await self.storage.get_by_session_id(session_id)
        if session is not None:
            return session
        return await self.storage.get_by_id(session_id)

    async def _release_recovery_lock(self, lock_key: str) -> None:
        await self._recovery_service().release_recovery_lock(lock_key)

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
        run_id: Optional[str] = None,
        project_id: Optional[str] = None,
        disabled_skills: Optional[List[str]] = None,
        disabled_mcp_tools: Optional[List[str]] = None,
        session_name: Optional[str] = None,
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
            session_name: 自定义 session 名称（可选）

        Returns:
            (run_id, trace_id) 元组
        """
        # 确保 executor 已初始化
        task_executor = self._ensure_executor()

        # 生成 run_id
        run_id = run_id or generate_run_id()

        async with self._lock:
            # 确保 session 记录存在
            await task_executor.ensure_session(
                session_id,
                agent_id,
                user_id,
                project_id=project_id,
                session_name=session_name,
            )

            # 更新 MongoDB session 状态（包含 current_run_id）
            await task_executor._update_session_status(
                session_id, TaskStatus.PENDING, run_id=run_id
            )

            # 创建后台任务
            task = asyncio.create_task(
                task_executor.run_task(
                    session_id,
                    run_id,
                    agent_id,
                    message,
                    user_id,
                    executor,
                    disabled_tools,
                    agent_options,
                    attachments,
                    disabled_skills=disabled_skills,
                    disabled_mcp_tools=disabled_mcp_tools,
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
        # 清理运行信息，防止内存泄漏
        run_info = self._run_info.pop(run_id, None)
        # 清理待处理任务上下文（如果存在）
        self._pending_tasks.pop(run_id, None)
        # 释放并发槽位
        user_id = run_info.get("user_id") if run_info else None
        if user_id:
            asyncio.get_event_loop().call_soon(
                lambda: asyncio.ensure_future(self._release_concurrency(user_id, run_id))
            )

    def pop_pending_task(self, run_id: str) -> Optional[Dict[str, Any]]:
        """Pop and return a pending task context (used by concurrency limiter to dispatch queued tasks)."""
        return self._pending_tasks.pop(run_id, None)

    async def _release_concurrency(self, user_id: str, run_id: str) -> None:
        """Release a concurrency slot for the user."""
        try:
            from .concurrency import get_concurrency_limiter

            limiter = get_concurrency_limiter()
            await limiter.release(user_id, run_id)
        except Exception as e:
            logger.warning(f"Failed to release concurrency slot: {e}")

    async def get_status(self, session_id: str) -> TaskStatus:
        return await self._status_queries().get_status(session_id)

    async def get_run_status(self, session_id: str, run_id: str) -> TaskStatus:
        return await self._status_queries().get_run_status(session_id, run_id)

    async def get_error(self, session_id: str) -> Optional[str]:
        return await self._status_queries().get_error(session_id)

    async def get_run_error(self, run_id: str) -> Optional[str]:
        return await self._status_queries().get_run_error(run_id)

    def get_trace_id(self, run_id: str) -> Optional[str]:
        return self._status_queries().get_trace_id(run_id)

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

    async def resume_session(
        self,
        session_id: str,
        reason: str = "manual_resume",
    ) -> Dict[str, Any]:
        return await self._recovery_service().resume_session(session_id, reason)

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
        await self._startup_cleanup_service().cleanup_stale_tasks()

    async def _cleanup_stale_queues(self) -> None:
        await TaskStartupCleanupService(
            storage=self.storage,
            heartbeat=self._heartbeat,
            ensure_executor=self._ensure_executor,
            load_session_record=self._load_session_record,
            resume_interrupted_run=self._resume_interrupted_run,
        ).cleanup_stale_queues()

    async def _replay_pending_queued_tasks(self) -> None:
        await TaskStartupCleanupService(
            storage=self.storage,
            heartbeat=self._heartbeat,
            ensure_executor=self._ensure_executor,
            load_session_record=self._load_session_record,
            resume_interrupted_run=self._resume_interrupted_run,
        ).replay_pending_queued_tasks()

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

            from .concurrency import get_concurrency_limiter

            limiter = get_concurrency_limiter()
            for run_id, task in self._tasks.items():
                if not task.done():
                    task.cancel()

                    # 获取 session_id 并更新状态
                    info = self._run_info.get(run_id)
                    if info:
                        session_id = info.get("session_id")
                        if session_id:
                            await self._mark_run_recoverable_failure(
                                session_id,
                                run_id,
                                "Server shutdown",
                            )
                        # 释放 Redis 并发槽位
                        user_id = info.get("user_id")
                        if user_id:
                            try:
                                await limiter.release(user_id, run_id, dequeue=False)
                            except Exception as e:
                                logger.warning(
                                    f"Failed to release concurrency slot on shutdown: {e}"
                                )
                    logger.warning(f"Task marked as failed (shutdown): run_id={run_id}")

            self._tasks.clear()
            self._run_info.clear()
            self._pending_tasks.clear()
            logger.info("Task manager shutdown complete")


# Singleton instance
_task_manager: Optional[BackgroundTaskManager] = None


def get_task_manager() -> BackgroundTaskManager:
    """获取 TaskManager 单例"""
    global _task_manager
    if _task_manager is None:
        _task_manager = BackgroundTaskManager()
    return _task_manager
