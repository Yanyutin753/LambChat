from __future__ import annotations

from typing import Any

from .status import TaskStatus


class InvalidTaskTransitionError(ValueError):
    """Raised when a task attempts to move through an invalid lifecycle edge."""


class TaskStateMachine:
    """Validate task lifecycle transitions and build persistent status metadata."""

    _terminal_statuses = {
        TaskStatus.CANCELLED,
        TaskStatus.COMPLETED,
        TaskStatus.FAILED,
        TaskStatus.EXPIRED,
    }

    _allowed_transitions: dict[TaskStatus | None, set[TaskStatus]] = {
        None: {TaskStatus.QUEUED, TaskStatus.PENDING, TaskStatus.STARTING},
        TaskStatus.QUEUED: {
            TaskStatus.PENDING,
            TaskStatus.STARTING,
            TaskStatus.RUNNING,
            TaskStatus.CANCELLING,
            TaskStatus.CANCELLED,
            TaskStatus.EXPIRED,
            TaskStatus.FAILED,
            TaskStatus.RECOVERING,
        },
        TaskStatus.PENDING: {
            TaskStatus.QUEUED,
            TaskStatus.STARTING,
            TaskStatus.RUNNING,
            TaskStatus.CANCELLING,
            TaskStatus.CANCELLED,
            TaskStatus.FAILED,
            TaskStatus.RECOVERING,
        },
        TaskStatus.STARTING: {
            TaskStatus.RUNNING,
            TaskStatus.CANCELLING,
            TaskStatus.CANCELLED,
            TaskStatus.FAILED,
        },
        TaskStatus.RUNNING: {
            TaskStatus.WAITING_HUMAN,
            TaskStatus.CANCELLING,
            TaskStatus.CANCELLED,
            TaskStatus.COMPLETED,
            TaskStatus.FAILED,
            TaskStatus.RECOVERING,
        },
        TaskStatus.WAITING_HUMAN: {
            TaskStatus.PENDING,
            TaskStatus.STARTING,
            TaskStatus.RUNNING,
            TaskStatus.CANCELLING,
            TaskStatus.CANCELLED,
            TaskStatus.FAILED,
            TaskStatus.EXPIRED,
        },
        TaskStatus.CANCELLING: {
            TaskStatus.CANCELLED,
            TaskStatus.FAILED,
        },
        TaskStatus.RECOVERING: {
            TaskStatus.QUEUED,
            TaskStatus.PENDING,
            TaskStatus.STARTING,
            TaskStatus.RUNNING,
            TaskStatus.FAILED,
        },
        TaskStatus.CANCELLED: set(),
        TaskStatus.COMPLETED: set(),
        TaskStatus.FAILED: {TaskStatus.RECOVERING},
        TaskStatus.EXPIRED: {TaskStatus.RECOVERING},
    }

    def validate_transition(
        self,
        current: TaskStatus | str | None,
        target: TaskStatus | str,
    ) -> None:
        current_status = self._coerce_status(current)
        target_status = self._coerce_status(target)
        allowed = self._allowed_transitions.get(current_status, set())
        if target_status not in allowed and current_status != target_status:
            raise InvalidTaskTransitionError(
                f"Invalid task transition: {current_status!s} -> {target_status!s}"
            )

    def is_terminal(self, status: TaskStatus | str) -> bool:
        return self._coerce_status(status) in self._terminal_statuses

    def build_metadata(
        self,
        status: TaskStatus | str,
        *,
        run_id: str | None = None,
        error: str | None = None,
        error_code: str | None = None,
        recoverable: bool | None = None,
    ) -> dict[str, Any]:
        coerced = self._coerce_status(status)
        assert coerced is not None  # status param is never None here
        metadata: dict[str, Any] = {
            "task_status": coerced.value,
            "task_error": error,
            "task_error_code": error_code,
        }
        if run_id:
            metadata["current_run_id"] = run_id

        if recoverable is not None:
            metadata["task_recoverable"] = recoverable
        elif status in {
            TaskStatus.QUEUED,
            TaskStatus.PENDING,
            TaskStatus.STARTING,
            TaskStatus.RUNNING,
            TaskStatus.WAITING_HUMAN,
            TaskStatus.CANCELLING,
            TaskStatus.CANCELLED,
            TaskStatus.COMPLETED,
            TaskStatus.EXPIRED,
        }:
            metadata["task_recoverable"] = False

        if status == TaskStatus.CANCELLED and error_code is None:
            metadata["task_error_code"] = "cancelled"
        if status == TaskStatus.EXPIRED and error_code is None:
            metadata["task_error_code"] = "expired"

        return metadata

    @staticmethod
    def _coerce_status(status: TaskStatus | str | None) -> TaskStatus | None:
        if status is None:
            return None
        if isinstance(status, TaskStatus):
            return status
        return TaskStatus(status)
