# src/infra/task/constants.py
"""
Background Task Manager - Constants
"""

# Redis keys and channels
CANCEL_CHANNEL = "task:cancel"
HEARTBEAT_PREFIX = "task:heartbeat:"
INTERRUPT_PREFIX = "task:interrupt:"  # 中断信号前缀
HEARTBEAT_INTERVAL = 10  # 心跳间隔（秒）
HEARTBEAT_TIMEOUT = 60  # 心跳超时阈值（秒）
