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
# 按时间戳判过期的阈值：超过该时长没有新心跳即视为执行实例死亡
HEARTBEAT_STALE_THRESHOLD_SECONDS = max(30, HEARTBEAT_INTERVAL * 3)

# Settings sync channel (distributed instances)
SETTINGS_CHANNEL = "settings:changed"

# Model config sync channel (distributed instances)
MODEL_CONFIG_CHANNEL = "model_config:changed"

# Pricing snapshot/cache invalidation across replicas
PRICING_CACHE_CHANNEL = "pricing:cache_invalidate"
