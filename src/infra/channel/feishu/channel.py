"""
Feishu/Lark channel implementation using lark-oapi SDK with WebSocket long connection.

Supports per-user bot configurations - each user can have their own Feishu bot.
"""

import asyncio
import importlib
import importlib.util
import json
import re
import threading
import time
from collections import OrderedDict
from typing import Any, Callable, Optional

from src.infra.async_utils import run_blocking_io
from src.infra.channel.base import BaseChannel
from src.infra.channel.feishu.sender import FeishuSenderMixin
from src.infra.channel.feishu.state import ConnectionState
from src.infra.channel.feishu.utils import (
    MSG_TYPE_MAP,
    extract_post_content,
    extract_share_card_content,
)
from src.infra.logging import get_logger
from src.infra.storage.redis import get_redis_client
from src.kernel.schemas.channel import ChannelCapability, ChannelType
from src.kernel.schemas.feishu import (
    DEFAULT_AUDIO_TRANSCRIBE_PROMPT,
    FeishuConfig,
    FeishuGroupPolicy,
)

logger = get_logger(__name__)

FEISHU_AVAILABLE = importlib.util.find_spec("lark_oapi") is not None
_PROCESSED_MESSAGE_TTL_SECONDS = 15 * 60
_PROCESSED_MESSAGE_CACHE_MAX = 1000
_FEISHU_WS_LOOP_LOCK = threading.Lock()
_FEISHU_WS_LOOP: asyncio.AbstractEventLoop | None = None
_FEISHU_WS_THREAD: threading.Thread | None = None
_LARK_OAPI_WS_PRIVATE_API_VERSION = "1.6.5"


async def _cancel_and_wait_future(future: Any) -> None:
    if future is None or future.done():
        return
    future.cancel()
    try:
        if isinstance(future, asyncio.Future):
            await future
        else:
            await asyncio.wrap_future(future)
    except (asyncio.CancelledError, Exception):
        pass


def _ensure_feishu_ws_loop() -> asyncio.AbstractEventLoop:
    """Return the shared lark-oapi WebSocket loop.

    lark-oapi keeps a process-global ``lark_oapi.ws.client.loop`` and uses it
    inside client methods. Running each tenant on a separate event loop makes
    SDK tasks await futures created by another loop, so all Feishu WS clients
    share one dedicated loop thread.
    """
    global _FEISHU_WS_LOOP, _FEISHU_WS_THREAD
    with _FEISHU_WS_LOOP_LOCK:
        if _FEISHU_WS_LOOP and not _FEISHU_WS_LOOP.is_closed():
            return _FEISHU_WS_LOOP

        ready = threading.Event()
        ws_loop = asyncio.new_event_loop()

        def _run_feishu_ws_loop() -> None:
            import lark_oapi.ws.client as _lark_ws_client

            asyncio.set_event_loop(ws_loop)
            _lark_ws_client.loop = ws_loop
            ready.set()
            ws_loop.run_forever()

        _FEISHU_WS_LOOP = ws_loop
        _FEISHU_WS_THREAD = threading.Thread(
            target=_run_feishu_ws_loop,
            daemon=True,
            name="feishu-ws-loop",
        )
        _FEISHU_WS_THREAD.start()
        ready.wait(timeout=5)
        return ws_loop


class FeishuChannel(FeishuSenderMixin, BaseChannel):
    """Feishu/Lark channel implementation for a single user."""

    channel_type = ChannelType.FEISHU
    display_name = "Feishu / Lark"
    description = "Feishu/Lark enterprise communication platform"
    icon = "BotMessageSquare"

    # Reconnection configuration
    INITIAL_RECONNECT_DELAY = 1.0  # Initial delay in seconds
    MAX_RECONNECT_DELAY = 60.0  # Maximum delay in seconds
    RECONNECT_BACKOFF_FACTOR = 2.0  # Exponential backoff factor
    HEALTH_CHECK_INTERVAL = 30.0  # Check connection health every 30 seconds
    CONNECTION_TIMEOUT = 180.0  # Consider connection dead if no response for 3 minutes

    # Override SDK defaults for faster reconnection
    _SDK_RECONNECT_INTERVAL = 10  # SDK retry interval (default 120s, too slow)
    _SDK_RECONNECT_NONCE = 5  # SDK first-reconnect jitter (default 30s, too much)

    # Processing status emoji shown while the agent is working.
    PROCESSING_EMOJI = "StatusInFlight"

    def __init__(self, config: FeishuConfig, message_handler: Optional[Callable] = None):
        super().__init__(config, message_handler)
        self._client: Any = None
        self._feishu_http_client: Any = None
        self._ws_client: Any = None
        self._ws_thread: threading.Thread | None = None
        self._ws_future: Any = None
        self._health_check_future: Any = None
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
                "stream_reply": {
                    "type": "boolean",
                    "title": "Stream Replies",
                    "description": "Render replies with Feishu CardKit streaming updates",
                    "default": True,
                },
                "auto_transcribe_audio": {
                    "type": "boolean",
                    "title": "Auto Transcribe Audio",
                    "description": "Attach audio and ask the agent to transcribe it",
                    "default": True,
                },
                "audio_transcribe_prompt": {
                    "type": "string",
                    "title": "Audio Transcription Prompt",
                    "description": "Prompt sent to the agent when an audio message arrives",
                    "default": DEFAULT_AUDIO_TRANSCRIBE_PROMPT,
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
                    {"value": "THUMBSUP", "label": "👍 已收到"},
                    {"value": "OK", "label": "👌 好的"},
                    {"value": "DONE", "label": "✅ 已完成"},
                    {"value": "Yes", "label": "☑️ 确认"},
                    {"value": "CheckMark", "label": "✔️ 打勾"},
                    {"value": "Get", "label": "📥 收到"},
                    {"value": "OnIt", "label": "🎯 在做了"},
                    {"value": "OneSecond", "label": "⏳ 稍等"},
                    {"value": "LGTM", "label": "👀 看过了"},
                    {"value": "MeMeMe", "label": "🙋 我来"},
                    {"value": "THANKS", "label": "🙏 谢谢"},
                    {"value": "SALUTE", "label": "🫡 收到"},
                    {"value": "CLAP", "label": "👏 好的"},
                    {"value": "Fire", "label": "🔥 处理中"},
                    {"value": "MUSCLE", "label": "💪 加油"},
                    {"value": "PRAISE", "label": "🏅 好样的"},
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
            {
                "name": "stream_reply",
                "title": "Stream Replies",
                "type": "toggle",
                "required": False,
                "sensitive": False,
                "default": True,
            },
            {
                "name": "auto_transcribe_audio",
                "title": "Auto Transcribe Audio",
                "type": "toggle",
                "required": False,
                "sensitive": False,
                "default": True,
            },
            {
                "name": "audio_transcribe_prompt",
                "title": "Audio Transcription Prompt",
                "type": "textarea",
                "required": False,
                "sensitive": False,
                "default": DEFAULT_AUDIO_TRANSCRIBE_PROMPT,
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

        self._running = True
        self._loop = asyncio.get_running_loop()
        self._set_connection_state(ConnectionState.CONNECTING)

        # Build SDK clients in executor to avoid blocking the event loop
        # (lark SDK import/constructors may make synchronous work)
        def _build_clients():
            lark = importlib.import_module("lark_oapi")
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
            )
            builder = builder.register_p2_im_message_receive_v1(self._on_message_sync)
            if hasattr(builder, "register_p2_im_message_reaction_created_v1"):
                builder = builder.register_p2_im_message_reaction_created_v1(lambda data: None)
            if hasattr(builder, "register_p2_im_message_reaction_deleted_v1"):
                builder = builder.register_p2_im_message_reaction_deleted_v1(lambda data: None)
            if hasattr(builder, "register_p2_card_action_trigger"):
                builder = builder.register_p2_card_action_trigger(self._on_card_action_sync)

            event_handler = builder.build()
            return client, event_handler

        self._client, event_handler = await run_blocking_io(_build_clients)

        self._ws_loop_ref = _ensure_feishu_ws_loop()
        self._ws_future = asyncio.run_coroutine_threadsafe(
            self._run_ws_client(event_handler),
            self._ws_loop_ref,
        )

        self._health_check_future = asyncio.run_coroutine_threadsafe(
            self._health_check_loop(),
            self._ws_loop_ref,
        )

        logger.info(
            f"Feishu bot started for user {self.config.user_id} with WebSocket long connection"
        )
        return True

    async def _run_ws_client(self, event_handler: Any) -> None:
        """Run one SDK WebSocket client on the shared lark-oapi loop."""
        import lark_oapi as lark
        import lark_oapi.ws.client as _lark_ws_client

        ws_loop = asyncio.get_running_loop()
        # lark-oapi reads this process-global loop; every tenant is scheduled
        # onto the shared loop from _ensure_feishu_ws_loop(), so this assignment
        # is idempotent across tenants.
        _lark_ws_client.loop = ws_loop
        self._ws_client = lark.ws.Client(
            self.config.app_id,
            self.config.app_secret,
            event_handler=event_handler,
            log_level=lark.LogLevel.INFO,
            auto_reconnect=True,
        )
        self._ws_client._reconnect_interval = self._SDK_RECONNECT_INTERVAL
        self._ws_client._reconnect_nonce = self._SDK_RECONNECT_NONCE

        ping_task: asyncio.Task | None = None
        try:
            while self._running:
                try:
                    self._set_connection_state(ConnectionState.CONNECTING)
                    logger.info(
                        f"Feishu WebSocket connecting for user {self.config.user_id} "
                        f"(attempt {self._reconnect_attempts + 1})"
                    )
                    await self._sdk_ws_connect()
                    self._set_connection_state(ConnectionState.CONNECTED)
                    self._reset_reconnect_delay()
                    if ping_task is None or ping_task.done():
                        ping_task = self._sdk_ws_start_ping(ws_loop)
                    while self._running:
                        await asyncio.sleep(1)
                except Exception as e:
                    logger.warning(f"Feishu WebSocket error for user {self.config.user_id}: {e}")
                    if self._running:
                        self._set_connection_state(ConnectionState.RECONNECTING)
                        delay = self._get_reconnect_delay()
                        logger.info(
                            f"Reconnecting in {delay:.1f}s (attempt {self._reconnect_attempts})"
                        )
                        await asyncio.sleep(delay)
        finally:
            if ping_task:
                ping_task.cancel()
                try:
                    await ping_task
                except asyncio.CancelledError:
                    pass
            if self._ws_client is not None:
                try:
                    await self._sdk_ws_disconnect()
                except Exception:
                    pass
            self._set_connection_state(ConnectionState.DISCONNECTED)

    async def _sdk_ws_connect(self) -> None:
        """Connect through lark-oapi's private WS API.

        lark-oapi 1.6.5 does not expose a public async runner that can host all
        tenant clients on the SDK's process-global loop. Keep the private-method
        dependency in these adapter methods so future SDK changes have one place
        to update.
        """
        await self._ws_client._connect()

    def _sdk_ws_start_ping(self, loop: asyncio.AbstractEventLoop) -> asyncio.Task:
        """Start the lark-oapi 1.6.5 private ping loop."""
        return loop.create_task(self._ws_client._ping_loop())

    async def _sdk_ws_disconnect(self) -> None:
        """Disconnect through lark-oapi's private WS API."""
        await self._ws_client._disconnect()

    async def _health_check_loop(self) -> None:
        """Observe connection state; reconnects are handled by the SDK.

        The lark-oapi SDK runs its own keep-alive ping loop
        (``_sdk_ws_start_ping``) and auto-reconnects on real disconnects. We
        previously force-closed connections with no business-message activity
        within ``CONNECTION_TIMEOUT``, but ping/pong success never updated that
        timestamp — so healthy idle connections were misjudged as dead and
        cycled every few minutes (issue #200). The loop now only observes.
        """
        while self._running:
            await asyncio.sleep(self.HEALTH_CHECK_INTERVAL)
            if not self._running:
                break
            state = self._get_connection_state()
            if state == ConnectionState.CONNECTED:
                logger.debug(
                    "Feishu connection alive for user %s "
                    "(SDK keep-alive + auto-reconnect active)",
                    self.config.user_id,
                )

    async def stop(self) -> None:
        """Stop the Feishu bot."""
        self._running = False
        if self._ws_loop_ref is not None and self._ws_client is not None:
            try:
                await asyncio.wrap_future(
                    asyncio.run_coroutine_threadsafe(
                        self._sdk_ws_disconnect(),
                        self._ws_loop_ref,
                    )
                )
            except Exception:
                pass
        await _cancel_and_wait_future(self._ws_future)
        await _cancel_and_wait_future(self._health_check_future)
        await self.close_feishu_http_client()
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

    def _on_card_action_sync(self, data: Any) -> Any:
        """Sync handler for Feishu interactive card button clicks."""
        logger.debug("[HITL] Received card action callback")
        self._update_activity_time()
        if self._get_connection_state() != ConnectionState.CONNECTED:
            self._set_connection_state(ConnectionState.CONNECTED)
        response_payload = self._build_card_action_response_payload(data)
        approval_id = self._extract_lambchat_approval_id(data)
        logger.debug(
            "[HITL] approval_id=%s Returned processing card synchronously",
            approval_id,
        )
        if self._loop and self._loop.is_running():
            asyncio.run_coroutine_threadsafe(self._on_card_action(data), self._loop)

        try:
            from lark_oapi.event.callback.model.p2_card_action_trigger import (
                P2CardActionTriggerResponse,
            )

            return P2CardActionTriggerResponse(response_payload)
        except Exception:
            return None

    def _build_card_action_response_payload(self, data: Any) -> dict[str, Any]:
        """Build immediate Feishu callback response payload for known card actions."""
        approval_id = self._extract_lambchat_approval_id(data)
        if not approval_id:
            return {}

        from src.infra.channel.feishu.approval import build_feishu_approval_processing_card_data

        return {
            "card": {
                "type": "raw",
                "data": build_feishu_approval_processing_card_data(approval_id),
            },
            "toast": {
                "type": "success",
                "content": "已收到确认操作，正在处理",
            },
        }

    @staticmethod
    def _extract_lambchat_approval_id(data: Any) -> str | None:
        """Return the LambChat approval id from a Feishu card action callback."""
        try:
            event = getattr(data, "event", None)
            action = getattr(event, "action", None)
            value = getattr(action, "value", None)
            if isinstance(value, str) and value.strip():
                value = json.loads(value)
            if not isinstance(value, dict):
                return None

            from src.infra.channel.feishu.approval import FEISHU_APPROVAL_ACTION

            if value.get("action") != FEISHU_APPROVAL_ACTION:
                return None
            approval_id = value.get("approval_id")
            return approval_id if isinstance(approval_id, str) and approval_id else None
        except Exception:
            return None

    async def _on_card_action(self, data: Any) -> None:
        """Handle Feishu interactive card actions."""
        # This coroutine runs on the main event loop (scheduled from the lark WS
        # thread), so it bypasses the HTTP middleware that normally populates the
        # request context. Seed user_id here so downstream logs auto-include it.
        try:
            from src.infra.logging.context import TraceContext

            TraceContext.set_request_context(user_id=self.config.user_id)
        except Exception as e:
            logger.debug("[HITL] Failed to set request context for card action: %s", e)

        try:
            event = getattr(data, "event", None)
            action = getattr(event, "action", None)
            context = getattr(event, "context", None)
            value = getattr(action, "value", None)
            message_id = getattr(context, "open_message_id", None)

            approval_id = self._extract_lambchat_approval_id(data)
            logger.debug("[HITL] approval_id=%s Handling card action", approval_id)

            from src.infra.channel.feishu.approval import handle_feishu_approval_action
            from src.infra.channel.feishu.manager import get_feishu_channel_manager

            await handle_feishu_approval_action(
                value=value,
                message_id=message_id,
                user_id=self.config.user_id,
                instance_id=self.config.instance_id,
                manager=get_feishu_channel_manager(),
            )
        except Exception as e:
            logger.error(
                f"Error processing Feishu card action for user {self.config.user_id}: {e}",
                exc_info=True,
            )

    async def _on_message(self, data: Any) -> None:
        """Handle incoming message from Feishu."""
        try:
            event = data.event
            message = event.message
            sender = event.sender

            # Deduplication check
            message_id = message.message_id
            if not await self._mark_message_processed(message_id):
                return

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

            # Add reaction to indicate the message is being handled; the handler
            # receives the reaction id so it can remove it after processing.
            reaction_id = await self._add_reaction(message_id, self.config.react_emoji)

            # Parse content and extract attachments
            content_parts = []
            attachments = []

            try:
                content_json = (
                    await run_blocking_io(json.loads, message.content) if message.content else {}
                )
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
                file_key = content_json.get("file_key")
                file_name = content_json.get("file_name") or content_json.get("name") or file_key
                if msg_type == "audio" and file_name and "." not in file_name:
                    file_name = f"{file_name}.opus"
                if msg_type == "media" and file_name and "." not in file_name:
                    file_name = f"{file_name}.mp4"

                if file_key and file_name:
                    attachment_type = (
                        "audio"
                        if msg_type == "audio"
                        else "video"
                        if msg_type == "media"
                        else "document"
                    )
                    content_type = (
                        "audio/ogg"
                        if msg_type == "audio"
                        else "video/mp4"
                        if msg_type == "media"
                        else None
                    )
                    attachment = await self._download_and_store_resource(
                        file_key,
                        message_id,
                        resource_type="file",
                        file_name=file_name,
                        attachment_type=attachment_type,
                        content_type=content_type,
                    )
                    if attachment:
                        attachments.append(attachment)

                if msg_type == "audio" and getattr(self.config, "auto_transcribe_audio", True):
                    content_parts.append(
                        getattr(
                            self.config,
                            "audio_transcribe_prompt",
                            DEFAULT_AUDIO_TRANSCRIBE_PROMPT,
                        )
                        or DEFAULT_AUDIO_TRANSCRIBE_PROMPT
                    )
                else:
                    content_parts.append(MSG_TYPE_MAP.get(msg_type, f"[{msg_type}]"))

            elif msg_type in (
                "share_chat",
                "share_user",
                "interactive",
                "share_calendar_event",
                "system",
                "merge_forward",
            ):
                text = await run_blocking_io(extract_share_card_content, content_json, msg_type)
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
                "reply_chat_id": chat_id,
            }
            if reaction_id:
                metadata["reaction_id"] = reaction_id
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

    async def _mark_message_processed(self, message_id: str) -> bool:
        """Mark a message as processed using local cache plus Redis NX dedupe."""
        if message_id in self._processed_message_ids:
            return False

        redis_claimed = True
        try:
            redis_client = get_redis_client()
            redis_claimed = bool(
                await redis_client.set(
                    f"feishu:processed:{message_id}",
                    self.config.instance_id or self.config.user_id,
                    nx=True,
                    ex=_PROCESSED_MESSAGE_TTL_SECONDS,
                )
            )
        except Exception as e:
            logger.warning(
                "Feishu distributed dedupe unavailable for message %s: %s",
                message_id,
                e,
            )

        if not redis_claimed:
            return False

        self._processed_message_ids[message_id] = None
        while len(self._processed_message_ids) > _PROCESSED_MESSAGE_CACHE_MAX:
            self._processed_message_ids.popitem(last=False)
        return True
