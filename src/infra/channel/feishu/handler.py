"""
Feishu 消息处理器模块

处理飞书消息的 Agent 执行和响应。
发送一条卡片消息，支持 markdown 渲染。
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from tempfile import NamedTemporaryFile
from typing import Any, AsyncGenerator, Callable, Optional, cast

from src.infra.async_utils import run_blocking_io
from src.infra.channel.feishu import handler_helpers
from src.infra.channel.feishu.channel import FeishuChannel
from src.infra.channel.feishu.handler_helpers import (
    _SESSION_LINK_TEXT,
    EVENT_MESSAGE_CHUNK,
    EVENT_TOOL_RESULT,
    EVENT_TOOL_START,
    FEISHU_REVEAL_DOWNLOAD_CHUNK_SIZE,
    FEISHU_REVEAL_DOWNLOAD_MAX_BYTES,
    FEISHU_REVEAL_LEGACY_DOWNLOAD_MAX_BYTES,
    FEISHU_STREAM_FIRST_PAINT_CHARS,
    FEISHU_STREAM_UPDATE_DEBOUNCE_SECONDS,
    _build_session_run_url,
    _create_new_feishu_session,
    _extract_tool_media_files,
    _get_feishu_session_id,
)
from src.infra.channel.feishu.manager import FeishuChannelManager
from src.infra.channel.feishu.markdown import FeishuMarkdownAdapter
from src.infra.logging import get_logger
from src.infra.utils.datetime import utc_now
from src.kernel.config import settings  # noqa: F401 - compatibility for handler tests/patching
from src.kernel.extensions import BUILTIN_PLUGIN_MANIFESTS, PluginRuntime
from src.kernel.extensions.plugin_options import (
    AGENT_TEAM_PLUGIN_ID,
    AGENT_TEAM_SELECTED_TEAM_OPTION,
    agent_uses_agent_team_options,
    declared_plugin_options_from_metadata,
    plugin_option_from_metadata,
)

logger = get_logger(__name__)

_STREAM_UPDATE_SIGNAL = object()
EVENT_APPROVAL_REQUIRED = "approval_required"
FEISHU_APPROVAL_ACTION = "lambchat.approval"
_FEISHU_APPROVAL_ACTION_LOCK_TTL_SECONDS = 30
_feishu_approval_action_locks: set[str] = set()


async def _download_storage_object_to_file(
    backend: Any,
    key: str,
    file: Any,
    *,
    chunk_size: int = FEISHU_REVEAL_DOWNLOAD_CHUNK_SIZE,
) -> int:
    handler_helpers.FEISHU_REVEAL_LEGACY_DOWNLOAD_MAX_BYTES = (
        FEISHU_REVEAL_LEGACY_DOWNLOAD_MAX_BYTES
    )
    handler_helpers.FEISHU_REVEAL_DOWNLOAD_MAX_BYTES = FEISHU_REVEAL_DOWNLOAD_MAX_BYTES
    handler_helpers.run_blocking_io = run_blocking_io
    return await handler_helpers._download_storage_object_to_file(
        backend,
        key,
        file,
        chunk_size=chunk_size,
    )


def _approval_status_text(status: str) -> str:
    return {
        "pending": "等待确认",
        "processing": "正在处理",
        "approved": "已确认",
        "rejected": "已拒绝",
        "error": "处理失败",
    }.get(status, status)


def _approval_message_preview(message: str, *, max_chars: int = 1600) -> str:
    message = message.strip()
    if len(message) <= max_chars:
        return message
    return f"{message[:max_chars].rstrip()}\n\n...（内容较长，请打开详情页查看完整信息）"


def _coerce_json_dict(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    return None


def _extract_approval_result_status(result: Any) -> tuple[str | None, str]:
    data = _coerce_json_dict(result)
    if not data:
        return None, "pending"
    approval_id = data.get("approval_id")
    if not isinstance(approval_id, str) or not approval_id:
        return None, "pending"
    status = str(data.get("status") or "")
    if status == "approved" or data.get("approved") is True:
        return approval_id, "approved"
    if status == "rejected" or data.get("approved") is False:
        return approval_id, "rejected"
    if status == "timeout":
        return approval_id, "error"
    return approval_id, "pending"


def _approval_status_from_record(approval: Any, response: Any = None) -> str:
    status = str(getattr(approval, "status", "") or "")
    if status in {"approved", "rejected"}:
        return status
    approved = getattr(response, "approved", None)
    if approved is True:
        return "approved"
    if approved is False:
        return "rejected"
    return "error"


async def _get_existing_approval_status(approval_id: str) -> str:
    from src.infra.storage.mongodb import get_approval_storage

    storage = get_approval_storage()
    approval = await storage.get(approval_id)
    response = await storage.get_response(approval_id)
    return _approval_status_from_record(approval, response)


async def _respond_to_human_approval(approval_id: str, *, approved: bool) -> None:
    from src.api.routes.human import respond_to_approval

    await respond_to_approval(
        approval_id,
        approved=approved,
        response="{}",
    )


async def _claim_feishu_approval_action(approval_id: str) -> bool:
    if approval_id in _feishu_approval_action_locks:
        return False

    try:
        from src.infra.storage.redis import get_redis_client

        redis_client = get_redis_client()
        claimed = await redis_client.set(
            f"feishu:approval_action:{approval_id}",
            "1",
            nx=True,
            ex=_FEISHU_APPROVAL_ACTION_LOCK_TTL_SECONDS,
        )
        if not claimed:
            return False
    except Exception as e:
        logger.debug("[Feishu] Redis approval action dedupe unavailable: %s", e)

    _feishu_approval_action_locks.add(approval_id)
    return True


def _release_feishu_approval_action(approval_id: str) -> None:
    _feishu_approval_action_locks.discard(approval_id)


async def _build_approval_card_content(
    approval: dict[str, Any],
    *,
    session_url: str | None,
    status: str,
) -> str:
    approval_id = str(approval.get("id") or "")
    approval_type = str(approval.get("type") or "form")
    message = _approval_message_preview(str(approval.get("message") or "需要用户确认"))
    pending = status == "pending"

    elements: list[dict[str, Any]] = [
        {
            "tag": "markdown",
            "content": f"**需要用户确认**\n\n{message}",
        },
        {"tag": "hr"},
        {
            "tag": "markdown",
            "content": f"状态：**{_approval_status_text(status)}**",
        },
    ]

    actions: list[dict[str, Any]] = []
    if pending and approval_type == "confirm":
        actions.extend(
            [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "确认"},
                    "type": "primary",
                    "value": {
                        "action": FEISHU_APPROVAL_ACTION,
                        "approval_id": approval_id,
                        "approved": True,
                    },
                },
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "拒绝"},
                    "type": "danger",
                    "value": {
                        "action": FEISHU_APPROVAL_ACTION,
                        "approval_id": approval_id,
                        "approved": False,
                    },
                },
            ]
        )

    if session_url:
        actions.append(
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "打开详情页"},
                "type": "default",
                "url": session_url,
            }
        )

    if actions:
        elements.append({"tag": "action", "actions": actions})

    card = {"config": {"wide_screen_mode": True}, "elements": elements}
    return json.dumps(card, ensure_ascii=False)


def build_feishu_approval_processing_card_data(approval_id: str) -> dict[str, Any]:
    """Build card JSON returned synchronously to disable clicked approval buttons."""
    card: dict[str, Any] = {
        "config": {"wide_screen_mode": True},
        "elements": [
            {
                "tag": "markdown",
                "content": "**需要用户确认**\n\n已收到确认操作，正在处理审批请求。",
            },
            {"tag": "hr"},
            {
                "tag": "markdown",
                "content": f"状态：**{_approval_status_text('processing')}**",
            },
        ],
    }
    if approval_id:
        card["elements"].append(
            {
                "tag": "note",
                "elements": [
                    {
                        "tag": "plain_text",
                        "content": f"审批 ID：{approval_id}",
                    }
                ],
            }
        )
    return card


async def _safe_unlink(path: str) -> None:
    try:
        await run_blocking_io(os.unlink, path)
    except FileNotFoundError:
        pass
    except Exception as exc:
        logger.debug("[Feishu] Failed to remove temporary file %s: %s", path, exc)


def _runtime_or_builtin(runtime: object) -> PluginRuntime:
    if isinstance(runtime, PluginRuntime):
        return runtime
    return PluginRuntime(BUILTIN_PLUGIN_MANIFESTS, core_dependencies=("skill_core",))


def _channel_team_id_from_plugin_options(
    *,
    runtime: PluginRuntime,
    channel_config: dict[str, Any],
    agent_id: str | None,
) -> str | None:
    plugin_options = declared_plugin_options_from_metadata(
        runtime,
        channel_config,
        scope="channel",
        agent_id=agent_id,
        executable_only=True,
    )
    selected_team_id = plugin_option_from_metadata(
        {"plugin_options": plugin_options},
        plugin_id=AGENT_TEAM_PLUGIN_ID,
        key=AGENT_TEAM_SELECTED_TEAM_OPTION,
    )
    if isinstance(selected_team_id, str) and selected_team_id.strip():
        return selected_team_id
    return None


def _ensure_agent_executable_with_runtime(
    runtime: PluginRuntime,
    agent_id: str,
) -> None:
    if runtime.plugin_for_agent(agent_id):
        runtime.ensure_agent_available(agent_id)
        return
    from src.agents import ensure_agent_executable

    ensure_agent_executable(agent_id)


class FeishuResponseCollector:
    """
    飞书响应收集器

    收集 Agent 响应内容，发送一条美观的 markdown 卡片消息。
    """

    def __init__(
        self,
        manager: "FeishuChannelManager",
        user_id: str,
        chat_id: str,
        reply_to_message_id: str | None = None,
        sender_id: str | None = None,
        chat_type: str | None = None,
        stream_reply: bool = True,
        instance_id: str | None = None,
    ):
        self.manager = manager
        self.user_id = user_id
        self.chat_id = chat_id
        self.reply_to_message_id = reply_to_message_id
        self.sender_id = sender_id
        self.chat_type = chat_type
        self.stream_reply = stream_reply
        self.instance_id = instance_id
        self.session_id: str | None = None
        self.run_id: str | None = None

        # 内容收集
        self.text_parts: list[str] = []
        self.tools_used: list[str] = []
        self.files_to_reveal: list[dict] = []
        self._sent_file_keys: set[str] = set()

        # 处理中 emoji 控制
        self._processing_message_id: str | None = None
        self._processing_reaction_id: str | None = None
        self._stream_card_id: str | None = None
        self._stream_message_id: str | None = None
        self._stream_sequence = 0
        self._stream_failed = False
        self._stream_finalized = False
        self._stream_lock = asyncio.Lock()
        self._stream_update_queue: asyncio.Queue[object | None] = asyncio.Queue(maxsize=1)
        self._stream_update_task: asyncio.Task | None = None
        self._stream_last_pushed_content = ""
        self._stream_status_text: str | None = None
        self._approval_card_message_ids: dict[str, str] = {}
        self._approval_card_sent_ids: set[str] = set()

    def _current_stream_content(self) -> str:
        content = "".join(self.text_parts)
        if self._stream_status_text:
            return (
                f"{content.rstrip()}\n\n{self._stream_status_text}"
                if content.strip()
                else self._stream_status_text
            )
        return content

    def _final_stream_content(self) -> str:
        return "".join(self.text_parts)

    def _queue_latest_stream_update(self) -> None:
        while True:
            try:
                pending = self._stream_update_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            if pending is None:
                self._stream_update_queue.put_nowait(None)
                return
        self._stream_update_queue.put_nowait(_STREAM_UPDATE_SIGNAL)

    def append_text(self, chunk: str) -> None:
        """追加文本内容"""
        self.text_parts.append(chunk)

    async def append_stream_chunk(self, chunk: str) -> None:
        """Append one response chunk and push it to a Feishu streaming card when enabled."""
        self.append_text(chunk)
        if not self.stream_reply or self._stream_failed or self._stream_finalized:
            return

        if self._stream_card_id:
            self._ensure_stream_update_worker()
            self._queue_latest_stream_update()
            return

        initialized = False
        content = self._current_stream_content()
        initial_content = self._first_paint_content(content)
        async with self._stream_lock:
            if self._stream_failed or self._stream_finalized:
                return
            client = self._get_client()
            if not client:
                self._stream_failed = True
                return

            if not self._stream_card_id:
                card_id = await client.create_stream_card(initial_content)
                if not card_id:
                    self._stream_failed = True
                    return
                sent, message_id = await client.send_card_by_id(
                    self.chat_id,
                    card_id,
                    reply_to_id=self.reply_to_message_id,
                )
                if not sent:
                    self._stream_failed = True
                    return
                self._stream_card_id = card_id
                self._stream_message_id = message_id
                self._stream_last_pushed_content = initial_content
                initialized = True

        self._ensure_stream_update_worker()
        if initialized:
            if initial_content != content:
                self._queue_latest_stream_update()
        else:
            self._queue_latest_stream_update()

    def _first_paint_content(self, content: str) -> str:
        """Return a tiny first update so Feishu starts typewriter rendering quickly."""
        stripped = content.strip()
        if not stripped:
            return content
        if len(stripped) <= FEISHU_STREAM_FIRST_PAINT_CHARS:
            return content
        return stripped[:FEISHU_STREAM_FIRST_PAINT_CHARS]

    def _ensure_stream_update_worker(self) -> None:
        if self._stream_update_task and not self._stream_update_task.done():
            return
        self._stream_update_task = asyncio.create_task(self._stream_update_worker())
        self._stream_update_task.add_done_callback(self._on_stream_update_task_done)

    def _on_stream_update_task_done(self, task: asyncio.Task) -> None:
        if task.cancelled():
            return
        try:
            task.result()
        except Exception as e:
            self._stream_failed = True
            logger.warning("[Feishu] Stream update worker failed: %s", e, exc_info=True)

    async def _stream_update_worker(self) -> None:
        first_update = True
        while True:
            marker = await self._stream_update_queue.get()
            if marker is None:
                return

            if not first_update:
                await asyncio.sleep(FEISHU_STREAM_UPDATE_DEBOUNCE_SECONDS)
                while True:
                    try:
                        next_marker = self._stream_update_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    if next_marker is None:
                        return
            first_update = False
            content = self._current_stream_content()

            if content == self._stream_last_pushed_content:
                continue

            async with self._stream_lock:
                if self._stream_failed or self._stream_finalized or not self._stream_card_id:
                    return
                client = self._get_client()
                if not client:
                    self._stream_failed = True
                    return
                self._stream_sequence += 1
                success = await client.update_stream_card(
                    self._stream_card_id,
                    content,
                    self._stream_sequence,
                )
                if not success:
                    self._stream_failed = True
                    return
                self._stream_last_pushed_content = content

    async def _cancel_stream_update_worker(self) -> None:
        task = self._stream_update_task
        if not task or task.done():
            return
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

    def add_tool(self, tool_name: str) -> None:
        """添加使用的工具"""
        if tool_name:
            self.tools_used.append(tool_name)

    def add_file_to_reveal(self, file_info: dict) -> None:
        """添加待展示的文件"""
        self.files_to_reveal.append(file_info)

    def set_session_link(self, session_id: str, run_id: str | None) -> None:
        self.session_id = session_id
        self.run_id = run_id

    def _session_link_markdown(self) -> str | None:
        if not self.session_id:
            return None
        return f"[{_SESSION_LINK_TEXT}]({_build_session_run_url(self.session_id, self.run_id)})"

    def _append_session_link_to_text(self, text: str) -> str:
        link = self._session_link_markdown()
        if not link:
            return text
        return f"{text.rstrip()}\n\n{link}" if text.strip() else link

    async def set_waiting_for_approval(self, approval: dict[str, Any]) -> None:
        """Show a non-final waiting status while a human approval is pending."""
        logger.debug(
            "[HITL] approval_id=%s Showing waiting status on stream card",
            str(approval.get("id") or ""),
        )
        message = str(approval.get("message") or "需要用户确认")
        first_line = message.strip().splitlines()[0][:80] if message.strip() else "需要用户确认"
        self._stream_status_text = f"⏳ 等待用户确认：{first_line}"
        if self._stream_card_id and not self._stream_failed and not self._stream_finalized:
            self._ensure_stream_update_worker()
            self._queue_latest_stream_update()

    async def clear_waiting_for_approval(self) -> None:
        """Remove the temporary approval wait status from the streaming card."""
        if not self._stream_status_text:
            return
        self._stream_status_text = None
        if self._stream_card_id and not self._stream_failed and not self._stream_finalized:
            self._ensure_stream_update_worker()
            self._queue_latest_stream_update()

    def record_approval_card(self, approval_id: str, message_id: str | None) -> None:
        if approval_id and message_id:
            self._approval_card_message_ids[approval_id] = message_id

    def has_sent_approval_card(self, approval_id: str) -> bool:
        return approval_id in self._approval_card_sent_ids

    async def start_processing_indicator(self, message_id: str) -> None:
        """发送一次处理中 emoji 指示器。"""
        if self._processing_reaction_id:
            return
        reaction_id = await self.manager.add_reaction(
            self.user_id,
            message_id,
            FeishuChannel.PROCESSING_EMOJI,
            self.instance_id,
        )
        if reaction_id:
            self._processing_message_id = message_id
            self._processing_reaction_id = reaction_id

    async def stop_processing_indicator(self) -> None:
        """移除处理中 emoji 指示器。"""
        if not self._processing_message_id or not self._processing_reaction_id:
            return
        message_id = self._processing_message_id
        reaction_id = self._processing_reaction_id
        self._processing_message_id = None
        self._processing_reaction_id = None
        try:
            await self.manager.delete_reaction(
                self.user_id,
                message_id,
                reaction_id,
                self.instance_id,
            )
        except Exception as e:
            logger.debug(f"[Feishu] Processing emoji error: {e}")

    async def _upload_image_from_uri(self, uri: str) -> str | None:
        """从 send:// URI 读取图片并上传到飞书，返回 image_key。"""
        from src.infra.storage.s3.service import get_or_init_storage

        base_client = self.manager._find_channel(self.user_id, self.instance_id)
        if not base_client:
            return None
        client = cast(FeishuChannel, base_client)

        try:
            # send:// URI maps to S3 key path
            s3_key = uri.replace("send://", "")
            storage = await get_or_init_storage()
            backend = storage._get_backend()
            image_name = os.path.basename(s3_key) or "image"
            tmp_path: str | None = None
            try:
                with NamedTemporaryFile(
                    prefix="lambchat-feishu-image-",
                    suffix=f"-{image_name}",
                    delete=False,
                ) as tmp:
                    tmp_path = tmp.name
                    size = await _download_storage_object_to_file(
                        backend,
                        s3_key,
                        tmp,
                        chunk_size=FEISHU_REVEAL_DOWNLOAD_CHUNK_SIZE,
                    )
                if size <= 0:
                    return None
                if not hasattr(client, "upload_image_file"):
                    logger.warning("[Feishu] Client does not support streaming image upload")
                    return None
                return await client.upload_image_file(tmp_path)
            finally:
                if tmp_path is not None:
                    await _safe_unlink(tmp_path)
        except Exception as e:
            logger.debug(f"[Feishu] Failed to upload image from URI {uri}: {e}")
            return None

    def _get_client(self) -> "FeishuChannel | None":
        base_client = self.manager._find_channel(self.user_id, self.instance_id)
        if not base_client:
            logger.warning(f"[Feishu] No client for user {self.user_id}")
            return None
        return cast(FeishuChannel, base_client)

    async def finalize_stream_message(self) -> bool:
        """Close the streaming card. Returns True when the reply was streamed."""
        if not self._stream_card_id or self._stream_failed or self._stream_finalized:
            return False

        await self._cancel_stream_update_worker()
        async with self._stream_lock:
            if not self._stream_card_id or self._stream_failed or self._stream_finalized:
                return False
            client = self._get_client()
            if not client:
                return False
            final_content = self._final_stream_content()
            final_text = self._append_session_link_to_text(final_content.strip() or " ")
            self._stream_sequence += 1
            success = await client.finalize_stream_card(
                self._stream_card_id,
                final_text,
                self._stream_sequence,
            )
            self._stream_finalized = success
            return success

    async def send_card_message(self) -> bool:
        """发送卡片消息（支持回复引用、图片嵌入）"""
        if self._stream_finalized:
            return True

        client = self._get_client()
        if not client:
            return False

        content = await self._build_card_content_async(client)
        success = await client.send_card_message(
            self.chat_id, content, reply_to_id=self.reply_to_message_id
        )
        if success:
            reply_info = (
                f" (reply to {self.reply_to_message_id})" if self.reply_to_message_id else ""
            )
            logger.info(f"[Feishu] Card message sent to {self.chat_id}{reply_info}")
        else:
            logger.warning("[Feishu] Failed to send card message")
        return success

    async def _build_card_content_async(self, client: "FeishuChannel") -> str:
        """构建飞书卡片消息内容（异步，支持图片上传嵌入）"""
        elements: list[dict[str, Any]] = []

        # ===== @mention（群聊回复时 @原发送者）=====
        if self.chat_type == "group" and self.sender_id:
            elements.append(
                {
                    "tag": "markdown",
                    "content": f'<at user_id="{self.sender_id}"></at>',
                }
            )

        # ===== 主要内容区域 =====
        if self.text_parts:
            raw_content = "".join(self.text_parts)
            # 使用带图片上传的适配器构建 elements
            elements.extend(
                await FeishuMarkdownAdapter.build_elements_with_images(
                    raw_content, self._upload_image_from_uri
                )
            )

        # ===== 元数据区域（工具 + 文件）=====
        metadata_parts = []

        if self.tools_used:
            unique_tools = list(dict.fromkeys(self.tools_used))
            tool_badges = " ".join(f"`{t}`" for t in unique_tools)
            metadata_parts.append(f"🔧 {tool_badges}")

        if self.files_to_reveal:
            file_names = [f.get("name", "未知文件") for f in self.files_to_reveal]
            metadata_parts.append(f"📎 {', '.join(file_names)}")

        if metadata_parts:
            elements.append({"tag": "hr"})
            elements.append({"tag": "markdown", "content": " · ".join(metadata_parts)})

        if session_link := self._session_link_markdown():
            elements.append({"tag": "hr"})
            elements.append({"tag": "markdown", "content": session_link})

        if not elements:
            elements.append({"tag": "div", "text": {"tag": "plain_text", "content": "(无内容)"}})

        card = {"config": {"wide_screen_mode": True}, "elements": elements}
        return await run_blocking_io(json.dumps, card, ensure_ascii=False)

    async def send_approval_card(self, approval: dict[str, Any]) -> bool:
        """Send a Feishu approval card and remember its message id for status updates."""
        approval_id = str(approval.get("id") or "")
        if approval_id and approval_id in self._approval_card_sent_ids:
            logger.info("[HITL] approval_id=%s Skip duplicate approval card", approval_id)
            return True
        # Mark as sent before the network call. The reply API can deliver the
        # card while reporting failure (e.g. a non-230011 error code with no
        # fallback), and a duplicate approval_required event must not re-send;
        # better to skip a retry than to spam a second approval card.
        if approval_id:
            self._approval_card_sent_ids.add(approval_id)
        logger.info(
            "[HITL] approval_id=%s Sending approval card (session=%s run=%s)",
            approval_id,
            self.session_id,
            self.run_id,
        )
        session_url = (
            _build_session_run_url(self.session_id, self.run_id) if self.session_id else None
        )
        content = await _build_approval_card_content(
            approval,
            session_url=session_url,
            status="pending",
        )
        success, message_id = await self.manager.send_card_message_with_id(
            self.user_id,
            self.chat_id,
            content,
            self.instance_id,
            reply_to_id=self.reply_to_message_id,
        )
        self.record_approval_card(approval_id, message_id)
        if success:
            logger.info(
                "[HITL] approval_id=%s Approval card sent message_id=%s",
                approval_id,
                message_id,
            )
        return success

    async def update_approval_card(
        self,
        approval_id: str,
        approval: dict[str, Any],
        *,
        status: str,
    ) -> bool:
        """Patch a previously-sent approval card to a terminal status."""
        message_id = self._approval_card_message_ids.get(approval_id)
        if not message_id:
            logger.debug(
                "[HITL] approval_id=%s Skip update_approval_card: no recorded message_id",
                approval_id,
            )
            return False
        client = self._get_client()
        if not client:
            return False
        session_url = (
            _build_session_run_url(self.session_id, self.run_id) if self.session_id else None
        )
        content = await _build_approval_card_content(
            approval,
            session_url=session_url,
            status=status,
        )
        logger.info(
            "[HITL] approval_id=%s Patching approval card to status=%s message_id=%s",
            approval_id,
            status,
            message_id,
        )
        return await client.patch_card_message(message_id, content)

    async def upload_and_send_files(self) -> None:
        """上传文件并发送文件卡片

        直接从 S3 storage 流式读取文件到临时文件，然后上传到飞书。
        """
        from src.infra.storage.s3.service import get_or_init_storage

        if not self.files_to_reveal:
            return

        base_client = self.manager._find_channel(self.user_id, self.instance_id)
        if not base_client:
            logger.warning(f"[Feishu] No client for user {self.user_id}")
            return

        client = cast(FeishuChannel, base_client)

        try:
            storage = await get_or_init_storage()
        except Exception as e:
            logger.error(f"[Feishu] Failed to init storage: {e}")
            return

        for file_info in self.files_to_reveal:
            try:
                file_name = file_info.get("name", "unknown")
                file_key = file_info.get("key", "")

                if not file_key:
                    logger.warning(f"[Feishu] No key for file {file_name}")
                    continue
                if file_key in self._sent_file_keys:
                    continue

                logger.info(f"[Feishu] Reading file {file_name} from storage, key={file_key}")

                backend = storage._get_backend()
                safe_suffix = os.path.basename(file_name) or "file"
                tmp_path: str | None = None
                try:
                    with NamedTemporaryFile(
                        prefix="lambchat-feishu-",
                        suffix=f"-{safe_suffix}",
                        delete=False,
                    ) as tmp:
                        tmp_path = tmp.name
                        size = await _download_storage_object_to_file(
                            backend,
                            file_key,
                            tmp,
                            chunk_size=FEISHU_REVEAL_DOWNLOAD_CHUNK_SIZE,
                        )
                    if size <= 0:
                        logger.warning(f"[Feishu] File not found or empty: {file_key}")
                        continue

                    logger.info(f"[Feishu] Streamed file {file_name}, size: {size} bytes")

                    file_type = str(file_info.get("type") or "").lower()
                    mime_type = str(file_info.get("mime_type") or "").lower()
                    if file_type == "image" or mime_type.startswith("image/"):
                        if not hasattr(client, "upload_image_file"):
                            logger.warning(
                                "[Feishu] Client does not support streaming image upload"
                            )
                            continue
                        feishu_image_key = await client.upload_image_file(tmp_path)
                        if feishu_image_key:
                            sent = await client.send_image_by_key(
                                chat_id=self.chat_id,
                                image_key=feishu_image_key,
                                reply_to_id=self.reply_to_message_id,
                            )
                            if sent:
                                self._sent_file_keys.add(file_key)
                                logger.info(f"[Feishu] Sent image: {file_name}")
                            else:
                                logger.warning(
                                    f"[Feishu] Failed to send image {file_name} to Feishu"
                                )
                        else:
                            logger.warning(f"[Feishu] Failed to upload image {file_name} to Feishu")
                        continue

                    feishu_file_key = await client.upload_file(tmp_path, file_name)
                    if feishu_file_key:
                        sent = await client.send_file_by_key(
                            chat_id=self.chat_id,
                            file_key=feishu_file_key,
                            file_name=file_name,
                            reply_to_id=self.reply_to_message_id,
                        )
                        if sent:
                            self._sent_file_keys.add(file_key)
                            logger.info(f"[Feishu] Sent file: {file_name}")
                        else:
                            logger.warning(f"[Feishu] Failed to send file {file_name} to Feishu")
                    else:
                        logger.warning(f"[Feishu] Failed to upload file {file_name} to Feishu")
                finally:
                    if tmp_path is not None:
                        await _safe_unlink(tmp_path)
            except Exception as e:
                logger.error(f"[Feishu] Failed to upload file {file_info.get('name')}: {e}")


async def execute_feishu_agent(
    session_id: str,
    agent_id: str,
    message: str,
    user_id: str,
    presenter: Optional[Any] = None,
    disabled_tools: list[str] | None = None,
    agent_options: dict | None = None,
    attachments: list[dict] | None = None,
    disabled_skills: list[str] | None = None,
    enabled_skills: list[str] | None = None,
    persona_system_prompt: str | None = None,
    disabled_mcp_tools: list[str] | None = None,
    recommendation_input: str | None = None,
    team_id: str | None = None,
    active_goal: dict | None = None,
) -> AsyncGenerator[dict[str, Any], None]:
    """执行 Agent 并生成事件流"""
    from src.agents.core.base import AgentFactory
    from src.infra.task.exceptions import TaskInterruptedError

    agent = await AgentFactory.get(agent_id)
    run_id = presenter.run_id if presenter else None

    started_at: str | None = None
    if active_goal is not None:
        started_at = datetime.now(timezone.utc).isoformat()
        yield {"event": "goal:start", "data": {"goal": active_goal, "started_at": started_at}}

    try:
        async for event in agent.stream(
            message,
            session_id,
            user_id=user_id,
            presenter=presenter,
            disabled_tools=disabled_tools,
            agent_options=agent_options,
            attachments=attachments,
            disabled_skills=disabled_skills,
            enabled_skills=enabled_skills,
            persona_system_prompt=persona_system_prompt,
            disabled_mcp_tools=disabled_mcp_tools,
            recommendation_input=recommendation_input,
            team_id=team_id,
            active_goal=active_goal,
            goal_started_at=started_at,
        ):
            yield event
    except (asyncio.CancelledError, TaskInterruptedError):
        if run_id:
            await agent.close(run_id)
        if active_goal is not None:
            ended_at = datetime.now(timezone.utc).isoformat()
            yield {
                "event": "goal:end",
                "data": {"goal": active_goal, "started_at": started_at, "ended_at": ended_at},
            }
        raise


def create_feishu_message_handler(
    manager: "FeishuChannelManager",
    default_agent: str,
    show_tools: bool = True,
    plugin_runtime: PluginRuntime | None = None,
) -> Callable:
    """
    创建飞书消息处理器

    Args:
        manager: 飞书渠道管理器
        default_agent: 默认 Agent ID
        show_tools: 是否显示工具调用
    """
    from src.infra.task.manager import get_task_manager

    async def feishu_message_handler(
        user_id: str,
        sender_id: str,
        chat_id: str,
        content: str,
        metadata: dict,
    ) -> None:
        """处理飞书消息"""
        print(
            f"[DEBUG] feishu_message_handler: {content[:50]}",
            file=sys.stderr,
            flush=True,
        )

        original_message_id = metadata.get("message_id")
        received_reaction_id = metadata.get("reaction_id")
        instance_id = metadata.get("instance_id")
        delivery_chat_id = chat_id

        try:
            logger.info(
                f"[Feishu] Processing message from {sender_id} for user {user_id}: {content[:50]}..."
            )
            runtime = _runtime_or_builtin(
                plugin_runtime or getattr(manager, "plugin_runtime", None)
            )

            sender_id_from_msg = metadata.get("sender_id")
            chat_type_from_msg = metadata.get("chat_type")
            reply_to_message_id = original_message_id
            if chat_type_from_msg == "p2p":
                delivery_chat_id = metadata.get("reply_chat_id") or chat_id
            attachments = metadata.get("attachments")

            # 处理 /new 命令 - 严格匹配
            if content.strip() == "/new":
                new_session_id = await _create_new_feishu_session(chat_id)
                await manager.send_message(
                    user_id,
                    delivery_chat_id,
                    "✅ 已创建新对话，请发送消息开始",
                    instance_id,
                )
                logger.info(f"[Feishu] New session created for chat {chat_id}: {new_session_id}")
                return

            # 获取当前 session ID
            session_id = await _get_feishu_session_id(chat_id)
            task_manager = get_task_manager()

            # Resolve agent, model & project: use per-channel config if available
            agent_to_use = default_agent
            model_id: str | None = None
            project_id: str | None = None
            team_id: str | None = None
            persona_preset_id: str | None = None
            enabled_skills: list[str] | None = None
            persona_system_prompt: str | None = None
            persona_metadata: dict[str, Any] | None = None
            channel_name: str | None = None
            stream_reply = True
            ch_storage = None
            if instance_id:
                from src.infra.channel.channel_storage import ChannelStorage
                from src.kernel.schemas.channel import ChannelType

                ch_storage = ChannelStorage()
                ch_config = await ch_storage.get_config(user_id, ChannelType.FEISHU, instance_id)
                if ch_config:
                    if ch_config.get("agent_id"):
                        agent_to_use = ch_config["agent_id"]
                        logger.info(
                            f"[Feishu] Using channel agent: {agent_to_use} for instance {instance_id}"
                        )
                    model_id = ch_config.get("model_id")
                    project_id = ch_config.get("project_id")
                    team_id = _channel_team_id_from_plugin_options(
                        runtime=runtime,
                        channel_config=ch_config,
                        agent_id=agent_to_use,
                    )
                    uses_agent_team_options = agent_uses_agent_team_options(
                        agent_to_use,
                        runtime=runtime,
                    )
                    persona_preset_id = (
                        None if uses_agent_team_options else ch_config.get("persona_preset_id")
                    )
                    channel_name = ch_config.get("name")
                    stream_reply = bool(ch_config.get("stream_reply", True))

            if persona_preset_id:
                try:
                    from src.infra.persona_preset.manager import PersonaPresetManager

                    snapshot = await PersonaPresetManager().use_preset(
                        persona_preset_id,
                        user_id=user_id,
                        is_admin=False,
                    )
                    persona_system_prompt = snapshot.system_prompt
                    enabled_skills = snapshot.skill_names or None
                    persona_metadata = {
                        "persona_preset_id": snapshot.preset_id,
                        "persona_preset_name": snapshot.name,
                        "persona_snapshot": snapshot.model_dump(),
                        "enabled_skills": enabled_skills,
                    }
                    if snapshot.avatar:
                        persona_metadata["persona_avatar"] = snapshot.avatar
                    logger.info(
                        f"[Feishu] Using channel persona: {snapshot.name} "
                        f"({persona_preset_id}) for instance {instance_id}"
                    )
                except Exception as e:
                    logger.warning(
                        f"[Feishu] Ignoring unavailable channel persona {persona_preset_id}: {e}"
                    )

            if project_id:
                try:
                    from src.infra.folder.storage import get_project_storage

                    proj_storage = get_project_storage()
                    project = await proj_storage.get_by_id(project_id, user_id)
                    if not project:
                        logger.warning(
                            f"[Feishu] Ignoring missing channel project_id {project_id} "
                            f"for user {user_id}"
                        )
                        if ch_storage and instance_id:
                            await ch_storage.clear_config_project_id(
                                user_id, ChannelType.FEISHU, instance_id
                            )
                        project_id = None
                except Exception as e:
                    logger.warning(f"[Feishu] Failed to validate channel project_id: {e}")
                    project_id = None

            # Auto-create project by channel name if not manually configured
            if not project_id and channel_name:
                try:
                    from src.infra.folder.storage import get_project_storage

                    proj_storage = get_project_storage()
                    project = await proj_storage.get_or_create_by_name(user_id, channel_name)
                    project_id = project.id
                except Exception as e:
                    logger.warning(f"[Feishu] Failed to auto-create project: {e}")

            # Build agent_options with model_id if configured
            feishu_agent_options: dict | None = None
            if model_id:
                feishu_agent_options = {"model_id": model_id}

            _ensure_agent_executable_with_runtime(runtime, agent_to_use)

            collector = FeishuResponseCollector(
                manager=manager,
                user_id=user_id,
                chat_id=delivery_chat_id,
                reply_to_message_id=reply_to_message_id,
                sender_id=sender_id_from_msg,
                chat_type=chat_type_from_msg,
                stream_reply=stream_reply,
                instance_id=instance_id,
            )

            async def executor(
                session_id: str,
                agent_id: str,
                message: str,
                user_id: str,
                presenter=None,
                disabled_tools=None,
                agent_options=None,
                attachments=None,
                disabled_skills=None,
                enabled_skills=None,
                persona_system_prompt=None,
                disabled_mcp_tools=None,
                recommendation_input=None,
                team_id=None,
                active_goal=None,
            ):
                async for event in execute_feishu_agent(
                    session_id=session_id,
                    agent_id=agent_id,
                    message=message,
                    user_id=user_id,
                    presenter=presenter,
                    disabled_tools=disabled_tools,
                    agent_options=agent_options,
                    attachments=attachments,
                    disabled_skills=disabled_skills,
                    enabled_skills=enabled_skills,
                    persona_system_prompt=persona_system_prompt,
                    disabled_mcp_tools=disabled_mcp_tools,
                    recommendation_input=recommendation_input,
                    team_id=team_id,
                    active_goal=active_goal,
                ):
                    yield event

            # Use time-based session title for Feishu
            session_title = utc_now().strftime("%Y-%m-%d %H:%M")

            run_id, _ = await task_manager.submit(
                session_id=session_id,
                agent_id=agent_to_use,
                message=content,
                user_id=user_id,
                executor=executor,
                attachments=attachments,
                project_id=project_id,
                agent_options=feishu_agent_options,
                session_name=session_title,
                enabled_skills=enabled_skills,
                persona_system_prompt=persona_system_prompt,
                team_id=(
                    team_id
                    if agent_uses_agent_team_options(agent_to_use, runtime=runtime)
                    else None
                ),
            )
            collector.set_session_link(session_id, run_id)
            try:
                from src.infra.session.manager import SessionManager
                from src.kernel.schemas.channel import ChannelType

                await SessionManager().update_session_metadata(
                    session_id,
                    {
                        "channel_delivery": {
                            "channel_type": ChannelType.FEISHU.value,
                            "chat_id": delivery_chat_id,
                            "channel_instance_id": instance_id,
                            "enabled": True,
                            "send_on_success": True,
                        }
                    },
                )
            except Exception as e:
                logger.warning(f"[Feishu] Failed to persist channel delivery metadata: {e}")
            if persona_metadata:
                try:
                    from src.infra.session.manager import SessionManager
                    from src.kernel.schemas.session import SessionUpdate

                    await SessionManager().update_session(
                        session_id,
                        SessionUpdate(metadata=persona_metadata),
                    )
                except Exception as e:
                    logger.warning(f"[Feishu] Failed to persist persona metadata: {e}")

            logger.info(f"[Feishu] Task submitted: session={session_id}, run_id={run_id}")

            await _process_events(
                collector=collector,
                session_id=session_id,
                run_id=run_id,
                show_tools=show_tools,
            )

            streamed = await collector.finalize_stream_message()
            if not streamed:
                await collector.send_card_message()
            await collector.upload_and_send_files()

            logger.info(f"[Feishu] Message processing completed for {chat_id}")

        except Exception as e:
            logger.error(f"[Feishu] Error handling message: {e}", exc_info=True)
            try:
                await manager.send_message(
                    user_id,
                    delivery_chat_id,
                    f"❌ 处理消息时发生错误: {str(e)[:200]}",
                    instance_id,
                )
            except Exception:
                pass
        finally:
            if original_message_id and received_reaction_id:
                try:
                    await manager.delete_reaction(
                        user_id,
                        original_message_id,
                        received_reaction_id,
                        instance_id,
                    )
                except Exception as e:
                    logger.debug(f"[Feishu] Failed to remove received reaction: {e}")

    return feishu_message_handler


async def _process_events(
    collector: FeishuResponseCollector,
    session_id: str,
    run_id: str,
    show_tools: bool,
) -> None:
    """处理事件流并收集响应"""
    from src.infra.session.dual_writer import get_dual_writer

    dual_writer = get_dual_writer()
    pending_approvals: dict[str, dict[str, Any]] = {}

    try:
        async for event in dual_writer.read_from_redis(session_id, run_id):
            event_type = event.get("event_type", "")
            data = event.get("data", {})

            if event_type == EVENT_MESSAGE_CHUNK:
                chunk = data.get("content", "")
                if chunk:
                    await collector.append_stream_chunk(chunk)

            elif event_type == EVENT_TOOL_START and show_tools:
                tool_name = data.get("tool", "")
                if tool_name:
                    collector.add_tool(tool_name)

            elif event_type == EVENT_APPROVAL_REQUIRED:
                approval_id = str(data.get("id") or "")
                logger.info(
                    "[HITL] approval_id=%s Received approval_required event",
                    approval_id,
                )
                if approval_id:
                    if collector.has_sent_approval_card(approval_id):
                        logger.info(
                            "[HITL] approval_id=%s Skip duplicate approval_required event",
                            approval_id,
                        )
                        continue
                    pending_approvals[approval_id] = data
                await collector.set_waiting_for_approval(data)
                sent = await collector.send_approval_card(data)
                if sent:
                    logger.info("[HITL] approval_id=%s Sent approval card", approval_id)
                else:
                    logger.warning(
                        "[HITL] approval_id=%s Failed to send approval card", approval_id
                    )

            elif event_type == EVENT_TOOL_RESULT:
                tool_name = data.get("tool", "")
                logger.debug(f"[Feishu] tool:result event: tool={tool_name}")
                result = data.get("result", "")
                result_approval_id, approval_status = _extract_approval_result_status(result)
                if result_approval_id:
                    # A tool result is only emitted after the approval was
                    # resolved (the tool already awaited the user response), so
                    # "pending" here means the tool forgot to carry its outcome.
                    # Never revert an already-handled card to pending — refresh
                    # the authoritative status from the approval record instead.
                    if approval_status == "pending":
                        approval_status = await _get_existing_approval_status(result_approval_id)
                    logger.info(
                        "[HITL] approval_id=%s Tool result received, finalizing card status=%s",
                        result_approval_id,
                        approval_status,
                    )
                    await collector.clear_waiting_for_approval()
                    approval = pending_approvals.get(result_approval_id) or {
                        "id": result_approval_id,
                        "message": "审批请求",
                        "type": "confirm",
                    }
                    await collector.update_approval_card(
                        result_approval_id,
                        approval,
                        status=approval_status,
                    )

                if tool_name == "reveal_file":
                    logger.info(f"[Feishu] reveal_file result type={type(result).__name__}")
                    if isinstance(result, str) and result:
                        try:
                            file_info = await run_blocking_io(json.loads, result)
                            if (
                                isinstance(file_info, dict)
                                and "key" in file_info
                                and "name" in file_info
                            ):
                                collector.add_file_to_reveal(file_info)
                                await collector.upload_and_send_files()
                                logger.info(
                                    f"[Feishu] Added file to reveal: {file_info.get('name')}"
                                )
                        except json.JSONDecodeError as e:
                            logger.warning(f"[Feishu] Failed to parse reveal_file result: {e}")
                    elif isinstance(result, dict):
                        if "key" in result and "name" in result:
                            collector.add_file_to_reveal(result)
                            await collector.upload_and_send_files()
                            logger.info(
                                f"[Feishu] Added file to reveal (dict): {result.get('name')}"
                            )

                for file_info in _extract_tool_media_files(result):
                    collector.add_file_to_reveal(file_info)
                    await collector.upload_and_send_files()
                    logger.info(
                        "[Feishu] Added tool media file to reveal: %s",
                        file_info.get("name"),
                    )

            elif event_type in ("done", "complete", "error"):
                break

        logger.info(f"[Feishu] Event processing completed for session={session_id}")

    except Exception as e:
        logger.error(f"[Feishu] Event processing error: {e}", exc_info=True)


async def handle_feishu_approval_action(
    *,
    value: Any,
    message_id: str | None = None,
    user_id: str | None = None,
    instance_id: str | None = None,
    manager: FeishuChannelManager | None = None,
) -> bool:
    """Handle a Feishu card button click for LambChat approvals."""
    action_value = _coerce_json_dict(value)
    if not action_value or action_value.get("action") != FEISHU_APPROVAL_ACTION:
        return False

    approval_id = str(action_value.get("approval_id") or "")
    if not approval_id:
        return False
    approved = bool(action_value.get("approved"))
    logger.info(
        "[HITL] approval_id=%s Card action received approved=%s",
        approval_id,
        approved,
    )
    claimed = await _claim_feishu_approval_action(approval_id)
    if not claimed:
        status = await _get_existing_approval_status(approval_id)
        logger.info(
            "[HITL] approval_id=%s Action already in progress, refreshing card status=%s",
            approval_id,
            status,
        )
        if manager and user_id and message_id and status != "error":
            await _patch_feishu_approval_card(
                manager=manager,
                user_id=user_id,
                instance_id=instance_id,
                message_id=message_id,
                approval_id=approval_id,
                status=status,
            )
        return True

    try:
        from fastapi import HTTPException

        await _respond_to_human_approval(approval_id, approved=approved)
        status = "approved" if approved else "rejected"
        logger.info(
            "[HITL] approval_id=%s Approval action accepted status=%s",
            approval_id,
            status,
        )
    except HTTPException as e:
        if e.status_code == 400:
            status = await _get_existing_approval_status(approval_id)
            logger.info(
                "[HITL] approval_id=%s Approval action already handled status=%s",
                approval_id,
                status,
            )
        else:
            status = "error"
            logger.warning(
                "[HITL] approval_id=%s Failed to respond to approval from card action "
                "status_code=%s detail=%s",
                approval_id,
                e.status_code,
                e.detail,
            )
    except Exception as e:
        status = "error"
        logger.warning(
            "[HITL] approval_id=%s Failed to respond to approval from card action error=%s",
            approval_id,
            e,
        )

    if manager and user_id and message_id:
        await _patch_feishu_approval_card(
            manager=manager,
            user_id=user_id,
            instance_id=instance_id,
            message_id=message_id,
            approval_id=approval_id,
            status=status,
        )

    _release_feishu_approval_action(approval_id)

    return True


async def _patch_feishu_approval_card(
    *,
    manager: FeishuChannelManager,
    user_id: str,
    instance_id: str | None,
    message_id: str,
    approval_id: str,
    status: str,
) -> None:
    logger.info(
        "[HITL] approval_id=%s Patching clicked card to status=%s message_id=%s",
        approval_id,
        status,
        message_id,
    )
    try:
        client = manager._find_channel(user_id, instance_id)
        if client:
            content = await _build_approval_card_content(
                {
                    "id": approval_id,
                    "message": "审批请求已处理，任务将继续执行。",
                    "type": "confirm",
                },
                session_url=None,
                status=status,
            )
            await client.patch_card_message(message_id, content)
    except Exception as e:
        logger.debug(
            "[HITL] approval_id=%s Failed to patch clicked approval card: %s",
            approval_id,
            e,
        )


async def setup_feishu_handler(
    default_agent: str,
    show_tools: bool = True,
    plugin_runtime: PluginRuntime | None = None,
) -> None:
    """
    设置飞书消息处理器

    Args:
        default_agent: 默认 Agent ID
        show_tools: 是否显示工具调用
    """
    from src.infra.channel.feishu import get_feishu_channel_manager, start_feishu_channels

    manager = get_feishu_channel_manager()
    if plugin_runtime is not None and hasattr(manager, "set_plugin_runtime"):
        manager.set_plugin_runtime(plugin_runtime)
        try:
            from src.agents import set_plugin_runtime as set_agent_plugin_runtime

            set_agent_plugin_runtime(plugin_runtime)
        except Exception as exc:  # noqa: BLE001 - Feishu can still rely on local guards
            logger.warning("Failed to attach plugin runtime to Feishu agent guard: %s", exc)
    handler = create_feishu_message_handler(
        manager=manager,
        default_agent=default_agent,
        show_tools=show_tools,
        plugin_runtime=plugin_runtime,
    )

    await start_feishu_channels(handler)
    logger.info("Feishu channels started")
