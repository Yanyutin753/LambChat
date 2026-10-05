"""PushPlus 推送渠道

出站推送渠道：pushplus.plus 微信推送（markdown 模板）。
"""

from __future__ import annotations

from typing import Any

from src.infra.channel.outbound import OutboundChannel, OutboundChannelManager
from src.kernel.schemas.channel import ChannelCapability, ChannelConfigBase, ChannelType


class PushPlusConfig(ChannelConfigBase):
    """PushPlus 推送渠道配置。"""

    channel_type = ChannelType.PUSHPLUS
    user_id: str = ""
    instance_id: str = ""
    enabled: bool = True
    token: str = ""
    template: str = "markdown"
    default_chat_id: str = ""

    @classmethod
    def get_schema_name(cls) -> str:
        return "pushplus"

    @classmethod
    def get_capabilities(cls) -> list[ChannelCapability]:
        return [ChannelCapability.SEND_MESSAGE]


class PushPlusChannel(OutboundChannel):
    channel_type = ChannelType.PUSHPLUS
    display_name = "PushPlus"
    description = "Push notifications to WeChat via PushPlus"
    icon = "zap"
    max_content_chars = 10000

    async def _send(self, *, title: str, content: str, target: str) -> bool:
        if not self.config.token:
            return False
        response = await self._post(
            "https://www.pushplus.plus/send",
            json={
                "token": self.config.token,
                "title": title,
                "content": content,
                "template": self.config.template or "markdown",
            },
        )
        if response is None or response.is_error:
            return False
        try:
            data = response.json()
        except Exception:
            return False
        return bool(isinstance(data, dict) and data.get("code") == 200)

    @classmethod
    def get_config_fields(cls) -> list[dict[str, Any]]:
        return [
            {
                "name": "token",
                "title": "Token",
                "type": "password",
                "required": True,
                "sensitive": True,
                "placeholder": "pushplus.plus 用户中心的 token",
            },
            {
                "name": "template",
                "title": "Template",
                "type": "select",
                "required": False,
                "sensitive": False,
                "default": "markdown",
                "options": [
                    {"value": "markdown", "label": "Markdown"},
                    {"value": "html", "label": "HTML"},
                    {"value": "txt", "label": "Plain text"},
                ],
            },
        ]

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return cls._build_config_schema(cls.get_config_fields())

    @classmethod
    def get_setup_guide(cls) -> list[str]:
        return [
            "Log in to pushplus.plus with WeChat and copy your token",
            "Messages arrive in your WeChat via the PushPlus official account",
        ]


class PushPlusChannelManager(OutboundChannelManager):
    channel_type = ChannelType.PUSHPLUS
    channel_class = PushPlusChannel
    config_class = PushPlusConfig
