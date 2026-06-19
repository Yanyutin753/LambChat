# src/infra/task/manager.py
"""
Background Task Manager - 后台任务管理器

支持按 run_id 管理任务状态，实现多轮对话隔离。
支持分布式取消任务。
"""

import asyncio
import inspect
from collections.abc import Awaitable
from typing import Any, Callable, Dict, List, Optional, Tuple

from arq.connections import create_pool

from src.infra.logging import get_logger
from src.infra.session.storage import SessionStorage
from src.kernel.config import settings

from .arq_payloads import TaskArqPayloadStore
from .arq_settings import build_arq_redis_settings
from .cancellation import TaskCancellation
from .exceptions import TaskInterruptedError
from .executor import TaskExecutor
from .heartbeat import TaskHeartbeat
from .pubsub import TaskPubSub
from .recovery import TaskRecoveryService
from .run_ids import generate_run_id
from .startup_cleanup import TaskStartupCleanupService, _gather_limited
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


def _ensure_agent_executable(agent_id: str) -> None:
    from src.agents import ensure_agent_executable

    ensure_agent_executable(agent_id)


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
        self._arq_pool: Any | None = None
        self._release_tasks: set[asyncio.Task[None]] = set()

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

    async def _get_arq_pool(self) -> Any:
        """Return a manager-owned arq pool, creating it lazily."""
        if self._arq_pool is None:
            self._arq_pool = await create_pool(
                build_arq_redis_settings(settings),
                default_queue_name=settings.ARQ_QUEUE_NAME,
            )
        return self._arq_pool

    async def _close_arq_pool(self) -> None:
        """Close the manager-owned arq pool if it was created."""
        arq_pool = self._arq_pool
        self._arq_pool = None
        if arq_pool is None:
            return

        close = getattr(arq_pool, "close", None)
        if close is not None:
            result = close()
            if inspect.isawaitable(result):
                await result
        wait_closed = getattr(arq_pool, "wait_closed", None)
        if wait_closed is not None:
            result = wait_closed()
            if inspect.isawaitable(result):
                await result

    async def _persist_initial_user_message(
        self,
        *,
        session_id: str,
        agent_id: str,
        user_id: str,
        run_id: str,
        trace_id: str | None,
        message: str,
        display_message: str | None,
        attachments: Optional[List[Dict[str, Any]]],
    ) -> str:
        """Persist the user message before the background worker starts."""
        from src.agents.core import resolve_agent_name
        from src.infra.writer.present import Presenter, PresenterConfig

        presenter = Presenter(
            PresenterConfig(
                session_id=session_id,
                agent_id=agent_id,
                agent_name=resolve_agent_name(agent_id),
                user_id=user_id,
                run_id=run_id,
                trace_id=trace_id,
                enable_storage=True,
            )
        )
        await presenter._ensure_trace()
        await presenter.emit_user_message(display_message or message, attachments=attachments)
        return presenter.trace_id

    def _status_queries(self) -> TaskStatusQueries:
        return TaskStatusQueries(storage=self.storage, run_info=self._run_info)

    def _recovery_service(self) -> TaskRecoveryService:
        return TaskRecoveryService(
            storage=self.storage,
            run_info=self._run_info,
            heartbeat=self._heartbeat,
            ensure_executor=self._ensure_executor,
            submit_task=self.submit,
            submit_recovery_task=self._submit_recovery_task,
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

    async def _submit_recovery_task(self, **kwargs: Any) -> Tuple[str, str]:
        executor_key = str(kwargs.pop("executor_key", "agent_stream"))
        if settings.TASK_BACKEND == "arq":
            kwargs.pop("executor", None)
            return await self.submit_arq(
                executor_key=executor_key,
                **kwargs,
            )
        kwargs.pop("trace_id", None)
        kwargs.pop("user_message_written", None)
        return await self.submit(**kwargs)

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

    async def _release_recovery_lock(self, lock_key: str, token: str) -> None:
        await self._recovery_service().release_recovery_lock(lock_key, token)

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
        enabled_skills: Optional[List[str]] = None,
        persona_system_prompt: Optional[str] = None,
        disabled_mcp_tools: Optional[List[str]] = None,
        session_name: Optional[str] = None,
        display_message: Optional[str] = None,
        recommendation_input: Optional[str] = None,
        team_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        active_goal: Optional[Dict[str, Any]] = None,
        session_metadata: Optional[Dict[str, Any]] = None,
        user_message_written: bool = False,
        write_user_message_immediately: bool = False,
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
        _ensure_agent_executable(agent_id)
        task_executor = self._ensure_executor()

        # 生成 run_id
        run_id = run_id or generate_run_id()
        trace_id = trace_id or ""

        async with self._lock:
            # 确保 session 记录存在
            await task_executor.ensure_session(
                session_id,
                agent_id,
                user_id,
                project_id=project_id,
                session_name=session_name,
                session_metadata=session_metadata,
            )

            # 更新 MongoDB session 状态（包含 current_run_id）
            await task_executor._update_session_status(
                session_id, TaskStatus.PENDING, run_id=run_id
            )

            if write_user_message_immediately and not user_message_written:
                trace_id = await self._persist_initial_user_message(
                    session_id=session_id,
                    agent_id=agent_id,
                    user_id=user_id,
                    run_id=run_id,
                    trace_id=trace_id,
                    message=message,
                    display_message=display_message,
                    attachments=attachments,
                )
                user_message_written = True

            self._run_info[run_id] = {
                "session_id": session_id,
                "trace_id": trace_id,
                "agent_id": agent_id,
                "user_id": user_id,
                "user_message_written": user_message_written,
            }

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
                    enabled_skills=enabled_skills,
                    persona_system_prompt=persona_system_prompt,
                    disabled_mcp_tools=disabled_mcp_tools,
                    display_message=display_message,
                    recommendation_input=recommendation_input,
                    team_id=team_id,
                    existing_trace_id=trace_id or None,
                    active_goal=active_goal,
                    user_message_written=user_message_written,
                )
            )
            self._tasks[run_id] = task

            # 添加完成回调
            task.add_done_callback(lambda t: self._on_task_done(run_id, t))

        logger.info(f"Task submitted: session={session_id}, run_id={run_id}, agent={agent_id}")
        return run_id, trace_id

    async def submit_arq(
        self,
        session_id: str,
        agent_id: str,
        message: str,
        user_id: str,
        executor_key: str,
        disabled_tools: Optional[List[str]] = None,
        agent_options: Optional[Dict[str, Any]] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        run_id: Optional[str] = None,
        project_id: Optional[str] = None,
        disabled_skills: Optional[List[str]] = None,
        enabled_skills: Optional[List[str]] = None,
        persona_system_prompt: Optional[str] = None,
        disabled_mcp_tools: Optional[List[str]] = None,
        session_name: Optional[str] = None,
        display_message: Optional[str] = None,
        recommendation_input: Optional[str] = None,
        trace_id: Optional[str] = None,
        user_message_written: bool = False,
        payload_store: Optional[TaskArqPayloadStore] = None,
        arq_pool: Any | None = None,
        team_id: Optional[str] = None,
        active_goal: Optional[Dict[str, Any]] = None,
        session_metadata: Optional[Dict[str, Any]] = None,
        write_user_message_immediately: bool = False,
    ) -> Tuple[str, str]:
        """Submit a task to arq after persisting serializable task context."""
        _ensure_agent_executable(agent_id)
        task_executor = self._ensure_executor()
        run_id = run_id or generate_run_id()
        trace_id = trace_id or ""
        payload_store = payload_store or TaskArqPayloadStore()

        async with self._lock:
            await task_executor.ensure_session(
                session_id,
                agent_id,
                user_id,
                project_id=project_id,
                session_name=session_name,
                session_metadata=session_metadata,
            )
            await task_executor._update_session_status(
                session_id,
                TaskStatus.QUEUED,
                run_id=run_id,
            )
            if write_user_message_immediately and not user_message_written:
                trace_id = await self._persist_initial_user_message(
                    session_id=session_id,
                    agent_id=agent_id,
                    user_id=user_id,
                    run_id=run_id,
                    trace_id=trace_id,
                    message=message,
                    display_message=display_message,
                    attachments=attachments,
                )
                user_message_written = True

            await payload_store.save(
                run_id,
                {
                    "session_id": session_id,
                    "run_id": run_id,
                    "trace_id": trace_id,
                    "agent_id": agent_id,
                    "message": message,
                    "display_message": display_message,
                    "user_id": user_id,
                    "executor_key": executor_key,
                    "disabled_tools": disabled_tools,
                    "agent_options": agent_options,
                    "attachments": attachments,
                    "disabled_skills": disabled_skills,
                    "enabled_skills": enabled_skills,
                    "persona_system_prompt": persona_system_prompt,
                    "disabled_mcp_tools": disabled_mcp_tools,
                    "user_message_written": user_message_written,
                    "team_id": team_id,
                    "active_goal": active_goal,
                    "recommendation_input": recommendation_input,
                },
            )

        if arq_pool is None:
            arq_pool = await self._get_arq_pool()
        await arq_pool.enqueue_job("run_agent_task", run_id, _job_id=run_id)

        logger.info(
            "Task submitted to arq: session=%s, run_id=%s, agent=%s", session_id, run_id, agent_id
        )
        return run_id, trace_id

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
            release_task = asyncio.create_task(self._release_concurrency(user_id, run_id))
            self._release_tasks.add(release_task)
            release_task.add_done_callback(self._on_release_task_done)

    def _on_release_task_done(self, task: asyncio.Task[None]) -> None:
        self._release_tasks.discard(task)
        if task.cancelled():
            return
        try:
            task.result()
        except Exception as e:
            logger.warning("Failed to release concurrency slot after task completion: %s", e)

    async def _drain_release_tasks(self) -> None:
        tasks = list(self._release_tasks)
        if not tasks:
            return
        await asyncio.gather(*tasks, return_exceptions=True)
        self._release_tasks.difference_update(tasks)

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
                    run_info = await self._build_run_info_from_session(
                        session,
                        session_id=session_id,
                        run_id=str(run_id),
                        user_id=user_id,
                    )
                    return await self.cancel_run(
                        str(run_id),
                        user_id=user_id,
                        run_info_override=run_info,
                    )
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

    async def _build_run_info_from_session(
        self,
        session: Any,
        *,
        session_id: str,
        run_id: str,
        user_id: Optional[str],
    ) -> Dict[str, Any]:
        metadata = getattr(session, "metadata", None) or {}
        trace_id = metadata.get("trace_id") or await self._lookup_trace_id_for_run(run_id)
        run_info: Dict[str, Any] = {
            "session_id": session_id,
            "trace_id": trace_id or "",
            "agent_id": metadata.get("agent_id") or getattr(session, "agent_id", None),
            "user_id": user_id or getattr(session, "user_id", None),
        }
        existing = self._run_info.get(run_id)
        if existing:
            run_info.update({key: value for key, value in existing.items() if value is not None})
        self._run_info.setdefault(run_id, run_info)
        return run_info

    async def _lookup_trace_id_for_run(self, run_id: str) -> Optional[str]:
        try:
            from src.infra.session.trace_storage import get_trace_storage

            trace_storage = get_trace_storage()
            cursor = (
                trace_storage.collection.find({"run_id": run_id}, {"trace_id": 1, "_id": 0})
                .sort("started_at", -1)
                .limit(1)
            )
            traces = await cursor.to_list(length=1)
            if traces:
                trace_id = traces[0].get("trace_id")
                return str(trace_id) if trace_id else None
        except Exception as e:
            logger.warning("Failed to lookup trace_id for run %s: %s", run_id, e)
        return None

    async def resume_session(
        self,
        session_id: str,
        reason: str = "manual_resume",
    ) -> Dict[str, Any]:
        return await self._recovery_service().resume_session(session_id, reason)

    async def cancel_run(
        self,
        run_id: str,
        publish: bool = True,
        user_id: Optional[str] = None,
        run_info_override: Optional[Dict[str, Any]] = None,
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
        run_info = run_info_override or self._run_info.get(run_id)

        result = await self._cancellation.cancel_run(
            run_id=run_id,
            publish=publish,
            user_id=user_id,
            run_info=run_info,
        )

        # 更新 session 状态为 cancelled
        if result["success"] and run_info:
            session_id = run_info.get("session_id")
            if session_id:
                executor = self._ensure_executor()
                await executor._update_session_status(
                    session_id, TaskStatus.CANCELLED, "Task cancelled", run_id=run_id
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
            shutdown_items = list(self._tasks.items())

            async def _shutdown_run(run_id: str, task: asyncio.Task) -> None:
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

            async def _await_cancelled_run(run_id: str, task: asyncio.Task) -> None:
                if task.done():
                    return
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.warning("Task raised while shutting down: run_id=%s error=%s", run_id, e)

            shutdown_factories: list[Callable[[], Awaitable[None]]] = []
            for run_id, task in shutdown_items:

                async def _shutdown_current(
                    run_id: str = run_id,
                    task: asyncio.Task = task,
                ) -> None:
                    await _shutdown_run(run_id, task)

                shutdown_factories.append(_shutdown_current)

            await _gather_limited(shutdown_factories)

            await_factories: list[Callable[[], Awaitable[None]]] = []
            for run_id, task in shutdown_items:

                async def _await_current(
                    run_id: str = run_id,
                    task: asyncio.Task = task,
                ) -> None:
                    await _await_cancelled_run(run_id, task)

                await_factories.append(_await_current)

            await _gather_limited(await_factories)

            self._tasks.clear()
            self._run_info.clear()
            self._pending_tasks.clear()

        await self._drain_release_tasks()
        await self._close_arq_pool()
        global _task_manager
        if _task_manager is self:
            _task_manager = None
        logger.info("Task manager shutdown complete")


# Singleton instance
_task_manager: Optional[BackgroundTaskManager] = None


def get_task_manager() -> BackgroundTaskManager:
    """获取 TaskManager 单例"""
    global _task_manager
    if _task_manager is None:
        _task_manager = BackgroundTaskManager()
    return _task_manager
