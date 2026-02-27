"""
Setting schemas for API request/response
"""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class SettingType(str, Enum):
    """Setting value type"""

    STRING = "string"
    TEXT = "text"  # Long text (renders as textarea)
    NUMBER = "number"
    BOOLEAN = "boolean"
    JSON = "json"


class SettingCategory(str, Enum):
    """Setting category for grouping"""

    FRONTEND = "frontend"
    AGENT = "agent"
    LLM = "llm"
    SESSION = "session"
    DATABASE = "database"
    SECURITY = "security"
    S3 = "s3"
    SANDBOX = "sandbox"
    FEATURES = "features"
    TOOLS = "tools"
    TRACING = "tracing"
    USER = "user"


class SettingItem(BaseModel):
    """Single setting item"""

    key: str
    value: Any
    type: SettingType
    category: SettingCategory
    description: str = ""
    default_value: Any = None
    requires_restart: bool = False
    is_sensitive: bool = False
    frontend_visible: bool = False
    updated_at: Optional[str] = None
    updated_by: Optional[str] = None


class SettingUpdate(BaseModel):
    """Setting update request"""

    value: Any


class SettingsResponse(BaseModel):
    """Settings grouped by category"""

    settings: dict[str, list[SettingItem]] = Field(default_factory=dict)


class SettingUpdateResponse(BaseModel):
    """Response after updating a setting"""

    setting: SettingItem
    message: str
    requires_restart: bool


class SettingResetResponse(BaseModel):
    """Reset response"""

    message: str
    reset_count: int
