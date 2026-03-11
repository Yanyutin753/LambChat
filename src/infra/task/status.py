# src/infra/task/status.py
"""
Background Task Manager - Task Status Enum
"""

from enum import Enum


class TaskStatus(str, Enum):
    """任务状态"""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
