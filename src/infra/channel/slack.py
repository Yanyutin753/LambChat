"""Slack Incoming Webhook 渠道

出站推送渠道：单个 Webhook URL 直推指定频道。
"""

from __future__ import annotations

from typing import Any

from src.infra.channel.outbound import OutboundChannel, OutboundChannelManager
from src.kernel.schemas.channel import ChannelCapability, ChannelConfigBase, ChannelType


class SlackConfig(ChannelConfigBase):
    """Slack Incoming Webhook 渠道配置。"""

    channel_type = ChannelType.SLACK
    user_id: str = ""
    instance_id: str = ""
    enabled: bool = True
    webhook_url: str = ""
    default_chat_id: str = ""

    @classmethod
    def get_schema_name(cls) -> str:
        return "slack"

    @classmethod
    def get_capabilities(cls) -> list[ChannelCapability]:
        return [ChannelCapability.SEND_MESSAGE]


class SlackChannel(OutboundChannel):
    channel_type = ChannelType.SLACK
    display_name = "Slack"
    description = "Push notifications to a Slack channel via an incoming webhook"
    icon = "hash"
    max_content_chars = 35000  # Slack text block 上限 40000 字符

    async def _send(self, *, title: str, content: str, target: str) -> bool:
        if not self.config.webhook_url:
            return False
        response = await self._post(self.config.webhook_url, json={"text": content})
        if response is None or response.is_error:
            return False
        # Slack 成功返回 200 + body "ok"；4xx（invalid_payload 等）由 is_error 兜住
        return True

    @classmethod
    def get_config_fields(cls) -> list[dict[str, Any]]:
        return [
            {
                "name": "webhook_url",
                "title": "Webhook URL",
                "type": "text",
                "required": True,
                "sensitive": True,
                "placeholder": "https://hooks.slack.com/services/T.../B.../...",
            },
        ]

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return cls._build_config_schema(cls.get_config_fields())

    @classmethod
    def get_setup_guide(cls) -> list[str]:
        return [
            "Create an incoming webhook at api.slack.com/messaging/webhooks",
            "Choose the target channel and copy the webhook URL",
        ]


class SlackChannelManager(OutboundChannelManager):
    channel_type = ChannelType.SLACK
    channel_class = SlackChannel
    config_class = SlackConfig
