"""
Feishu/Lark channel implementation using lark-oapi SDK with WebSocket long connection.

Supports per-user bot configurations - each user can have their own Feishu bot.
"""

import asyncio
import importlib.util
import json
import re
import threading
import time
from collections import OrderedDict
from typing import Any, Callable, Optional

from src.infra.channel.base import BaseChannel
from src.infra.channel.feishu.state import ConnectionState
from src.infra.channel.feishu.utils import (
    MSG_TYPE_MAP,
    extract_post_content,
    extract_share_card_content,
)
from src.infra.logging import get_logger
from src.kernel.schemas.channel import ChannelCapability, ChannelType
from src.kernel.schemas.feishu import FeishuConfig, FeishuGroupPolicy

logger = get_logger(__name__)

FEISHU_AVAILABLE = importlib.util.find_spec("lark_oapi") is not None


class FeishuChannel(BaseChannel):
    """Feishu/Lark channel implementation for a single user."""

    channel_type = ChannelType.FEISHU
    display_name = "Feishu / Lark"
    description = "Feishu/Lark enterprise communication platform"
    icon = "message-circle"

    # Reconnection configuration
    INITIAL_RECONNECT_DELAY = 1.0  # Initial delay in seconds
    MAX_RECONNECT_DELAY = 60.0  # Maximum delay in seconds
    RECONNECT_BACKOFF_FACTOR = 2.0  # Exponential backoff factor
    HEALTH_CHECK_INTERVAL = 30.0  # Check connection health every 30 seconds
    CONNECTION_TIMEOUT = 180.0  # Consider connection dead if no response for 3 minutes

    # Processing status emojis (cycled while agent is working)
    PROCESSING_EMOJIS = [
        "StatusInFlight",
        "OneSecond",
        "Typing",
        "OnIt",
        "Coffee",
        "OnIt",
        "EatingFood",
    ]

    def __init__(self, config: FeishuConfig, message_handler: Optional[Callable] = None):
        super().__init__(config, message_handler)
        self._client: Any = None
        self._ws_client: Any = None
        self._ws_thread: threading.Thread | None = None
        self._health_check_thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._processed_message_ids: OrderedDict[str, None] = OrderedDict()
        self._chat_mode_cache: OrderedDict[str, str] = (
            OrderedDict()
        )  # Cache: chat_id -> "group"|"thread"

        # Connection state tracking
        self._connection_state = ConnectionState.DISCONNECTED
        self._state_lock = threading.Lock()
        self._last_activity_time = 0.0
        self._reconnect_attempts = 0
        self._current_reconnect_delay = self.INITIAL_RECONNECT_DELAY

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

    def _set_connection_state(self, new_state: ConnectionState) -> None:
        """Update connection state with logging."""
        with self._state_lock:
            old_state = self._connection_state
            if old_state != new_state:
                self._connection_state = new_state
                logger.info(
                    f"Feishu connection state changed for user {self.config.user_id}: "
                    f"{old_state.value} -> {new_state.value}"
                )
                # Reset reconnect delay on successful connection
                if new_state == ConnectionState.CONNECTED:
                    self._reconnect_attempts = 0
                    self._current_reconnect_delay = self.INITIAL_RECONNECT_DELAY
                    self._last_activity_time = time.time()

    def _get_connection_state(self) -> ConnectionState:
        """Get current connection state."""
        with self._state_lock:
            return self._connection_state

    def _update_activity_time(self) -> None:
        """Update last activity timestamp."""
        self._last_activity_time = time.time()

    def _get_reconnect_delay(self) -> float:
        """Calculate reconnect delay with exponential backoff."""
        delay = self._current_reconnect_delay
        self._reconnect_attempts += 1
        self._current_reconnect_delay = min(
            self._current_reconnect_delay * self.RECONNECT_BACKOFF_FACTOR,
            self.MAX_RECONNECT_DELAY,
        )
        return delay

    def _reset_reconnect_delay(self) -> None:
        """Reset reconnect delay to initial value."""
        self._reconnect_attempts = 0
        self._current_reconnect_delay = self.INITIAL_RECONNECT_DELAY

    def _is_connection_healthy(self) -> bool:
        """Check if connection is healthy based on activity."""
        if self._last_activity_time == 0:
            return True  # No activity recorded yet
        elapsed = time.time() - self._last_activity_time
        return elapsed < self.CONNECTION_TIMEOUT

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
        self._set_connection_state(ConnectionState.CONNECTING)

        # Build SDK clients in executor to avoid blocking the event loop
        # (lark SDK constructors may make synchronous HTTP calls)
        def _build_clients():
            client = (
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

            ws_client = lark.ws.Client(
                self.config.app_id,
                self.config.app_secret,
                event_handler=event_handler,
                log_level=lark.LogLevel.INFO,
            )
            return client, ws_client

        self._client, self._ws_client = await self._loop.run_in_executor(None, _build_clients)

        # Start WebSocket client in a separate thread
        def run_ws():
            import lark_oapi.ws.client as _lark_ws_client

            ws_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(ws_loop)
            _lark_ws_client.loop = ws_loop

            try:
                while self._running:
                    try:
                        self._set_connection_state(ConnectionState.CONNECTING)
                        logger.info(
                            f"Feishu WebSocket connecting for user {self.config.user_id} "
                            f"(attempt {self._reconnect_attempts + 1})"
                        )
                        self._ws_client.start()
                        # If start() returns normally, connection was established and then closed
                        # Set to CONNECTED while the connection is active
                        self._set_connection_state(ConnectionState.CONNECTED)
                        # When start() returns, connection has ended
                        if self._running:
                            self._set_connection_state(ConnectionState.RECONNECTING)
                            delay = self._get_reconnect_delay()
                            logger.warning(
                                f"Feishu WebSocket disconnected for user {self.config.user_id}, "
                                f"reconnecting in {delay:.1f}s"
                            )
                            time.sleep(delay)
                    except Exception as e:
                        logger.warning(
                            f"Feishu WebSocket error for user {self.config.user_id}: {e}"
                        )
                        if self._running:
                            self._set_connection_state(ConnectionState.RECONNECTING)
                            delay = self._get_reconnect_delay()
                            logger.info(
                                f"Reconnecting in {delay:.1f}s (attempt {self._reconnect_attempts})"
                            )
                            time.sleep(delay)
                # Loop exited, set final state
                self._set_connection_state(ConnectionState.DISCONNECTED)
            finally:
                ws_loop.close()

        self._ws_thread = threading.Thread(target=run_ws, daemon=True)
        self._ws_thread.start()

        # Start health check thread
        self._health_check_thread = threading.Thread(target=self._health_check_loop, daemon=True)
        self._health_check_thread.start()

        logger.info(
            f"Feishu bot started for user {self.config.user_id} with WebSocket long connection"
        )
        return True

    def _health_check_loop(self) -> None:
        """Health check loop to detect zombie connections."""
        while self._running:
            time.sleep(self.HEALTH_CHECK_INTERVAL)
            if not self._running:
                break

            state = self._get_connection_state()
            if state == ConnectionState.CONNECTED:
                if not self._is_connection_healthy():
                    logger.warning(
                        f"Feishu connection appears dead for user {self.config.user_id} "
                        f"(no activity for {time.time() - self._last_activity_time:.0f}s), "
                        "will attempt reconnect"
                    )
                    # The SDK should handle reconnection, but we log the issue
                    self._set_connection_state(ConnectionState.RECONNECTING)
                else:
                    logger.debug(f"Feishu connection healthy for user {self.config.user_id}")

    async def stop(self) -> None:
        """Stop the Feishu bot."""
        self._running = False
        self._set_connection_state(ConnectionState.DISCONNECTED)
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

    async def send_message(self, chat_id: str, content: str, **kwargs: Any) -> bool:
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
            # Return message_id (response.data is an attribute, not a method)
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
            # Use ReplyMessageRequest API for replies
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

                # If original message was withdrawn (230011), fallback to new message
                if not response.success() and response.code == 230011:
                    logger.warning(
                        f"Original message {reply_to_id} was withdrawn, falling back to new message"
                    )
                    from lark_oapi.api.im.v1 import (
                        CreateMessageRequest,
                        CreateMessageRequestBody,
                    )

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
            else:
                # Use CreateMessageRequest API for new messages
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

        # Try update API first (for text messages)
        success = await loop.run_in_executor(
            None, self._update_text_message_sync, message_id, content
        )
        if success:
            return True

        # Fall back to patch API (for card messages only)
        return await loop.run_in_executor(None, self._patch_message_sync, message_id, text_body)

    # File type mapping (consistent with nanobot)
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

    def _upload_bytes_sync(self, file_data: bytes, file_name: str) -> str | None:
        """Upload file bytes and return file_key."""
        import os
        from io import BytesIO

        from lark_oapi.api.im.v1 import CreateFileRequest, CreateFileRequestBody

        try:
            # Wrap bytes in BytesIO object
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

    def _download_image_sync(self, image_key: str, message_id: str) -> bytes | None:
        """Download image from Feishu via GetMessageResourceRequest (sync, runs in executor)."""
        from lark_oapi.api.im.v1 import GetMessageResourceRequest

        try:
            request = (
                GetMessageResourceRequest.builder()
                .message_id(message_id)
                .file_key(image_key)
                .type("image")
                .build()
            )
            response = self._client.im.v1.message_resource.get(request)
            if response.success():
                return response.file.read()
            logger.warning(f"Failed to download image: code={response.code}, msg={response.msg}")
        except Exception as e:
            logger.error(f"Error downloading Feishu image: {e}")
        return None

    async def _download_and_store_image(self, image_key: str, message_id: str) -> dict | None:
        """Download image from Feishu, upload to S3, return attachment info dict."""
        loop = asyncio.get_running_loop()
        image_bytes = await loop.run_in_executor(
            None, self._download_image_sync, image_key, message_id
        )
        if not image_bytes:
            return None

        try:
            from src.api.routes.upload import get_or_init_storage

            storage = await get_or_init_storage()
            result = await storage.upload_bytes(
                data=image_bytes,
                folder="feishu_images",
                filename=f"{image_key}.png",
                content_type="image/png",
            )
            url = result.url or storage.get_file_url(result.key)
            return {
                "key": result.key,
                "name": f"{image_key}.png",
                "type": "image",
                "url": url,
            }
        except Exception as e:
            logger.error(f"Error uploading Feishu image to S3: {e}")
            return None

    def _upload_image_sync(self, image_data: bytes) -> str | None:
        """Upload image to Feishu media library, return image_key (sync, runs in executor)."""
        from io import BytesIO

        from lark_oapi.api.im.v1 import CreateImageRequest, CreateImageRequestBody

        try:
            request = (
                CreateImageRequest.builder()
                .request_body(
                    CreateImageRequestBody.builder()
                    .image_type("message")
                    .image(BytesIO(image_data))
                    .build()
                )
                .build()
            )
            response = self._client.im.v1.image.create(request)
            if response.success():
                return response.data.image_key
            logger.warning(
                f"Failed to upload image to Feishu: code={response.code}, msg={response.msg}"
            )
        except Exception as e:
            logger.error(f"Error uploading image to Feishu: {e}")
        return None

    async def upload_image(self, image_data: bytes) -> str | None:
        """Upload image to Feishu media library asynchronously, return image_key."""
        if not self._client:
            return None

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._upload_image_sync, image_data)

    def _get_chat_mode_sync(self, chat_id: str) -> str:
        """Get chat mode: 'group' (normal) or 'thread' (topic group) via GetChatRequest (sync)."""
        from lark_oapi.api.im.v1 import GetChatRequest

        try:
            request = GetChatRequest.builder().chat_id(chat_id).build()
            response = self._client.im.v1.chat.get(request)
            if response.success():
                chat_mode = getattr(response.data, "chat_mode", "group")
                return "thread" if chat_mode == "topic" else "group"
            logger.warning(f"Failed to get chat mode for {chat_id}: {response.msg}")
        except Exception as e:
            logger.warning(f"Error getting chat mode for {chat_id}: {e}")
        return "group"

    async def _get_chat_mode(self, chat_id: str) -> str:
        """Get chat mode with caching."""
        if chat_id in self._chat_mode_cache:
            self._chat_mode_cache.move_to_end(chat_id)
            return self._chat_mode_cache[chat_id]

        loop = asyncio.get_running_loop()
        mode = await loop.run_in_executor(None, self._get_chat_mode_sync, chat_id)
        self._chat_mode_cache[chat_id] = mode
        # LRU eviction: keep at most 1000 entries
        while len(self._chat_mode_cache) > 1000:
            self._chat_mode_cache.popitem(last=False)
        return mode

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
        # Update activity time to indicate connection is alive
        self._update_activity_time()
        # Set state to connected if not already
        if self._get_connection_state() != ConnectionState.CONNECTED:
            self._set_connection_state(ConnectionState.CONNECTED)
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

            # Add reaction to indicate "seen"
            await self._add_reaction(message_id, self.config.react_emoji)

            # Parse content and extract attachments
            content_parts = []
            attachments = []

            try:
                content_json = json.loads(message.content) if message.content else {}
            except json.JSONDecodeError:
                content_json = {}

            if msg_type == "text":
                text = content_json.get("text", "")
                if text:
                    content_parts.append(text)

            elif msg_type == "post":
                text, image_keys = extract_post_content(content_json)
                if text:
                    content_parts.append(text)
                # Download embedded images from post
                for img_key in image_keys:
                    attachment = await self._download_and_store_image(img_key, message_id)
                    if attachment:
                        attachments.append(attachment)

            elif msg_type == "image":
                image_key = content_json.get("image_key")
                if image_key:
                    content_parts.append("[image]")
                    attachment = await self._download_and_store_image(image_key, message_id)
                    if attachment:
                        attachments.append(attachment)
                else:
                    content_parts.append("[image]")

            elif msg_type in ("audio", "file", "media"):
                content_parts.append(MSG_TYPE_MAP.get(msg_type, f"[{msg_type}]"))

            elif msg_type in (
                "share_chat",
                "share_user",
                "interactive",
                "share_calendar_event",
                "system",
                "merge_forward",
            ):
                text = extract_share_card_content(content_json, msg_type)
                if text:
                    content_parts.append(text)

            else:
                content_parts.append(MSG_TYPE_MAP.get(msg_type, f"[{msg_type}]"))

            content = "\n".join(content_parts) if content_parts else ""

            # Replace @_user_N mentions with actual sender
            content = re.sub(r"@_user_\d+", f"@{sender_id}", content)

            if not content and not attachments:
                return

            # Determine reply_to and handle topic groups
            reply_to = chat_id if chat_type == "group" else sender_id
            root_id = None

            if chat_type == "group":
                chat_mode = await self._get_chat_mode(chat_id)
                if chat_mode == "thread":
                    root_id = message.root_id or message_id
                    # Use root_id as session isolation key
                    reply_to = f"{chat_id}#{root_id}"

            # Forward to message handler via base class method
            metadata = {
                "message_id": message_id,
                "chat_type": chat_type,
                "msg_type": msg_type,
                "sender_id": sender_id,
            }
            if root_id:
                metadata["root_id"] = root_id
            if attachments:
                metadata["attachments"] = attachments

            await self._handle_message(
                sender_id=sender_id,
                chat_id=reply_to,
                content=content,
                metadata=metadata,
            )

        except Exception as e:
            logger.error(f"Error processing Feishu message for user {self.config.user_id}: {e}")
