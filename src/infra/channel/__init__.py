"""Channel infrastructure module.

Provides abstract base classes, registry, and implementations for
various chat platform integrations (Feishu, WeChat, DingTalk, etc.).
"""

from src.infra.channel.base import BaseChannel, UserChannelManager
from src.infra.channel.channel_storage import ChannelStorage
from src.infra.channel.feishu_handler import (
    FeishuResponseCollector,
    create_feishu_message_handler,
    execute_feishu_agent,
    setup_feishu_handler,
)
from src.infra.channel.feishu_storage import FeishuStorage
from src.infra.channel.manager import (
    ChannelCoordinator,
    get_channel_coordinator,
    start_channels,
    stop_channels,
)
from src.infra.channel.registry import ChannelRegistry, get_registry

__all__ = [
    # Base classes
    "BaseChannel",
    "UserChannelManager",
    # Registry
    "ChannelRegistry",
    "get_registry",
    # Coordinator
    "ChannelCoordinator",
    "get_channel_coordinator",
    "start_channels",
    "stop_channels",
    # Storage
    "ChannelStorage",
    "FeishuStorage",
    # Feishu Handler
    "FeishuResponseCollector",
    "create_feishu_message_handler",
    "execute_feishu_agent",
    "setup_feishu_handler",
]
