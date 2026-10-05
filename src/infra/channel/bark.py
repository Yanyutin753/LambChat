"""Bark（iOS）推送渠道

出站推送渠道：自建或官方 Bark 服务的设备推送（POST /push）。
"""

from __future__ import annotations

from typing import Any

from src.infra.channel.outbound import OutboundChannel, OutboundChannelManager
from src.kernel.schemas.channel import ChannelCapability, ChannelConfigBase, ChannelType


class BarkConfig(ChannelConfigBase):
    """Bark（iOS）推送渠道配置。"""

    channel_type = ChannelType.BARK
    user_id: str = ""
    instance_id: str = ""
    enabled: bool = True
    server: str = "https://api.day.app"
    device_key: str = ""
    group: str = "LambChat"
    default_chat_id: str = ""

    @classmethod
    def get_schema_name(cls) -> str:
        return "bark"

    @classmethod
    def get_capabilities(cls) -> list[ChannelCapability]:
        return [ChannelCapability.SEND_MESSAGE]


class BarkChannel(OutboundChannel):
    channel_type = ChannelType.BARK
    display_name = "Bark"
    description = "Push notifications to iOS via the Bark app"
    icon = "dog"
    max_content_chars = 3000

    async def _send(self, *, title: str, content: str, target: str) -> bool:
        if not self.config.device_key:
            return False
        server = (self.config.server or "https://api.day.app").rstrip("/")
        response = await self._post(
            f"{server}/push",
            json={
                "device_key": self.config.device_key,
                "title": title,
                "body": content,
                "group": self.config.group or "LambChat",
            },
        )
        if response is None or response.is_error:
            return False
        try:
            data = response.json()
        except Exception:
            return True  # 2xx 即视为送达（部分自建端点返回非 JSON）
        return bool(isinstance(data, dict) and data.get("code") == 200)

    @classmethod
    def get_config_fields(cls) -> list[dict[str, Any]]:
        return [
            {
                "name": "server",
                "title": "Server URL",
                "type": "text",
                "required": False,
                "sensitive": False,
                "default": "https://api.day.app",
                "placeholder": "https://api.day.app（自建改为你的域名）",
            },
            {
                "name": "device_key",
                "title": "Device Key",
                "type": "password",
                "required": True,
                "sensitive": True,
                "placeholder": "App 首页复制的 Key",
            },
            {
                "name": "group",
                "title": "Group",
                "type": "text",
                "required": False,
                "sensitive": False,
                "default": "LambChat",
            },
        ]

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return cls._build_config_schema(cls.get_config_fields())

    @classmethod
    def get_setup_guide(cls) -> list[str]:
        return [
            "Install the Bark app from the App Store",
            "Copy the device key shown on the app home screen",
        ]


class BarkChannelManager(OutboundChannelManager):
    channel_type = ChannelType.BARK
    channel_class = BarkChannel
    config_class = BarkConfig
