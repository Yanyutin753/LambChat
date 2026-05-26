"""Session-related schemas."""

from copy import deepcopy
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from src.infra.utils.datetime import utc_now


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
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    is_active: bool = True
    # Task execution status
    task_status: Optional[str] = None  # pending, running, completed, failed
    task_error: Optional[str] = None
    completed_at: Optional[datetime] = None
    unread_count: int = 0

    class Config:
        from_attributes = True


class SessionCheckpoint(BaseModel):
    """Message-level fork checkpoint metadata."""

    id: str
    message_id: str
    name: str
    created_at: datetime = Field(default_factory=utc_now)
    source_run_id: Optional[str] = None
    source_trace_id: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class MessageCheckpointCreate(BaseModel):
    """Payload for creating a message checkpoint."""

    name: Optional[str] = None


def clone_session_metadata(
    metadata: dict[str, Any] | None,
    *,
    include_checkpoints: bool = False,
) -> dict[str, Any]:
    """Return a copy of session metadata without transient branching state."""
    copied = deepcopy(metadata or {})
    if not include_checkpoints:
        copied.pop("checkpoints", None)
    copied.pop("current_run_id", None)
    copied.pop("active_run_id", None)
    copied.pop("last_started_run_id", None)
    copied.pop("interrupted_run_id", None)
    return copied
