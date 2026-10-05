"""Discord webhook notifications and Gateway bots.

Protocol: https://docs.discord.com/developers/events/gateway
"""

from __future__ import annotations

import asyncio
import random
from contextlib import suppress
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


class DiscordConfig(ChatConfig):
    """Discord Webhook 渠道配置。"""

    channel_type = ChannelType.DISCORD
    user_id: str = ""
    instance_id: str = ""
    enabled: bool = True
    webhook_url: str = ""
    default_chat_id: str = ""
    bot_token: str = ""
    require_mention: bool = True

    @classmethod
    def get_schema_name(cls) -> str:
        return "discord"

    @classmethod
    def get_capabilities(cls) -> list[ChannelCapability]:
        return list(DiscordChannel.capabilities)


class DiscordChannel(ChatChannel):
    channel_type = ChannelType.DISCORD
    display_name = "Discord"
    description = "Chat through a Discord bot or send webhook notifications"
    icon = "gamepad-2"
    max_content_chars = 2000  # Discord 消息硬上限
    capabilities = (
        ChannelCapability.SEND_MESSAGE,
        ChannelCapability.WEBSOCKET,
        ChannelCapability.DIRECT_MESSAGE,
        ChannelCapability.GROUP_CHAT,
    )

    def __init__(self, config: DiscordConfig, message_handler=None):
        super().__init__(config, message_handler)
        self._bot_user_id = ""
        self._session_id: str | None = None
        self._resume_gateway_url: str | None = None
        self._gateway_seq: int | None = None
        self._heartbeat_ack = True

    def _validate_inbound_config(self) -> bool:
        return bool(self.config.bot_token.strip())

    def _clear_session(self) -> None:
        self._session_id = None
        self._resume_gateway_url = None
        self._gateway_seq = None

    async def _run_inbound(self) -> None:
        url = self._resume_gateway_url
        if not url or not self._session_id:
            client = await self._get_http()
            response = await client.get(
                "https://discord.com/api/v10/gateway/bot",
                headers={"Authorization": f"Bot {self.config.bot_token}"},
            )
            if response.status_code in {401, 403}:
                raise InboundConfigurationError("Discord bot authentication failed")
            if response.is_error:
                raise RuntimeError("Discord Gateway temporarily unavailable")
            data = response.json()
            if data.get("shards", 1) > 1:
                raise InboundConfigurationError("Discord bot requires Gateway sharding")
            limit = data.get("session_start_limit", {})
            if limit.get("remaining", 1) < 1:
                raise RuntimeError("Discord Gateway session limit temporarily exhausted")
            url = data["url"]
        heartbeat: asyncio.Task | None = None
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(f"{url.rstrip('/')}?v=10&encoding=json") as ws:
                    hello = await ws.receive_json(timeout=20)
                    if hello.get("op") != 10:
                        raise RuntimeError("Discord Gateway did not send Hello")
                    interval = hello.get("d", {}).get("heartbeat_interval", 0) / 1000
                    if interval <= 0:
                        raise RuntimeError("Discord Gateway sent an invalid heartbeat interval")
                    self._heartbeat_ack = True
                    heartbeat = asyncio.create_task(self._heartbeat(ws, interval))
                    await self._identify_or_resume(ws)
                    try:
                        async for frame in ws:
                            if frame.type == aiohttp.WSMsgType.TEXT:
                                if not await self._handle_gateway_event(ws, frame.json()):
                                    # 1000 invalidates resumable sessions; use an abnormal close.
                                    await ws.close(code=4000)
                                    break
                            elif frame.type == aiohttp.WSMsgType.ERROR:
                                raise RuntimeError("Discord WebSocket connection failed")
                    finally:
                        if not ws.closed:
                            await ws.close(code=4000)
                    if ws.close_code in {4004, 4010, 4011, 4012, 4013, 4014}:
                        self._clear_session()
                        raise InboundConfigurationError(
                            "Discord Gateway rejected bot credentials or intents"
                        )
                    if ws.close_code in {4007, 4009}:
                        self._clear_session()
        finally:
            self._connected = False
            if heartbeat is not None:
                heartbeat.cancel()
                with suppress(asyncio.CancelledError):
                    await heartbeat

    async def _identify_or_resume(self, ws: Any) -> None:
        if self._session_id and self._gateway_seq is not None:
            await ws.send_json(
                {
                    "op": 6,
                    "d": {
                        "token": self.config.bot_token,
                        "session_id": self._session_id,
                        "seq": self._gateway_seq,
                    },
                }
            )
        else:
            intents = (1 << 9) | (1 << 12)
            if not self.config.require_mention:
                intents |= 1 << 15
            await ws.send_json(
                {
                    "op": 2,
                    "d": {
                        "token": self.config.bot_token,
                        "intents": intents,
                        "properties": {"os": "linux", "browser": "lambchat", "device": "lambchat"},
                    },
                }
            )

    async def _heartbeat(self, ws: Any, interval: float) -> None:
        await asyncio.sleep(interval * random.random())
        try:
            while not ws.closed:
                if not self._heartbeat_ack:
                    await ws.close(code=4000)
                    return
                self._heartbeat_ack = False
                await ws.send_json({"op": 1, "d": self._gateway_seq})
                await asyncio.sleep(interval)
        except (aiohttp.ClientError, ConnectionError):
            await ws.close(code=4000)

    async def _handle_gateway_event(self, ws: Any, packet: dict[str, Any]) -> bool:
        op = packet.get("op")
        if op == 11:
            self._heartbeat_ack = True
        elif op == 1:
            await ws.send_json({"op": 1, "d": self._gateway_seq})
        elif op == 7:
            return False
        elif op == 9:
            if not packet.get("d"):
                self._clear_session()
            return False
        elif op == 0:
            data = packet.get("d", {})
            if packet.get("t") == "READY":
                self._session_id = data["session_id"]
                self._resume_gateway_url = data["resume_gateway_url"]
                self._bot_user_id = data["user"]["id"]
                self._connected = True
            elif packet.get("t") == "RESUMED":
                self._connected = True
            elif packet.get("t") == "MESSAGE_CREATE":
                author = data.get("author", {})
                text = data.get("content", "")
                mentioned = any(
                    user.get("id") == self._bot_user_id for user in data.get("mentions", [])
                )
                relevant = not data.get("guild_id") or not self.config.require_mention or mentioned
                if (
                    relevant
                    and not author.get("bot")
                    and not data.get("webhook_id")
                    and author.get("id")
                    and author["id"] != self._bot_user_id
                    and data.get("type", 0) in {0, 19}
                    and isinstance(text, str)
                    and text.strip()
                    and data.get("id")
                    and data.get("channel_id")
                ):
                    if self._bot_user_id:
                        text = (
                            text.replace(f"<@{self._bot_user_id}>", "")
                            .replace(f"<@!{self._bot_user_id}>", "")
                            .strip()
                        )
                    if text and not await self.enqueue_inbound(
                        {
                            "sender_id": author["id"],
                            "chat_id": data["channel_id"],
                            "content": text,
                            "message_id": data["id"],
                            "metadata": {"reply_message_id": data["id"]},
                        }
                    ):
                        # Preserve previous sequence so Resume replays this undelivered message.
                        raise RuntimeError("Discord message queue temporarily unavailable")
            if packet.get("s") is not None:
                self._gateway_seq = packet["s"]
        return True

    async def _send_reply(self, chat_id: str, content: str, **metadata: Any) -> bool:
        if not self.config.bot_token or not chat_id or not content:
            return False
        for offset in range(0, len(content), 2000):
            payload = {
                "content": content[offset : offset + 2000],
                "allowed_mentions": {"parse": [], "replied_user": False},
            }
            if metadata.get("reply_message_id"):
                payload["message_reference"] = {
                    "message_id": metadata["reply_message_id"],
                    "fail_if_not_exists": False,
                }
            response = None
            for attempt in range(3):
                response = await self._post(
                    f"https://discord.com/api/v10/channels/{chat_id}/messages",
                    headers={"Authorization": f"Bot {self.config.bot_token}"},
                    json=payload,
                )
                if response is None or response.status_code != 429 or attempt == 2:
                    break
                retry_after = float(response.json().get("retry_after", 1))
                if not 0 <= retry_after <= 60:
                    return False
                await asyncio.sleep(retry_after)
            if response is None or response.is_error:
                return False
        return True

    async def _send(self, *, title: str, content: str, target: str) -> bool:
        if not self.config.webhook_url:
            return False
        response = await self._post(
            self.config.webhook_url,
            json={
                "content": f"**{title}**\n{content[: max(0, self.max_content_chars - len(title) - 5)]}"
            },
        )
        return response is not None and not response.is_error

    @classmethod
    def get_config_fields(cls) -> list[dict[str, Any]]:
        fields: list[dict[str, Any]] = [
            {
                "name": "webhook_url",
                "title": "Webhook URL",
                "type": "text",
                "required": False,
                "sensitive": True,
                "placeholder": "https://discord.com/api/webhooks/...",
            },
            {"name": "bot_token", "title": "Bot Token", "type": "text", "sensitive": True},
            {"name": "default_chat_id", "title": "Default Chat ID", "type": "text"},
            {
                "name": "require_mention",
                "title": "Require Mention in Groups",
                "type": "toggle",
                "default": True,
            },
        ]
        return fields + chat_config_fields()

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return cls._build_config_schema(cls.get_config_fields())

    @classmethod
    def get_setup_guide(cls) -> list[str]:
        return [
            "Use a channel webhook for notifications, or create a bot in the Discord Developer Portal to receive messages",
            "Invite the bot with View Channels, Send Messages and Read Message History permissions; enter its bot token and allowed sender IDs",
            "Group chats require a mention by default; enable Message Content Intent in the Developer Portal before turning this requirement off",
        ]


class DiscordChannelManager(ChatChannelManager):
    channel_type = ChannelType.DISCORD
    channel_class = DiscordChannel
    config_class = DiscordConfig
