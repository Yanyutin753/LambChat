# src/infra/task/executor.py
"""
Background Task Manager - Task Executor

Handles task execution including session management, presenter setup,
error handling, and status updates.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from src.infra.session.dual_writer import get_dual_writer
from src.infra.session.storage import SessionStorage
from src.kernel.schemas.session import SessionCreate, SessionUpdate

from .exceptions import TaskInterruptedError
from .heartbeat import TaskHeartbeat
from .status import TaskStatus

logger = logging.getLogger(__name__)


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
    ) -> None:
        """执行任务"""
        from src.infra.writer.present import Presenter, PresenterConfig

        presenter = None
        dual_writer = None

        try:
            await self._update_session_status(session_id, TaskStatus.RUNNING, run_id=run_id)

            # 启动心跳
            await self._heartbeat.start(run_id)

            # 创建 Presenter 并传递给 agent
            presenter = Presenter(
                PresenterConfig(
                    session_id=session_id,
                    agent_id=agent_id,
                    user_id=user_id,
                    run_id=run_id,  # 传递 run_id
                    enable_storage=True,
                )
            )

            # 设置请求上下文（供工具使用，如 ask_human）
            from src.infra.logging.context import TraceContext

            logger.info(
                f"[TaskManager] Setting TraceContext: session_id={session_id}, run_id={run_id}"
            )
            TraceContext.set_request_context(
                session_id=session_id,
                run_id=run_id,
                user_id=user_id,
            )

            await presenter._ensure_trace()

            # 立即发送 user:message 事件（任务开始时固定发送）
            if message:
                await presenter.emit_user_message(message, attachments=attachments)

            # 保存 trace_id 和 agent_id 到 run_info
            self._run_info[run_id] = {
                "session_id": session_id,
                "trace_id": presenter.trace_id,
                "agent_id": agent_id,
            }

            dual_writer = get_dual_writer()

            # 注意: 不再清除 Redis Stream，因为：
            # 1. 每个 run_id 都是唯一的，不会与之前的 events 冲突
            # 2. 清除可能导致与 SSE 连接的竞争条件
            # 3. Redis Stream 有 TTL 自动过期

            # 执行 agent，统一保存所有事件
            async for event in executor(
                session_id,
                agent_id,
                message,
                user_id,
                presenter=presenter,
                disabled_tools=disabled_tools,
                agent_options=agent_options,
                attachments=attachments,
            ):
                await presenter.save_event(event)

            # 完成 trace（更新 MongoDB trace 状态为 completed）
            await presenter.complete("completed")

            # 标记完成
            await self._update_session_status(session_id, TaskStatus.COMPLETED, run_id=run_id)
            logger.info(f"Task completed: session={session_id}, run_id={run_id}")
            # 发送任务完成通知
            await self._send_task_notification(session_id, run_id, TaskStatus.COMPLETED, user_id)

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

        finally:
            # 无论成功、取消还是失败，都停止心跳并清除中断信号
            await self._heartbeat.stop(run_id)
            from .cancellation import TaskCancellation

            await TaskCancellation.clear_interrupt(run_id)

    async def _handle_cancelled_error(
        self,
        session_id: str,
        run_id: str,
        user_id: str,
        dual_writer: Any,
        presenter: Any,
    ) -> None:
        """处理任务取消错误"""

        await self._update_session_status(
            session_id, TaskStatus.FAILED, "Task cancelled", run_id=run_id
        )
        # 先刷新所有缓冲，确保已产生的事件不丢失
        if dual_writer is not None:
            try:
                await dual_writer._flush_redis_buffer()
                await dual_writer.flush_mongo_buffer()
            except Exception:
                pass
        # 完成 trace（如果已创建）
        if presenter is not None:
            await presenter.complete("error")
        # 写入错误事件（包含 trace_id 以写入 MongoDB）
        trace_id = presenter.trace_id if presenter else None
        if dual_writer is not None:
            await dual_writer.write_event(
                session_id=session_id,
                event_type="error",
                data={
                    "error": "Task cancelled",
                    "type": "CancelledError",
                    "run_id": run_id,
                },
                trace_id=trace_id,
                run_id=run_id,
            )
            # 再次刷新，确保 error 事件被持久化
            try:
                await dual_writer._flush_redis_buffer()
                await dual_writer.flush_mongo_buffer()
            except Exception:
                pass
        logger.warning(f"Task cancelled: session={session_id}, run_id={run_id}")
        # 发送任务取消通知
        await self._send_task_notification(
            session_id, run_id, TaskStatus.FAILED, user_id, "Task cancelled"
        )

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
        # 任务被中断
        await self._update_session_status(session_id, TaskStatus.FAILED, error_msg, run_id=run_id)
        # 先刷新所有缓冲，确保已产生的事件不丢失
        # 注意：dual_writer 可能还是 None（如果任务在 get_dual_writer() 之前就被取消）
        if dual_writer is None:
            dual_writer = get_dual_writer()
        try:
            await dual_writer._flush_redis_buffer()
            await dual_writer.flush_mongo_buffer()
        except Exception as flush_error:
            logger.warning(f"Failed to flush events on TaskInterruptedError: {flush_error}")
        # 完成 trace
        if presenter is not None:
            await presenter.complete("error")
        # 写入错误事件（包含 trace_id 以写入 MongoDB）
        trace_id = presenter.trace_id if presenter else None
        if dual_writer is not None:
            await dual_writer.write_event(
                session_id=session_id,
                event_type="error",
                data={
                    "error": error_msg,
                    "type": "TaskInterruptedError",
                    "run_id": run_id,
                },
                trace_id=trace_id,
                run_id=run_id,
            )
            # 再次刷新，确保 error 事件被持久化
            try:
                await dual_writer._flush_redis_buffer()
                await dual_writer.flush_mongo_buffer()
            except Exception:
                pass
        logger.info(f"Task interrupted: session={session_id}, run_id={run_id}")
        # 发送任务中断通知
        await self._send_task_notification(
            session_id, run_id, TaskStatus.FAILED, user_id, "Task interrupted"
        )

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
        await self._update_session_status(session_id, TaskStatus.FAILED, str(error), run_id=run_id)
        logger.error(f"Task failed: session={session_id}, run_id={run_id}, error={error}")

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

        # 写入错误事件（包含 trace_id 以写入 MongoDB）
        trace_id = presenter.trace_id if presenter else None
        await dual_writer.write_event(
            session_id=session_id,
            event_type="error",
            data={"error": str(error), "type": type(error).__name__, "run_id": run_id},
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
            session_id, run_id, TaskStatus.FAILED, user_id, str(error)
        )

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

            await manager.send_to_user(user_id, notification)
            logger.info(
                f"Task notification sent: user_id={user_id}, session={session_id}, status={status.value}"
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
            metadata = {"task_status": status.value}
            if error:
                metadata["task_error"] = error
            if run_id:
                metadata["current_run_id"] = run_id
            if status == TaskStatus.COMPLETED:
                metadata["completed_at"] = datetime.now().isoformat()

            await self._storage.update(
                session_id,
                SessionUpdate(metadata=metadata),
            )
        except Exception as e:
            logger.warning(f"Failed to update session status: {e}")

    async def ensure_session(
        self,
        session_id: str,
        agent_id: str,
        user_id: str,
    ) -> None:
        """确保 session 记录存在，不存在则创建

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
            await self._storage.create(
                SessionCreate(
                    name="新对话",
                    metadata={"agent_id": agent_id},
                ),
                user_id=user_id,
                session_id=session_id,
            )
            logger.info(f"Created session {session_id} for user {user_id}")
        except PermissionError:
            raise  # 重新抛出权限错误
        except Exception as e:
            logger.warning(f"Failed to ensure session: {e}")
