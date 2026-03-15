"""Generic channel configuration schemas.

Supports multiple chat platforms (Feishu, WeChat, DingTalk, Slack, etc.)
with a unified interface.
"""

from abc import ABC, abstractmethod
from datetime import datetime
from enum import Enum
from typing import Any, ClassVar, Optional

from pydantic import BaseModel, ConfigDict, Field


class ChannelType(str, Enum):
    """Supported channel types."""

    FEISHU = "feishu"
    # Future channels:
    # WECHAT = "wechat"
    # DINGTALK = "dingtalk"
    # SLACK = "slack"
    # TELEGRAM = "telegram"
    # DISCORD = "discord"


class ChannelCapability(str, Enum):
    """Channel capabilities."""

    WEBSOCKET = "websocket"  # Supports WebSocket long connection
    WEBHOOK = "webhook"  # Supports webhook callbacks
    SEND_MESSAGE = "send_message"  # Can send messages
    SEND_IMAGE = "send_image"  # Can send images
    SEND_FILE = "send_file"  # Can send files
    REACTIONS = "reactions"  # Supports message reactions
    GROUP_CHAT = "group_chat"  # Supports group chats
    DIRECT_MESSAGE = "direct_message"  # Supports direct messages


class GroupPolicy(str, Enum):
    """Group message handling policy."""

    OPEN = "open"  # Respond to all group messages
    MENTION = "mention"  # Respond only when mentioned


# ============================================
# Channel Configuration Base
# ============================================


class ChannelConfigBase(BaseModel, ABC):
    """Base class for channel configurations.

    Each channel type should implement its own config model.
    """

    channel_type: ClassVar[ChannelType]
    enabled: bool = Field(default=True, description="Whether the channel is enabled")

    @classmethod
    @abstractmethod
    def get_schema_name(cls) -> str:
        """Get the schema name for this channel type."""
        pass

    @classmethod
    @abstractmethod
    def get_capabilities(cls) -> list[ChannelCapability]:
        """Get the capabilities of this channel type."""
        pass


# ============================================
# Channel Configuration - Database Models
# ============================================


class ChannelConfigCreate(BaseModel):
    """Schema for creating a channel configuration.

    This is a generic wrapper that accepts different channel configs.
    """

    channel_type: ChannelType
    config: dict[str, Any]  # Channel-specific config as dict


class ChannelConfigUpdate(BaseModel):
    """Schema for updating a channel configuration."""

    model_config = ConfigDict(extra="forbid")

    config: dict[str, Any]
    enabled: Optional[bool] = None


class ChannelConfigResponse(BaseModel):
    """Channel configuration response (sensitive fields masked)."""

    channel_type: ChannelType
    user_id: str
    enabled: bool
    config: dict[str, Any]  # Masked config for display
    capabilities: list[ChannelCapability]
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class ChannelConfigStatus(BaseModel):
    """Channel connection status."""

    channel_type: ChannelType
    enabled: bool
    connected: bool = False
    error_message: Optional[str] = None
    last_connected_at: Optional[datetime] = None


# ============================================
# Channel Registry Entry
# ============================================


class ChannelMetadata(BaseModel):
    """Metadata for a channel type."""

    channel_type: ChannelType
    display_name: str
    description: str
    icon: str  # Lucide icon name
    capabilities: list[ChannelCapability]
    config_schema: dict[str, Any]  # JSON Schema for config
    requires_webhook: bool = False
    requires_websocket: bool = False
    setup_guide: list[str] = Field(default_factory=list)
    config_fields: list[dict[str, Any]] = Field(default_factory=list)


# ============================================
# Channel List Response
# ============================================


class ChannelListResponse(BaseModel):
    """List of available channels with their configurations."""

    channels: list[ChannelConfigResponse]


class ChannelTypeListResponse(BaseModel):
    """List of available channel types with metadata."""

    types: list[ChannelMetadata]
