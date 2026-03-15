"""Feishu/Lark channel configuration schemas."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class FeishuGroupPolicy(str, Enum):
    """Group message handling policy."""

    OPEN = "open"  # Respond to all group messages
    MENTION = "mention"  # Respond only when @mentioned


class FeishuConfigBase(BaseModel):
    """Base Feishu configuration schema."""

    app_id: str = Field(..., description="Feishu/Lark App ID")
    app_secret: str = Field(..., description="Feishu/Lark App Secret")
    encrypt_key: str = Field("", description="Encrypt key for event encryption (optional)")
    verification_token: str = Field(
        "", description="Verification token for event verification (optional)"
    )
    react_emoji: str = Field("THUMBSUP", description="Emoji reaction when receiving a message")
    group_policy: FeishuGroupPolicy = Field(
        FeishuGroupPolicy.MENTION, description="Group message policy"
    )
    enabled: bool = Field(True, description="Whether the channel is enabled")


class FeishuConfigCreate(FeishuConfigBase):
    """Schema for creating Feishu configuration."""

    pass


class FeishuConfigUpdate(BaseModel):
    """Schema for updating Feishu configuration."""

    model_config = ConfigDict(extra="forbid")

    app_id: Optional[str] = None
    app_secret: Optional[str] = None
    encrypt_key: Optional[str] = None
    verification_token: Optional[str] = None
    react_emoji: Optional[str] = None
    group_policy: Optional[FeishuGroupPolicy] = None
    enabled: Optional[bool] = None


class FeishuConfig(FeishuConfigBase):
    """Feishu configuration model (database view)."""

    user_id: str
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    class Config:
        from_attributes = True


class FeishuConfigResponse(BaseModel):
    """Feishu configuration response (masked sensitive fields)."""

    user_id: str
    app_id: str  # Can show app_id (not sensitive)
    has_app_secret: bool  # Only show if secret is set
    encrypt_key: str = ""  # Masked
    verification_token: str = ""  # Masked
    react_emoji: str = "THUMBSUP"
    group_policy: FeishuGroupPolicy = FeishuGroupPolicy.MENTION
    enabled: bool = True
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class FeishuConfigStatus(BaseModel):
    """Feishu connection status."""

    enabled: bool
    connected: bool = False
    error_message: Optional[str] = None
    last_connected_at: Optional[datetime] = None
