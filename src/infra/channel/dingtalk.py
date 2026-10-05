"""钉钉（DingTalk）自定义机器人渠道

出站推送渠道：群机器人 Webhook，支持加签（HMAC-SHA256）安全设置，Markdown 消息。
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
from typing import Any
from urllib.parse import quote_plus

from src.infra.channel.outbound import OutboundChannel, OutboundChannelManager
from src.kernel.schemas.channel import ChannelCapability, ChannelConfigBase, ChannelType


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


class DingTalkConfig(ChannelConfigBase):
    """钉钉（DingTalk）自定义机器人渠道配置。"""

    channel_type = ChannelType.DINGTALK
    user_id: str = ""
    instance_id: str = ""
    enabled: bool = True
    webhook_url: str = ""
    secret: str = ""
    default_chat_id: str = ""

    @classmethod
    def get_schema_name(cls) -> str:
        return "dingtalk"

    @classmethod
    def get_capabilities(cls) -> list[ChannelCapability]:
        return [ChannelCapability.SEND_MESSAGE]


class DingTalkChannel(OutboundChannel):
    channel_type = ChannelType.DINGTALK
    display_name = "DingTalk"
    description = "Push notifications to DingTalk group chats via a custom robot webhook"
    icon = "bell-ring"
    max_content_chars = 6000  # 钉钉 markdown 上限 20000 字节，留余量

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
        return [
            {
                "name": "webhook_url",
                "title": "Webhook URL",
                "type": "text",
                "required": True,
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

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        return cls._build_config_schema(cls.get_config_fields())

    @classmethod
    def get_setup_guide(cls) -> list[str]:
        return [
            "Open the target DingTalk group chat settings and choose 机器人 (Robots)",
            "Add a custom robot (自定义机器人) with Markdown message support",
            "Copy the Webhook URL into the config above",
            "If the robot's security setting is 加签 (sign), also fill in the secret",
        ]


class DingTalkChannelManager(OutboundChannelManager):
    channel_type = ChannelType.DINGTALK
    channel_class = DingTalkChannel
    config_class = DingTalkConfig
