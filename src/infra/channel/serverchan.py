"""Server酱（ServerChan）渠道

出站推送渠道：sctapi.ftqq.com SendKey 推送（微信服务号收信）。
"""

from __future__ import annotations

from typing import Any

from src.infra.channel.outbound import OutboundChannel, OutboundChannelManager
from src.kernel.schemas.channel import ChannelCapability, ChannelConfigBase, ChannelType


class ServerChanConfig(ChannelConfigBase):
    """Server酱（ServerChan）渠道配置。"""

    channel_type = ChannelType.SERVERCHAN
    user_id: str = ""
    instance_id: str = ""
    enabled: bool = True
    send_key: str = ""
    default_chat_id: str = ""

    @classmethod
    def get_schema_name(cls) -> str:
        return "serverchan"

    @classmethod
    def get_capabilities(cls) -> list[ChannelCapability]:
        return [ChannelCapability.SEND_MESSAGE]


class ServerChanChannel(OutboundChannel):
    channel_type = ChannelType.SERVERCHAN
    display_name = "ServerChan"
    description = "Push notifications to WeChat via Server酱 (ServerChan)"
    icon = "send-horizontal"
    max_content_chars = 10000  # Server酱 desp（markdown）上限 32KB

    async def _send(self, *, title: str, content: str, target: str) -> bool:
        if not self.config.send_key:
            return False
        response = await self._post(
            f"https://sctapi.ftqq.com/{self.config.send_key}.send",
            data={"title": title, "desp": content},
        )
        if response is None or response.is_error:
            return False
        try:
            data = response.json()
        except Exception:
            return False
        return bool(isinstance(data, dict) and data.get("code") == 0)

    @classmethod
    def get_config_fields(cls) -> list[dict[str, Any]]:
        return [
            {
                "name": "send_key",
                "title": "SendKey",
                "type": "password",
                "required": True,
                "sensitive": True,
                "placeholder": "SCT 开头（sct.ftqq.com 获取）",
            },
        ]

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return cls._build_config_schema(cls.get_config_fields())

    @classmethod
    def get_setup_guide(cls) -> list[str]:
        return [
            "Log in to sct.ftqq.com with WeChat and copy your SendKey",
            "Messages arrive in your WeChat via the 方糖 service account",
        ]


class ServerChanChannelManager(OutboundChannelManager):
    channel_type = ChannelType.SERVERCHAN
    channel_class = ServerChanChannel
    config_class = ServerChanConfig
