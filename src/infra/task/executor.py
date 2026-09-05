# src/infra/task/executor.py
"""
Background Task Manager - Task Executor

Handles task execution including session management, presenter setup,
error handling, and status updates.
"""

import asyncio
from typing import Any, Callable, Dict, List, Optional

from src.agents.core import resolve_agent_name
from src.infra.logging import get_logger
from src.infra.session.dual_writer import get_dual_writer
from src.infra.session.favorites import is_session_favorite
from src.infra.session.storage import SessionStorage
from src.infra.utils.datetime import utc_now_iso
from src.infra.writer.presenter_events import derive_user_message_run_modes
from src.kernel.config import settings
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.session import SessionCreate, SessionUpdate

from .cancellation import TaskCancellation
from .exceptions import TaskInterruptedError
from .heartbeat import TaskHeartbeat
from .stall_watchdog import aiter_with_stall_timeout
from .state_machine import TaskStateMachine
from .status import TaskStatus

logger = get_logger(__name__)
_TERMINAL_STREAM_TTL_SECONDS = 60
_DEFAULT_RUN_STALL_TIMEOUT_SECONDS = 3600


def _run_stall_timeout_seconds() -> float:
    """Watchdog deadline between executor events; 0/negative disables it."""
    value = getattr(settings, "TASK_RUN_STALL_TIMEOUT", _DEFAULT_RUN_STALL_TIMEOUT_SECONDS)
    try:
        return float(value)
    except (TypeError, ValueError):
        return _DEFAULT_RUN_STALL_TIMEOUT_SECONDS


def should_schedule_recommend_questions() -> bool:
    """Return whether this run should generate follow-up question suggestions."""
    return bool(getattr(settings, "ENABLE_RECOMMEND_QUESTIONS", True))


def _is_main_agent_text_event(event: Any) -> bool:
    """主代理（depth=0）的非空 message:chunk —— run 有用户可见正文的判据。

    子代理 chunk 带 data.depth>0，纯空白不算正文；图片/文件类结果没有独立
    事件类型（随 tool:result 与最终文本一起出），因此只认 message:chunk。
    """
    if not isinstance(event, dict) or event.get("event") != "message:chunk":
        return False
    data = event.get("data")
    if not isinstance(data, dict):
        return False
    depth = data.get("depth", 0)
    if isinstance(depth, int) and depth > 0:
        return False
    content = data.get("content")
    return isinstance(content, str) and bool(content.strip())


class TaskExecutor:
    """
    任务执行器类

    处理任务的执行、状态更新、错误处理和通知发送。
    """

    def __init__(
        self,
        storage: SessionStorage,
        run_info: Dict[str, Dict[str, str]],
        heartbeat_manager: "TaskHeartbeat",
    ):
        """
        初始化任务执行器

        Args:
            storage: Session 存储实例
            run_info: 运行信息字典 run_id -> {session_id, trace_id, agent_id}
            heartbeat_manager: 心跳管理器实例
        """
        self._storage = storage
        self._run_info = run_info
        self._heartbeat = heartbeat_manager
        self._state_machine = TaskStateMachine()

    async def run_task(
        self,
        session_id: str,
        run_id: str,
        agent_id: str,
        message: str,
        user_id: str,
        executor: Callable,
        disabled_tools: Optional[List[str]] = None,
        agent_options: Optional[Dict[str, Any]] = None,
        attachments: Optional[List[Dict[str, Any]]] = None,
        existing_trace_id: Optional[str] = None,
        user_message_written: bool = False,
        disabled_skills: Optional[List[str]] = None,
        enabled_skills: Optional[List[str]] = None,
        persona_system_prompt: Optional[str] = None,
        disabled_mcp_tools: Optional[List[str]] = None,
        display_message: Optional[str] = None,
        recommendation_input: Optional[str] = None,
        team_id: Optional[str] = None,
        active_goal: Optional[Dict[str, Any]] = None,
        auto_mode: bool = False,
        attachment_references_claimed: bool = False,
        hitl_resume: Optional[Dict[str, Any]] = None,
        interrupted_resume: bool = False,
    ) -> bool | None:
        """执行任务"""
        from src.infra.writer.present import Presenter, PresenterConfig

        presenter = None
        dual_writer = None
        self._user_id = user_id

        try:
            await self._update_session_status(session_id, TaskStatus.STARTING, run_id=run_id)

            # queued path 已经同时创建 trace 和写入 user:message 时，可安全复用。
            already_written = user_message_written or self._run_info.get(run_id, {}).get(
                "user_message_written", False
            )
            trace_precreated = bool(existing_trace_id and already_written)

            # 创建 Presenter 并传递给 agent
            agent_options = agent_options or {}
            presenter = Presenter(
                PresenterConfig(
                    session_id=session_id,
                    agent_id=agent_id,
                    agent_name=resolve_agent_name(agent_id),
                    user_id=user_id,
                    run_id=run_id,  # 传递 run_id
                    trace_id=existing_trace_id,  # reuse trace from queued path
                    enable_storage=True,
                    model_id=agent_options.get("model_id"),
                    model=agent_options.get("model"),
                )
            )

            # 设置请求上下文（供工具使用，如 ask_human）
            from src.infra.logging.context import TraceContext

            logger.info(
                f"[TaskManager] Setting TraceContext: session_id={session_id}, run_id={run_id}"
            )
            current_trace = TraceContext.get()
            TraceContext.set(
                trace_id=presenter.trace_id,
                span_id=current_trace.span_id,
                parent_span_id=current_trace.parent_span_id,
            )
            TraceContext.set_request_context(
                session_id=session_id,
                run_id=run_id,
                user_id=user_id,
                trace_id=presenter.trace_id,
            )

            if trace_precreated:
                presenter._trace_created = True
            else:
                await presenter._ensure_trace()

            # 心跳与 RUNNING 状态彼此独立；并发完成后才进入 agent stream。
            await asyncio.gather(
                self._heartbeat.start(run_id, user_id=user_id),
                self._update_session_status(session_id, TaskStatus.RUNNING, run_id=run_id),
            )

            # 立即发送 user:message 事件（任务开始时固定发送）
            if message and not already_written:
                await presenter.emit_user_message(
                    display_message or message,
                    attachments=attachments,
                    enabled_skills=enabled_skills,
                    attachment_references_claimed=attachment_references_claimed,
                    run_modes=derive_user_message_run_modes(auto_mode, active_goal),
                )

            # 保存 trace_id 和 agent_id 到 run_info，保留已有的 flag
            run_info_entry: dict[str, Any] = {
                "session_id": session_id,
                "trace_id": presenter.trace_id,
                "agent_id": agent_id,
                "user_id": user_id,
            }
            if already_written:
                run_info_entry["user_message_written"] = True
            if attachment_references_claimed:
                run_info_entry["attachment_references_claimed"] = True
            self._run_info[run_id] = run_info_entry

            dual_writer = get_dual_writer()

            # 系统中断后的同 run 无缝续跑：先发 run:resumed 标记事件，前端据此
            # 清空原气泡的半截内容再接收重新生成的输出（不写新的 user:message）。
            if interrupted_resume:
                await presenter.save_event(
                    {
                        "event": "run:resumed",
                        "data": {
                            "run_id": run_id,
                            "trace_id": presenter.trace_id,
                            "timestamp": utc_now_iso(),
                        },
                    }
                )

            if hitl_resume is not None:
                resolved = hitl_resume.get("approval_resolved")
                if isinstance(resolved, dict):
                    await presenter.save_event({"event": "approval_resolved", "data": resolved})
                await presenter.save_event(
                    {
                        "event": "human_resume_started",
                        "data": {
                            "approval_id": hitl_resume.get("approval_id"),
                            "session_id": session_id,
                            "run_id": run_id,
                            "trace_id": presenter.trace_id,
                            "timestamp": utc_now_iso(),
                        },
                    }
                )

            # 注意: 不再清除 Redis Stream，因为：
            # 1. 每个 run_id 都是唯一的，不会与之前的 events 冲突
            # 2. 清除可能导致与 SSE 连接的竞争条件
            # 3. Redis Stream 有 TTL 自动过期

            # 执行 agent，统一保存所有事件；watchdog 保证事件流停滞时迁移 error 终态
            produced_main_text = False
            async for event in aiter_with_stall_timeout(
                executor(
                    session_id,
                    agent_id,
                    message,
                    user_id,
                    presenter=presenter,
                    disabled_tools=disabled_tools,
                    agent_options=agent_options,
                    attachments=attachments,
                    disabled_skills=disabled_skills,
                    enabled_skills=enabled_skills,
                    persona_system_prompt=persona_system_prompt,
                    disabled_mcp_tools=disabled_mcp_tools,
                    recommendation_input=recommendation_input,
                    team_id=team_id,
                    active_goal=active_goal,
                    auto_mode=auto_mode,
                    hitl_resume=hitl_resume,
                ),
                timeout=_run_stall_timeout_seconds(),
            ):
                await presenter.save_event(event)
                if not produced_main_text and _is_main_agent_text_event(event):
                    produced_main_text = True

            # interrupt 模式挂起（issue #218）：保留 checkpoint，标记 WAITING_HUMAN
            if presenter is not None and getattr(presenter, "hitl_suspended", False):
                if dual_writer is not None:
                    try:
                        await dual_writer.flush_mongo_buffer(require_empty=True)
                    except Exception as e:
                        logger.warning("Failed to flush suspended HITL trace: %s", e)
                await self._update_session_status(
                    session_id, TaskStatus.WAITING_HUMAN, run_id=run_id
                )
                logger.info(
                    "Task waiting for human input: session=%s, run_id=%s", session_id, run_id
                )
                await self._send_task_notification(
                    session_id, run_id, TaskStatus.WAITING_HUMAN, user_id
                )
                return True

            # 兜底守卫：run 正常走到终点却没有任何主代理正文（中间件空正文静默
            # 放行的漏网路径）→ 按 error 终结，绝不假装 completed 让用户对着
            # 空气泡（2026-09-05 生产事故：续跑后 done(completed) 无答案）。
            if not produced_main_text:
                raise AppError(ErrorCode.MODEL_EMPTY_RESPONSE)

            # 完成 trace（更新 MongoDB trace 状态为 completed）
            await presenter.complete("completed")

            # 标记完成
            await self._update_session_status(session_id, TaskStatus.COMPLETED, run_id=run_id)
            logger.info(f"Task completed: session={session_id}, run_id={run_id}")
            # 发送任务完成通知
            await self._send_task_notification(session_id, run_id, TaskStatus.COMPLETED, user_id)
            await self._expire_terminal_stream(session_id, run_id, dual_writer)
            return False

        except asyncio.CancelledError:
            await self._handle_cancelled_error(session_id, run_id, user_id, dual_writer, presenter)
            raise

        except TaskInterruptedError as e:
            await self._handle_interrupted_error(
                session_id, run_id, user_id, str(e), dual_writer, presenter
            )
            raise

        except Exception as e:
            await self._handle_generic_error(session_id, run_id, user_id, e, dual_writer, presenter)
            return None

        finally:
            # 无论成功、取消还是失败，都停止心跳并清除中断信号
            await self._heartbeat.stop(run_id)
            await TaskCancellation.clear_interrupt(run_id)
            # 清除请求上下文，防止 contextvars 泄漏到后续任务
            TraceContext.clear_request_context()
            TraceContext.clear()

    async def _handle_cancelled_error(
        self,
        session_id: str,
        run_id: str,
        user_id: str,
        dual_writer: Any,
        presenter: Any,
    ) -> None:
        """处理任务取消错误"""
        # 无中断信号的取消是系统中断（优雅关停/部署），不是用户操作：
        # 不写 user:cancel/error/done 终态事件、不终结 trace、不过期 stream，
        # 只 flush 缓冲让半截事件落库。recoverable 元数据由调用方标记
        # （manager.shutdown / arq_worker），随后同 run_id 无缝续跑。
        # 用户取消判定用权威信号（内存 + Redis）：跨副本取消时本副本内存标志
        # 可能尚未同步，Redis 中断键才是可靠依据（系统中断从不设置）。
        user_cancelled = False
        try:
            await TaskCancellation.check_interrupt(run_id)
        except TaskInterruptedError:
            user_cancelled = True
        if not user_cancelled:
            if dual_writer is None:
                dual_writer = get_dual_writer()
            try:
                await dual_writer._flush_redis_buffer()
                await dual_writer.flush_mongo_buffer()
            except Exception as e:
                logger.warning(f"Failed to flush events on system interruption: {e}")
            logger.info(
                f"Task interrupted by system shutdown (resumable): "
                f"session={session_id}, run_id={run_id}"
            )
            return

        await self._update_session_status(
            session_id, TaskStatus.CANCELLED, "Task cancelled", run_id=run_id
        )
        # 先刷新所有缓冲，确保已产生的事件不丢失
        if dual_writer is not None:
            try:
                await dual_writer._flush_redis_buffer()
                await dual_writer.flush_mongo_buffer()
            except Exception:
                pass
        trace_id = presenter.trace_id if presenter else None
        if dual_writer is not None:
            await self._emit_cancel_terminal_events(
                session_id=session_id,
                run_id=run_id,
                user_id=user_id,
                trace_id=trace_id,
                dual_writer=dual_writer,
                presenter=presenter,
                error_data={
                    "error": "Task cancelled",
                    "type": "CancelledError",
                    "run_id": run_id,
                },
            )
            # 再次刷新，确保取消终态事件被持久化
            try:
                await dual_writer._flush_redis_buffer()
                await dual_writer.flush_mongo_buffer()
            except Exception:
                pass
        if presenter is not None:
            await presenter.complete("error")
        logger.warning(f"Task cancelled: session={session_id}, run_id={run_id}")
        # 发送任务取消通知
        await self._send_task_notification(
            session_id, run_id, TaskStatus.CANCELLED, user_id, "Task cancelled"
        )
        await self._expire_terminal_stream(session_id, run_id, dual_writer)

    async def _emit_cancel_terminal_events(
        self,
        *,
        session_id: str,
        run_id: str,
        user_id: str,
        trace_id: str | None,
        dual_writer: Any,
        presenter: Any,
        error_data: dict[str, Any],
    ) -> None:
        """Persist cancel-specific terminal events before the stream done marker."""
        done_event: dict[str, Any] | None = None
        if presenter is not None:
            await presenter._ensure_token_usage_event()
            done_event = presenter.done()
            self._move_recorded_done_to_end(dual_writer, trace_id, run_id)
            presenter._done_recorded = False

        await self._record_user_cancel_event(
            session_id=session_id,
            run_id=run_id,
            user_id=user_id,
            trace_id=trace_id,
            dual_writer=dual_writer,
        )
        await dual_writer.write_event(
            session_id=session_id,
            event_type="error",
            data=error_data,
            trace_id=trace_id,
            run_id=run_id,
        )
        if presenter is not None and done_event is not None:
            await presenter.emit(done_event)

    @staticmethod
    def _move_recorded_done_to_end(
        dual_writer: Any,
        trace_id: str | None,
        run_id: str,
    ) -> None:
        """Remove an already-buffered done event so cancel events can precede it."""
        events = getattr(dual_writer, "events", None)
        if isinstance(events, list):
            for index in range(len(events) - 1, -1, -1):
                event = events[index]
                if (
                    isinstance(event, dict)
                    and event.get("event_type") == "done"
                    and event.get("run_id") == run_id
                    and (trace_id is None or event.get("trace_id") == trace_id)
                ):
                    del events[index]
                    return

        mongo_buffer = getattr(dual_writer, "_mongo_buffer", None)
        if isinstance(mongo_buffer, list):
            for index in range(len(mongo_buffer) - 1, -1, -1):
                item = mongo_buffer[index]
                if (
                    isinstance(item, tuple)
                    and len(item) >= 5
                    and item[1] == "done"
                    and item[4] == run_id
                    and (trace_id is None or item[0] == trace_id)
                ):
                    del mongo_buffer[index]
                    return

    async def _handle_interrupted_error(
        self,
        session_id: str,
        run_id: str,
        user_id: str,
        error_msg: str,
        dual_writer: Any,
        presenter: Any,
    ) -> None:
        """处理任务中断错误"""
        # TaskInterruptedError is raised by the user-cancel interrupt path.
        await self._update_session_status(
            session_id,
            TaskStatus.CANCELLED,
            error_msg,
            run_id=run_id,
        )
        # 先刷新所有缓冲，确保已产生的事件不丢失
        # 注意：dual_writer 可能还是 None（如果任务在 get_dual_writer() 之前就被取消）
        if dual_writer is None:
            dual_writer = get_dual_writer()
        try:
            await dual_writer._flush_redis_buffer()
            await dual_writer.flush_mongo_buffer()
        except Exception as flush_error:
            logger.warning(f"Failed to flush events on TaskInterruptedError: {flush_error}")
        trace_id = presenter.trace_id if presenter else None
        if dual_writer is not None:
            await self._emit_cancel_terminal_events(
                session_id=session_id,
                run_id=run_id,
                user_id=user_id,
                trace_id=trace_id,
                dual_writer=dual_writer,
                presenter=presenter,
                error_data={
                    "error": error_msg,
                    "type": "TaskInterruptedError",
                    "run_id": run_id,
                },
            )
            # 再次刷新，确保取消终态事件被持久化
            try:
                await dual_writer._flush_redis_buffer()
                await dual_writer.flush_mongo_buffer()
            except Exception:
                pass
        if presenter is not None:
            await presenter.complete("error")
        logger.info(f"Task interrupted: session={session_id}, run_id={run_id}")
        # 发送任务中断通知
        await self._send_task_notification(
            session_id, run_id, TaskStatus.CANCELLED, user_id, "Task interrupted"
        )
        await self._expire_terminal_stream(session_id, run_id, dual_writer)

    async def _record_user_cancel_event(
        self,
        *,
        session_id: str,
        run_id: str,
        user_id: str,
        trace_id: str | None,
        dual_writer: Any,
    ) -> None:
        if not user_id or not trace_id or dual_writer is None:
            return
        try:
            from src.infra.utils.datetime import utc_now_iso

            await dual_writer.write_event(
                session_id=session_id,
                event_type="user:cancel",
                data={
                    "user_id": user_id,
                    "run_id": run_id,
                    "timestamp": utc_now_iso(),
                },
                trace_id=trace_id,
                run_id=run_id,
            )
        except Exception as e:
            logger.warning("Failed to record user cancel event after terminal cleanup: %s", e)

    async def _handle_generic_error(
        self,
        session_id: str,
        run_id: str,
        user_id: str,
        error: Exception,
        dual_writer: Any,
        presenter: Any,
    ) -> None:
        """处理通用异常"""
        error_msg = str(error) or type(error).__name__
        await self._update_session_status(session_id, TaskStatus.FAILED, error_msg, run_id=run_id)
        logger.error(
            f"Task failed: session={session_id}, run_id={run_id}, error={error}", exc_info=True
        )

        # 先刷新所有缓冲，确保已产生的事件不丢失
        # 注意：dual_writer 可能还是 None（如果任务在 get_dual_writer() 之前就失败）
        if dual_writer is None:
            dual_writer = get_dual_writer()
        try:
            await dual_writer._flush_redis_buffer()
            await dual_writer.flush_mongo_buffer()
        except Exception as flush_err:
            logger.warning(f"Failed to flush events on task failure: {flush_err}")

        # 完成 trace（如果已创建）
        if presenter is not None:
            await presenter.complete("error")

        # 写入错误事件（包含 trace_id 以写入 MongoDB）；code 为稳定错误码供前端翻译
        trace_id = presenter.trace_id if presenter else None
        error_code = getattr(error, "error_code", None)
        await dual_writer.write_event(
            session_id=session_id,
            event_type="error",
            data={
                "error": str(error),
                "code": error_code.code if error_code else "internal_error",
                "type": type(error).__name__,
                "run_id": run_id,
            },
            trace_id=trace_id,
            run_id=run_id,
        )
        # 再次刷新，确保 error 事件被持久化
        try:
            await dual_writer._flush_redis_buffer()
            await dual_writer.flush_mongo_buffer()
        except Exception as flush_err:
            logger.warning(f"Failed to flush error event: {flush_err}")

        # 发送任务失败通知
        await self._send_task_notification(
            session_id, run_id, TaskStatus.FAILED, user_id, error_msg
        )
        await self._expire_terminal_stream(session_id, run_id, dual_writer)

    async def _expire_terminal_stream(
        self,
        session_id: str,
        run_id: str,
        dual_writer: Any,
    ) -> None:
        """Shorten terminal run streams without failing the completed task path."""
        try:
            if dual_writer is None:
                dual_writer = get_dual_writer()
            expire_stream = getattr(dual_writer, "expire_stream", None)
            if expire_stream is None:
                return
            await expire_stream(
                session_id,
                run_id=run_id,
                ttl_seconds=_TERMINAL_STREAM_TTL_SECONDS,
            )
        except Exception as e:
            logger.warning("Failed to expire terminal stream for run_id=%s: %s", run_id, e)

    async def _send_task_notification(
        self,
        session_id: str,
        run_id: str,
        status: TaskStatus,
        user_id: str,
        message: str | None = None,
    ) -> None:
        """
        发送任务完成通知

        Args:
            session_id: 会话 ID
            run_id: 运行 ID
            status: 任务状态
            user_id: 用户 ID
            message: 可选的消息
        """
        try:
            from src.infra.websocket import get_connection_manager

            manager = get_connection_manager()
            notification: dict[str, Any] = {
                "type": "task:complete",
                "data": {
                    "session_id": session_id,
                    "run_id": run_id,
                    "status": status.value,
                },
            }
            if message:
                notification["data"]["message"] = message

            # 附带最新的 unread_count，让前端实时更新侧边栏
            try:
                from src.infra.session.manager import SessionManager

                session = await SessionManager().get_session(session_id)
                if session:
                    favorites_project_id = None
                    if session.user_id:
                        from src.infra.folder.storage import get_project_storage

                        favorites_project = await get_project_storage().get_by_type(
                            session.user_id,
                            "favorites",
                        )
                        favorites_project_id = favorites_project.id if favorites_project else None
                    notification["data"]["unread_count"] = getattr(session, "unread_count", 0)
                    notification["data"]["project_id"] = (
                        session.metadata.get("project_id") if session.metadata else None
                    )
                    notification["data"]["scheduled_task_id"] = (
                        session.metadata.get("scheduled_task_id") if session.metadata else None
                    )
                    notification["data"]["is_favorite"] = is_session_favorite(
                        session.metadata,
                        favorites_project_id,
                    )
            except Exception:
                pass

            delivered_count = await manager.send_to_user_with_broadcast(user_id, notification)
            if delivered_count <= 0:
                logger.warning(
                    "Task notification had no active WebSocket delivery: "
                    "user_id=%s, session=%s, status=%s, delivered=%s",
                    user_id,
                    session_id,
                    status.value,
                    delivered_count,
                )
                # Web Push fallback when WebSocket has no active connection
                try:
                    from src.infra.push.manager import PushManager

                    push_mgr = PushManager()
                    push_payload = {
                        "title": "LambChat",
                        "body": message or f"Task {status.value}",
                        "url": f"/chat/{session_id}",
                    }
                    push_delivered = await push_mgr.send_push_to_user(user_id, push_payload)
                    if push_delivered > 0:
                        logger.info(
                            "Push notification delivered as fallback: user_id=%s, count=%s",
                            user_id,
                            push_delivered,
                        )
                except Exception as push_err:
                    logger.warning("Failed to send push notification fallback: %s", push_err)
            else:
                logger.info(
                    "Task notification delivered: user_id=%s, session=%s, status=%s, delivered=%s",
                    user_id,
                    session_id,
                    status.value,
                    delivered_count,
                )
        except Exception as e:
            logger.warning(f"Failed to send task notification: {e}")

    async def _update_session_status(
        self,
        session_id: str,
        status: TaskStatus,
        error: Optional[str] = None,
        run_id: Optional[str] = None,
    ) -> None:
        """更新 session 状态"""
        try:
            if await self._is_stale_run_status_update(session_id, status, run_id):
                logger.info(
                    "Skipping stale task status update: session=%s, run_id=%s, status=%s",
                    session_id,
                    run_id,
                    status.value,
                )
                return

            metadata: Dict[str, Any] = self._state_machine.build_metadata(
                status,
                run_id=run_id,
                error=error,
            )
            if status == TaskStatus.COMPLETED:
                metadata["completed_at"] = utc_now_iso()

            await self._storage.update(
                session_id,
                SessionUpdate(metadata=metadata),
            )

            # Send real-time task status update to sidebar
            try:
                uid = getattr(self, "_user_id", None)
                if uid:
                    from src.infra.websocket import get_connection_manager

                    cm = get_connection_manager()
                    await cm.send_to_user_with_broadcast(
                        uid,
                        {
                            "type": "session:task_status",
                            "data": {
                                "session_id": session_id,
                                "task_status": status.value,
                            },
                        },
                    )
            except Exception:
                logger.debug("Failed to send task status WebSocket notification")
        except Exception as e:
            logger.warning(f"Failed to update session status: {e}")

    async def _is_stale_run_status_update(
        self,
        session_id: str,
        status: TaskStatus,
        run_id: Optional[str],
    ) -> bool:
        """Return true when an old run is trying to overwrite a newer current run."""
        if not run_id or status in {
            TaskStatus.QUEUED,
            TaskStatus.PENDING,
            TaskStatus.STARTING,
        }:
            return False

        try:
            session = await self._storage.get_by_session_id(session_id)
        except Exception as e:
            logger.warning("Failed to check current run before status update: %s", e)
            return False

        current_run_id = None
        if session and getattr(session, "metadata", None):
            current_run_id = session.metadata.get("current_run_id")

        return bool(current_run_id and current_run_id != run_id)

    async def ensure_session(
        self,
        session_id: str,
        agent_id: str,
        user_id: str,
        project_id: str | None = None,
        session_name: str | None = None,
        session_metadata: dict[str, Any] | None = None,
    ) -> None:
        """确保 session 记录存在，不存在则创建

        Args:
            session_name: 自定义 session 名称，默认 "新对话"

        Raises:
            PermissionError: 如果 session 存在但不属于当前用户
        """
        try:
            # 检查 session 是否存在
            existing = await self._storage.get_by_session_id(session_id)
            if existing:
                # 验证用户所有权
                if existing.user_id and existing.user_id != user_id:
                    logger.warning(
                        f"User {user_id} attempted to access session {session_id} owned by {existing.user_id}"
                    )
                    raise PermissionError("无权访问此会话")
                logger.debug(f"Session {session_id} already exists")
                return

            # 创建新的 session
            metadata = {"agent_id": agent_id, **(session_metadata or {})}
            if project_id:
                metadata["project_id"] = project_id
            await self._storage.create(
                SessionCreate(
                    name=session_name or "新对话",
                    metadata=metadata,
                ),
                user_id=user_id,
                session_id=session_id,
            )
            logger.info(
                f"Created session {session_id} for user {user_id} (project_id={project_id})"
            )
        except PermissionError:
            raise  # 重新抛出权限错误
        except Exception as e:
            logger.warning(f"Failed to ensure session: {e}")
