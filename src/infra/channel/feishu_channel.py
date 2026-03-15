"""
Feishu/Lark channel implementation using lark-oapi SDK with WebSocket long connection.

Supports per-user bot configurations - each user can have their own Feishu bot.
"""

import asyncio
import importlib.util
import json
import logging
import threading
from collections import OrderedDict
from typing import Any, Callable, Optional

from src.infra.channel.base import BaseChannel, UserChannelManager
from src.infra.channel.channel_storage import ChannelStorage
from src.kernel.schemas.channel import ChannelCapability, ChannelType
from src.kernel.schemas.feishu import FeishuConfig, FeishuGroupPolicy

logger = logging.getLogger(__name__)
FEISHU_AVAILABLE = importlib.util.find_spec("lark_oapi") is not None

# Message type display mapping
MSG_TYPE_MAP = {
    "image": "[image]",
    "audio": "[audio]",
    "file": "[file]",
    "sticker": "[sticker]",
}


def _extract_share_card_content(content_json: dict, msg_type: str) -> str:
    """Extract text representation from share cards and interactive messages."""
    parts = []

    if msg_type == "share_chat":
        parts.append(f"[shared chat: {content_json.get('chat_id', '')}]")
    elif msg_type == "share_user":
        parts.append(f"[shared user: {content_json.get('user_id', '')}]")
    elif msg_type == "interactive":
        parts.extend(_extract_interactive_content(content_json))
    elif msg_type == "share_calendar_event":
        parts.append(f"[shared calendar event: {content_json.get('event_key', '')}]")
    elif msg_type == "system":
        parts.append("[system message]")
    elif msg_type == "merge_forward":
        parts.append("[merged forward messages]")

    return "\n".join(parts) if parts else f"[{msg_type}]"


def _extract_interactive_content(content: dict) -> list[str]:
    """Recursively extract text and links from interactive card content."""
    parts = []

    if isinstance(content, str):
        try:
            content = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            return [content] if content.strip() else []

    if not isinstance(content, dict):
        return parts

    if "title" in content:
        title = content["title"]
        if isinstance(title, dict):
            title_content = title.get("content", "") or title.get("text", "")
            if title_content:
                parts.append(f"title: {title_content}")
        elif isinstance(title, str):
            parts.append(f"title: {title}")

    for elements in (
        content.get("elements", []) if isinstance(content.get("elements"), list) else []
    ):
        for element in elements:
            parts.extend(_extract_element_content(element))

    card = content.get("card", {})
    if card:
        parts.extend(_extract_interactive_content(card))

    header = content.get("header", {})
    if header:
        header_title = header.get("title", {})
        if isinstance(header_title, dict):
            header_text = header_title.get("content", "") or header_title.get("text", "")
            if header_text:
                parts.append(f"title: {header_text}")

    return parts


def _extract_element_content(element: dict) -> list[str]:
    """Extract content from a single card element."""
    parts = []

    if not isinstance(element, dict):
        return parts

    tag = element.get("tag", "")

    if tag in ("markdown", "lark_md"):
        content = element.get("content", "")
        if content:
            parts.append(content)

    elif tag == "div":
        text = element.get("text", {})
        if isinstance(text, dict):
            text_content = text.get("content", "") or text.get("text", "")
            if text_content:
                parts.append(text_content)
        elif isinstance(text, str):
            parts.append(text)
        for field in element.get("fields", []):
            if isinstance(field, dict):
                field_text = field.get("text", {})
                if isinstance(field_text, dict):
                    c = field_text.get("content", "")
                    if c:
                        parts.append(c)

    elif tag == "a":
        href = element.get("href", "")
        text = element.get("text", "")
        if href:
            parts.append(f"link: {href}")
        if text:
            parts.append(text)

    elif tag == "button":
        text = element.get("text", {})
        if isinstance(text, dict):
            c = text.get("content", "")
            if c:
                parts.append(c)
        url = element.get("url", "") or element.get("multi_url", {}).get("url", "")
        if url:
            parts.append(f"link: {url}")

    elif tag == "img":
        alt = element.get("alt", {})
        parts.append(alt.get("content", "[image]") if isinstance(alt, dict) else "[image]")

    elif tag == "note":
        for ne in element.get("elements", []):
            parts.extend(_extract_element_content(ne))

    elif tag == "column_set":
        for col in element.get("columns", []):
            for ce in col.get("elements", []):
                parts.extend(_extract_element_content(ce))

    elif tag == "plain_text":
        content = element.get("content", "")
        if content:
            parts.append(content)

    else:
        for ne in element.get("elements", []):
            parts.extend(_extract_element_content(ne))

    return parts


def _extract_post_content(content_json: dict) -> tuple[str, list[str]]:
    """Extract text and image keys from Feishu post (rich text) message."""

    def _parse_block(block: dict) -> tuple[str | None, list[str]]:
        if not isinstance(block, dict) or not isinstance(block.get("content"), list):
            return None, []
        texts, images = [], []
        if title := block.get("title"):
            texts.append(title)
        for row in block["content"]:
            if not isinstance(row, list):
                continue
            for el in row:
                if not isinstance(el, dict):
                    continue
                tag = el.get("tag")
                if tag in ("text", "a"):
                    texts.append(el.get("text", ""))
                elif tag == "at":
                    texts.append(f"@{el.get('user_name', 'user')}")
                elif tag == "img" and (key := el.get("image_key")):
                    images.append(key)
        return (" ".join(texts).strip() or None), images

    # Unwrap optional {"post": ...} envelope
    root = content_json
    if isinstance(root, dict) and isinstance(root.get("post"), dict):
        root = root["post"]
    if not isinstance(root, dict):
        return "", []

    # Direct format
    if "content" in root:
        text, imgs = _parse_block(root)
        if text or imgs:
            return text or "", imgs

    # Localized: prefer known locales, then fall back to any dict child
    for key in ("zh_cn", "en_us", "ja_jp"):
        if key in root:
            text, imgs = _parse_block(root[key])
            if text or imgs:
                return text or "", imgs
    for val in root.values():
        if isinstance(val, dict):
            text, imgs = _parse_block(val)
            if text or imgs:
                return text or "", imgs

    return "", []


class FeishuChannel(BaseChannel):
    """Feishu/Lark channel implementation for a single user."""

    channel_type = ChannelType.FEISHU
    display_name = "Feishu / Lark"
    description = "Feishu/Lark enterprise communication platform"
    icon = "message-circle"

    def __init__(self, config: FeishuConfig, message_handler: Optional[Callable] = None):
        super().__init__(config, message_handler)
        self._client: Any = None
        self._ws_client: Any = None
        self._ws_thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._processed_message_ids: OrderedDict[str, None] = OrderedDict()

    @classmethod
    def get_capabilities(cls) -> list[ChannelCapability]:
        """Get Feishu channel capabilities."""
        return [
            ChannelCapability.WEBSOCKET,
            ChannelCapability.WEBHOOK,
            ChannelCapability.SEND_MESSAGE,
            ChannelCapability.SEND_IMAGE,
            ChannelCapability.SEND_FILE,
            ChannelCapability.REACTIONS,
            ChannelCapability.GROUP_CHAT,
            ChannelCapability.DIRECT_MESSAGE,
        ]

    @classmethod
    def get_config_schema(cls) -> dict[str, Any]:
        """Get JSON schema for Feishu configuration."""
        return {
            "type": "object",
            "required": ["app_id", "app_secret"],
            "properties": {
                "app_id": {
                    "type": "string",
                    "title": "App ID",
                    "description": "Feishu application App ID",
                },
                "app_secret": {
                    "type": "string",
                    "title": "App Secret",
                    "description": "Feishu application App Secret",
                    "sensitive": True,
                },
                "verification_token": {
                    "type": "string",
                    "title": "Verification Token",
                    "description": "Verification token for webhook events (optional)",
                },
                "encrypt_key": {
                    "type": "string",
                    "title": "Encrypt Key",
                    "description": "Encryption key for event decryption (optional)",
                    "sensitive": True,
                },
                "group_policy": {
                    "type": "string",
                    "enum": ["open", "mention"],
                    "title": "Group Policy",
                    "description": "How to handle group messages",
                    "default": "mention",
                },
                "react_emoji": {
                    "type": "string",
                    "title": "Reaction Emoji",
                    "description": "Emoji to react when receiving messages",
                    "default": "THUMBSUP",
                },
            },
        }

    @classmethod
    def get_config_fields(cls) -> list[dict[str, Any]]:
        """Get configuration fields for UI rendering."""
        return [
            {
                "name": "app_id",
                "title": "App ID",
                "type": "text",
                "required": True,
                "sensitive": False,
                "placeholder": "cli_xxxxxxxxxx",
            },
            {
                "name": "app_secret",
                "title": "App Secret",
                "type": "password",
                "required": True,
                "sensitive": True,
                "placeholder": "",
            },
            {
                "name": "encrypt_key",
                "title": "Encrypt Key",
                "type": "text",
                "required": False,
                "sensitive": True,
                "placeholder": "",
            },
            {
                "name": "verification_token",
                "title": "Verification Token",
                "type": "text",
                "required": False,
                "sensitive": False,
                "placeholder": "",
            },
            {
                "name": "react_emoji",
                "title": "Reaction Emoji",
                "type": "select",
                "required": False,
                "sensitive": False,
                "default": "THUMBSUP",
                "options": [
                    {"value": "THUMBSUP", "label": "👍 Thumbs Up"},
                    {"value": "OK", "label": "👌 OK"},
                    {"value": "EYES", "label": "👀 Eyes"},
                    {"value": "DONE", "label": "✅ Done"},
                    {"value": "HEART", "label": "❤️ Heart"},
                    {"value": "FIRE", "label": "🔥 Fire"},
                ],
            },
            {
                "name": "group_policy",
                "title": "Group Message Policy",
                "type": "select",
                "required": False,
                "sensitive": False,
                "default": "mention",
                "options": [
                    {"value": "mention", "label": "Reply only when @mentioned"},
                    {"value": "open", "label": "Reply to all messages"},
                ],
            },
        ]

    @classmethod
    def get_setup_guide(cls) -> list[str]:
        """Get Feishu setup guide."""
        return [
            "Go to Feishu Open Platform (open.feishu.cn)",
            "Create a custom app and get App ID and App Secret",
            "Enable bot capability and subscribe to message events",
            "Use WebSocket long connection (no public IP required)",
        ]

    async def start(self) -> bool:
        """Start the Feishu bot with WebSocket long connection."""
        if not FEISHU_AVAILABLE:
            logger.error(
                f"Feishu SDK not installed for user {self.config.user_id}. Run: pip install lark-oapi"
            )
            return False

        if not self.config.app_id or not self.config.app_secret:
            logger.error(
                f"Feishu app_id and app_secret not configured for user {self.config.user_id}"
            )
            return False

        import lark_oapi as lark

        self._running = True
        self._loop = asyncio.get_running_loop()

        # Create Lark client for sending messages
        self._client = (
            lark.Client.builder()
            .app_id(self.config.app_id)
            .app_secret(self.config.app_secret)
            .log_level(lark.LogLevel.INFO)
            .build()
        )

        builder = lark.EventDispatcherHandler.builder(
            self.config.encrypt_key or "",
            self.config.verification_token or "",
        ).register_p2_im_message_receive_v1(self._on_message_sync)

        event_handler = builder.build()

        # Create WebSocket client for long connection
        self._ws_client = lark.ws.Client(
            self.config.app_id,
            self.config.app_secret,
            event_handler=event_handler,
            log_level=lark.LogLevel.INFO,
        )

        # Start WebSocket client in a separate thread
        def run_ws():
            import time

            import lark_oapi.ws.client as _lark_ws_client

            ws_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(ws_loop)
            _lark_ws_client.loop = ws_loop
            try:
                while self._running:
                    try:
                        self._ws_client.start()
                    except Exception as e:
                        logger.warning(
                            f"Feishu WebSocket error for user {self.config.user_id}: {e}"
                        )
                    if self._running:
                        time.sleep(5)
            finally:
                ws_loop.close()

        self._ws_thread = threading.Thread(target=run_ws, daemon=True)
        self._ws_thread.start()

        logger.info(
            f"Feishu bot started for user {self.config.user_id} with WebSocket long connection"
        )
        return True

    async def stop(self) -> None:
        """Stop the Feishu bot."""
        self._running = False
        logger.info(f"Feishu bot stopped for user {self.config.user_id}")

    def _is_bot_mentioned(self, message: Any) -> bool:
        """Check if the bot is @mentioned in the message."""
        raw_content = message.content or ""
        if "@_all" in raw_content:
            return True

        for mention in getattr(message, "mentions", None) or []:
            mid = getattr(mention, "id", None)
            if not mid:
                continue
            if not getattr(mid, "user_id", None) and (
                getattr(mid, "open_id", None) or ""
            ).startswith("ou_"):
                return True
        return False

    def _is_group_message_for_bot(self, message: Any) -> bool:
        """Allow group messages when policy is open or bot is @mentioned."""
        if self.config.group_policy == FeishuGroupPolicy.OPEN:
            return True
        return self._is_bot_mentioned(message)

    def _add_reaction_sync(self, message_id: str, emoji_type: str) -> None:
        """Sync helper for adding reaction."""
        from lark_oapi.api.im.v1 import (
            CreateMessageReactionRequest,
            CreateMessageReactionRequestBody,
            Emoji,
        )

        try:
            request = (
                CreateMessageReactionRequest.builder()
                .message_id(message_id)
                .request_body(
                    CreateMessageReactionRequestBody.builder()
                    .reaction_type(Emoji.builder().emoji_type(emoji_type).build())
                    .build()
                )
                .build()
            )

            response = self._client.im.v1.message_reaction.create(request)

            if not response.success():
                logger.warning(f"Failed to add reaction: code={response.code}, msg={response.msg}")
        except Exception as e:
            logger.warning(f"Error adding reaction: {e}")

    async def _add_reaction(self, message_id: str, emoji_type: str = "THUMBSUP") -> None:
        """Add a reaction emoji to a message."""
        if not self._client:
            return

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, self._add_reaction_sync, message_id, emoji_type)

    def _send_message_sync(
        self, receive_id_type: str, receive_id: str, msg_type: str, content: str
    ) -> bool:
        """Send a message synchronously."""
        from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

        try:
            request = (
                CreateMessageRequest.builder()
                .receive_id_type(receive_id_type)
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(receive_id)
                    .msg_type(msg_type)
                    .content(content)
                    .build()
                )
                .build()
            )
            response = self._client.im.v1.message.create(request)
            if not response.success():
                logger.error(
                    f"Failed to send Feishu {msg_type} message: code={response.code}, msg={response.msg}"
                )
                return False
            return True
        except Exception as e:
            logger.error(f"Error sending Feishu {msg_type} message: {e}")
            return False

    async def send_message(self, chat_id: str, content: str) -> bool:
        """Send a text message to a chat."""
        if not self._client:
            return False

        receive_id_type = "chat_id" if chat_id.startswith("oc_") else "open_id"
        text_body = json.dumps({"text": content}, ensure_ascii=False)

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._send_message_sync, receive_id_type, chat_id, "text", text_body
        )

    def _send_message_with_id_sync(
        self, receive_id_type: str, receive_id: str, msg_type: str, content: str
    ) -> tuple[bool, str | None]:
        """Send a message synchronously and return (success, message_id)."""
        from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

        try:
            request = (
                CreateMessageRequest.builder()
                .receive_id_type(receive_id_type)
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(receive_id)
                    .msg_type(msg_type)
                    .content(content)
                    .build()
                )
                .build()
            )
            response = self._client.im.v1.message.create(request)
            if not response.success():
                logger.error(
                    f"Failed to send Feishu {msg_type} message: code={response.code}, msg={response.msg}"
                )
                return False, None
            # 返回 message_id (response.data 是属性，不是方法)
            data = response.data
            message_id = data.message_id if data else None
            return True, message_id
        except Exception as e:
            logger.error(f"Error sending Feishu {msg_type} message: {e}")
            return False, None

    async def send_message_with_id(self, chat_id: str, content: str) -> tuple[bool, str | None]:
        """Send a text message and return (success, message_id)."""
        if not self._client:
            return False, None

        receive_id_type = "chat_id" if chat_id.startswith("oc_") else "open_id"
        text_body = json.dumps({"text": content}, ensure_ascii=False)

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._send_message_with_id_sync, receive_id_type, chat_id, "text", text_body
        )

    def _send_card_message_sync(
        self,
        receive_id_type: str,
        receive_id: str,
        card_content: str,
        reply_to_id: str | None = None,
    ) -> tuple[bool, str | None]:
        """Send a card message synchronously and return (success, message_id).

        Args:
            receive_id_type: Type of receive_id (chat_id, open_id, etc.)
            receive_id: The target ID
            card_content: JSON string of the card content
            reply_to_id: Optional message ID to reply to (for quote/reply)
        """
        try:
            # 使用 ReplyMessageRequest API 进行回复
            if reply_to_id:
                from lark_oapi.api.im.v1 import ReplyMessageRequest, ReplyMessageRequestBody

                request = (
                    ReplyMessageRequest.builder()
                    .message_id(reply_to_id)
                    .request_body(
                        ReplyMessageRequestBody.builder()
                        .msg_type("interactive")
                        .content(card_content)
                        .build()
                    )
                    .build()
                )
                response = self._client.im.v1.message.reply(request)
            else:
                # 使用 CreateMessageRequest API 发送新消息
                from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

                request = (
                    CreateMessageRequest.builder()
                    .receive_id_type(receive_id_type)
                    .request_body(
                        CreateMessageRequestBody.builder()
                        .receive_id(receive_id)
                        .msg_type("interactive")
                        .content(card_content)
                        .build()
                    )
                    .build()
                )
                response = self._client.im.v1.message.create(request)

            if not response.success():
                logger.error(
                    f"Failed to send Feishu card message: code={response.code}, msg={response.msg}"
                )
                return False, None
            data = response.data
            message_id = data.message_id if data else None
            return True, message_id
        except Exception as e:
            logger.error(f"Error sending Feishu card message: {e}")
            return False, None

    async def _send_card_message_internal(
        self,
        receive_id_type: str,
        receive_id: str,
        card_content: str,
        reply_to_id: str | None = None,
    ) -> tuple[bool, str | None]:
        """Send a card message and return (success, message_id).

        Args:
            receive_id_type: Type of receive_id
            receive_id: The target ID
            card_content: JSON string of the card content
            reply_to_id: Optional message ID to reply to
        """
        if not self._client:
            return False, None

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            self._send_card_message_sync,
            receive_id_type,
            receive_id,
            card_content,
            reply_to_id,
        )

    async def send_card_message(
        self, chat_id: str, card_content: str, reply_to_id: str | None = None
    ) -> bool:
        """Send a card message to a chat.

        Args:
            chat_id: Chat ID or open_id
            card_content: JSON string of the card content
            reply_to_id: Optional message ID to reply to (for quote/reply)
        """
        if not self._client:
            return False

        receive_id_type = "chat_id" if chat_id.startswith("oc_") else "open_id"
        success, _ = await self._send_card_message_internal(
            receive_id_type, chat_id, card_content, reply_to_id
        )
        return success

    def _patch_message_sync(self, message_id: str, content: str) -> bool:
        """Patch/update a message synchronously. Only works for card messages."""
        from lark_oapi.api.im.v1 import PatchMessageRequest, PatchMessageRequestBody

        try:
            request = (
                PatchMessageRequest.builder()
                .message_id(message_id)
                .request_body(PatchMessageRequestBody.builder().content(content).build())
                .build()
            )
            response = self._client.im.v1.message.patch(request)
            if not response.success():
                logger.debug(
                    f"Failed to patch Feishu message (may not be a card): code={response.code}"
                )
                return False
            return True
        except Exception as e:
            logger.debug(f"Error patching Feishu message: {e}")
            return False

    def _update_text_message_sync(self, message_id: str, content: str) -> bool:
        """Update a text message using the update API."""
        from lark_oapi.api.im.v1 import UpdateMessageRequest, UpdateMessageRequestBody

        try:
            text_body = json.dumps({"text": content}, ensure_ascii=False)
            request = (
                UpdateMessageRequest.builder()
                .message_id(message_id)
                .request_body(UpdateMessageRequestBody.builder().content(text_body).build())
                .build()
            )
            response = self._client.im.v1.message.update(request)
            if not response.success():
                logger.debug(f"Failed to update Feishu text message: code={response.code}")
                return False
            return True
        except Exception as e:
            logger.debug(f"Error updating Feishu text message: {e}")
            return False

    async def patch_message(self, message_id: str, content: str) -> bool:
        """Update an existing message's content. Tries update API first, then patch."""
        if not self._client:
            return False

        text_body = json.dumps({"text": content}, ensure_ascii=False)

        loop = asyncio.get_running_loop()

        # 先尝试 update API（适用于文本消息）
        success = await loop.run_in_executor(
            None, self._update_text_message_sync, message_id, content
        )
        if success:
            return True

        # 降级到 patch API（仅适用于卡片消息）
        return await loop.run_in_executor(None, self._patch_message_sync, message_id, text_body)

    def _upload_file_sync(self, file_path: str, file_name: str) -> str | None:
        """Upload a file and return file_key."""
        import os

        from lark_oapi.api.im.v1 import CreateFileRequest, CreateFileRequestBody

        try:
            ext = os.path.splitext(file_name)[1].lower()
            file_type = self._FILE_TYPE_MAP.get(ext, "stream")

            with open(file_path, "rb") as f:
                request = (
                    CreateFileRequest.builder()
                    .request_body(
                        CreateFileRequestBody.builder()
                        .file_name(file_name)
                        .file_type(file_type)
                        .file(f)
                        .build()
                    )
                    .build()
                )

                response = self._client.im.v1.file.create(request)
            if not response.success():
                logger.error(f"Failed to upload file: code={response.code}, msg={response.msg}")
                return None

            data = response.data
            return data.file_key if data else None
        except Exception as e:
            logger.error(f"Error uploading file: {e}")
            return None

    async def upload_file(self, file_path: str, file_name: str) -> str | None:
        """Upload a file asynchronously and return file_key."""
        if not self._client:
            return None

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._upload_file_sync, file_path, file_name)

    # 文件类型映射（与 nanobot 保持一致）
    _FILE_TYPE_MAP = {
        ".opus": "opus",
        ".mp4": "mp4",
        ".pdf": "pdf",
        ".doc": "doc",
        ".docx": "doc",
        ".xls": "xls",
        ".xlsx": "xls",
        ".ppt": "ppt",
        ".pptx": "ppt",
    }

    def _upload_bytes_sync(self, file_data: bytes, file_name: str) -> str | None:
        """Upload file bytes and return file_key."""
        import os
        from io import BytesIO

        from lark_oapi.api.im.v1 import CreateFileRequest, CreateFileRequestBody

        try:
            # 将 bytes 包装成 BytesIO 对象
            file_obj = BytesIO(file_data)
            ext = os.path.splitext(file_name)[1].lower()
            file_type = self._FILE_TYPE_MAP.get(ext, "stream")

            logger.info(
                f"[Feishu] Uploading file: name={file_name}, type={file_type}, size={len(file_data)}"
            )

            request = (
                CreateFileRequest.builder()
                .request_body(
                    CreateFileRequestBody.builder()
                    .file_name(file_name)
                    .file_type(file_type)
                    .file(file_obj)
                    .build()
                )
                .build()
            )

            response = self._client.im.v1.file.create(request)
            if not response.success():
                logger.error(
                    f"Failed to upload file bytes: code={response.code}, msg={response.msg}"
                )
                return None

            data = response.data
            logger.info(
                f"[Feishu] File uploaded successfully: file_key={data.file_key if data else None}"
            )
            return data.file_key if data else None
        except Exception as e:
            logger.error(f"Error uploading file bytes: {e}")
            return None

    async def upload_bytes(self, file_data: bytes, file_name: str) -> str | None:
        """Upload file bytes asynchronously and return file_key."""
        if not self._client:
            return None

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._upload_bytes_sync, file_data, file_name)

    def _send_file_message_sync(self, chat_id: str, file_key: str, file_name: str) -> bool:
        """Send a file message synchronously."""
        from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

        try:
            receive_id_type = "chat_id" if chat_id.startswith("oc_") else "open_id"
            content = json.dumps(
                {
                    "file_key": file_key,
                    "file_name": file_name,
                },
                ensure_ascii=False,
            )

            request = (
                CreateMessageRequest.builder()
                .receive_id_type(receive_id_type)
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(chat_id)
                    .msg_type("file")
                    .content(content)
                    .build()
                )
                .build()
            )

            response = self._client.im.v1.message.create(request)
            if not response.success():
                logger.error(f"Failed to send file message: code={response.code}")
                return False
            return True
        except Exception as e:
            logger.error(f"Error sending file message: {e}")
            return False

    async def send_file_message(self, chat_id: str, file_path: str, file_name: str) -> bool:
        """Upload and send a file message."""
        file_key = await self.upload_file(file_path, file_name)
        if not file_key:
            return False

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._send_file_message_sync, chat_id, file_key, file_name
        )

    async def send_file_by_key(self, chat_id: str, file_key: str, file_name: str) -> bool:
        """Send a file message using an already uploaded file_key.

        Args:
            chat_id: Chat ID or open_id
            file_key: The file_key from a previous upload
            file_name: Display name for the file

        Returns:
            True if successful, False otherwise
        """
        if not self._client:
            return False

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None, self._send_file_message_sync, chat_id, file_key, file_name
        )

    def _on_message_sync(self, data: Any) -> None:
        """Sync handler for incoming messages."""
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._on_message(data), self._loop)

    async def _on_message(self, data: Any) -> None:
        """Handle incoming message from Feishu."""
        try:
            event = data.event
            message = event.message
            sender = event.sender

            # Deduplication check
            message_id = message.message_id
            if message_id in self._processed_message_ids:
                return
            self._processed_message_ids[message_id] = None

            # Trim cache
            while len(self._processed_message_ids) > 1000:
                self._processed_message_ids.popitem(last=False)

            # Skip bot messages
            if sender.sender_type == "bot":
                return

            sender_id = sender.sender_id.open_id if sender.sender_id else "unknown"
            chat_id = message.chat_id
            chat_type = message.chat_type
            msg_type = message.message_type

            if chat_type == "group" and not self._is_group_message_for_bot(message):
                logger.debug(
                    f"Feishu: skipping group message (not mentioned) for user {self.config.user_id}"
                )
                return

            # Add reaction
            await self._add_reaction(message_id, self.config.react_emoji)

            # Parse content
            content_parts = []

            try:
                content_json = json.loads(message.content) if message.content else {}
            except json.JSONDecodeError:
                content_json = {}

            if msg_type == "text":
                text = content_json.get("text", "")
                if text:
                    content_parts.append(text)

            elif msg_type == "post":
                text, _ = _extract_post_content(content_json)
                if text:
                    content_parts.append(text)

            elif msg_type in ("image", "audio", "file", "media"):
                content_parts.append(MSG_TYPE_MAP.get(msg_type, f"[{msg_type}]"))

            elif msg_type in (
                "share_chat",
                "share_user",
                "interactive",
                "share_calendar_event",
                "system",
                "merge_forward",
            ):
                text = _extract_share_card_content(content_json, msg_type)
                if text:
                    content_parts.append(text)

            else:
                content_parts.append(MSG_TYPE_MAP.get(msg_type, f"[{msg_type}]"))

            content = "\n".join(content_parts) if content_parts else ""

            if not content:
                return

            # Forward to message handler via base class method
            reply_to = chat_id if chat_type == "group" else sender_id
            await self._handle_message(
                sender_id=sender_id,
                chat_id=reply_to,
                content=content,
                metadata={
                    "message_id": message_id,
                    "chat_type": chat_type,
                    "msg_type": msg_type,
                },
            )

        except Exception as e:
            logger.error(f"Error processing Feishu message for user {self.config.user_id}: {e}")


class FeishuChannelManager(UserChannelManager):
    """
    Manager for all user Feishu channels.

    Manages multiple Feishu bot connections, one per user.
    """

    channel_type = ChannelType.FEISHU
    config_class = FeishuConfig

    def __init__(self, message_handler: Optional[Callable] = None):
        super().__init__(message_handler)
        self._storage = ChannelStorage()

    @classmethod
    def get_instance(cls) -> "FeishuChannelManager":
        """Get the singleton instance, consistent with get_feishu_channel_manager()."""
        return get_feishu_channel_manager()

    def _dict_to_config(self, user_id: str, config_dict: dict[str, Any]) -> FeishuConfig:
        """Convert a config dict to FeishuConfig."""
        return FeishuConfig(
            user_id=user_id,
            app_id=config_dict.get("app_id") or "",
            app_secret=config_dict.get("app_secret") or "",
            encrypt_key=config_dict.get("encrypt_key") or "",
            verification_token=config_dict.get("verification_token") or "",
            react_emoji=config_dict.get("react_emoji") or "THUMBSUP",
            group_policy=FeishuGroupPolicy(config_dict.get("group_policy") or "mention"),
            enabled=config_dict.get("enabled", True),
        )

    async def start(self) -> None:
        """Start all enabled Feishu channels."""
        if not FEISHU_AVAILABLE:
            logger.warning("Feishu SDK not installed. Run: pip install lark-oapi")
            return

        self._running = True

        # Load all enabled configs from ChannelStorage
        config_dicts = await self._storage.list_enabled_configs(ChannelType.FEISHU)
        logger.info(f"Found {len(config_dicts)} enabled Feishu configurations")

        for config_dict in config_dicts:
            try:
                user_id = config_dict.get("user_id")
                if not user_id:
                    logger.warning("Skipping config without user_id")
                    continue

                # Check if required fields are present (decryption may have failed)
                app_id = config_dict.get("app_id") or ""
                app_secret = config_dict.get("app_secret") or ""

                if not app_id or not app_secret:
                    logger.warning(
                        f"Skipping Feishu config for user {user_id}: "
                        "missing app_id or app_secret (decryption may have failed). "
                        "Please re-save the channel configuration."
                    )
                    continue

                config = self._dict_to_config(user_id, config_dict)
                await self._start_user_client(config)
            except Exception as e:
                logger.error(
                    f"Failed to start Feishu client for user {config_dict.get('user_id')}: {e}"
                )

    async def stop(self) -> None:
        """Stop all Feishu channels."""
        self._running = False

        for user_id, client in list(self._channels.items()):
            try:
                await client.stop()
            except Exception as e:
                logger.error(f"Error stopping Feishu client for user {user_id}: {e}")

        self._channels.clear()
        await self._storage.close()

    async def _start_user_client(self, config: FeishuConfig) -> bool:
        """Start a user's Feishu client."""
        if config.user_id in self._channels:
            await self._channels[config.user_id].stop()

        client = FeishuChannel(config, self._message_handler)
        success = await client.start()

        if success:
            self._channels[config.user_id] = client
            return True
        return False

    async def reload_user(self, user_id: str) -> bool:
        """Reload a user's Feishu configuration and restart the client."""
        config_dict = await self._storage.get_config(user_id, ChannelType.FEISHU)

        # Stop existing client if any
        if user_id in self._channels:
            await self._channels[user_id].stop()
            del self._channels[user_id]

        # Start new client if enabled
        if config_dict and config_dict.get("enabled", True):
            config = self._dict_to_config(user_id, config_dict)
            return await self._start_user_client(config)

        return True

    async def send_message(self, user_id: str, chat_id: str, content: str) -> bool:
        """Send a message through a user's Feishu bot."""
        client = self._channels.get(user_id)
        if not client:
            logger.warning(f"No Feishu client for user {user_id}")
            return False

        return await client.send_message(chat_id, content)

    def is_connected(self, user_id: str) -> bool:
        """Check if a user's Feishu bot is connected."""
        return user_id in self._channels and self._channels[user_id]._running


# Global instance
_feishu_channel_manager: Optional[FeishuChannelManager] = None


def get_feishu_channel_manager() -> FeishuChannelManager:
    """Get the global Feishu channel manager instance."""
    global _feishu_channel_manager
    if _feishu_channel_manager is None:
        _feishu_channel_manager = FeishuChannelManager()
    return _feishu_channel_manager


async def start_feishu_channels(message_handler=None) -> None:
    """Start the Feishu channel manager with all enabled user bots."""
    manager = get_feishu_channel_manager()
    manager._message_handler = message_handler
    await manager.start()


async def stop_feishu_channels() -> None:
    """Stop the Feishu channel manager."""
    global _feishu_channel_manager
    if _feishu_channel_manager:
        await _feishu_channel_manager.stop()
        _feishu_channel_manager = None
