from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class InstalledFrom(str, Enum):
    """Skill 安装来源"""

    BUILTIN = "builtin"
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


class SkillToggle(BaseModel):
    """用户 Skill 开关"""

    skill_name: str
    user_id: str
    enabled: bool = True
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
    files: list[str] = Field(default_factory=list, description="文件路径列表")
    enabled: bool = True
    installed_from: Optional[str] = None
    published_marketplace_name: Optional[str] = None
    file_count: int = 0
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    is_published: bool = False
    marketplace_is_active: bool = True


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


class PublishToMarketplaceRequest(BaseModel):
    """发布到商店的请求（可选覆盖 metadata）"""

    skill_name: Optional[str] = None
    description: Optional[str] = None
    tags: Optional[list[str]] = None
    version: Optional[str] = None
