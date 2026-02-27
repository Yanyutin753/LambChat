"""
类型和协议定义

定义系统中的核心类型、协议和枚举。
"""

from enum import Enum
from typing import (
    Any,
    AsyncGenerator,
    Dict,
    List,
    Optional,
    Protocol,
    runtime_checkable,
)


class Permission(str, Enum):
    """权限枚举"""

    # Chat
    CHAT_READ = "chat:read"
    CHAT_WRITE = "chat:write"

    # Session
    SESSION_READ = "session:read"
    SESSION_WRITE = "session:write"
    SESSION_DELETE = "session:delete"

    # Skill
    SKILL_READ = "skill:read"
    SKILL_WRITE = "skill:write"
    SKILL_DELETE = "skill:delete"
    SKILL_ADMIN = "skill:admin"

    # User (Admin)
    USER_READ = "user:read"
    USER_WRITE = "user:write"
    USER_DELETE = "user:delete"

    # Role (Admin)
    ROLE_MANAGE = "role:manage"

    # Settings (Admin)
    SETTINGS_MANAGE = "settings:manage"

    # MCP
    MCP_READ = "mcp:read"
    MCP_WRITE = "mcp:write"
    MCP_DELETE = "mcp:delete"
    MCP_ADMIN = "mcp:admin"

    # File
    FILE_UPLOAD = "file:upload"


class MessageType(str, Enum):
    """消息类型"""

    HUMAN = "human"
    AI = "ai"
    SYSTEM = "system"
    TOOL = "tool"


@runtime_checkable
class AgentProtocol(Protocol):
    """Agent 协议接口"""

    @property
    def agent_id(self) -> str:
        """Agent ID"""
        ...

    @property
    def name(self) -> str:
        """Agent 名称"""
        ...

    @property
    def description(self) -> str:
        """Agent 描述"""
        ...

    async def initialize(self) -> None:
        """初始化 Agent"""
        ...

    async def chat(self, message: str, session_id: str = "default") -> str:
        """非流式聊天"""
        ...

    async def stream_chat(
        self, message: str, session_id: str = "default"
    ) -> AsyncGenerator[dict, None]:
        """流式聊天"""
        ...


@runtime_checkable
class StorageProtocol(Protocol):
    """存储协议接口"""

    async def get(self, key: str) -> Optional[Any]:
        """获取数据"""
        ...

    async def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """设置数据"""
        ...

    async def delete(self, key: str) -> bool:
        """删除数据"""
        ...

    async def exists(self, key: str) -> bool:
        """检查是否存在"""
        ...


@runtime_checkable
class LLMClientProtocol(Protocol):
    """LLM 客户端协议接口"""

    async def complete(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> str:
        """非流式完成"""
        ...

    async def stream_complete(
        self,
        messages: List[Dict[str, Any]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AsyncGenerator[str, None]:
        """流式完成"""
        ...


@runtime_checkable
class ToolProtocol(Protocol):
    """工具协议接口"""

    @property
    def name(self) -> str:
        """工具名称"""
        ...

    @property
    def description(self) -> str:
        """工具描述"""
        ...

    async def execute(self, **kwargs: Any) -> Any:
        """执行工具"""
        ...
