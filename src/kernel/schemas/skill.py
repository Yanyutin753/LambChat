"""
Skill schemas for API request/response

Follows the same pattern as MCP schemas for consistency.
"""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class SkillSource(str, Enum):
    """Skill source type"""

    BUILTIN = "builtin"
    GITHUB = "github"
    MANUAL = "manual"


class SkillBase(BaseModel):
    """Base skill configuration"""

    name: str = Field(..., description="Skill name (unique identifier)")
    description: str = Field("", description="Skill description")
    content: str = Field("", description="Skill content (full SKILL.md), used when files is empty")
    enabled: bool = Field(True, description="Whether skill is enabled")
    files: dict[str, str] = Field(
        default_factory=dict,
        description="Skill files dict, key is file path relative to skill root (e.g., 'SKILL.md', 'templates/main.py')",
    )


class SkillCreate(SkillBase):
    """Schema for creating a new skill"""

    source: SkillSource = Field(SkillSource.MANUAL, description="Skill source")
    github_url: Optional[str] = Field(None, description="GitHub source URL")
    version: Optional[str] = Field(None, description="Version number")


class SkillUpdate(BaseModel):
    """Schema for updating a skill"""

    name: Optional[str] = None
    description: Optional[str] = None
    content: Optional[str] = None
    enabled: Optional[bool] = None
    version: Optional[str] = None
    files: Optional[dict[str, str]] = None
    is_system: Optional[bool] = Field(
        None, description="Change skill type (admin can change system/user)"
    )


class SystemSkill(SkillBase):
    """System-level skill configuration (admin managed)"""

    source: SkillSource = Field(SkillSource.MANUAL, description="Skill source")
    github_url: Optional[str] = Field(None, description="GitHub source URL")
    version: Optional[str] = Field(None, description="Version number")
    is_system: bool = Field(True, description="Always True for system skills")
    created_at: Optional[str] = Field(None, description="Creation timestamp")
    updated_at: Optional[str] = Field(None, description="Last update timestamp")
    updated_by: Optional[str] = Field(None, description="Admin user ID who last updated")


class UserSkill(SkillBase):
    """User-level skill configuration"""

    source: SkillSource = Field(SkillSource.MANUAL, description="Skill source")
    github_url: Optional[str] = Field(None, description="GitHub source URL")
    version: Optional[str] = Field(None, description="Version number")
    user_id: str = Field(..., description="Owner user ID")
    is_system: bool = Field(False, description="Always False for user skills")
    created_at: Optional[str] = Field(None, description="Creation timestamp")
    updated_at: Optional[str] = Field(None, description="Last update timestamp")


class SkillResponse(SkillBase):
    """Skill response with additional metadata"""

    source: SkillSource = Field(SkillSource.MANUAL, description="Skill source")
    github_url: Optional[str] = Field(None, description="GitHub source URL")
    version: Optional[str] = Field(None, description="Version number")
    is_system: bool = Field(..., description="Whether this is a system skill")
    can_edit: bool = Field(..., description="Whether current user can edit this skill")
    created_at: Optional[str] = Field(None, description="Creation timestamp")
    updated_at: Optional[str] = Field(None, description="Last update timestamp")


class SkillsResponse(BaseModel):
    """Response containing list of skills"""

    skills: list[SkillResponse] = Field(default_factory=list)
    total: int = Field(0, description="Total number of skills")


class SkillToggleResponse(BaseModel):
    """Response after toggling skill enabled status"""

    skill: SkillResponse
    message: str


class SkillImportRequest(BaseModel):
    """Request to import skills from JSON"""

    skills: dict[str, dict[str, Any]] = Field(..., description="Skills config")
    overwrite: bool = Field(False, description="Overwrite existing skills with same name")


class SkillImportResponse(BaseModel):
    """Response after importing skills"""

    message: str
    imported_count: int
    skipped_count: int
    errors: list[str] = Field(default_factory=list)


class SkillExportResponse(BaseModel):
    """Response for exporting skill configuration"""

    skills: dict[str, dict[str, Any]] = Field(default_factory=dict)


class SkillMoveRequest(BaseModel):
    """Request to move a skill between user and system"""

    target_user_id: Optional[str] = Field(
        None, description="Target user ID when demoting system skill to user skill"
    )


class SkillMoveResponse(BaseModel):
    """Response after moving a skill"""

    skill: SkillResponse
    message: str
    from_type: str = Field(..., description="Original skill type (user/system)")
    to_type: str = Field(..., description="New skill type (user/system)")


# GitHub Sync related schemas


class GitHubSkillPreview(BaseModel):
    """Preview of a skill from GitHub repository"""

    name: str = Field(..., description="Skill name")
    description: str = Field("", description="Skill description")
    path: str = Field(..., description="Path in repository")
    files: list[str] = Field(default_factory=list, description="List of files in this skill")


class GitHubPreviewResponse(BaseModel):
    """Response for GitHub repository preview"""

    repo_url: str = Field(..., description="Repository URL")
    skills: list[GitHubSkillPreview] = Field(default_factory=list)


class GitHubInstallRequest(BaseModel):
    """Request to install skills from GitHub repository"""

    repo_url: str = Field(..., description="GitHub repository URL")
    branch: str = Field("main", description="Branch name")
    skill_names: Optional[list[str]] = Field(
        None, description="Specific skills to install (all if not specified)"
    )
    as_system: bool = Field(False, description="Install as system skills (admin only)")
