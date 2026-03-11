# src/infra/task/exceptions.py
"""
Background Task Manager - Exceptions
"""


class TaskInterruptedError(Exception):
    """任务被中断异常"""

    pass
