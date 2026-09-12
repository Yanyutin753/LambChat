"""插件中心 Pydantic 模型。"""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator

from src.infra.utils.datetime import utc_now


class PluginStatus(str, Enum):
    """插件在平台商店中的状态。"""

    DRAFT = "draft"
    ACTIVE = "active"
    DEACTIVATED = "deactivated"


class PluginSkillPayload(BaseModel):
    """插件携带的单个技能负载声明。"""

    skill_name: str = Field(..., min_length=1, max_length=100)
    description: str = Field(default="", max_length=1000)
    tags: list[str] = Field(default_factory=list)


class PluginMcpServerPayload(BaseModel):
    """插件携带的 MCP server 声明。

    ref=True 表示引用平台既有 system server（按名字），不携带配置；
    ref=False 时为 inline 配置，激活时物化为 system_mcp_servers。
    """

    name: str = Field(..., min_length=1, max_length=100)
    transport: str = Field(..., pattern="^(sse|streamable_http)$")
    url: Optional[str] = Field(None, max_length=2048)
    headers: Optional[dict[str, str]] = None
    ref: bool = False
    enabled: bool = True


class PluginPersonaPayload(BaseModel):
    """插件可选携带的角色预设负载（安装时复制为用户私有草稿）。"""

    name: str = Field(..., min_length=1, max_length=80)
    description: str = Field(default="", max_length=500)
    avatar: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    system_prompt: str = Field(..., min_length=1)
    starter_prompts: list[dict] = Field(default_factory=list)


class PluginBase(BaseModel):
    """插件元数据与负载。"""

    name: str = Field(..., min_length=1, max_length=64, pattern="^[a-z0-9][a-z0-9_-]*$")
    display_name: str = Field(default="", max_length=120)
    description: str = Field(default="", max_length=2000)
    version: str = Field(default="1.0.0", max_length=32)
    author_name: str = Field(default="", max_length=80)
    tags: list[str] = Field(default_factory=list)
    skills: list[PluginSkillPayload] = Field(default_factory=list)
    mcp_servers: list[PluginMcpServerPayload] = Field(default_factory=list)
    persona: Optional[PluginPersonaPayload] = None

    @field_validator("tags")
    @classmethod
    def _dedupe_tags(cls, values: list[str]) -> list[str]:
        seen: set[str] = set()
        result: list[str] = []
        for value in values:
            item = value.strip()
            if item and item not in seen:
                seen.add(item)
                result.append(item)
        return result


class PluginCreate(PluginBase):
    """创建插件请求。"""

    activate: bool = False


class PluginUpdate(BaseModel):
    """更新插件请求（仅创建者或 admin）。"""

    display_name: Optional[str] = Field(None, max_length=120)
    description: Optional[str] = Field(None, max_length=2000)
    version: Optional[str] = Field(None, max_length=32)
    author_name: Optional[str] = Field(None, max_length=80)
    tags: Optional[list[str]] = None
    skills: Optional[list[PluginSkillPayload]] = None
    mcp_servers: Optional[list[PluginMcpServerPayload]] = None
    persona: Optional[PluginPersonaPayload] = None


class PluginSkillFilePayload(BaseModel):
    """插件技能文件写入请求。"""

    content: str = Field(..., max_length=512 * 1024)


class PluginResponse(BaseModel):
    """插件详情/列表项响应。"""

    name: str
    display_name: str = ""
    description: str = ""
    version: str = "1.0.0"
    author_name: str = ""
    tags: list[str] = Field(default_factory=list)
    skills: list[PluginSkillPayload] = Field(default_factory=list)
    mcp_servers: list[PluginMcpServerPayload] = Field(default_factory=list)
    persona: Optional[PluginPersonaPayload] = None
    status: PluginStatus = PluginStatus.DRAFT
    created_by: Optional[str] = None
    created_by_username: Optional[str] = None
    install_count: int = 0
    is_owner: bool = False
    installed: bool = False
    installed_version: Optional[str] = None
    migrated_from: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    @property
    def skill_count(self) -> int:
        return len(self.skills)

    @property
    def mcp_count(self) -> int:
        return len(self.mcp_servers)

    @property
    def has_persona(self) -> bool:
        return self.persona is not None


class PluginListResponse(BaseModel):
    """分页插件列表。"""

    plugins: list[PluginResponse]
    total: int
    skip: int = 0
    limit: int = 50


class PluginInstallResponse(BaseModel):
    """安装/更新插件结果。"""

    message: str
    plugin_name: str
    version: str
    installed_skills: list[str] = Field(default_factory=list)
    persona_created: bool = False


class PluginInstallRecord(BaseModel):
    """用户已安装插件记录。"""

    plugin_name: str
    version: str
    installed_at: datetime = Field(default_factory=utc_now)


class PluginInstalledListResponse(BaseModel):
    """用户已安装插件列表。"""

    installs: list[PluginInstallRecord]
    total: int


class PluginTagsResponse(BaseModel):
    """插件标签列表。"""

    tags: list[str]
