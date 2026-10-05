"""ntfy 推送渠道

出站推送渠道：自建或公共 ntfy.sh 的主题订阅推送（PUT/POST /topic，标题走 Header）。
"""

from __future__ import annotations

from typing import Any

from src.infra.channel.outbound import OutboundChannel, OutboundChannelManager
from src.kernel.schemas.channel import ChannelCapability, ChannelConfigBase, ChannelType


class NtfyConfig(ChannelConfigBase):
    """ntfy 推送渠道配置。"""

    channel_type = ChannelType.NTFY
    user_id: str = ""
    instance_id: str = ""
    enabled: bool = True
    server: str = "https://ntfy.sh"
    topic: str = ""
    priority: str = "default"
    default_chat_id: str = ""

    @classmethod
    def get_schema_name(cls) -> str:
        return "ntfy"

    @classmethod
    def get_capabilities(cls) -> list[ChannelCapability]:
        return [ChannelCapability.SEND_MESSAGE]


class NtfyChannel(OutboundChannel):
    channel_type = ChannelType.NTFY
    display_name = "ntfy"
    description = "Push notifications to ntfy topics (self-hosted or ntfy.sh)"
    icon = "radio-tower"
    max_content_chars = 4000

    async def _send(self, *, title: str, content: str, target: str) -> bool:
        topic = self.config.topic
        if not topic:
            return False
        server = (self.config.server or "https://ntfy.sh").rstrip("/")
        headers = {"Title": title}
        if self.config.priority and self.config.priority != "default":
            headers["Priority"] = self.config.priority
        response = await self._post(
            f"{server}/{topic}", content=content.encode("utf-8"), headers=headers
        )
        return response is not None and not response.is_error

    @classmethod
    def get_config_fields(cls) -> list[dict[str, Any]]:
        return [
            {
                "name": "server",
                "title": "Server URL",
                "type": "text",
                "required": False,
                "sensitive": False,
                "default": "https://ntfy.sh",
                "placeholder": "https://ntfy.sh（自建改为你的域名）",
            },
            {
                "name": "topic",
                "title": "Topic",
                "type": "text",
                "required": True,
                "sensitive": False,
                "placeholder": "your-secret-topic",
            },
            {
                "name": "priority",
                "title": "Priority",
                "type": "select",
                "required": False,
                "sensitive": False,
                "default": "default",
                "options": [
                    {"value": "default", "label": "Default"},
                    {"value": "high", "label": "High"},
                    {"value": "urgent", "label": "Urgent"},
                ],
            },
        ]

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return cls._build_config_schema(cls.get_config_fields())

    @classmethod
    def get_setup_guide(cls) -> list[str]:
        return [
            "Pick a unique topic name (treat it as a password - anyone with it can read)",
            "Subscribe to the topic in the ntfy app",
            "Self-hosting? Point the server URL at your own ntfy instance",
        ]


class NtfyChannelManager(OutboundChannelManager):
    channel_type = ChannelType.NTFY
    channel_class = NtfyChannel
    config_class = NtfyConfig
