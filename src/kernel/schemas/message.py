"""Message-related schemas."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from src.kernel.types import MessageType

__all__ = ["Message", "MessageType", "ToolCall", "ToolResult"]


class Message(BaseModel):
    """Single message in a conversation."""

    type: MessageType
    content: str
    timestamp: datetime = Field(default_factory=datetime.now)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolCall(BaseModel):
    """Tool call details."""

    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    call_id: Optional[str] = None


class ToolResult(BaseModel):
    """Tool execution result."""

    call_id: str
    name: str
    content: str
    success: bool
    error: Optional[str] = None
    execution_time_ms: Optional[float] = None
