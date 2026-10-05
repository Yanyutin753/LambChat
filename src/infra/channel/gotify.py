"""Gotify 推送渠道

出站推送渠道：自建 Gotify 服务（POST /message?token=，应用令牌认证）。
"""

from __future__ import annotations

from typing import Any

from src.infra.channel.outbound import OutboundChannel, OutboundChannelManager
from src.kernel.schemas.channel import ChannelCapability, ChannelConfigBase, ChannelType


class GotifyConfig(ChannelConfigBase):
    """Gotify 推送渠道配置。"""

    channel_type = ChannelType.GOTIFY
    user_id: str = ""
    instance_id: str = ""
    enabled: bool = True
    server: str = ""
    app_token: str = ""
    priority: int = 5
    default_chat_id: str = ""

    @classmethod
    def get_schema_name(cls) -> str:
        return "gotify"

    @classmethod
    def get_capabilities(cls) -> list[ChannelCapability]:
        return [ChannelCapability.SEND_MESSAGE]


class GotifyChannel(OutboundChannel):
    channel_type = ChannelType.GOTIFY
    display_name = "Gotify"
    description = "Push notifications to a self-hosted Gotify server"
    icon = "bell"
    max_content_chars = 8000

    async def _send(self, *, title: str, content: str, target: str) -> bool:
        if not self.config.server or not self.config.app_token:
            return False
        server = self.config.server.rstrip("/")
        from urllib.parse import quote

        url = f"{server}/message?token={quote(self.config.app_token)}"
        response = await self._post(
            url,
            json={"title": title, "message": content, "priority": self.config.priority},
        )
        return response is not None and not response.is_error

    @classmethod
    def get_config_fields(cls) -> list[dict[str, Any]]:
        return [
            {
                "name": "server",
                "title": "Server URL",
                "type": "text",
                "required": True,
                "sensitive": False,
                "placeholder": "https://gotify.example.com",
            },
            {
                "name": "app_token",
                "title": "App Token",
                "type": "password",
                "required": True,
                "sensitive": True,
                "placeholder": "Gotify 应用创建后的 token",
            },
            {
                "name": "priority",
                "title": "Priority",
                "type": "select",
                "required": False,
                "sensitive": False,
                "default": 5,
                "options": [
                    {"value": 3, "label": "Low (3)"},
                    {"value": 5, "label": "Default (5)"},
                    {"value": 8, "label": "High (8)"},
                ],
            },
        ]

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return cls._build_config_schema(cls.get_config_fields())

    @classmethod
    def get_setup_guide(cls) -> list[str]:
        return [
            "Create an application in your Gotify server and copy its token",
            "Fill in the server URL and app token above",
        ]


class GotifyChannelManager(OutboundChannelManager):
    channel_type = ChannelType.GOTIFY
    channel_class = GotifyChannel
    config_class = GotifyConfig
