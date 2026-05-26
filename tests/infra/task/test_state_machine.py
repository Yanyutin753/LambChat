from __future__ import annotations

import pytest

from src.infra.task.state_machine import InvalidTaskTransitionError, TaskStateMachine
from src.infra.task.status import TaskStatus


def test_allows_expected_lifecycle_transitions() -> None:
    state_machine = TaskStateMachine()

    state_machine.validate_transition(None, TaskStatus.QUEUED)
    state_machine.validate_transition(TaskStatus.QUEUED, TaskStatus.PENDING)
    state_machine.validate_transition(TaskStatus.PENDING, TaskStatus.STARTING)
    state_machine.validate_transition(TaskStatus.STARTING, TaskStatus.RUNNING)
    state_machine.validate_transition(TaskStatus.RUNNING, TaskStatus.COMPLETED)


def test_rejects_terminal_transition_back_to_running() -> None:
    state_machine = TaskStateMachine()

    with pytest.raises(InvalidTaskTransitionError):
        state_machine.validate_transition(TaskStatus.COMPLETED, TaskStatus.RUNNING)


def test_builds_session_metadata_for_cancelled_task() -> None:
    metadata = TaskStateMachine().build_metadata(
        TaskStatus.CANCELLED,
        run_id="run-1",
        error="Task cancelled",
        error_code="cancelled",
    )

    assert metadata["task_status"] == "cancelled"
    assert metadata["current_run_id"] == "run-1"
    assert metadata["active_run_id"] is None
    assert metadata["task_error"] == "Task cancelled"
    assert metadata["task_error_code"] == "cancelled"
    assert metadata["task_recoverable"] is False


def test_builds_session_metadata_for_recoverable_failed_task() -> None:
    metadata = TaskStateMachine().build_metadata(
        TaskStatus.FAILED,
        run_id="run-1",
        error="Server shutdown",
        error_code="server_restart",
        recoverable=True,
    )

    assert metadata["task_status"] == "failed"
    assert metadata["task_error"] == "Server shutdown"
    assert metadata["task_error_code"] == "server_restart"
    assert metadata["task_recoverable"] is True


def test_builds_session_metadata_for_running_task_tracks_active_run() -> None:
    metadata = TaskStateMachine().build_metadata(
        TaskStatus.RUNNING,
        run_id="run-1",
    )

    assert metadata["current_run_id"] == "run-1"
    assert metadata["active_run_id"] == "run-1"
    assert metadata["last_started_run_id"] == "run-1"
