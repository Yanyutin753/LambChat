"""WAITING_HUMAN（等待人工输入）状态相关转换测试（issue #218）。"""

import pytest

from src.infra.task.state_machine import InvalidTaskTransitionError, TaskStateMachine
from src.infra.task.status import TaskStatus


@pytest.fixture
def machine() -> TaskStateMachine:
    return TaskStateMachine()


def test_running_to_waiting_human_allowed(machine):
    machine.validate_transition(TaskStatus.RUNNING, TaskStatus.WAITING_HUMAN)


def test_waiting_human_to_running_allowed(machine):
    machine.validate_transition(TaskStatus.WAITING_HUMAN, TaskStatus.RUNNING)


def test_waiting_human_to_terminal_states_allowed(machine):
    for target in (TaskStatus.CANCELLED, TaskStatus.EXPIRED, TaskStatus.FAILED):
        machine.validate_transition(TaskStatus.WAITING_HUMAN, target)


def test_waiting_human_resume_run_lifecycle_allowed(machine):
    # 恢复运行会经 PENDING/STARTING 回到 RUNNING
    machine.validate_transition(TaskStatus.WAITING_HUMAN, TaskStatus.PENDING)
    machine.validate_transition(TaskStatus.WAITING_HUMAN, TaskStatus.STARTING)


def test_waiting_human_not_terminal(machine):
    assert not machine.is_terminal(TaskStatus.WAITING_HUMAN)


def test_waiting_human_cannot_complete(machine):
    with pytest.raises(InvalidTaskTransitionError):
        machine.validate_transition(TaskStatus.WAITING_HUMAN, TaskStatus.COMPLETED)


def test_build_metadata_marks_waiting_human_not_recoverable(machine):
    metadata = machine.build_metadata(TaskStatus.WAITING_HUMAN, run_id="run-1")
    assert metadata["task_status"] == "waiting_human"
    assert metadata["task_recoverable"] is False
    assert metadata["current_run_id"] == "run-1"
