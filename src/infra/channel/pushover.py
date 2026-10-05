"""Pushover 推送渠道

出站推送渠道：官方 API（form 表单，应用 token + 用户 key）。
"""

from __future__ import annotations

from typing import Any

from src.infra.channel.outbound import OutboundChannel, OutboundChannelManager
from src.kernel.schemas.channel import ChannelCapability, ChannelConfigBase, ChannelType


class PushoverConfig(ChannelConfigBase):
    """Pushover 推送渠道配置。"""

    channel_type = ChannelType.PUSHOVER
    user_id: str = ""
    instance_id: str = ""
    enabled: bool = True
    api_token: str = ""
    user_key: str = ""
    default_chat_id: str = ""

    @classmethod
    def get_schema_name(cls) -> str:
        return "pushover"

    @classmethod
    def get_capabilities(cls) -> list[ChannelCapability]:
        return [ChannelCapability.SEND_MESSAGE]


class PushoverChannel(OutboundChannel):
    channel_type = ChannelType.PUSHOVER
    display_name = "Pushover"
    description = "Push notifications to devices via Pushover"
    icon = "megaphone"
    max_content_chars = 1000  # Pushover message 建议 ≤1024 字符

    async def _send(self, *, title: str, content: str, target: str) -> bool:
        if not self.config.api_token or not self.config.user_key:
            return False
        response = await self._post(
            "https://api.pushover.net/1/messages.json",
            data={
                "token": self.config.api_token,
                "user": self.config.user_key,
                "title": title,
                "message": content,
            },
        )
        if response is None or response.is_error:
            return False
        try:
            data = response.json()
        except Exception:
            return False
        return bool(isinstance(data, dict) and data.get("status") == 1)

    @classmethod
    def get_config_fields(cls) -> list[dict[str, Any]]:
        return [
            {
                "name": "api_token",
                "title": "API Token",
                "type": "password",
                "required": True,
                "sensitive": True,
                "placeholder": "pushover.net 创建应用后的 token",
            },
            {
                "name": "user_key",
                "title": "User Key",
                "type": "password",
                "required": True,
                "sensitive": True,
                "placeholder": "pushover.net 用户主页的 key",
            },
        ]

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return cls._build_config_schema(cls.get_config_fields())

    @classmethod
    def get_setup_guide(cls) -> list[str]:
        return [
            "Create an application at pushover.net and copy the API token",
            "Copy your user key from the Pushover dashboard",
        ]


class PushoverChannelManager(OutboundChannelManager):
    channel_type = ChannelType.PUSHOVER
    channel_class = PushoverChannel
    config_class = PushoverConfig
