"""钉钉（DingTalk）自定义机器人渠道

兼容群机器人 Webhook，并支持企业应用 Stream 收消息和机器人 REST 主动发送。
协议：https://opensource.dingtalk.com/developerpedia/docs/learn/stream/protocol/
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any
from urllib.parse import quote_plus, urlsplit

import aiohttp
import httpx

from src.infra.channel.chat import (
    ChatChannel,
    ChatChannelManager,
    ChatConfig,
    InboundConfigurationError,
    chat_config_fields,
)
from src.kernel.schemas.channel import ChannelCapability, ChannelType


def build_signed_url(webhook_url: str, secret: str, timestamp: int | None = None) -> str:
    """按钉钉加签算法（timestamp\nsecret 作 HMAC key、空消息体）追加签名参数。"""
    if not secret:
        return webhook_url
    ts = timestamp if timestamp is not None else int(time.time() * 1000)
    string_to_sign = f"{ts}\n{secret}"
    digest = hmac.new(string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    sign = quote_plus(base64.b64encode(digest))
    sep = "&" if "?" in webhook_url else "?"
    return f"{webhook_url}{sep}timestamp={ts}&sign={sign}"


def _safe_json(response: Any) -> dict[str, Any]:
    try:
        data = response.json()
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


class DingTalkConfig(ChatConfig):
    """钉钉（DingTalk）自定义机器人渠道配置。"""

    channel_type = ChannelType.DINGTALK
    user_id: str = ""
    instance_id: str = ""
    enabled: bool = True
    webhook_url: str = ""
    secret: str = ""
    default_chat_id: str = ""
    client_id: str = ""
    client_secret: str = ""
    corp_id: str = ""

    @classmethod
    def get_schema_name(cls) -> str:
        return "dingtalk"

    @classmethod
    def get_capabilities(cls) -> list[ChannelCapability]:
        return list(DingTalkChannel.capabilities)


class DingTalkChannel(ChatChannel):
    channel_type = ChannelType.DINGTALK
    display_name = "DingTalk"
    description = "Push notifications to DingTalk group chats via a custom robot webhook"
    icon = "bell-ring"
    max_content_chars = 6000  # 钉钉 markdown 上限 20000 字节，留余量
    capabilities = (
        ChannelCapability.SEND_MESSAGE,
        ChannelCapability.WEBSOCKET,
        ChannelCapability.DIRECT_MESSAGE,
        ChannelCapability.GROUP_CHAT,
    )

    def _validate_inbound_config(self) -> bool:
        return bool(self.config.client_id and self.config.client_secret and self.config.corp_id)

    async def _open_stream_url(self) -> str:
        client = await self._get_http()
        response = await client.post(
            "https://api.dingtalk.com/v1.0/gateway/connections/open",
            json={
                "clientId": self.config.client_id,
                "clientSecret": self.config.client_secret,
                "subscriptions": [{"type": "CALLBACK", "topic": "/v1.0/im/bot/messages/get"}],
                "ua": "lambchat-python/1.0",
            },
        )
        if response.status_code in (400, 401, 403):
            raise InboundConfigurationError("DingTalk Stream credentials rejected")
        if response.is_error:
            raise RuntimeError("DingTalk Stream ticket request failed")
        data = _safe_json(response)
        endpoint, ticket = data.get("endpoint"), data.get("ticket")
        if not isinstance(endpoint, str) or not isinstance(ticket, str) or not ticket:
            raise RuntimeError("DingTalk Stream returned invalid connection credentials")
        parts = urlsplit(endpoint)
        if (
            parts.scheme != "wss"
            or not (parts.hostname or "").endswith(".dingtalk.com")
            or parts.username
            or parts.password
            or parts.port not in (None, 443)
        ):
            raise RuntimeError("DingTalk Stream returned an invalid endpoint")
        return f"{endpoint}{'&' if parts.query else '?'}ticket={quote_plus(ticket)}"

    async def _run_inbound(self) -> None:
        url = await self._open_stream_url()
        try:
            async with aiohttp.ClientSession() as session:
                async with session.ws_connect(url, heartbeat=30, max_msg_size=1024 * 1024) as ws:
                    self._connected = True
                    async for frame in ws:
                        if frame.type == aiohttp.WSMsgType.TEXT:
                            try:
                                data = json.loads(frame.data)
                            except (ValueError, TypeError):
                                continue
                            if isinstance(data, dict):
                                await self._handle_stream_frame(ws, data)
                        elif frame.type == aiohttp.WSMsgType.ERROR:
                            raise RuntimeError("DingTalk Stream disconnected")
        finally:
            self._connected = False

    async def _handle_stream_frame(self, ws: Any, frame: dict[str, Any]) -> None:
        headers = frame.get("headers")
        if not isinstance(headers, dict):
            return
        topic = headers.get("topic")
        if frame.get("type") == "SYSTEM" and topic == "disconnect":
            await ws.close()
            return
        raw = frame.get("data", "{}")
        try:
            body = json.loads(raw) if isinstance(raw, str) else raw
        except (ValueError, TypeError):
            return
        if not isinstance(body, dict):
            return
        accepted = True
        ack_data = body if frame.get("type") == "SYSTEM" else {"response": "OK"}
        if frame.get("type") == "CALLBACK" and topic == "/v1.0/im/bot/messages/get":
            sender = body.get("senderStaffId")
            content = body.get("text", {})
            chat_type = body.get("conversationType")
            if (
                body.get("senderCorpId") == self.config.corp_id
                and body.get("chatbotCorpId") == self.config.corp_id
                and isinstance(sender, str)
                and sender
                and body.get("senderId") != body.get("chatbotUserId")
                and body.get("msgtype") == "text"
                and isinstance(content, dict)
                and isinstance(content.get("content"), str)
                and chat_type in ("1", "2")
                and (chat_type == "1" or body.get("isInAtList") is True)
                and body.get("conversationId")
                and body.get("msgId")
            ):
                accepted = await self.enqueue_inbound(
                    {
                        "sender_id": sender,
                        "chat_id": sender if chat_type == "1" else body["conversationId"],
                        "message_id": body["msgId"],
                        "content": content["content"],
                        "metadata": {
                            "session_webhook": body.get("sessionWebhook", ""),
                            "session_webhook_expired_time": body.get(
                                "sessionWebhookExpiredTime", 0
                            ),
                            "chat_type": "single" if chat_type == "1" else "group",
                        },
                    }
                )
        if headers.get("messageId"):
            await ws.send_json(
                {
                    "code": 200 if accepted else 500,
                    "message": "OK" if accepted else "Busy",
                    "headers": {
                        "messageId": headers["messageId"],
                        "contentType": "application/json",
                    },
                    "data": json.dumps(ack_data),
                }
            )

    async def _send_reply(self, chat_id: str, content: str, **metadata: Any) -> bool:
        url = metadata.get("session_webhook")
        if url:
            parts = urlsplit(str(url))
            if (
                parts.scheme != "https"
                or parts.hostname != "oapi.dingtalk.com"
                or parts.path != "/robot/sendBySession"
                or parts.username
                or parts.password
                or parts.port not in (None, 443)
            ):
                return False
            expiry = metadata.get("session_webhook_expired_time")
            if expiry and float(expiry) <= time.time() * 1000:
                return await self._send_reply(
                    chat_id,
                    content,
                    **{key: value for key, value in metadata.items() if key != "session_webhook"},
                )
            client = await self._get_http()
            try:
                response = await client.post(
                    url,
                    json={"msgtype": "text", "text": {"content": content}},
                    follow_redirects=False,
                )
            except httpx.HTTPError:
                return False
            return not response.is_error and _safe_json(response).get("errcode") == 0
        # A retained legacy webhook names a fixed group, not this reply's target.
        # Bot mode must use the authenticated robot API for the requested chat.
        if not chat_id or not self.config.client_id or not self.config.client_secret:
            return False
        client = await self._get_http()
        # Tokens stay local to this request; a credential edit cannot retain a stale token.
        token_response = await client.post(
            "https://api.dingtalk.com/v1.0/oauth2/accessToken",
            json={"appKey": self.config.client_id, "appSecret": self.config.client_secret},
        )
        token = _safe_json(token_response).get("accessToken")
        if token_response.is_error or not token:
            return False
        direct = metadata.get("chat_type") == "single" or chat_id.startswith("user:")
        target = chat_id.removeprefix("user:") if direct else chat_id
        body = {
            "robotCode": self.config.client_id,
            "msgKey": "sampleText",
            "msgParam": json.dumps({"content": content}),
        }
        body["userIds" if direct else "openConversationId"] = [target] if direct else target
        path = "oToMessages/batchSend" if direct else "groupMessages/send"
        response = await client.post(
            f"https://api.dingtalk.com/v1.0/robot/{path}",
            json=body,
            headers={"x-acs-dingtalk-access-token": token},
        )
        result = _safe_json(response)
        return (
            not response.is_error
            and bool(result.get("processQueryKey"))
            and not result.get("invalidStaffIdList")
        )

    async def _send(self, *, title: str, content: str, target: str) -> bool:
        if not self.config.webhook_url:
            return False
        url = build_signed_url(self.config.webhook_url, self.config.secret)
        response = await self._post(
            url,
            json={"msgtype": "markdown", "markdown": {"title": title, "text": content}},
        )
        if response is None or response.is_error:
            return False
        data = _safe_json(response)
        # 钉钉失败形态：{"errcode": 310000, "errmsg": "sign not match"}
        return bool(data.get("errcode") == 0)

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
                    "placeholder": "https://oapi.dingtalk.com/robot/send?access_token=...",
                },
                {
                    "name": "secret",
                    "title": "加签 Secret",
                    "type": "password",
                    "required": False,
                    "sensitive": True,
                    "placeholder": "SEC 开头（安全设置选「加签」时必填）",
                },
            ]
            + [
                {"name": "client_id", "title": "Client ID", "type": "text", "required": False},
                {
                    "name": "client_secret",
                    "title": "Client Secret",
                    "type": "password",
                    "sensitive": True,
                    "required": False,
                },
                {"name": "corp_id", "title": "Corporation ID", "type": "text", "required": False},
            ]
            + chat_config_fields()
        )

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return cls._build_config_schema(cls.get_config_fields())

    @classmethod
    def get_setup_guide(cls) -> list[str]:
        return [
            "For two-way chat, create an enterprise app robot with Stream mode; enter Client ID, Client Secret and Corporation ID, then enable receiving",
            "Restrict allowed senders to their DingTalk staff IDs; default targets are group conversation IDs, or user:<staffId> for direct messages",
            "Open the target DingTalk group chat settings and choose 机器人 (Robots)",
            "Add a custom robot (自定义机器人) with Markdown message support",
            "Copy the Webhook URL into the config above",
            "If the robot's security setting is 加签 (sign), also fill in the secret",
        ]


class DingTalkChannelManager(ChatChannelManager):
    channel_type = ChannelType.DINGTALK
    channel_class = DingTalkChannel
    config_class = DingTalkConfig
