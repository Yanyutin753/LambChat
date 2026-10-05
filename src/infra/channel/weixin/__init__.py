"""微信 iLink Bot 渠道。"""

from src.infra.channel.weixin.channel import WeixinChannel
from src.infra.channel.weixin.manager import (
    WeixinChannelManager,
    get_weixin_channel_manager,
    setup_weixin_handler,
    stop_weixin_channels,
)

__all__ = [
    "WeixinChannel",
    "WeixinChannelManager",
    "get_weixin_channel_manager",
    "setup_weixin_handler",
    "stop_weixin_channels",
]
