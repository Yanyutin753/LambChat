"""
共享内核 (Shared Kernel)

零依赖的核心模块，包含：
- 异常定义
- 类型/协议定义
- 事件构建器
- Pydantic 模型
"""

from src.kernel.events import EventBuilder
from src.kernel.exceptions import (
    AgentError,
    AuthenticationError,
    AuthorizationError,
    ConfigurationError,
    NotFoundError,
    ValidationError,
)
from src.kernel.types import (
    AgentProtocol,
    LLMClientProtocol,
    Permission,
    StorageProtocol,
)

__all__ = [
    # 异常
    "AgentError",
    "AuthenticationError",
    "AuthorizationError",
    "ConfigurationError",
    "NotFoundError",
    "ValidationError",
    # 事件
    "EventBuilder",
    # 类型
    "Permission",
    "AgentProtocol",
    "StorageProtocol",
    "LLMClientProtocol",
]
