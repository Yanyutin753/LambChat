# src/infra/task/manager.py
"""
Background Task Manager - 后台任务管理器

支持按 run_id 管理任务状态，实现多轮对话隔离。
支持分布式取消任务。
"""

import asyncio
import json
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, Tuple

from src.infra.logging import get_logger
from src.infra.session.storage import SessionStorage
from src.infra.session.trace_storage import get_trace_storage
from src.infra.storage.redis import get_redis_client
from src.infra.user.storage import UserStorage
from src.infra.writer.present import Presenter, PresenterConfig
from src.kernel.schemas.session import SessionUpdate

from .cancellation import TaskCancellation
from .concurrency import ConcurrencyResult, get_concurrency_limiter, get_registered_executor
from .exceptions import TaskInterruptedError
from .executor import TaskExecutor
from .heartbeat import TaskHeartbeat
from .pubsub import TaskPubSub
from .recovery_texts import build_recovery_message, normalize_recovery_language
from .status import TaskStatus

# 重导出供外部使用
__all__ = [
    "BackgroundTaskManager",
    "TaskStatus",
    "TaskInterruptedError",
    "TaskCancellation",
]

logger = get_logger(__name__)

RECOVERY_LOCK_PREFIX = "task:recovery:"
RECOVERY_LOCK_TTL_SECONDS = 300


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

    async def _get_preferred_language(self, user_id: Optional[str], session: Any) -> str:
        """Resolve the preferred language for recovery messages."""
        if user_id:
            try:
                user = await UserStorage().get_by_id(user_id)
                metadata = getattr(user, "metadata", None) or {}
                language = metadata.get("language")
                if language:
                    return normalize_recovery_language(str(language))
            except Exception as e:
                logger.warning("Failed to load user language for recovery: %s", e)

        session_metadata = getattr(session, "metadata", None) or {}
        return normalize_recovery_language(session_metadata.get("language"))

    async def _get_user_roles(self, user_id: Optional[str]) -> list[str]:
        """Load the user's current roles for distributed concurrency decisions."""
        if not user_id:
            return []
        try:
            user = await UserStorage().get_by_id(user_id)
            return list(getattr(user, "roles", None) or [])
        except Exception as e:
            logger.warning("Failed to load user roles for recovery: %s", e)
            return []

    async def _mark_run_failed(self, run_id: str, reason: str, session: Any) -> None:
        """Mark a stale run and its trace as failed before recovery."""
        executor = self._ensure_executor()
        await executor._update_session_status(
            session.id,
            TaskStatus.FAILED,
            reason,
            run_id=run_id,
        )
        await self.storage.update(
            session.id,
            SessionUpdate(
                metadata={
                    "task_recoverable": True,
                    "task_error_code": "server_restart",
                    "interrupted_run_id": run_id,
                }
            ),
        )
        try:
            trace_storage = get_trace_storage()
            cursor = (
                trace_storage.collection.find({"run_id": run_id}, {"trace_id": 1, "_id": 0})
                .sort("started_at", -1)
                .limit(1)
            )
            traces = await cursor.to_list(length=1)
            if traces:
                await trace_storage.complete_trace(
                    traces[0]["trace_id"],
                    status="error",
                    metadata={"error": reason, "error_code": "server_restart"},
                )
        except Exception as e:
            logger.warning("Failed to mark trace failed for run %s: %s", run_id, e)

    async def _mark_run_recoverable_failure(
        self,
        session_id: str,
        run_id: str,
        error_message: str,
        error_code: str = "server_restart",
    ) -> None:
        """Persist a failed task state that is eligible for automatic recovery."""
        executor = self._ensure_executor()
        await executor._update_session_status(
            session_id,
            TaskStatus.FAILED,
            error_message,
            run_id=run_id,
        )
        await self.storage.update(
            session_id,
            SessionUpdate(
                metadata={
                    "task_recoverable": True,
                    "task_error_code": error_code,
                    "interrupted_run_id": run_id,
                }
            ),
        )

    async def _submit_recovery_run(
        self,
        session: Any,
        source_run_id: str,
        reason: str,
    ) -> Dict[str, Any]:
        """Submit a new run that resumes the session from the latest checkpoint."""
        session_metadata = getattr(session, "metadata", None) or {}
        executor_key = session_metadata.get("executor_key") or "agent_stream"
        executor_fn = get_registered_executor(str(executor_key))
        if executor_fn is None:
            return {
                "success": False,
                "run_id": None,
                "resumed_from_run_id": source_run_id,
                "message": f"恢复失败：未找到执行器 {executor_key}",
            }

        language = await self._get_preferred_language(session.user_id, session)
        recovery_message = build_recovery_message(reason, language)
        agent_id = str(session_metadata.get("agent_id") or getattr(session, "agent_id", "search"))
        new_run_id = _generate_run_id()
        recovery_trace = Presenter(
            PresenterConfig(
                session_id=session.id,
                agent_id=agent_id,
                user_id=session.user_id,
                run_id=new_run_id,
                enable_storage=False,
            )
        )
        recovery_trace_id = recovery_trace.trace_id
        user_roles = await self._get_user_roles(session.user_id)
        limiter = get_concurrency_limiter()
        task_context = {
            "executor_key": executor_key,
            "agent_id": agent_id,
            "message": recovery_message,
            "disabled_tools": session_metadata.get("disabled_tools") or None,
            "agent_options": session_metadata.get("agent_options") or None,
            "attachments": None,
            "trace_id": recovery_trace_id,
            "user_message_written": True,
            "disabled_skills": session_metadata.get("disabled_skills") or None,
            "disabled_mcp_tools": session_metadata.get("disabled_mcp_tools") or None,
        }

        concurrency_result = await limiter.claim_recovery_slot(
            user_id=session.user_id,
            roles=user_roles,
            old_run_id=source_run_id,
            new_run_id=new_run_id,
            session_id=session.id,
            task_context=task_context,
        )

        if concurrency_result.result == ConcurrencyResult.REJECTED_QUEUE:
            return {
                "success": False,
                "run_id": None,
                "resumed_from_run_id": source_run_id,
                "message": "恢复失败：当前恢复队列已满",
            }

        if concurrency_result.result == ConcurrencyResult.STARTED:
            try:
                await self.submit(
                    session_id=session.id,
                    agent_id=agent_id,
                    message=recovery_message,
                    user_id=session.user_id,
                    executor=executor_fn,
                    disabled_tools=session_metadata.get("disabled_tools") or None,
                    agent_options=session_metadata.get("agent_options") or None,
                    attachments=None,
                    run_id=new_run_id,
                    project_id=session_metadata.get("project_id"),
                    disabled_skills=session_metadata.get("disabled_skills") or None,
                    disabled_mcp_tools=session_metadata.get("disabled_mcp_tools") or None,
                    session_name=getattr(session, "name", None),
                )
            except Exception:
                await limiter.release(session.user_id, new_run_id, dequeue=False)
                raise
        else:
            executor = self._ensure_executor()
            await executor.ensure_session(
                session.id,
                agent_id,
                session.user_id,
                project_id=session_metadata.get("project_id"),
                session_name=getattr(session, "name", None),
            )
            await executor._update_session_status(
                session.id,
                TaskStatus.PENDING,
                run_id=new_run_id,
            )
            trace_presenter = Presenter(
                PresenterConfig(
                    session_id=session.id,
                    agent_id=agent_id,
                    user_id=session.user_id,
                    run_id=new_run_id,
                    trace_id=recovery_trace_id,
                    enable_storage=True,
                )
            )
            await trace_presenter._ensure_trace()
            await trace_presenter.emit_user_message(recovery_message)
            self._run_info[new_run_id] = {
                "session_id": session.id,
                "agent_id": agent_id,
                "user_id": session.user_id,
                "trace_id": recovery_trace_id,
                "user_message_written": True,
            }

        await self.storage.update(
            session.id,
            SessionUpdate(
                metadata={
                    "current_run_id": new_run_id,
                    "agent_id": agent_id,
                    "executor_key": executor_key,
                    "agent_options": session_metadata.get("agent_options") or {},
                    "disabled_tools": session_metadata.get("disabled_tools") or [],
                    "disabled_skills": session_metadata.get("disabled_skills") or [],
                    "disabled_mcp_tools": session_metadata.get("disabled_mcp_tools") or [],
                    "language": language,
                    "project_id": session_metadata.get("project_id"),
                    "recovery_of_run_id": source_run_id,
                    "recovery_reason": reason,
                    "recovery_requested_at": datetime.now().isoformat(),
                    "task_recoverable": False,
                    "task_error_code": None,
                }
            ),
        )

        return {
            "success": True,
            "run_id": new_run_id,
            "resumed_from_run_id": source_run_id,
            "message": "任务恢复已开始"
            if concurrency_result.result == ConcurrencyResult.STARTED
            else "任务恢复已加入队列",
        }

    async def _resume_interrupted_run(
        self,
        session: Any,
        source_run_id: str,
        reason: str,
    ) -> Dict[str, Any]:
        """Resume an interrupted run in a distributed-safe way."""
        if not source_run_id:
            return {
                "success": False,
                "run_id": None,
                "resumed_from_run_id": None,
                "message": "没有可恢复的任务",
            }

        redis_client = get_redis_client()
        lock_key = f"{RECOVERY_LOCK_PREFIX}{session.id}:{source_run_id}"
        acquired = await redis_client.set(
            lock_key,
            datetime.now().isoformat(),
            ex=RECOVERY_LOCK_TTL_SECONDS,
            nx=True,
        )
        if not acquired:
            return {
                "success": False,
                "run_id": None,
                "resumed_from_run_id": source_run_id,
                "message": "恢复任务已在其他实例中启动",
            }

        try:
            session_metadata = getattr(session, "metadata", None) or {}
            current_run_id = session_metadata.get("current_run_id")
            if current_run_id and str(current_run_id) != str(source_run_id):
                await self._release_recovery_lock(lock_key)
                return {
                    "success": False,
                    "run_id": None,
                    "resumed_from_run_id": source_run_id,
                    "message": "该任务已由其他恢复流程接管",
                }

            await self._mark_run_failed(
                source_run_id,
                "Task interrupted (instance unavailable)",
                session,
            )
            return await self._submit_recovery_run(session, source_run_id, reason)
        except Exception as e:
            await self._release_recovery_lock(lock_key)
            logger.error("Failed to resume interrupted run %s: %s", source_run_id, e)
            return {
                "success": False,
                "run_id": None,
                "resumed_from_run_id": source_run_id,
                "message": f"恢复任务失败: {e}",
            }

    async def _load_session_record(self, raw_session: dict[str, Any]) -> Any | None:
        """Load a normalized session model from a raw MongoDB session document."""
        session_id = raw_session.get("session_id") or str(raw_session.get("_id"))
        session = await self.storage.get_by_session_id(session_id)
        if session is not None:
            return session
        return await self.storage.get_by_id(session_id)

    async def _release_recovery_lock(self, lock_key: str) -> None:
        """Release a distributed recovery lock when immediate retry is safe."""
        try:
            await get_redis_client().delete(lock_key)
        except Exception as e:
            logger.warning("Failed to release recovery lock %s: %s", lock_key, e)

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
        run_id = run_id or _generate_run_id()

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

    async def resume_session(
        self,
        session_id: str,
        reason: str = "manual_resume",
    ) -> Dict[str, Any]:
        """Resume the current interrupted run for a session."""
        session = await self.storage.get_by_session_id(session_id)
        if not session:
            return {
                "success": False,
                "run_id": None,
                "resumed_from_run_id": None,
                "message": "会话不存在",
            }

        session_metadata = session.metadata or {}
        source_run_id = session_metadata.get("current_run_id")
        task_status = session_metadata.get("task_status")
        if not source_run_id:
            return {
                "success": False,
                "run_id": None,
                "resumed_from_run_id": None,
                "message": "没有可恢复的任务",
            }

        if task_status == TaskStatus.COMPLETED.value:
            return {
                "success": False,
                "run_id": None,
                "resumed_from_run_id": source_run_id,
                "message": "当前任务已经完成，无需恢复",
            }

        if (
            session_metadata.get("task_recoverable") is False
            or session_metadata.get("task_error_code") == "cancelled"
        ):
            return {
                "success": False,
                "run_id": None,
                "resumed_from_run_id": source_run_id,
                "message": "该任务已被用户取消，不能恢复",
            }

        if await self._heartbeat.check_exists(str(source_run_id)):
            return {
                "success": False,
                "run_id": None,
                "resumed_from_run_id": source_run_id,
                "message": "任务仍在其他实例运行中",
            }

        return await self._resume_interrupted_run(session, str(source_run_id), reason)

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

        清理两类任务：
        1. task_status=RUNNING：心跳超时的任务（executor 崩溃）
        2. task_status=PENDING + 在 active set 中：心跳超时的任务
           （任务被分派后 executor 崩溃，但状态未更新为 RUNNING）
        心跳还在的任务说明其他实例正在运行，不应清理。
        """
        from .concurrency import get_concurrency_limiter

        limiter = get_concurrency_limiter()
        redis = limiter.redis

        try:
            # 清理 RUNNING 状态且心跳超时的任务
            cursor = self.storage.collection.find(
                {"metadata.task_status": TaskStatus.RUNNING.value}
            )
            running_sessions = await cursor.to_list(length=1000)

            cleaned_count = 0
            for session in running_sessions:
                session_model = await self._load_session_record(session)
                if session_model is None:
                    continue
                session_id = session_model.id
                run_id = session.get("metadata", {}).get("current_run_id")
                if not run_id:
                    continue

                # 检查心跳是否存在
                heartbeat_exists = await self._heartbeat.check_exists(run_id)

                if heartbeat_exists:
                    logger.debug(
                        f"Task still running on another instance: session={session_id}, run_id={run_id}"
                    )
                    continue

                # 心跳不存在，清理
                logger.warning(
                    f"Cleaning up stale RUNNING task (no heartbeat): session={session_id}, run_id={run_id}"
                )
                recovery_result = await self._resume_interrupted_run(
                    session=session_model,
                    source_run_id=run_id,
                    reason="server_restart",
                )
                if recovery_result.get("success"):
                    logger.info(
                        "Recovered stale RUNNING task: session=%s, old_run=%s, new_run=%s",
                        session_id,
                        run_id,
                        recovery_result.get("run_id"),
                    )
                else:
                    logger.warning(
                        "Failed to auto-recover stale RUNNING task %s: %s",
                        run_id,
                        recovery_result.get("message"),
                    )
                cleaned_count += 1

            # 清理 PENDING 状态但心跳超时的任务（被分派后 executor 崩溃，状态未更新）
            cursor = self.storage.collection.find(
                {"metadata.task_status": TaskStatus.PENDING.value}
            )
            pending_sessions = await cursor.to_list(length=1000)

            for session in pending_sessions:
                session_model = await self._load_session_record(session)
                if session_model is None:
                    continue
                session_id = session_model.id
                run_id = session.get("metadata", {}).get("current_run_id")
                user_id = session.get("user_id")

                if not run_id or not user_id:
                    continue

                # 检查是否在 active set 中
                active_key = f"chat:active:{user_id}"
                in_active = await redis.zscore(active_key, run_id) is not None
                if not in_active:
                    # 不在 active set 中，由 _replay_pending_queued_tasks 处理
                    continue

                # 在 active set 中，检查心跳是否超时
                heartbeat_exists = await self._heartbeat.check_exists(run_id)
                if heartbeat_exists:
                    # 有心跳，说明有 worker 在处理
                    logger.debug(
                        f"Pending task still in active set (running elsewhere): session={session_id}, run_id={run_id}"
                    )
                    continue

                # 心跳超时，清理
                logger.warning(
                    f"Cleaning up stale PENDING task (in active set, no heartbeat): "
                    f"session={session_id}, run_id={run_id}"
                )
                recovery_result = await self._resume_interrupted_run(
                    session=session_model,
                    source_run_id=run_id,
                    reason="server_restart",
                )
                if recovery_result.get("success"):
                    logger.info(
                        "Recovered stale PENDING task: session=%s, old_run=%s, new_run=%s",
                        session_id,
                        run_id,
                        recovery_result.get("run_id"),
                    )
                else:
                    logger.warning(
                        "Failed to auto-recover stale PENDING task %s: %s",
                        run_id,
                        recovery_result.get("message"),
                    )
                cleaned_count += 1

            # 清理 FAILED 但可恢复的任务（优雅关闭后重启）
            cursor = self.storage.collection.find(
                {
                    "metadata.task_status": TaskStatus.FAILED.value,
                    "metadata.task_recoverable": True,
                    "metadata.task_error_code": "server_restart",
                }
            )
            failed_recoverable_sessions = await cursor.to_list(length=1000)

            for session in failed_recoverable_sessions:
                session_model = await self._load_session_record(session)
                if session_model is None:
                    continue
                session_id = session_model.id
                run_id = session.get("metadata", {}).get("current_run_id")
                if not run_id:
                    continue

                heartbeat_exists = await self._heartbeat.check_exists(run_id)
                if heartbeat_exists:
                    logger.debug(
                        "Recoverable failed task still has heartbeat: session=%s, run_id=%s",
                        session_id,
                        run_id,
                    )
                    continue

                logger.warning(
                    "Recovering failed-but-recoverable task: session=%s, run_id=%s",
                    session_id,
                    run_id,
                )
                recovery_result = await self._resume_interrupted_run(
                    session=session_model,
                    source_run_id=run_id,
                    reason="server_restart",
                )
                if recovery_result.get("success"):
                    logger.info(
                        "Recovered failed task: session=%s, old_run=%s, new_run=%s",
                        session_id,
                        run_id,
                        recovery_result.get("run_id"),
                    )
                else:
                    logger.warning(
                        "Failed to auto-recover failed task %s: %s",
                        run_id,
                        recovery_result.get("message"),
                    )
                cleaned_count += 1

            if cleaned_count > 0:
                logger.info(f"Cleaned up {cleaned_count} stale tasks without heartbeat")

            # 重放 PENDING session 的排队任务（服务器重启后恢复）
            await self._replay_pending_queued_tasks()

            # 清理过期的排队条目
            await self._cleanup_stale_queues()
        except Exception as e:
            logger.error(f"Failed to cleanup stale tasks: {e}")

    async def _cleanup_stale_queues(self) -> None:
        """清理过期的排队条目（超过 QUEUE_TIMEOUT 的）"""
        try:
            from .concurrency import QUEUE_TIMEOUT, get_concurrency_limiter

            limiter = get_concurrency_limiter()
            redis = limiter.redis

            import time

            cursor = 0
            while True:
                cursor, keys = await redis.scan(cursor=cursor, match="chat:queue:*", count=100)
                for key in keys:
                    entries = await redis.lrange(key, 0, -1)
                    valid = []
                    expired = 0
                    for entry in entries:
                        data = json.loads(entry)
                        if time.time() - data.get("queued_at", 0) > QUEUE_TIMEOUT:
                            expired += 1
                        else:
                            valid.append(entry)
                    if expired:
                        await redis.delete(key)
                        if valid:
                            await redis.rpush(key, *valid)
                        logger.info(f"Cleaned {expired} expired queue entries from {key}")
                if cursor == 0:
                    break
        except Exception as e:
            logger.warning(f"Failed to cleanup stale queues: {e}")

    async def _replay_pending_queued_tasks(self) -> None:
        """
        服务器重启后重放 PENDING 状态的排队任务。

        排队任务在 Redis 队列中持久化，但进程内存（_run_info 等）在重启后丢失。
        对每个 PENDING session：
        - 队列条目仍在 → 触发 release() 释放并发槽，触发 _try_dequeue_next 重新分派
        - 队列条目已消失 + 无心跳 → 任务被遗弃，标记为 FAILED
        """
        try:
            from .concurrency import get_concurrency_limiter

            limiter = get_concurrency_limiter()
            redis = limiter.redis

            # 查找所有 task_status=pending 的 session
            cursor = self.storage.collection.find(
                {"metadata.task_status": TaskStatus.PENDING.value}
            )
            pending_sessions = await cursor.to_list(length=1000)

            replayed = 0
            abandoned = 0

            for session in pending_sessions:
                session_model = await self._load_session_record(session)
                if session_model is None:
                    continue
                session_id = session_model.id
                run_id = session.get("metadata", {}).get("current_run_id")
                user_id = session.get("user_id")

                if not run_id or not user_id:
                    continue

                # 检查 Redis 队列中是否还有这个任务的条目
                queue_key = f"chat:queue:{user_id}"
                entries = await redis.lrange(queue_key, 0, -1)
                queue_entry = None
                for entry in entries:
                    data = json.loads(entry)
                    if data.get("run_id") == run_id:
                        queue_entry = data
                        break

                if queue_entry:
                    # 队列条目存在，触发 release 释放并发槽 → 会触发 _try_dequeue_next
                    logger.info(
                        f"Replaying queued task on startup: session={session_id}, run_id={run_id}"
                    )
                    try:
                        await limiter.release(user_id, run_id)
                        replayed += 1
                    except Exception as e:
                        logger.warning(f"Failed to replay queued task {run_id}: {e}")
                else:
                    # 队列条目已消失：任务已被分派或被超时清理
                    # - in_active：cleanup_stale_tasks 已处理（心跳超时后标记 FAILED）
                    # - 有心跳：其他 worker 在处理，不动
                    # - 无心跳且不在 active：任务被遗弃，标记 FAILED
                    active_key = f"chat:active:{user_id}"
                    in_active = await redis.zscore(active_key, run_id) is not None
                    heartbeat_exists = await self._heartbeat.check_exists(run_id)

                    if in_active or heartbeat_exists:
                        # 任务正在被处理（in_active 或有心跳），cleanup_stale_tasks 会处理超时情况
                        logger.debug(
                            f"Pending task still active or running elsewhere: "
                            f"session={session_id}, run_id={run_id}"
                        )
                    else:
                        # 既不在 active set 也没有心跳 → 任务被遗弃
                        logger.warning(
                            f"Abandoned queued task (no queue entry, no active, no heartbeat): "
                            f"session={session_id}, run_id={run_id}"
                        )
                        recovery_result = await self._resume_interrupted_run(
                            session=session_model,
                            source_run_id=run_id,
                            reason="server_restart",
                        )
                        if recovery_result.get("success"):
                            logger.info(
                                "Recovered abandoned queued task: session=%s, old_run=%s, new_run=%s",
                                session_id,
                                run_id,
                                recovery_result.get("run_id"),
                            )
                        else:
                            executor = self._ensure_executor()
                            await executor._update_session_status(
                                session_id,
                                TaskStatus.FAILED,
                                "Task abandoned (server restarted while queued)",
                                run_id=run_id,
                            )
                            abandoned += 1

            if replayed > 0:
                logger.info(f"Replayed {replayed} queued tasks on startup")
            if abandoned > 0:
                logger.warning(f"Marked {abandoned} abandoned queued tasks as FAILED")
        except Exception as e:
            logger.error(f"Failed to replay pending queued tasks: {e}")

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
