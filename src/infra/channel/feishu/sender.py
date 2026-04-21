"""Feishu message sending, file upload/download, and card operations.

This mixin provides all send/upload/download/patch methods for FeishuChannel,
keeping channel.py focused on lifecycle, connection management, and message handling.
"""

import asyncio
import json
from collections import OrderedDict
from typing import Any

from src.infra.logging import get_logger

logger = get_logger(__name__)


class FeishuSenderMixin:
    """Mixin providing message sending, file transfer, and card operations for FeishuChannel.

    Requires the host class to provide:
        - self._client: The lark SDK client instance
        - self.config.user_id: For logging purposes
    """

    _client: Any
    _chat_mode_cache: OrderedDict

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

    # ==========================================
    # File Operations
    # ==========================================

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
            from src.infra.storage.s3.service import get_or_init_storage

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
