# src/infra/task/status.py
"""
Background Task Manager - Task Status Enum
"""

from enum import Enum


class TaskStatus(str, Enum):
    """任务状态"""

    QUEUED = "queued"
    PENDING = "pending"
    STARTING = "starting"
    RUNNING = "running"
    WAITING_HUMAN = "waiting_human"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"
    RECOVERING = "recovering"
    EXPIRED = "expired"
