"""Session status persistence and current-run fencing for task executors."""

from typing import TYPE_CHECKING, Any, Dict, Optional

from src.infra.goal_runtime import GoalRunAdmissionError
from src.infra.logging import get_logger
from src.infra.sandbox.idle_pause import IDLE_PAUSE_TRIGGER_STATUSES
from src.infra.utils.datetime import utc_now_iso
from src.kernel.errors import AppError
from src.kernel.schemas.session import SessionUpdate

from .status import TaskStatus

if TYPE_CHECKING:
    from src.infra.session.storage import SessionStorage

    from .state_machine import TaskStateMachine

logger = get_logger(__name__)


class TaskSessionStatusMixin:
    """Preserve newer human runs when delayed task status updates arrive."""

    if TYPE_CHECKING:
        _storage: SessionStorage
        _state_machine: TaskStateMachine

        def _schedule_idle_pause_check(self, session_id: str) -> None: ...

    async def _record_uncertain_effect(self, session_id: str, run_id: str, error: AppError) -> None:
        await self._storage.update_metadata_for_run(
            session_id,
            run_id,
            {
                **self._state_machine.build_metadata(
                    TaskStatus.FAILED,
                    run_id=run_id,
                    error=error.display_message,
                    error_code=error.error_code.code,
                    recoverable=False,
                ),
                "verification_required": True,
                "verification_tool_calls": error.args_data.get("tool_calls", []),
            },
        )

    async def _update_session_status(
        self,
        session_id: str,
        status: TaskStatus,
        error: Optional[str] = None,
        run_id: Optional[str] = None,
        *,
        expected_run_id: str | None = None,
    ) -> None:
        """更新 session 状态；恢复接入要求原子保留当前 run 的所有权。"""
        try:
            if await self._is_stale_run_status_update(session_id, status, run_id):
                if expected_run_id:
                    raise GoalRunAdmissionError("Goal session ownership changed before admission")
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
            if (
                run_id
                and not expected_run_id
                and status
                in {
                    TaskStatus.QUEUED,
                    TaskStatus.PENDING,
                    TaskStatus.STARTING,
                }
            ):
                session = await self._storage.get_by_session_id(session_id)
                previous = getattr(session, "metadata", None) or {}
                if previous.get("current_run_id") != run_id:
                    # Recovery budgets belong to a run, not the lifetime of its conversation.
                    metadata.update(
                        resume_attempts=0,
                        resume_attempts_run_id=run_id,
                        interrupted_run_id=None,
                        recovery_of_run_id=None,
                        recovery_reason=None,
                        recovery_requested_at=None,
                    )
            if status == TaskStatus.COMPLETED:
                metadata["completed_at"] = utc_now_iso()

            update_for_run = getattr(self._storage, "update_metadata_for_run", None)
            if expected_run_id:
                if not callable(update_for_run) or not await update_for_run(
                    session_id, expected_run_id, metadata
                ):
                    raise GoalRunAdmissionError("Goal session ownership changed before admission")
            elif (
                run_id
                and status not in {TaskStatus.QUEUED, TaskStatus.PENDING, TaskStatus.STARTING}
                and callable(update_for_run)
            ):
                if not await update_for_run(session_id, run_id, metadata):
                    return
            else:
                await self._storage.update(
                    session_id,
                    SessionUpdate(metadata=metadata),
                )

            # 对话轮终态后安排沙箱空闲暂停检查（省成本）；fire-and-forget，
            # 任何失败只记日志，绝不影响状态更新主流程。
            if status.value in IDLE_PAUSE_TRIGGER_STATUSES:
                self._schedule_idle_pause_check(session_id)

            # Send real-time task status update to sidebar
            try:
                # Executors are shared by concurrent runs. Resolve ownership from
                # this session, never from mutable executor-wide run state.
                session = await self._storage.get_by_session_id(session_id)
                uid = getattr(session, "user_id", None)
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
            if expected_run_id:
                raise
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
