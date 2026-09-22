"""Feishu file, image, resource download, and chat metadata operations."""

import json
import mimetypes
from collections import OrderedDict
from tempfile import SpooledTemporaryFile
from typing import Any

from src.infra.async_utils import run_long_blocking_io
from src.infra.logging import get_logger
from src.kernel.config import settings

logger = get_logger(__name__)
_LEGACY_BYTES_DOWNLOAD_MAX_BYTES = 2 * 1024 * 1024
_UPLOAD_BYTES_MAX_SIZE = 20 * 1024 * 1024


def _get_upload_bytes_max_size() -> int:
    return max(
        int(getattr(settings, "FEISHU_UPLOAD_BYTES_MAX_SIZE", _UPLOAD_BYTES_MAX_SIZE) or 0), 1
    )


class FeishuFileSenderMixin:
    """Mixin providing file upload/download and media send operations."""

    _client: Any
    _resolve_receive_id: Any
    _chat_mode_cache: OrderedDict
    _FILE_TYPE_MAP: dict[str, str]
    _REPLY_FALLBACK_ERROR_CODES: set[int]

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

        return await run_long_blocking_io(self._upload_file_sync, file_path, file_name)

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
        max_size = _get_upload_bytes_max_size()
        if len(file_data) > max_size:
            logger.warning(
                "[Feishu] Refusing bytes upload above limit: name=%s size=%s max=%s",
                file_name,
                len(file_data),
                max_size,
            )
            return None

        return await run_long_blocking_io(self._upload_bytes_sync, file_data, file_name)

    def _upload_image_file_sync(self, file_path: str) -> str | None:
        """Upload image file path to Feishu media library, return image_key."""
        from lark_oapi.api.im.v1 import CreateImageRequest, CreateImageRequestBody

        try:
            with open(file_path, "rb") as image_file:
                request = (
                    CreateImageRequest.builder()
                    .request_body(
                        CreateImageRequestBody.builder()
                        .image_type("message")
                        .image(image_file)
                        .build()
                    )
                    .build()
                )
                response = self._client.im.v1.image.create(request)
            if response.success():
                return response.data.image_key
            logger.warning(
                f"Failed to upload image file to Feishu: code={response.code}, msg={response.msg}"
            )
        except Exception as e:
            logger.error(f"Error uploading image file to Feishu: {e}")
        return None

    async def upload_image_file(self, file_path: str) -> str | None:
        """Upload image from a local file asynchronously and return image_key."""
        if not self._client:
            return None

        return await run_long_blocking_io(self._upload_image_file_sync, file_path)

    def _download_image_sync(self, image_key: str, message_id: str) -> bytes | None:
        """Download image from Feishu via GetMessageResourceRequest (sync, runs in executor)."""
        return self._download_resource_sync(image_key, message_id, "image")

    def _download_resource_sync(
        self, file_key: str, message_id: str, resource_type: str
    ) -> bytes | None:
        """Download a Feishu message resource via GetMessageResourceRequest."""
        try:
            with SpooledTemporaryFile(max_size=2 * 1024 * 1024, mode="w+b") as spooled:
                size = self._download_resource_to_file_sync(
                    file_key,
                    message_id,
                    resource_type,
                    spooled,
                    max_bytes=_LEGACY_BYTES_DOWNLOAD_MAX_BYTES,
                )
                if size <= 0:
                    return None
                if size > _LEGACY_BYTES_DOWNLOAD_MAX_BYTES:
                    logger.warning(
                        "Feishu legacy bytes download refused: key=%s type=%s size=%s max=%s",
                        file_key,
                        resource_type,
                        size,
                        _LEGACY_BYTES_DOWNLOAD_MAX_BYTES,
                    )
                    return None
                spooled.seek(0)
                return spooled.read()
        except Exception as e:
            logger.error(
                "Error downloading Feishu resource: key=%s type=%s error=%s",
                file_key,
                resource_type,
                e,
            )
        return None

    def _download_resource_to_file_sync(
        self,
        file_key: str,
        message_id: str,
        resource_type: str,
        file: Any,
        *,
        max_bytes: int | None = None,
    ) -> int:
        """Download a Feishu message resource into a file-like object."""
        from lark_oapi.api.im.v1 import GetMessageResourceRequest

        try:
            request = (
                GetMessageResourceRequest.builder()
                .message_id(message_id)
                .file_key(file_key)
                .type(resource_type)
                .build()
            )
            response = self._client.im.v1.message_resource.get(request)
            if not response.success():
                logger.warning(
                    "Failed to download Feishu resource: key=%s type=%s code=%s msg=%s",
                    file_key,
                    resource_type,
                    response.code,
                    response.msg,
                )
                return 0

            total_size = 0
            while True:
                chunk = response.file.read(1024 * 1024)
                if not chunk:
                    break
                next_size = total_size + len(chunk)
                if max_bytes is not None and next_size > max_bytes:
                    logger.warning(
                        "Feishu resource download exceeded limit: key=%s type=%s size=%s max=%s",
                        file_key,
                        resource_type,
                        next_size,
                        max_bytes,
                    )
                    return next_size
                file.write(chunk)
                total_size = next_size
            file.seek(0)
            return total_size
        except Exception as e:
            logger.error(f"Error streaming Feishu resource: {e}")
            return 0

    async def _download_and_store_image(self, image_key: str, message_id: str) -> dict | None:
        """Download image from Feishu, upload to S3, return attachment info dict."""
        return await self._download_and_store_resource(
            image_key,
            message_id,
            resource_type="image",
            file_name=f"{image_key}.png",
            attachment_type="image",
            content_type="image/png",
        )

    async def _download_and_store_resource(
        self,
        file_key: str,
        message_id: str,
        *,
        resource_type: str,
        file_name: str,
        attachment_type: str,
        content_type: str | None = None,
    ) -> dict | None:
        """Download a Feishu resource, upload it to app storage, and return attachment info."""
        guessed_content_type = content_type or mimetypes.guess_type(file_name)[0]
        if not guessed_content_type:
            guessed_content_type = "application/octet-stream"

        try:
            from src.infra.storage.s3.service import get_or_init_storage

            storage = await get_or_init_storage()
            with SpooledTemporaryFile(max_size=2 * 1024 * 1024, mode="w+b") as spooled:
                max_size = _get_upload_bytes_max_size()
                size = await run_long_blocking_io(
                    self._download_resource_to_file_sync,
                    file_key,
                    message_id,
                    resource_type,
                    spooled,
                    max_bytes=max_size,
                )
                if size <= 0:
                    return None
                if size > max_size:
                    logger.warning(
                        "[Feishu] Refusing resource storage above limit: key=%s type=%s "
                        "size=%s max=%s",
                        file_key,
                        resource_type,
                        size,
                        max_size,
                    )
                    return None
                result = await storage.upload_file(
                    file=spooled,
                    folder=f"feishu_{attachment_type}",
                    filename=file_name,
                    content_type=guessed_content_type,
                    skip_size_limit=True,
                )
            url = result.url or storage.get_file_url(result.key)
            if not url:
                base_url = getattr(settings, "APP_BASE_URL", "").rstrip("/")
                url = (
                    f"{base_url}/api/upload/file/{result.key}"
                    if base_url
                    else f"/api/upload/file/{result.key}"
                )
            return {
                "key": result.key,
                "name": file_name,
                "type": attachment_type,
                "mime_type": guessed_content_type,
                "size": size,
                "url": url,
            }
        except Exception as e:
            logger.error(f"Error storing Feishu resource: {e}")
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
        max_size = _get_upload_bytes_max_size()
        if len(image_data) > max_size:
            logger.warning(
                "[Feishu] Refusing image upload above limit: size=%s max=%s",
                len(image_data),
                max_size,
            )
            return None

        return await run_long_blocking_io(self._upload_image_sync, image_data)

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

        mode = await run_long_blocking_io(self._get_chat_mode_sync, chat_id)
        self._chat_mode_cache[chat_id] = mode
        # LRU eviction: keep at most 1000 entries
        while len(self._chat_mode_cache) > 1000:
            self._chat_mode_cache.popitem(last=False)
        return mode

    def _send_file_message_sync(
        self,
        chat_id: str,
        file_key: str,
        file_name: str,
        msg_type: str = "file",
        reply_to_id: str | None = None,
    ) -> bool:
        """Send a file message synchronously."""

        try:
            receive_id_type, receive_id = self._resolve_receive_id(chat_id)
            payload = {"file_key": file_key}
            if msg_type == "file":
                payload["file_name"] = file_name
            content = json.dumps(payload, ensure_ascii=False)

            if reply_to_id:
                from lark_oapi.api.im.v1 import ReplyMessageRequest, ReplyMessageRequestBody

                request = (
                    ReplyMessageRequest.builder()
                    .message_id(reply_to_id)
                    .request_body(
                        ReplyMessageRequestBody.builder()
                        .msg_type(msg_type)
                        .content(content)
                        .build()
                    )
                    .build()
                )
                response = self._client.im.v1.message.reply(request)
                if not response.success() and response.code in self._REPLY_FALLBACK_ERROR_CODES:
                    logger.info(
                        "Falling back to create Feishu file after reply failure: "
                        "code=%s receive_id_type=%s receive_id=%s",
                        response.code,
                        receive_id_type,
                        receive_id,
                    )
                    reply_to_id = None

            if not reply_to_id:
                from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

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
                logger.error(f"Failed to send file message: code={response.code}")
                return False
            return True
        except Exception as e:
            logger.error(f"Error sending file message: {e}")
            return False

    def _send_image_message_sync(
        self,
        chat_id: str,
        image_key: str,
        reply_to_id: str | None = None,
    ) -> bool:
        """Send an image message synchronously using an uploaded image_key."""

        try:
            receive_id_type, receive_id = self._resolve_receive_id(chat_id)
            content = json.dumps({"image_key": image_key}, ensure_ascii=False)

            if reply_to_id:
                from lark_oapi.api.im.v1 import ReplyMessageRequest, ReplyMessageRequestBody

                request = (
                    ReplyMessageRequest.builder()
                    .message_id(reply_to_id)
                    .request_body(
                        ReplyMessageRequestBody.builder().msg_type("image").content(content).build()
                    )
                    .build()
                )
                response = self._client.im.v1.message.reply(request)
                if not response.success() and response.code in self._REPLY_FALLBACK_ERROR_CODES:
                    logger.info(
                        "Falling back to create Feishu image after reply failure: "
                        "code=%s receive_id_type=%s receive_id=%s",
                        response.code,
                        receive_id_type,
                        receive_id,
                    )
                    reply_to_id = None

            if not reply_to_id:
                from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

                request = (
                    CreateMessageRequest.builder()
                    .receive_id_type(receive_id_type)
                    .request_body(
                        CreateMessageRequestBody.builder()
                        .receive_id(receive_id)
                        .msg_type("image")
                        .content(content)
                        .build()
                    )
                    .build()
                )
                response = self._client.im.v1.message.create(request)

            if not response.success():
                logger.error(f"Failed to send image message: code={response.code}")
                return False
            return True
        except Exception as e:
            logger.error(f"Error sending image message: {e}")
            return False

    async def send_file_message(self, chat_id: str, file_path: str, file_name: str) -> bool:
        """Upload and send a file message."""
        file_key = await self.upload_file(file_path, file_name)
        if not file_key:
            return False

        return await run_long_blocking_io(
            self._send_file_message_sync, chat_id, file_key, file_name
        )

    async def send_file_by_key(
        self,
        chat_id: str,
        file_key: str,
        file_name: str,
        reply_to_id: str | None = None,
    ) -> bool:
        """Send a file message using an already uploaded file_key.

        Args:
            chat_id: Chat ID or open_id
            file_key: The file_key from a previous upload
            file_name: Display name for the file
            reply_to_id: Optional message ID to reply to (for quote/reply)

        Returns:
            True if successful, False otherwise
        """
        if not self._client:
            return False

        ext = file_name.lower().rsplit(".", 1)[-1] if "." in file_name else ""
        msg_type = "audio" if ext == "opus" else "media" if ext == "mp4" else "file"

        return await run_long_blocking_io(
            self._send_file_message_sync,
            chat_id,
            file_key,
            file_name,
            msg_type,
            reply_to_id,
        )

    async def send_image_by_key(
        self,
        chat_id: str,
        image_key: str,
        reply_to_id: str | None = None,
    ) -> bool:
        """Send an image message using an already uploaded image_key."""
        if not self._client:
            return False

        return await run_long_blocking_io(
            self._send_image_message_sync,
            chat_id,
            image_key,
            reply_to_id,
        )
