"""
Share-related schemas.

Schema definitions for session sharing feature.
"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from src.infra.utils.datetime import utc_now


class ShareType(str, Enum):
    """Share type enum.

    Semantics depend on ``share_scope``:

    - ``scope=session``: ``full`` = 全量事件; ``partial`` = 按 ``run_ids`` 选部分
    - ``scope=project``: ``full`` = 实时分享项目内全部会话; ``partial`` = 快照选中的 ``session_ids``
    """

    FULL = "full"
    PARTIAL = "partial"


class ShareVisibility(str, Enum):
    """Share visibility enum."""

    PUBLIC = "public"
    AUTHENTICATED = "authenticated"


class ShareScope(str, Enum):
    """Share scope enum: a single session or a whole project."""

    SESSION = "session"
    PROJECT = "project"


class ProjectSnapshot(BaseModel):
    """Frozen project display info.

    Captured at share creation so the shared card stays stable after the
    project is renamed or deleted.
    """

    id: str
    name: str
    icon: Optional[str] = None


class ShareCreate(BaseModel):
    """Schema for creating a share."""

    # scope=session 时必填; scope=project 时留空
    session_id: Optional[str] = None
    share_type: ShareType = ShareType.FULL
    # scope=session 且 partial 时必填
    run_ids: Optional[list[str]] = None
    visibility: ShareVisibility = ShareVisibility.PUBLIC

    # 项目分享
    share_scope: ShareScope = ShareScope.SESSION
    project_id: Optional[str] = None  # scope=project 时必填
    # scope=project 且 partial 时必填(冻结的会话快照)
    session_ids: Optional[list[str]] = None


class ShareUpdate(BaseModel):
    """Schema for updating a share."""

    share_type: Optional[ShareType] = None
    run_ids: Optional[list[str]] = None  # session partial
    session_ids: Optional[list[str]] = None  # project partial (刷新快照)
    visibility: Optional[ShareVisibility] = None


class SharedSession(BaseModel):
    """Shared session model."""

    id: str
    share_id: str  # Public share identifier (for URL)
    session_id: Optional[str] = None  # Original session ID (scope=session)
    owner_id: str  # Owner user ID

    # Share scope
    share_scope: ShareScope = ShareScope.SESSION

    # Share granularity
    share_type: ShareType
    run_ids: Optional[list[str]] = None  # scope=session partial
    session_ids: Optional[list[str]] = None  # scope=project partial (snapshot)
    project_id: Optional[str] = None  # scope=project
    project_snapshot: Optional[ProjectSnapshot] = None  # scope=project

    # Access control
    visibility: ShareVisibility

    # Timestamps
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)

    class Config:
        from_attributes = True


class SharedSessionResponse(BaseModel):
    """Response model for share creation/retrieval."""

    id: str
    share_id: str
    url: str  # Share URL path
    session_id: Optional[str] = None
    share_scope: ShareScope = ShareScope.SESSION
    project_id: Optional[str] = None
    share_type: ShareType
    visibility: ShareVisibility
    run_ids: Optional[list[str]] = None
    session_ids: Optional[list[str]] = None
    created_at: datetime


class SharedSessionListItem(BaseModel):
    """List item model for shares."""

    id: str
    share_id: str
    session_id: Optional[str] = None
    share_scope: ShareScope = ShareScope.SESSION
    project_id: Optional[str] = None
    session_name: Optional[str] = None
    project_name: Optional[str] = None
    share_type: ShareType
    visibility: ShareVisibility
    run_ids: Optional[list[str]] = None
    session_ids: Optional[list[str]] = None
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
    """Response model for viewing shared content (scope=session)."""

    share_scope: ShareScope = ShareScope.SESSION
    session: dict  # Session info
    events: list[dict]  # Session events
    owner: SharedContentOwner
    share_type: ShareType
    run_ids: Optional[list[str]] = None
    events_limited: bool = False
    events_limit: Optional[int] = None


class SharedProjectSessionItem(BaseModel):
    """A session summary inside a project share manifest (no full events)."""

    id: str
    name: Optional[str] = None
    agent_name: Optional[str] = None
    model: Optional[str] = None
    updated_at: Optional[datetime] = None
    event_count: Optional[int] = None  # v1 暂不填充(展开子会话时可知)


class SharedProjectContentResponse(BaseModel):
    """Response model for viewing a shared project (scope=project)."""

    share_scope: ShareScope = ShareScope.PROJECT
    share_type: ShareType
    project: ProjectSnapshot
    sessions: list[SharedProjectSessionItem]
    owner: SharedContentOwner
    visibility: ShareVisibility
    events_limited: bool = False
    events_limit: Optional[int] = None
    sessions_total: int = 0
    has_more: bool = False  # manifest 是否还有更多会话可分页加载
