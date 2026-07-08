from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from src.kernel.extensions.marketplace import (
    ExtensionMarketplaceEntry,
    build_skill_marketplace_entry,
)


class InstalledFrom(str, Enum):
    """Skill 安装来源"""

    MARKETPLACE = "marketplace"
    MANUAL = "manual"


class MarketplaceSkill(BaseModel):
    """商城 Skill 元数据"""

    skill_name: str = Field(..., description="Skill 名称（唯一标识）")
    description: str = Field("", description="Skill 描述")
    tags: list[str] = Field(default_factory=list, description="标签列表")
    version: str = Field("1.0.0", description="版本号")
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    created_by: Optional[str] = None
    is_active: bool = True


class MarketplaceSkillCreate(BaseModel):
    """创建商城 Skill 请求"""

    skill_name: str = Field(..., description="Skill 名称")
    description: str = Field("", description="Skill 描述")
    tags: list[str] = Field(default_factory=list, description="标签列表")
    version: str = Field("1.0.0", description="版本号")


class MarketplaceSkillUpdate(BaseModel):
    """更新商城 Skill 请求"""

    description: Optional[str] = None
    tags: Optional[list[str]] = None
    version: Optional[str] = None
    is_active: Optional[bool] = None


class SkillMeta(BaseModel):
    """Skill metadata stored as __meta__ doc in skill_files"""

    installed_from: InstalledFrom = InstalledFrom.MANUAL
    published_marketplace_name: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class SkillFile(BaseModel):
    """Skill 文件"""

    skill_name: str
    user_id: str
    file_path: str
    content: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class UserSkill(BaseModel):
    """用户 Skill 响应"""

    skill_name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list, description="标签列表")
    files: list[str] = Field(default_factory=list, description="文件路径列表")
    enabled: bool = True
    installed_from: Optional[str] = None
    published_marketplace_name: Optional[str] = None
    file_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    is_published: bool = False
    marketplace_is_active: bool = True
    is_favorite: bool = False
    is_pinned: bool = False


class UserSkillPreferenceUpdate(BaseModel):
    """Update the current user's presentation preferences for a skill."""

    is_favorite: Optional[bool] = None
    is_pinned: Optional[bool] = None


class UserSkillPreferenceResponse(BaseModel):
    """Current user's presentation preferences for a skill."""

    skill_name: str
    is_favorite: bool = False
    is_pinned: bool = False


class UserSkillListResponse(BaseModel):
    """Paginated user skill list."""

    skills: list[UserSkill] = Field(default_factory=list)
    total: int = 0
    enabled_count: int = 0
    skip: int = 0
    limit: int = 100
    available_tags: list[str] = Field(default_factory=list)


class MarketplaceSkillResponse(BaseModel):
    """商城 Skill 响应"""

    skill_name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    version: str = "1.0.0"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    created_by: Optional[str] = None
    created_by_username: Optional[str] = None
    is_active: bool = True
    is_owner: bool = False
    file_count: int = 0
    extension_type: str = "skill"
    extension_id: Optional[str] = None
    extension: Optional[ExtensionMarketplaceEntry] = None

    @model_validator(mode="after")
    def attach_extension_marketplace_entry(self) -> "MarketplaceSkillResponse":
        """Expose legacy Skill marketplace data through Extension Marketplace shape."""
        if self.extension_id is None:
            self.extension_id = f"skill:{self.skill_name}"
        if self.extension is None:
            self.extension = build_skill_marketplace_entry(
                skill_name=self.skill_name,
                description=self.description,
                tags=self.tags,
                version=self.version,
                publisher=self.created_by_username or self.created_by,
                enabled=self.is_active,
                file_count=self.file_count,
            )
        return self


class PublishToMarketplaceRequest(BaseModel):
    """发布到商店的请求（可选覆盖 metadata）"""

    skill_name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[list[str]] = None
    version: Optional[str] = None
