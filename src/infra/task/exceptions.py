# src/infra/task/exceptions.py
"""
Background Task Manager - Exceptions
"""


class TaskInterruptedError(Exception):
    """任务被中断异常"""

    pass


class TaskStalledError(TimeoutError):
    """任务事件流停滞异常（watchdog 超时，issue #293）"""

    pass
