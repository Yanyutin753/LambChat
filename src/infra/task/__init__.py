# src/infra/task/__init__.py
"""
Background Task Manager

A distributed task management system with support for:
- Task execution with async generators
- Distributed task cancellation via Redis pub/sub
- Heartbeat-based stale task detection
- Session and trace management
"""

from src.infra.task.cancellation import TaskCancellation
from src.infra.task.constants import (
    CANCEL_CHANNEL,
    HEARTBEAT_PREFIX,
    HEARTBEAT_TIMEOUT,
    INTERRUPT_PREFIX,
)
from src.infra.task.exceptions import TaskInterruptedError
from src.infra.task.executor import TaskExecutor
from src.infra.task.heartbeat import TaskHeartbeat
from src.infra.task.manager import BackgroundTaskManager, get_task_manager
from src.infra.task.pubsub import TaskPubSub
from src.infra.task.status import TaskStatus

__all__ = [
    # Main exports (backward compatibility)
    "BackgroundTaskManager",
    "TaskStatus",
    "get_task_manager",
    # Additional exports for advanced usage
    "TaskInterruptedError",
    "TaskCancellation",
    "TaskExecutor",
    "TaskHeartbeat",
    "TaskPubSub",
    "CANCEL_CHANNEL",
    "HEARTBEAT_PREFIX",
    "INTERRUPT_PREFIX",
    "HEARTBEAT_TIMEOUT",
]
