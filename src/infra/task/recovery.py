from __future__ import annotations

from datetime import datetime
from typing import Any, Awaitable, Callable

from src.infra.logging import get_logger
from src.infra.session.trace_storage import get_trace_storage
from src.infra.storage.redis import get_redis_client
from src.infra.user.storage import UserStorage
from src.infra.writer.present import Presenter, PresenterConfig
from src.kernel.schemas.session import SessionUpdate

from .concurrency import ConcurrencyResult, get_concurrency_limiter, get_registered_executor
from .recovery_texts import build_recovery_message, normalize_recovery_language
from .run_ids import generate_run_id
from .status import TaskStatus

logger = get_logger(__name__)

RECOVERY_LOCK_PREFIX = "task:recovery:"
RECOVERY_LOCK_TTL_SECONDS = 300


class TaskRecoveryService:
    """Coordinates task recovery and session resume flows."""

    def __init__(
        self,
        *,
        storage: Any,
        run_info: dict[str, dict[str, Any]],
        heartbeat: Any,
        ensure_executor: Callable[[], Any],
        submit_task: Callable[..., Awaitable[tuple[str, str]]],
        mark_run_failed: Callable[[str, str, Any], Awaitable[None]],
    ) -> None:
        self._storage = storage
        self._run_info = run_info
        self._heartbeat = heartbeat
        self._ensure_executor = ensure_executor
        self._submit_task = submit_task
        self._mark_run_failed = mark_run_failed

    async def get_preferred_language(self, user_id: str | None, session: Any) -> str:
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

    async def get_user_roles(self, user_id: str | None) -> list[str]:
        """Load current user roles for distributed concurrency decisions."""
        if not user_id:
            return []
        try:
            user = await UserStorage().get_by_id(user_id)
            return list(getattr(user, "roles", None) or [])
        except Exception as e:
            logger.warning("Failed to load user roles for recovery: %s", e)
            return []

    async def mark_run_failed(self, run_id: str, reason: str, session: Any) -> None:
        """Mark a stale run and its trace as failed before recovery."""
        executor = self._ensure_executor()
        await executor._update_session_status(
            session.id,
            TaskStatus.FAILED,
            reason,
            run_id=run_id,
        )
        await self._storage.update(
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

    async def mark_run_recoverable_failure(
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
        await self._storage.update(
            session_id,
            SessionUpdate(
                metadata={
                    "task_recoverable": True,
                    "task_error_code": error_code,
                    "interrupted_run_id": run_id,
                }
            ),
        )

    async def submit_recovery_run(
        self,
        session: Any,
        source_run_id: str,
        reason: str,
    ) -> dict[str, Any]:
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

        language = await self.get_preferred_language(session.user_id, session)
        recovery_message = build_recovery_message(reason, language)
        agent_id = str(session_metadata.get("agent_id") or getattr(session, "agent_id", "search"))
        new_run_id = generate_run_id()
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
        user_roles = await self.get_user_roles(session.user_id)
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
                await self._submit_task(
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

        await self._storage.update(
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

    async def resume_interrupted_run(
        self,
        session: Any,
        source_run_id: str,
        reason: str,
    ) -> dict[str, Any]:
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
                await self.release_recovery_lock(lock_key)
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
            return await self.submit_recovery_run(session, source_run_id, reason)
        except Exception as e:
            await self.release_recovery_lock(lock_key)
            logger.error("Failed to resume interrupted run %s: %s", source_run_id, e)
            return {
                "success": False,
                "run_id": None,
                "resumed_from_run_id": source_run_id,
                "message": f"恢复任务失败: {e}",
            }

    async def release_recovery_lock(self, lock_key: str) -> None:
        """Release a distributed recovery lock when immediate retry is safe."""
        try:
            await get_redis_client().delete(lock_key)
        except Exception as e:
            logger.warning("Failed to release recovery lock %s: %s", lock_key, e)

    async def resume_session(
        self,
        session_id: str,
        reason: str = "manual_resume",
    ) -> dict[str, Any]:
        """Resume the current interrupted run for a session."""
        session = await self._storage.get_by_session_id(session_id)
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

        return await self.resume_interrupted_run(session, str(source_run_id), reason)
