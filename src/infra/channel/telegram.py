"""Telegram Bot 渠道

Bot API 长轮询双向聊天，以及按 chat_id 定向投递的通知。
"""

from __future__ import annotations

import asyncio
import re
from typing import Any

from src.infra.channel.chat import (
    ChatChannel,
    ChatChannelManager,
    ChatConfig,
    InboundConfigurationError,
    chat_config_fields,
)
from src.infra.storage.redis import RedisStorage
from src.kernel.schemas.channel import ChannelCapability, ChannelType


def parse_telegram_update(update: dict, username: str) -> dict[str, Any] | None:
    """Parse new text messages; groups require a mention, reply, or bot command.

    Protocol: https://core.telegram.org/bots/api#getupdates
    """
    message = update.get("message")
    if not isinstance(message, dict):
        return None
    sender = message.get("from") or {}
    chat = message.get("chat") or {}
    text = message.get("text")
    if not isinstance(text, str) or not text.strip() or sender.get("is_bot"):
        return None
    if not sender.get("id") or not chat.get("id") or not message.get("message_id"):
        return None
    if chat.get("type") != "private":
        mention = (
            re.compile(rf"@{re.escape(username)}(?![A-Za-z0-9_])", re.IGNORECASE)
            if username
            else None
        )
        reply_sender = (message.get("reply_to_message") or {}).get("from") or {}
        addressed = bool(mention and mention.search(text))
        replied = bool(username and reply_sender.get("username", "").lower() == username.lower())
        if not addressed and not replied:
            return None
        if mention:
            text = mention.sub("", text).strip()
    metadata = {"telegram_message_id": message["message_id"]}
    if message.get("message_thread_id") is not None:
        metadata["message_thread_id"] = message["message_thread_id"]
    return {
        "sender_id": str(sender["id"]),
        "chat_id": str(chat["id"]),
        "content": text,
        "message_id": f"{chat['id']}:{message['message_id']}",
        "metadata": metadata,
    }


class TelegramConfig(ChatConfig):
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
        return [
            ChannelCapability.SEND_MESSAGE,
            ChannelCapability.LONG_POLLING,
            ChannelCapability.DIRECT_MESSAGE,
            ChannelCapability.GROUP_CHAT,
        ]


class TelegramChannel(ChatChannel):
    channel_type = ChannelType.TELEGRAM
    display_name = "Telegram"
    description = "Chat with your agent and receive notifications via a Telegram bot"
    capabilities = tuple(TelegramConfig.get_capabilities())
    _bot_username = ""
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

    def _validate_inbound_config(self) -> bool:
        return bool(self.config.bot_token.strip())

    async def _api(self, method: str, payload: dict | None = None) -> Any:
        client = await self._get_http()
        for attempt in range(3):
            response = await client.post(
                f"https://api.telegram.org/bot{self.config.bot_token}/{method}",
                json=payload or {},
                timeout=40,
            )
            data = response.json()
            if data.get("ok") is True:
                return data.get("result")
            code = data.get("error_code", response.status_code)
            if code in (401, 409):
                raise InboundConfigurationError("Telegram token/webhook conflicts")
            if code == 429 and attempt < 2:
                retry = float((data.get("parameters") or {}).get("retry_after", 1))
                await asyncio.sleep(min(max(retry, 0), 60))
                continue
            raise RuntimeError("Telegram API request failed")
        raise RuntimeError("Telegram API retry exhausted")

    async def _run_inbound(self) -> None:
        me = await self._api("getMe")
        self._bot_username = str(me.get("username", ""))
        info = await self._api("getWebhookInfo")
        if info.get("url"):
            # Never take over an existing integration without user action.
            raise InboundConfigurationError("Remove the existing Telegram webhook before polling")
        self._connected = True
        try:
            while self._running:
                await self._poll_once(RedisStorage())
        finally:
            self._connected = False

    async def _poll_once(self, storage: Any) -> None:
        key = f"{self._lease_key()}:offset"
        offset = await storage.get(key)
        updates = await self._api(
            "getUpdates",
            {
                "offset": int(offset or 0),
                "timeout": 30,
                "allowed_updates": ["message"],
            },
        )
        for update in updates:
            message = parse_telegram_update(update, self._bot_username)
            if message:
                if not await self.enqueue_inbound(message) or not await self.drain():
                    raise RuntimeError("Telegram message was not processed")
            # Only confirm updates after authorized messages have been handled.
            await storage.set(key, int(update["update_id"]) + 1)

    async def _send_reply(self, chat_id: str, content: str, **metadata: Any) -> bool:
        if not chat_id:
            return False
        for start in range(0, len(content), 4000):
            payload: dict[str, Any] = {"chat_id": chat_id, "text": content[start : start + 4000]}
            if metadata.get("message_thread_id") is not None:
                payload["message_thread_id"] = metadata["message_thread_id"]
            await self._api("sendMessage", payload)
        return True

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
                "required": False,
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
        ] + chat_config_fields()

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return cls._build_config_schema(cls.get_config_fields())

    @classmethod
    def get_setup_guide(cls) -> list[str]:
        return [
            "Create a bot with @BotFather and copy the bot token",
            "Enable receiving and allow specific sender or chat IDs; a default chat ID is also an allowlist fallback",
            "Remove any existing webhook before enabling long polling; LambChat will not delete it automatically",
            "Message the bot privately, or mention/reply to it in an allowed group; use /new to start a new conversation",
        ]


class TelegramChannelManager(ChatChannelManager):
    channel_type = ChannelType.TELEGRAM
    channel_class = TelegramChannel
    config_class = TelegramConfig
