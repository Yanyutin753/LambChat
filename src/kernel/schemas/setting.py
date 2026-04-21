"""
Setting schemas for API request/response
"""

from enum import Enum
from typing import Any, Optional, Union

from pydantic import BaseModel, Field


class SettingDependsOn(BaseModel):
    """Setting dependency condition"""

    key: str  # Parent setting key
    value: Any  # Expected value for visibility


class SettingType(str, Enum):
    """Setting value type"""

    STRING = "string"
    TEXT = "text"  # Long text (renders as textarea)
    NUMBER = "number"
    BOOLEAN = "boolean"
    JSON = "json"
    SELECT = "select"  # Dropdown select (uses options field)


class SettingCategory(str, Enum):
    """Setting category for grouping"""

    FRONTEND = "frontend"
    AGENT = "agent"
    LLM = "llm"
    SESSION = "session"
    MONGODB = "mongodb"
    REDIS = "redis"
    CHECKPOINT = "checkpoint"
    LONG_TERM_STORAGE = "long_term_storage"
    SECURITY = "security"
    EMAIL = "email"
    CAPTCHA = "captcha"
    S3 = "s3"
    FILE_UPLOAD = "file_upload"
    SANDBOX = "sandbox"
    SKILLS = "skills"
    TOOLS = "tools"
    TRACING = "tracing"
    USER = "user"
    OAUTH = "oauth"
    MEMORY = "memory"
    MEMORY_EMBEDDING = "memory_embedding"
    MEMORY_SEARCH = "memory_search"
    MEMORY_STORAGE = "memory_storage"


class JsonSchemaField(BaseModel):
    """Field definition within a JSON schema"""

    name: str
    type: str = "text"  # text, password, number, toggle, select
    label: str  # i18n key
    placeholder: Optional[str] = None
    required: bool = False
    options: Optional[list[str]] = None  # for select type


class JsonSchema(BaseModel):
    """Schema describing the structure of a JSON-type setting"""

    type: str  # "array" or "object"
    item_label: Optional[str] = None  # i18n key for array items
    key_label: Optional[str] = None  # i18n key for object keys (object type)
    value_type: Optional[str] = None  # "array" for object values that are arrays
    key_options: Optional[list[str]] = None  # allowed keys for object type
    fields: list[JsonSchemaField] = []


class SettingItem(BaseModel):
    """Single setting item"""

    key: str
    value: Any
    type: SettingType
    category: SettingCategory
    subcategory: str = ""
    description: str = ""
    default_value: Any = None
    requires_restart: bool = False
    is_sensitive: bool = False
    frontend_visible: bool = False
    depends_on: Optional[Union[str, SettingDependsOn]] = (
        None  # Key or condition for visibility control
    )
    options: Optional[list[str]] = None  # Available options for SELECT type
    json_schema: Optional[JsonSchema] = None  # Schema for JSON-type settings
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
