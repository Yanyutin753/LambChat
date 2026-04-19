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
from src.infra.channel.feishu.sender import FeishuSenderMixin
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


class FeishuChannel(FeishuSenderMixin, BaseChannel):
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

    # Override SDK defaults for faster reconnection
    _SDK_RECONNECT_INTERVAL = 10  # SDK retry interval (default 120s, too slow)
    _SDK_RECONNECT_NONCE = 5  # SDK first-reconnect jitter (default 30s, too much)

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
        self._ws_loop_ref: asyncio.AbstractEventLoop | None = None
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

        # Override SDK reconnect defaults for faster recovery
        self._ws_client._reconnect_interval = self._SDK_RECONNECT_INTERVAL
        self._ws_client._reconnect_nonce = self._SDK_RECONNECT_NONCE

        # Start WebSocket client in a separate thread
        def run_ws():
            import lark_oapi.ws.client as _lark_ws_client

            ws_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(ws_loop)
            _lark_ws_client.loop = ws_loop
            self._ws_loop_ref = ws_loop

            try:
                while self._running:
                    try:
                        self._set_connection_state(ConnectionState.CONNECTING)
                        logger.info(
                            f"Feishu WebSocket connecting for user {self.config.user_id} "
                            f"(attempt {self._reconnect_attempts + 1})"
                        )
                        self._ws_client.start()
                        # start() blocks until disconnect; reset state for next cycle
                        self._set_connection_state(ConnectionState.CONNECTED)
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
        """Health check loop to detect and force-reconnect zombie connections."""
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
                        "force-closing to trigger reconnect"
                    )
                    self._set_connection_state(ConnectionState.RECONNECTING)
                    # Force-close the underlying connection so the SDK detects
                    # the disconnect and triggers its reconnection loop.
                    try:
                        if self._ws_loop_ref is None:
                            continue
                        asyncio.run_coroutine_threadsafe(
                            self._ws_client._disconnect(), self._ws_loop_ref
                        ).result(timeout=5)
                    except Exception:
                        pass
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
