"""Role-related schemas."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field

from src.kernel.types import Permission


class RoleLimits(BaseModel):
    """Role-specific limits configuration."""

    max_channels: Optional[int] = Field(
        default=None, description="Maximum number of channels allowed (null = unlimited)"
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
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
