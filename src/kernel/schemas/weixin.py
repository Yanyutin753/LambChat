"""微信 iLink Bot 渠道配置模型。

token 由扫码登录（/api/channels/weixin/registrations）获得；
group_policy 控制群聊（room 消息）是否触发 agent。
"""

from pydantic import Field

from src.kernel.schemas.channel import ChannelCapability, ChannelConfigBase, ChannelType


class WeixinGroupPolicy:
    """群聊消息处理策略。"""

    OPEN = "open"  # 群聊（room）与私聊都响应
    OFF = "off"  # 仅私聊


class WeixinConfig(ChannelConfigBase):
    """微信 iLink Bot 配置。"""

    channel_type = ChannelType.WEIXIN
    user_id: str = ""
    instance_id: str = ""
    bot_token: str = ""
    default_chat_id: str = Field("", description="出站推送默认目标（微信 user id / room id）")
    group_policy: str = Field(WeixinGroupPolicy.OPEN, description="群聊消息处理策略 open|off")

    @classmethod
    def get_schema_name(cls) -> str:
        return "weixin"

    @classmethod
    def get_capabilities(cls) -> list[ChannelCapability]:
        return [
            ChannelCapability.SEND_MESSAGE,
            ChannelCapability.DIRECT_MESSAGE,
            ChannelCapability.GROUP_CHAT,
        ]
