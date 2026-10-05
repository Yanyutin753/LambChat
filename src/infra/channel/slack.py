"""Slack webhooks and Socket Mode bots.

Protocol: https://docs.slack.dev/apis/events-api/using-socket-mode/
"""

from __future__ import annotations

import asyncio
from typing import Any

import aiohttp

from src.infra.channel.chat import (
    ChatChannel,
    ChatChannelManager,
    ChatConfig,
    InboundConfigurationError,
    chat_config_fields,
)
from src.kernel.schemas.channel import ChannelCapability, ChannelType


class SlackConfig(ChatConfig):
    """Webhook-only configurations remain valid without bot credentials."""

    channel_type = ChannelType.SLACK
    user_id: str = ""
    instance_id: str = ""
    enabled: bool = True
    webhook_url: str = ""
    default_chat_id: str = ""
    bot_token: str = ""
    app_token: str = ""

    @classmethod
    def get_schema_name(cls) -> str:
        return "slack"

    @classmethod
    def get_capabilities(cls) -> list[ChannelCapability]:
        return list(SlackChannel.capabilities)


class SlackChannel(ChatChannel):
    channel_type = ChannelType.SLACK
    display_name = "Slack"
    description = "Chat through Slack Socket Mode or send webhook notifications"
    icon = "hash"
    max_content_chars = 35000  # Slack text block 上限 40000 字符
    capabilities = (
        ChannelCapability.SEND_MESSAGE,
        ChannelCapability.WEBSOCKET,
        ChannelCapability.DIRECT_MESSAGE,
        ChannelCapability.GROUP_CHAT,
    )

    def __init__(self, config: SlackConfig, message_handler=None):
        super().__init__(config, message_handler)
        self._bot_user_id = ""

    def _validate_inbound_config(self) -> bool:
        return bool(self.config.app_token.strip() and self.config.bot_token.strip())

    async def _run_inbound(self) -> None:
        client = await self._get_http()
        auth = await client.post(
            "https://slack.com/api/auth.test",
            headers={"Authorization": f"Bearer {self.config.bot_token}"},
        )
        if auth.status_code == 429 or auth.status_code >= 500:
            raise RuntimeError("Slack authentication temporarily unavailable")
        if auth.is_error or not auth.json().get("ok"):
            raise InboundConfigurationError("Slack bot authentication failed")
        self._bot_user_id = str(auth.json().get("user_id", ""))
        response = await client.post(
            "https://slack.com/api/apps.connections.open",
            headers={"Authorization": f"Bearer {self.config.app_token}"},
        )
        if response.status_code == 429 or response.status_code >= 500:
            raise RuntimeError("Slack Socket Mode temporarily unavailable")
        payload = response.json()
        if response.is_error or not payload.get("ok") or not payload.get("url"):
            raise InboundConfigurationError("Slack Socket Mode authentication failed")
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(payload["url"], heartbeat=10) as ws:
                    async for frame in ws:
                        if frame.type == aiohttp.WSMsgType.TEXT:
                            data = frame.json()
                            if data.get("type") == "hello":
                                self._connected = True
                            elif data.get("type") == "disconnect":
                                if data.get("reason") == "link_disabled":
                                    raise InboundConfigurationError("Slack Socket Mode is disabled")
                                return
                            else:
                                # ACK must not wait behind a model response or a stalled Redis.
                                async with asyncio.timeout(2):
                                    await self._handle_envelope(ws, data)
                        elif frame.type == aiohttp.WSMsgType.ERROR:
                            raise RuntimeError("Slack WebSocket connection failed")
        finally:
            self._connected = False

    async def _handle_envelope(self, ws: Any, data: dict[str, Any]) -> None:
        envelope_id = data.get("envelope_id")
        if not envelope_id:
            return
        accepted = True
        payload = data.get("payload", {})
        event = payload.get("event", {})
        if data.get("type") == "events_api" and event.get("type") in {"message", "app_mention"}:
            sender = event.get("user")
            text = event.get("text", "")
            relevant = event.get("type") == "app_mention" or event.get("channel_type") == "im"
            if (
                relevant
                and sender
                and sender != self._bot_user_id
                and not event.get("bot_id")
                and not event.get("subtype")
                and isinstance(text, str)
                and text.strip()
            ):
                if self._bot_user_id:
                    text = text.replace(f"<@{self._bot_user_id}>", "").strip()
                if text and event.get("channel") and event.get("ts"):
                    metadata = {}
                    thread = event.get("thread_ts")
                    if not thread and event.get("channel_type") != "im":
                        thread = event["ts"]
                    if thread:
                        metadata["thread_ts"] = thread
                    accepted = await self.enqueue_inbound(
                        {
                            "sender_id": sender,
                            "chat_id": event["channel"],
                            "content": text,
                            "message_id": f"{payload.get('team_id', '')}:{event['channel']}:{event['ts']}",
                            "metadata": metadata,
                        }
                    )
        if accepted:
            await ws.send_json({"envelope_id": envelope_id})

    async def _send_reply(self, chat_id: str, content: str, **metadata: Any) -> bool:
        if not self.config.bot_token or not chat_id or not content:
            return False
        for offset in range(0, len(content), 4000):
            payload = {
                "channel": chat_id,
                "text": content[offset : offset + 4000],
                "unfurl_links": False,
                "unfurl_media": False,
            }
            if metadata.get("thread_ts"):
                payload["thread_ts"] = metadata["thread_ts"]
            response = None
            for attempt in range(3):
                response = await self._post(
                    "https://slack.com/api/chat.postMessage",
                    headers={"Authorization": f"Bearer {self.config.bot_token}"},
                    json=payload,
                )
                if response is None or response.status_code != 429 or attempt == 2:
                    break
                retry_after = float(response.headers.get("Retry-After", "1"))
                if not 0 <= retry_after <= 60:
                    return False
                await asyncio.sleep(retry_after)
            if response is None or response.is_error or not response.json().get("ok"):
                return False
        return True

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
        fields: list[dict[str, Any]] = [
            {
                "name": "webhook_url",
                "title": "Webhook URL",
                "type": "text",
                "required": False,
                "sensitive": True,
                "placeholder": "https://hooks.slack.com/services/T.../B.../...",
            },
            {
                "name": "bot_token",
                "title": "Bot Token",
                "type": "text",
                "sensitive": True,
                "placeholder": "xoxb-...",
            },
            {
                "name": "app_token",
                "title": "App Token",
                "type": "text",
                "sensitive": True,
                "placeholder": "xapp-...",
            },
            {
                "name": "default_chat_id",
                "title": "Default Chat ID",
                "type": "text",
                "placeholder": "C0123456789",
            },
        ]
        return fields + chat_config_fields()

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return cls._build_config_schema(cls.get_config_fields())

    @classmethod
    def get_setup_guide(cls) -> list[str]:
        return [
            "Use an incoming webhook for notifications, or enable receiving to chat with your agent",
            "For receiving: enable Socket Mode; create an app token with connections:write and install a bot with chat:write, app_mentions:read and im:history",
            "Subscribe to app_mention and message.im; invite the bot to your channel and configure allowed sender IDs",
        ]


class SlackChannelManager(ChatChannelManager):
    channel_type = ChannelType.SLACK
    channel_class = SlackChannel
    config_class = SlackConfig
