"""Role-related schemas."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from src.infra.utils.datetime import utc_now
from src.kernel.types import Permission


class RoleQuotaUpdate(BaseModel):
    """Quota-only changes are allowed even for protected system roles."""

    model_config = ConfigDict(extra="forbid")

    five_hour_budget_usd: Optional[float] = Field(
        default=None, ge=0, le=1_000_000, allow_inf_nan=False
    )
    weekly_budget_usd: Optional[float] = Field(
        default=None, ge=0, le=1_000_000, allow_inf_nan=False
    )

    @field_validator("five_hour_budget_usd", "weekly_budget_usd", mode="before")
    @classmethod
    def validate_budget(cls, value):
        if isinstance(value, bool):
            raise ValueError("Budget must be a USD amount")
        return value


class RoleLimits(RoleQuotaUpdate):
    """Role-specific limits configuration."""

    max_channels: Optional[int] = Field(
        default=None, description="Maximum number of channels allowed (null = unlimited)"
    )
    max_concurrent_chats: Optional[int] = Field(
        default=5, description="Per-user max concurrent chat tasks (null = unlimited, default: 5)"
    )
    max_queued_chats: Optional[int] = Field(
        default=10, description="Per-user max queued chat tasks (null = unlimited, default: 10)"
    )
    max_file_size_image: Optional[int] = Field(
        default=None,
        description="Max file upload size for images in MB (null = use global default)",
    )
    max_file_size_video: Optional[int] = Field(
        default=None,
        description="Max file upload size for videos in MB (null = use global default)",
    )
    max_file_size_audio: Optional[int] = Field(
        default=None, description="Max file upload size for audio in MB (null = use global default)"
    )
    max_file_size_document: Optional[int] = Field(
        default=None,
        description="Max file upload size for documents in MB (null = use global default)",
    )
    max_files: Optional[int] = Field(
        default=None, description="Max number of files per upload (null = use global default)"
    )

    model_config = ConfigDict(extra="allow")  # Allow future extensions


class RoleBase(BaseModel):
    """Base role schema."""

    name: str = Field(..., min_length=2, max_length=50)
    description: Optional[str] = None


class RoleCreate(RoleBase):
    """Schema for creating a role."""

    permissions: List[Permission] = Field(default_factory=list)
    allowed_agents: List[str] = Field(default_factory=list, description="List of allowed agent IDs")
    limits: Optional[RoleLimits] = Field(default=None, description="Role-specific limits")


class RoleUpdate(BaseModel):
    """Schema for updating a role."""

    name: Optional[str] = Field(None, min_length=2, max_length=50)
    description: Optional[str] = None
    permissions: Optional[List[Permission]] = None
    allowed_agents: Optional[List[str]] = None
    limits: Optional[RoleLimits] = Field(None, description="Role-specific limits")


class Role(RoleBase):
    """Role model."""

    model_config = ConfigDict(from_attributes=True, use_enum_values=True)

    id: str
    permissions: List[Permission] = Field(default_factory=list)
    allowed_agents: List[str] = Field(default_factory=list, description="List of allowed agent IDs")
    limits: Optional[RoleLimits] = Field(default=None, description="Role-specific limits")
    is_system: bool = False  # System roles cannot be deleted
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class RoleListResponse(BaseModel):
    """Paginated role list."""

    roles: List[Role]
    total: int
    skip: int
    limit: int
