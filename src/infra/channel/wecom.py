"""企业微信（WeCom）群机器人渠道

出站推送渠道：群机器人 Webhook，Markdown 消息，单条上限 4096 字节。
"""

from __future__ import annotations

from typing import Any

from src.infra.channel.outbound import OutboundChannel, OutboundChannelManager
from src.kernel.schemas.channel import ChannelCapability, ChannelConfigBase, ChannelType


class WeComConfig(ChannelConfigBase):
    """企业微信（WeCom）群机器人渠道配置。"""

    channel_type = ChannelType.WECOM
    user_id: str = ""
    instance_id: str = ""
    enabled: bool = True
    webhook_url: str = ""
    default_chat_id: str = ""

    @classmethod
    def get_schema_name(cls) -> str:
        return "wecom"

    @classmethod
    def get_capabilities(cls) -> list[ChannelCapability]:
        return [ChannelCapability.SEND_MESSAGE]


class WeComChannel(OutboundChannel):
    channel_type = ChannelType.WECOM
    display_name = "WeCom Bot"
    description = "Push notifications to WeCom (企业微信) group chats via a bot webhook"
    icon = "message-square"
    max_content_chars = 1200  # 企微 markdown 上限 4096 字节（UTF-8），留余量

    async def _send(self, *, title: str, content: str, target: str) -> bool:
        if not self.config.webhook_url:
            return False
        response = await self._post(
            self.config.webhook_url,
            json={
                "msgtype": "markdown",
                "markdown": {
                    "content": f"**{title}**\n{content[: max(0, self.max_content_chars - len(title) - 5)]}"
                },
            },
        )
        if response is None or response.is_error:
            return False
        try:
            data = response.json()
        except Exception:
            return False
        return bool(isinstance(data, dict) and data.get("errcode") == 0)

    @classmethod
    def get_config_fields(cls) -> list[dict[str, Any]]:
        return [
            {
                "name": "webhook_url",
                "title": "Webhook URL",
                "type": "text",
                "required": True,
                "sensitive": True,
                "placeholder": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=...",
            },
        ]

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return cls._build_config_schema(cls.get_config_fields())

    @classmethod
    def get_setup_guide(cls) -> list[str]:
        return [
            "Open the target WeCom group chat and add a group bot (群机器人)",
            "Copy the Webhook URL into the config above",
        ]


class WeComChannelManager(OutboundChannelManager):
    channel_type = ChannelType.WECOM
    channel_class = WeComChannel
    config_class = WeComConfig
