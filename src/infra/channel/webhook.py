"""Authenticated JSON webhook chat channel.

Callbacks use an instance-specific shared secret, never a LambChat user token.
Replies are sent only to the URL saved by the channel owner, with public DNS
addresses pinned for each request so the secret cannot follow a redirect or a
DNS rebinding into the server's private network.
"""

from __future__ import annotations

import asyncio
import ipaddress
import socket
import time
from typing import Any

import httpx
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from src.infra.channel.chat import ChatChannel, ChatChannelManager, ChatConfig, chat_config_fields
from src.kernel.schemas.channel import ChannelCapability, ChannelType


class WebhookInbound(BaseModel):
    """Bounded text-only payload; provider actor IDs do not select the tenant."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    sender_id: str = Field(
        min_length=1, max_length=256, validation_alias=AliasChoices("sender_id", "userId")
    )
    chat_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=256,
        validation_alias=AliasChoices("chat_id", "chatId"),
    )
    content: str = Field(
        min_length=1, max_length=16000, validation_alias=AliasChoices("content", "text")
    )
    message_id: str = Field(
        min_length=1,
        max_length=256,
        validation_alias=AliasChoices("message_id", "messageId", "id"),
    )
    bot_id: str | None = Field(
        default=None, max_length=256, validation_alias=AliasChoices("bot_id", "botId")
    )

    def to_message(self) -> dict[str, Any]:
        return {
            "sender_id": self.sender_id,
            "chat_id": self.chat_id or self.sender_id,
            "content": self.content,
            "message_id": self.message_id,
        }


class WebhookConfig(ChatConfig):
    model_config = ConfigDict(hide_input_in_errors=True)
    channel_type = ChannelType.WEBHOOK
    receive_enabled: bool = True
    webhook_url: str = ""
    webhook_secret: str = Field(min_length=16, max_length=256, repr=False)

    @field_validator("webhook_secret")
    @classmethod
    def validate_secret(cls, value: str) -> str:
        # Restrict to visible ASCII for safe, unambiguous HTTP header transport.
        if any(not 33 <= ord(char) <= 126 for char in value):
            raise ValueError("Webhook secret must contain only visible ASCII characters")
        return value

    @classmethod
    def get_schema_name(cls) -> str:
        return "webhook"

    @classmethod
    def get_capabilities(cls) -> list[ChannelCapability]:
        return [
            ChannelCapability.WEBHOOK,
            ChannelCapability.SEND_MESSAGE,
            ChannelCapability.DIRECT_MESSAGE,
            ChannelCapability.GROUP_CHAT,
        ]


async def resolve_webhook_addresses(host: str, port: int) -> list[str]:
    """Resolve without blocking the event loop; callers validate all answers."""
    addresses = await asyncio.get_running_loop().getaddrinfo(
        host,
        port,
        type=socket.SOCK_STREAM,
    )
    return list(dict.fromkeys(str(item[4][0]) for item in addresses))


class WebhookChannel(ChatChannel):
    channel_type = ChannelType.WEBHOOK
    display_name = "Webhook"
    description = "Receive authenticated JSON messages and send replies to your endpoint"
    icon = "webhook"
    inbound_transport = False
    capabilities = tuple(WebhookConfig.get_capabilities())
    max_content_chars = 16000

    def _validate_inbound_config(self) -> bool:
        return bool(self.config.webhook_secret)

    async def _run_inbound(self) -> None:
        """Callbacks arrive through the API; no polling task is needed."""

    async def _get_http(self) -> httpx.AsyncClient:
        if self._http_lock is None:
            self._http_lock = asyncio.Lock()
        async with self._http_lock:
            if self._http is None or self._http.is_closed:
                self._http = httpx.AsyncClient(
                    timeout=self.timeout_seconds,
                    trust_env=False,
                    follow_redirects=False,
                )
        return self._http

    async def _send(self, *, title: str, content: str, target: str) -> bool:
        if not self.config.webhook_url:
            return False
        try:
            url = httpx.URL(self.config.webhook_url)
            if url.scheme != "https" or not url.host or url.userinfo or url.fragment:
                return False
            addresses = await asyncio.wait_for(
                resolve_webhook_addresses(url.host, url.port or 443),
                timeout=5.0,
            )
            parsed_addresses = [ipaddress.ip_address(ip) for ip in addresses]
            if not addresses or any(not ip.is_global or ip.is_multicast for ip in parsed_addresses):
                return False
            host_header = url.netloc.decode("ascii")
            client = await self._get_http()
            response = await client.post(
                url.copy_with(host=addresses[0]),
                headers={"host": host_header, "x-lambchat-bot-secret": self.config.webhook_secret},
                extensions={"sni_hostname": url.host},
                follow_redirects=False,
                json={
                    "type": "lambchat.bot.message",
                    "botId": self.config.instance_id,
                    "provider": "webhook",
                    "chatId": target,
                    "text": content,
                    "sentAt": int(time.time() * 1000),
                },
            )
            return response.is_success
        except (httpx.HTTPError, ValueError, OSError, TimeoutError):
            # Do not log exception strings: endpoint URLs can contain credentials.
            return False

    async def _send_reply(self, chat_id: str, content: str, **metadata: Any) -> bool:
        # The callback's input limit is not a limit on generated answers.
        return await self._send(title="", content=content, target=chat_id)

    @classmethod
    def get_config_fields(cls) -> list[dict[str, Any]]:
        common = chat_config_fields()
        for field in common:
            if field["name"] == "receive_enabled":
                field["default"] = True
        return [
            {
                "name": "webhook_url",
                "title": "Reply endpoint URL",
                "type": "text",
                "required": False,
                "sensitive": True,
                "placeholder": "https://example.com/replies",
            },
            {
                "name": "webhook_secret",
                "title": "Webhook secret",
                "type": "password",
                "required": True,
                "sensitive": True,
                "placeholder": "At least 16 random characters",
            },
            *common,
        ]

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return cls._build_config_schema(cls.get_config_fields())

    @classmethod
    def get_setup_guide(cls) -> list[str]:
        return [
            "Choose a random secret of at least 16 characters and configure allowed sender or chat IDs.",
            "Save the channel and copy its instance ID. POST to /api/channels/webhook/{instance_id}/callback.",
            "Set x-lambchat-bot-secret to the saved secret. Send JSON with sender_id, content, message_id, and optional chat_id.",
            "Use a stable unique message_id for retries. Send /new to start a new conversation.",
            "Optionally set a public HTTPS reply endpoint. Replies include chatId and text, authenticated with the same secret header.",
        ]


class WebhookChannelManager(ChatChannelManager):
    channel_type = ChannelType.WEBHOOK
    channel_class = WebhookChannel
    config_class = WebhookConfig

    async def receive_callback(self, config_dict: dict[str, Any], message: dict[str, Any]) -> bool:
        """Use a fresh config on any replica, without acquiring a polling lease."""
        # _start_instance has no network awaits for this transport. Serialize with
        # other callbacks to prevent one initial request replacing another's worker.
        if not hasattr(self, "_callback_lock"):
            self._callback_lock = asyncio.Lock()
        async with self._callback_lock:
            key = self._channel_key(config_dict)
            config = self.config_class(**config_dict)
            channel = self._channels.get(key)
            if not isinstance(channel, WebhookChannel) or not channel.is_running:
                channel = await self._start_instance(config_dict)
            elif channel.config != config:
                # Keep accepted tasks alive, while applying current allowlists and
                # reply credentials before another message can be enqueued.
                channel.config = config
            if not isinstance(channel, WebhookChannel):
                return False
            return await channel.enqueue_inbound(message)
