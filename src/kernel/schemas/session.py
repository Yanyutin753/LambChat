"""Session-related schemas."""

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class SessionBase(BaseModel):
    """Base session schema."""

    name: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class SessionCreate(SessionBase):
    """Schema for creating a session."""

    pass


class SessionUpdate(BaseModel):
    """Schema for updating a session."""

    name: Optional[str] = None
    metadata: Optional[dict[str, Any]] = None


class Session(SessionBase):
    """Session model."""

    id: str
    user_id: Optional[str] = None
    agent_id: str = "default"
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    is_active: bool = True
    # Task execution status
    task_status: Optional[str] = None  # pending, running, completed, failed
    task_error: Optional[str] = None
    completed_at: Optional[datetime] = None
    unread_count: int = 0

    class Config:
        from_attributes = True
