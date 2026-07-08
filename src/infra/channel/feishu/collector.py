"""Feishu response collection and card/file delivery."""

import asyncio
import json
import os
from tempfile import NamedTemporaryFile
from typing import Any, cast

from src.infra.async_utils import run_blocking_io
from src.infra.channel.feishu import handler_helpers
from src.infra.channel.feishu.approval import _build_approval_card_content
from src.infra.channel.feishu.channel import FeishuChannel
from src.infra.channel.feishu.handler_helpers import (
    _SESSION_LINK_TEXT,
    FEISHU_REVEAL_DOWNLOAD_CHUNK_SIZE,
    FEISHU_REVEAL_DOWNLOAD_MAX_BYTES,
    FEISHU_REVEAL_LEGACY_DOWNLOAD_MAX_BYTES,
    FEISHU_STREAM_FIRST_PAINT_CHARS,
    FEISHU_STREAM_UPDATE_DEBOUNCE_SECONDS,
    _build_session_run_url,
)
from src.infra.channel.feishu.manager import FeishuChannelManager
from src.infra.channel.feishu.markdown import FeishuMarkdownAdapter
from src.infra.logging import get_logger

logger = get_logger(__name__)
_STREAM_UPDATE_SIGNAL = object()


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


async def _safe_unlink(path: str) -> None:
    try:
        await run_blocking_io(os.unlink, path)
    except FileNotFoundError:
        pass
    except Exception as exc:
        logger.debug("[Feishu] Failed to remove temporary file %s: %s", path, exc)


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
