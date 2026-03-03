"""
Share-related schemas.

Schema definitions for session sharing feature.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class ShareType(str, Enum):
    """Share type enum."""

    FULL = "full"
    PARTIAL = "partial"


class ShareVisibility(str, Enum):
    """Share visibility enum."""

    PUBLIC = "public"
    AUTHENTICATED = "authenticated"


class ShareCreate(BaseModel):
    """Schema for creating a share."""

    session_id: str
    share_type: ShareType = ShareType.FULL
    run_ids: Optional[list[str]] = None  # Required when share_type=partial
    visibility: ShareVisibility = ShareVisibility.PUBLIC


class ShareUpdate(BaseModel):
    """Schema for updating a share."""

    share_type: Optional[ShareType] = None
    run_ids: Optional[list[str]] = None
    visibility: Optional[ShareVisibility] = None


class SharedSession(BaseModel):
    """Shared session model."""

    id: str
    share_id: str  # Public share identifier (for URL)
    session_id: str  # Original session ID
    owner_id: str  # Owner user ID

    # Share scope
    share_type: ShareType
    run_ids: Optional[list[str]] = None

    # Access control
    visibility: ShareVisibility

    # Timestamps
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    class Config:
        from_attributes = True


class SharedSessionResponse(BaseModel):
    """Response model for share creation/retrieval."""

    id: str
    share_id: str
    url: str  # Share URL path
    session_id: str
    share_type: ShareType
    visibility: ShareVisibility
    run_ids: Optional[list[str]] = None
    created_at: datetime


class SharedSessionListItem(BaseModel):
    """List item model for shares."""

    id: str
    share_id: str
    session_id: str
    session_name: Optional[str] = None
    share_type: ShareType
    visibility: ShareVisibility
    run_ids: Optional[list[str]] = None
    created_at: datetime


class ShareListResponse(BaseModel):
    """Response model for listing shares."""

    shares: list[SharedSessionListItem]
    total: int


class SharedContentOwner(BaseModel):
    """Owner info in shared content response."""

    username: str
    avatar_url: Optional[str] = None


class SharedContentResponse(BaseModel):
    """Response model for viewing shared content."""

    session: dict  # Session info
    events: list[dict]  # Session events
    owner: SharedContentOwner
    share_type: ShareType
    run_ids: Optional[list[str]] = None
