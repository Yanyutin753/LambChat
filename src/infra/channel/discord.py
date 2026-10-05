"""Discord Webhook 渠道

出站推送渠道：频道 Webhook，纯文本 content 消息。
"""

from __future__ import annotations

from typing import Any

from src.infra.channel.outbound import OutboundChannel, OutboundChannelManager
from src.kernel.schemas.channel import ChannelCapability, ChannelConfigBase, ChannelType


class DiscordConfig(ChannelConfigBase):
    """Discord Webhook 渠道配置。"""

    channel_type = ChannelType.DISCORD
    user_id: str = ""
    instance_id: str = ""
    enabled: bool = True
    webhook_url: str = ""
    default_chat_id: str = ""

    @classmethod
    def get_schema_name(cls) -> str:
        return "discord"

    @classmethod
    def get_capabilities(cls) -> list[ChannelCapability]:
        return [ChannelCapability.SEND_MESSAGE]


class DiscordChannel(OutboundChannel):
    channel_type = ChannelType.DISCORD
    display_name = "Discord"
    description = "Push notifications to a Discord channel via a webhook"
    icon = "gamepad-2"
    max_content_chars = 2000  # Discord 消息硬上限

    async def _send(self, *, title: str, content: str, target: str) -> bool:
        if not self.config.webhook_url:
            return False
        response = await self._post(
            self.config.webhook_url,
            json={
                "content": f"**{title}**\n{content[: max(0, self.max_content_chars - len(title) - 5)]}"
            },
        )
        return response is not None and not response.is_error

    @classmethod
    def get_config_fields(cls) -> list[dict[str, Any]]:
        return [
            {
                "name": "webhook_url",
                "title": "Webhook URL",
                "type": "text",
                "required": True,
                "sensitive": True,
                "placeholder": "https://discord.com/api/webhooks/...",
            },
        ]

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return cls._build_config_schema(cls.get_config_fields())

    @classmethod
    def get_setup_guide(cls) -> list[str]:
        return [
            "Open the target channel settings -> Integrations -> Webhooks",
            "Create a webhook, copy its URL into the config above",
        ]


class DiscordChannelManager(OutboundChannelManager):
    channel_type = ChannelType.DISCORD
    channel_class = DiscordChannel
    config_class = DiscordConfig
