from __future__ import annotations

import asyncio
import inspect
import uuid
from typing import Any, Awaitable, Callable

from src.infra.logging import get_logger
from src.infra.session.trace_storage import get_trace_storage
from src.infra.storage.redis import get_redis_client
from src.infra.user.storage import UserStorage
from src.infra.utils.datetime import utc_now_iso
from src.kernel.config import settings
from src.kernel.errors import ErrorCode
from src.kernel.schemas.session import SessionUpdate

from .concurrency import ConcurrencyResult, get_concurrency_limiter, get_registered_executor
from .recovery_texts import build_recovery_message, normalize_recovery_language
from .state_machine import TaskStateMachine
from .status import TaskStatus

logger = get_logger(__name__)

RECOVERY_LOCK_PREFIX = "task:recovery:"
RECOVERY_LOCK_TTL_SECONDS = 300
# 同一 run 的无缝恢复提交次数上限：超限视为毒消息，落终态 FAILED 防止无限重跑。
MAX_SEAMLESS_RESUME_ATTEMPTS = 3


def _get_enabled_skills_from_metadata(session_metadata: dict[str, Any]) -> list[str] | None:
    """Preserve [] as an explicit empty whitelist while treating missing/None as global."""
    if "enabled_skills" not in session_metadata:
        return None
    enabled_skills = session_metadata.get("enabled_skills")
    return enabled_skills if isinstance(enabled_skills, list) else None


async def _lookup_trace_id_for_run(run_id: str) -> str | None:
    """按 run_id 查最新 trace，无缝续跑复用它继续追加事件。"""
    try:
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


def _registered_agent_ids() -> set[str]:
    from src.agents import discover_agents
    from src.agents.core import base as agent_base

    if not agent_base._AGENT_REGISTRY:
        discover_agents()
    return set(agent_base._AGENT_REGISTRY)


def _resolve_recovery_agent_id(session_metadata: dict[str, Any], session: Any) -> str:
    candidate = str(
        session_metadata.get("agent_id") or getattr(session, "agent_id", "") or ""
    ).strip()
    registered_ids = _registered_agent_ids()
    if candidate in registered_ids:
        return candidate

    fallback_candidates = [
        str(getattr(settings, "DEFAULT_AGENT", "") or "").strip(),
        "fast",
        "search",
        "team",
        *sorted(registered_ids),
    ]
    for fallback in fallback_candidates:
        if fallback and fallback in registered_ids:
            if candidate:
                logger.warning(
                    "Recovery agent '%s' is not registered; using '%s' instead",
                    candidate,
                    fallback,
                )
            return fallback

    return candidate or str(getattr(settings, "DEFAULT_AGENT", "") or "search")


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
        submit_arq_task: Callable[..., Awaitable[tuple[str, str]]] | None = None,
    ) -> None:
        self._storage = storage
        self._run_info = run_info
        self._heartbeat = heartbeat
        self._ensure_executor = ensure_executor
        self._submit_task = submit_task
        self._submit_arq_task = submit_arq_task or submit_task
        self._mark_run_failed = mark_run_failed
        self._state_machine = TaskStateMachine()

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
                trace_id = traces[0]["trace_id"]
                # 终态只写 metadata 不写事件时，前端渲染不到失败原因；
                # 与 executor 失败路径一致，先补一条 error 事件再终结 trace。
                try:
                    from src.infra.session.dual_writer import get_dual_writer

                    dual_writer = get_dual_writer()
                    await dual_writer.write_event(
                        session_id=session.id,
                        event_type="error",
                        data={
                            "error": reason,
                            "code": ErrorCode.TASK_SERVER_RESTART.code,
                            "run_id": run_id,
                        },
                        trace_id=trace_id,
                        run_id=run_id,
                    )
                    await dual_writer.flush_mongo_buffer()
                except Exception as event_error:
                    logger.warning(
                        "Failed to persist interruption error event for run %s: %s",
                        run_id,
                        event_error,
                    )
                await trace_storage.complete_trace(
                    trace_id,
                    status="error",
                    metadata={"error": reason, "error_code": "server_restart"},
                )
        except Exception as e:
            logger.warning("Failed to mark trace failed for run %s: %s", run_id, e)

    async def _strip_terminal_stream_events(self, session_id: str, run_id: str) -> int:
        """删除 Redis Stream 中残留的终态事件，恢复后 SSE 重放才不会提前断开。

        SSE 读循环遇 error/done/complete 即断流；旧关停路径或跨版本升级可能已经
        写入了终态事件，同 run 续跑前必须清掉，非终态事件（半截输出）一律保留。
        """
        try:
            from src.infra.session.dual_writer import get_dual_writer

            dual_writer = get_dual_writer()
            stream_key = dual_writer._stream_key(session_id, run_id)
            terminal_types = {"error", "done", "complete"}
            removed = 0
            entries = await dual_writer.redis.xrange(stream_key, min="-", max="+")
            for entry_id, fields in entries:
                if fields.get("event_type") in terminal_types:
                    await dual_writer.redis.xdel(stream_key, entry_id)
                    removed += 1
            if removed:
                logger.info(
                    "Stripped %d terminal stream events before seamless resume: "
                    "session=%s, run_id=%s",
                    removed,
                    session_id,
                    run_id,
                )
            return removed
        except Exception as e:
            logger.warning(
                "Failed to strip terminal stream events (session=%s run=%s): %s",
                session_id,
                run_id,
                e,
            )
            return 0

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

    async def submit_seamless_resume(
        self,
        session: Any,
        source_run_id: str,
        trace_id: str | None,
        reason: str,
    ) -> dict[str, Any]:
        """以原 run_id/trace_id 提交无缝续跑（模板：submit_hitl_resume_run）。

        恢复指令只面向模型（作为新 HumanMessage 进入 checkpoint），不写
        user:message UI 事件；executor 端 interrupted_resume=True 会先发
        run:resumed 标记事件，前端据此清空原气泡后续接新生成的内容。
        """
        session_metadata = getattr(session, "metadata", None) or {}
        executor_key = str(session_metadata.get("executor_key") or "agent_stream")
        executor_fn = get_registered_executor(executor_key)
        if executor_fn is None and executor_key == "agent_stream":
            from importlib import import_module

            import_module("src.api.routes.chat")
            executor_fn = get_registered_executor(executor_key)
        if executor_fn is None:
            return {
                "success": False,
                "run_id": None,
                "resumed_from_run_id": source_run_id,
                "message": f"恢复失败：未找到执行器 {executor_key}",
            }

        language = await self.get_preferred_language(session.user_id, session)
        hidden_instruction = build_recovery_message(reason, language)
        agent_id = _resolve_recovery_agent_id(session_metadata, session)
        common_kwargs: dict[str, Any] = {
            "disabled_tools": session_metadata.get("disabled_tools") or None,
            "agent_options": session_metadata.get("agent_options") or None,
            "disabled_skills": session_metadata.get("disabled_skills") or None,
            "enabled_skills": _get_enabled_skills_from_metadata(session_metadata),
            "persona_system_prompt": (
                (session_metadata.get("persona_snapshot") or {}).get("system_prompt")
                if isinstance(session_metadata.get("persona_snapshot"), dict)
                else None
            ),
            "disabled_mcp_tools": session_metadata.get("disabled_mcp_tools") or None,
            "project_id": session_metadata.get("project_id"),
            "session_name": getattr(session, "name", None),
            "user_message_written": True,
            "run_id": source_run_id,
            "trace_id": trace_id or None,
            "interrupted_resume": True,
            "team_id": session_metadata.get("team_id"),
            "recommendation_input": hidden_instruction,
            "auto_mode": bool(session_metadata.get("auto_mode", False)),
        }

        if getattr(settings, "TASK_BACKEND", "local") == "arq":
            # arq：新 dispatch_id（旧 job 可能仍留档），run_id 沿用原值；
            # 并发槽由 worker 侧（run_agent_task）获取。
            dispatch_id = f"resume:{source_run_id}:{uuid.uuid4().hex}"
            run_id, _ = await self._submit_arq_task(
                session_id=session.id,
                agent_id=agent_id,
                message=hidden_instruction,
                user_id=str(session.user_id),
                executor_key=executor_key,
                dispatch_id=dispatch_id,
                initial_status=TaskStatus.PENDING,
                **common_kwargs,
            )
        else:
            limiter = get_concurrency_limiter()
            if not await limiter.try_acquire_run_slot(str(session.user_id), source_run_id):
                return {
                    "success": False,
                    "run_id": None,
                    "resumed_from_run_id": source_run_id,
                    "message": "当前并发任务已满，稍后将自动重试恢复",
                }
            try:
                run_id, _ = await self._submit_task(
                    session.id,
                    agent_id,
                    hidden_instruction,
                    str(session.user_id),
                    executor_fn,
                    **common_kwargs,
                )
            except Exception:
                await limiter.release(str(session.user_id), source_run_id, dequeue=False)
                raise

        logger.info(
            "Seamless resume submitted: session=%s run_id=%s trace_id=%s reason=%s",
            session.id,
            run_id,
            trace_id,
            reason,
        )
        return {
            "success": True,
            "run_id": run_id,
            "resumed_from_run_id": source_run_id,
            "seamless": True,
            "message": "任务已在原对话中恢复",
        }

    async def _restore_recoverable_failure(
        self,
        session_id: str,
        run_id: str,
        error_message: str,
    ) -> None:
        """Restore a failed run to a recoverable failed state after recovery submission fails."""
        await self._storage.update(
            session_id,
            SessionUpdate(
                metadata=self._state_machine.build_metadata(
                    TaskStatus.FAILED,
                    run_id=run_id,
                    error=error_message,
                    error_code="server_restart",
                    recoverable=True,
                )
            ),
        )

    async def resume_interrupted_run(
        self,
        session: Any,
        source_run_id: str,
        reason: str,
    ) -> dict[str, Any]:
        """Resume an interrupted run in-place (same run_id/trace, seamless to the user)."""
        if not source_run_id:
            return {
                "success": False,
                "run_id": None,
                "resumed_from_run_id": None,
                "message": "没有可恢复的任务",
            }

        redis_client = get_redis_client()
        lock_key = f"{RECOVERY_LOCK_PREFIX}{session.id}:{source_run_id}"
        lock_token = uuid.uuid4().hex
        acquired = await redis_client.set(
            lock_key,
            lock_token,
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
                await self.release_recovery_lock(lock_key, lock_token)
                return {
                    "success": False,
                    "run_id": None,
                    "resumed_from_run_id": source_run_id,
                    "message": "该任务已由其他恢复流程接管",
                }

            attempts = int(session_metadata.get("resume_attempts") or 0)
            if attempts >= MAX_SEAMLESS_RESUME_ATTEMPTS:
                # 毒消息防护：同 run 反复中断说明重跑本身在触发崩溃，
                # 终态失败（写 error 事件 + trace 终结），扫描器不再接管。
                await self._mark_run_failed(
                    source_run_id,
                    f"Resume attempts exhausted ({attempts})",
                    session,
                )
                return {
                    "success": False,
                    "run_id": None,
                    "resumed_from_run_id": source_run_id,
                    "message": "恢复次数已达上限，任务已终止",
                }

            trace_id = await _lookup_trace_id_for_run(source_run_id)
            if trace_id:
                await get_trace_storage().reopen_interrupted_trace(trace_id)
            await self._strip_terminal_stream_events(session.id, source_run_id)

            await self._storage.update(
                session.id,
                SessionUpdate(
                    metadata=self._state_machine.build_metadata(
                        TaskStatus.RECOVERING,
                        run_id=source_run_id,
                    )
                ),
            )
            recovery_result = await self.submit_seamless_resume(
                session, source_run_id, trace_id, reason
            )
            if not recovery_result.get("success"):
                await self._restore_recoverable_failure(
                    session.id,
                    source_run_id,
                    recovery_result.get("message") or "恢复任务失败",
                )
                # 提交失败释放锁，让下一轮扫描/手动重试可以立即接手
                await self.release_recovery_lock(lock_key, lock_token)
                return recovery_result

            await self._storage.update(
                session.id,
                SessionUpdate(
                    metadata={
                        "resume_attempts": attempts + 1,
                        "recovery_reason": reason,
                        "recovery_requested_at": utc_now_iso(),
                        "task_recoverable": False,
                        "task_error_code": None,
                    }
                ),
            )
            return recovery_result
        except asyncio.CancelledError:
            await self.release_recovery_lock(lock_key, lock_token)
            raise
        except Exception as e:
            await self.release_recovery_lock(lock_key, lock_token)
            await self._restore_recoverable_failure(
                session.id,
                source_run_id,
                f"恢复任务失败: {e}",
            )
            logger.error("Failed to resume interrupted run %s: %s", source_run_id, e)
            return {
                "success": False,
                "run_id": None,
                "resumed_from_run_id": source_run_id,
                "message": f"恢复任务失败: {e}",
            }

    async def release_recovery_lock(self, lock_key: str, token: str) -> None:
        """Release a distributed recovery lock when immediate retry is safe."""
        try:
            lua_script = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                return redis.call("del", KEYS[1])
            else
                return 0
            end
            """
            result = get_redis_client().eval(lua_script, 1, lock_key, token)
            if inspect.isawaitable(result):
                await result
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

        if task_status == TaskStatus.WAITING_HUMAN.value:
            return {
                "success": False,
                "run_id": None,
                "resumed_from_run_id": source_run_id,
                "message": "任务正在等待用户输入，请先响应审批请求",
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
