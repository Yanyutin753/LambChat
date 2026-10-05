"""Telegram Bot 渠道

出站推送渠道：Bot API sendMessage，按 chat_id 定向投递（对话/群/频道）。
"""

from __future__ import annotations

from typing import Any

from src.infra.channel.outbound import OutboundChannel, OutboundChannelManager
from src.kernel.schemas.channel import ChannelCapability, ChannelConfigBase, ChannelType


class TelegramConfig(ChannelConfigBase):
    """Telegram Bot 渠道配置。"""

    channel_type = ChannelType.TELEGRAM
    user_id: str = ""
    instance_id: str = ""
    enabled: bool = True
    bot_token: str = ""
    default_chat_id: str = ""
    parse_mode: str = ""

    @classmethod
    def get_schema_name(cls) -> str:
        return "telegram"

    @classmethod
    def get_capabilities(cls) -> list[ChannelCapability]:
        return [ChannelCapability.SEND_MESSAGE]


class TelegramChannel(OutboundChannel):
    channel_type = ChannelType.TELEGRAM
    display_name = "Telegram"
    description = "Push notifications to Telegram chats via a bot"
    icon = "send"
    max_content_chars = 4000  # Telegram 上限 4096 字符

    async def _send(self, *, title: str, content: str, target: str) -> bool:
        if not self.config.bot_token or not target:
            return False
        payload: dict[str, Any] = {"chat_id": target, "text": content}
        if self.config.parse_mode:
            payload["parse_mode"] = self.config.parse_mode
        response = await self._post(
            f"https://api.telegram.org/bot{self.config.bot_token}/sendMessage",
            json=payload,
        )
        if response is None or response.is_error:
            return False
        try:
            data = response.json()
        except Exception:
            return False
        return bool(isinstance(data, dict) and data.get("ok") is True)

    @classmethod
    def get_config_fields(cls) -> list[dict[str, Any]]:
        return [
            {
                "name": "bot_token",
                "title": "Bot Token",
                "type": "password",
                "required": True,
                "sensitive": True,
                "placeholder": "123456:ABC-DEF... (from @BotFather)",
            },
            {
                "name": "default_chat_id",
                "title": "Default Chat ID",
                "type": "text",
                "required": True,
                "sensitive": False,
                "placeholder": "Send a message to your bot, then check getUpdates",
            },
            {
                "name": "parse_mode",
                "title": "Parse Mode",
                "type": "select",
                "required": False,
                "sensitive": False,
                "default": "",
                "options": [
                    {"value": "", "label": "Plain text"},
                    {"value": "Markdown", "label": "Markdown"},
                    {"value": "HTML", "label": "HTML"},
                ],
            },
        ]

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return cls._build_config_schema(cls.get_config_fields())

    @classmethod
    def get_setup_guide(cls) -> list[str]:
        return [
            "Create a bot with @BotFather and copy the bot token",
            "Send any message to your bot, then resolve your chat id via getUpdates",
            "Fill in the bot token and default chat id above",
        ]


class TelegramChannelManager(OutboundChannelManager):
    channel_type = ChannelType.TELEGRAM
    channel_class = TelegramChannel
    config_class = TelegramConfig
