"""企业微信（WeCom）群机器人渠道

兼容旧群机器人 Webhook，并通过智能机器人 WebSocket 支持双向对话。
官方协议实现：https://github.com/WecomTeam/wecom-aibot-python-sdk
"""

from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import suppress
from typing import Any, Callable

import aiohttp

from src.infra.channel.chat import (
    ChatChannel,
    ChatChannelManager,
    ChatConfig,
    InboundConfigurationError,
    chat_config_fields,
)
from src.kernel.schemas.channel import ChannelCapability, ChannelType


class WeComConfig(ChatConfig):
    """企业微信（WeCom）群机器人渠道配置。"""

    channel_type = ChannelType.WECOM
    user_id: str = ""
    instance_id: str = ""
    enabled: bool = True
    webhook_url: str = ""
    default_chat_id: str = ""
    bot_id: str = ""
    bot_secret: str = ""

    @classmethod
    def get_schema_name(cls) -> str:
        return "wecom"

    @classmethod
    def get_capabilities(cls) -> list[ChannelCapability]:
        return list(WeComChannel.capabilities)


class WeComChannel(ChatChannel):
    channel_type = ChannelType.WECOM
    display_name = "WeCom Bot"
    description = "Push notifications to WeCom (企业微信) group chats via a bot webhook"
    icon = "message-square"
    max_content_chars = 1200  # 企微 markdown 上限 4096 字节（UTF-8），留余量
    capabilities = (
        ChannelCapability.SEND_MESSAGE,
        ChannelCapability.WEBSOCKET,
        ChannelCapability.DIRECT_MESSAGE,
        ChannelCapability.GROUP_CHAT,
    )
    heartbeat_seconds = 30.0

    def __init__(self, config: Any, message_handler: Callable | None = None):
        super().__init__(config, message_handler)
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._reply_acks: dict[str, asyncio.Future[bool]] = {}
        self._missed_pongs = 0
        self._ping_ids: set[str] = set()

    def _validate_inbound_config(self) -> bool:
        return bool(self.config.bot_id and self.config.bot_secret)

    async def _run_inbound(self) -> None:
        heartbeat = None
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(
                    "wss://openws.work.weixin.qq.com", max_msg_size=1024 * 1024
                ) as ws:
                    self._ws = ws
                    req_id = f"aibot_subscribe_{uuid.uuid4().hex}"
                    await ws.send_json(
                        {
                            "cmd": "aibot_subscribe",
                            "headers": {"req_id": req_id},
                            "body": {
                                "bot_id": self.config.bot_id,
                                "secret": self.config.bot_secret,
                            },
                        }
                    )
                    auth = await ws.receive_json(timeout=self.timeout_seconds)
                    if (
                        not isinstance(auth, dict)
                        or auth.get("headers", {}).get("req_id") != req_id
                        or auth.get("errcode") != 0
                    ):
                        raise InboundConfigurationError("WeCom smart bot authentication failed")
                    self._connected = True
                    self._missed_pongs = 0
                    self._ping_ids.clear()
                    heartbeat = asyncio.create_task(self._heartbeat())
                    async for frame in ws:
                        if frame.type == aiohttp.WSMsgType.TEXT:
                            try:
                                data = json.loads(frame.data)
                            except (ValueError, TypeError):
                                continue
                            if isinstance(data, dict):
                                await self._handle_ws_frame(data)
                        elif frame.type == aiohttp.WSMsgType.ERROR:
                            raise RuntimeError("WeCom smart bot disconnected")
        finally:
            self._connected = False
            self._ws = None
            if heartbeat is not None:
                heartbeat.cancel()
                with suppress(asyncio.CancelledError):
                    await heartbeat
            for future in self._reply_acks.values():
                if not future.done():
                    future.set_result(False)
            self._reply_acks.clear()

    async def _heartbeat(self) -> None:
        while self._connected and self._ws is not None:
            await asyncio.sleep(self.heartbeat_seconds)
            if self._missed_pongs >= 2:
                await self._ws.close()
                return
            self._missed_pongs += 1
            req_id = f"ping_{uuid.uuid4().hex}"
            self._ping_ids.add(req_id)
            await self._ws.send_json({"cmd": "ping", "headers": {"req_id": req_id}})

    async def _handle_ws_frame(self, frame: dict[str, Any]) -> None:
        headers = frame.get("headers")
        if not isinstance(headers, dict):
            return
        req_id = headers.get("req_id")
        if not isinstance(req_id, str) or not req_id:
            return
        cmd = frame.get("cmd")
        if not cmd:
            if req_id in self._ping_ids:
                self._ping_ids.discard(req_id)
                if frame.get("errcode") == 0:
                    self._missed_pongs = 0
                return
            pending = self._reply_acks.get(req_id)
            if pending is not None and not pending.done():
                pending.set_result(frame.get("errcode") == 0)
            return
        if cmd != "aibot_msg_callback":
            return
        body = frame.get("body")
        if (
            not isinstance(body, dict)
            or body.get("aibotid") != self.config.bot_id
            or body.get("msgtype") != "text"
        ):
            return
        sender = body.get("from")
        text = body.get("text")
        if not isinstance(sender, dict) or not isinstance(text, dict):
            return
        sender_id = sender.get("userid")
        chat_type = body.get("chattype")
        chat_id = sender_id if chat_type == "single" else body.get("chatid")
        if (
            not isinstance(sender_id, str)
            or not sender_id
            or sender_id == self.config.bot_id
            or chat_type not in ("single", "group")
            or not isinstance(chat_id, str)
            or not chat_id
            or not isinstance(text.get("content"), str)
            or not body.get("msgid")
        ):
            return
        if not await self.enqueue_inbound(
            {
                "sender_id": sender_id,
                "chat_id": chat_id,
                "content": text["content"],
                "message_id": body["msgid"],
                "metadata": {"wecom_req_id": req_id, "chat_type": chat_type},
            }
        ):
            raise RuntimeError("WeCom smart bot message queue unavailable")

    async def _send_reply(self, chat_id: str, content: str, **metadata: Any) -> bool:
        remaining = content.encode("utf-8")
        if not remaining:
            return False
        while remaining:
            # Stream replies allow 20480 UTF-8 bytes. Continuations are ordinary
            # messages to the same chat, using a conservative Markdown limit.
            limit = 20480 if metadata.get("wecom_req_id") else 4096
            part = remaining[:limit].decode("utf-8", errors="ignore")
            if not await self._send_reply_part(chat_id, part, **metadata):
                return False
            remaining = remaining[len(part.encode("utf-8")) :]
            metadata = {key: value for key, value in metadata.items() if key != "wecom_req_id"}
        return True

    async def _send_reply_part(self, chat_id: str, content: str, **metadata: Any) -> bool:
        ws = self._ws
        if not self._connected or ws is None:
            return False
        req_id = str(metadata.get("wecom_req_id") or f"aibot_send_msg_{uuid.uuid4().hex}")
        if req_id in self._reply_acks:
            return False
        if metadata.get("wecom_req_id"):
            cmd = "aibot_respond_msg"
            body = {
                "msgtype": "stream",
                "stream": {"id": uuid.uuid4().hex, "finish": True, "content": content},
            }
        else:
            if not chat_id:
                return False
            cmd = "aibot_send_msg"
            body = {"chatid": chat_id, "msgtype": "markdown", "markdown": {"content": content}}
        future: asyncio.Future[bool] = asyncio.get_running_loop().create_future()
        self._reply_acks[req_id] = future
        try:
            await ws.send_json({"cmd": cmd, "headers": {"req_id": req_id}, "body": body})
            return await asyncio.wait_for(future, self.timeout_seconds)
        except (TimeoutError, aiohttp.ClientError, ConnectionError):
            return False
        finally:
            self._reply_acks.pop(req_id, None)

    async def _send(self, *, title: str, content: str, target: str) -> bool:
        if not self.config.webhook_url:
            return False
        response = await self._post(
            self.config.webhook_url,
            json={
                "msgtype": "markdown",
                "markdown": {
                    "content": f"**{title}**\n{content[: max(0, self.max_content_chars - len(title) - 5)]}"
                },
            },
        )
        if response is None or response.is_error:
            return False
        try:
            data = response.json()
        except Exception:
            return False
        return bool(isinstance(data, dict) and data.get("errcode") == 0)

    @classmethod
    def get_config_fields(cls) -> list[dict[str, Any]]:
        return (
            [
                {
                    "name": "webhook_url",
                    "title": "Webhook URL",
                    "type": "text",
                    "required": False,
                    "sensitive": True,
                    "placeholder": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=...",
                },
            ]
            + [
                {"name": "bot_id", "title": "Bot ID", "type": "text", "required": False},
                {
                    "name": "bot_secret",
                    "title": "Bot Secret",
                    "type": "password",
                    "sensitive": True,
                    "required": False,
                },
            ]
            + chat_config_fields()
        )

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return cls._build_config_schema(cls.get_config_fields())

    @classmethod
    def get_setup_guide(cls) -> list[str]:
        return [
            "For two-way chat, create a smart robot in API mode with a persistent connection, enter Bot ID and Bot Secret, then enable receiving",
            "Restrict allowed senders to their WeCom user IDs; a legacy group webhook only supports outgoing notifications",
            "Open the target WeCom group chat and add a group bot (群机器人)",
            "Copy the Webhook URL into the config above",
        ]


class WeComChannelManager(ChatChannelManager):
    channel_type = ChannelType.WECOM
    channel_class = WeComChannel
    config_class = WeComConfig
