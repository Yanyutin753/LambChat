"""Middleware for converting model image_url blocks to base64 data URLs."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from langchain.agents.middleware.types import (
    AgentMiddleware,
    ContextT,
    ModelRequest,
    ModelResponse,
    ResponseT,
)

from src.agents.core.node_utils import (
    _download_image_url_as_data_url,
)
from src.infra.logging import get_logger

logger = get_logger(__name__)


def _image_url_from_block(block: Any) -> str | None:
    if not isinstance(block, dict):
        return None

    if block.get("type") == "image_url":
        image_url = block.get("image_url")
        if isinstance(image_url, dict):
            url = image_url.get("url")
        else:
            url = image_url
        return url if isinstance(url, str) and url else None

    if block.get("type") == "image":
        source = block.get("source")
        if isinstance(source, dict) and source.get("type") == "url":
            url = source.get("url")
            return url if isinstance(url, str) and url else None

    return None


def _with_data_url(block: dict, data_url: str) -> dict:
    if block.get("type") == "image":
        source = block.get("source")
        if isinstance(source, dict) and source.get("type") == "url":
            data_mime_type = ""
            if data_url.startswith("data:") and ";" in data_url:
                data_mime_type = data_url[5:].split(";", 1)[0]
            return {
                **block,
                "source": {
                    "type": "base64",
                    "media_type": data_mime_type or source.get("media_type") or "image/jpeg",
                    "data": data_url.split(",", 1)[1] if "," in data_url else data_url,
                },
            }

    image_url = block.get("image_url")
    if isinstance(image_url, dict):
        return {
            **block,
            "image_url": {**image_url, "url": data_url},
        }
    return {**block, "image_url": {"url": data_url}}


def _mime_type_from_block(block: dict) -> str:
    image_url = block.get("image_url")
    if isinstance(image_url, dict):
        detail = image_url.get("mime_type") or image_url.get("media_type")
        if isinstance(detail, str) and detail.startswith("image/"):
            return detail
    source = block.get("source")
    if isinstance(source, dict):
        media_type = source.get("media_type")
        if isinstance(media_type, str) and media_type.startswith("image/"):
            return media_type
    return "image/jpeg"


class ImageUrlToBase64Middleware(AgentMiddleware):
    """Convert every outbound image_url block to a base64 data URL."""

    async def _convert_content_blocks(self, content: Any) -> Any:
        if not isinstance(content, list):
            return content

        converted: list[Any] = []
        changed = False
        for block in content:
            url = _image_url_from_block(block)
            if not url or url.startswith("data:") or not isinstance(block, dict):
                converted.append(block)
                continue

            try:
                data_url = await _download_image_url_as_data_url(
                    url,
                    _mime_type_from_block(block),
                )
            except Exception as e:
                logger.warning(
                    "Failed to convert image_url to base64: error_type=%s",
                    type(e).__name__,
                )
                data_url = None

            if data_url:
                converted.append(_with_data_url(block, data_url))
                changed = True
            else:
                converted.append(block)

        return converted if changed else content

    async def _convert_messages(self, messages: list[Any]) -> list[Any]:
        converted_messages: list[Any] = []
        changed = False

        for message in messages:
            content = getattr(message, "content", None)
            converted_content = await self._convert_content_blocks(content)
            if converted_content is content:
                converted_messages.append(message)
                continue

            changed = True
            if hasattr(message, "model_copy"):
                converted_messages.append(message.model_copy(update={"content": converted_content}))
            else:
                clone = message.copy()
                clone.content = converted_content
                converted_messages.append(clone)

        return converted_messages if changed else messages

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT]:
        messages = await self._convert_messages(request.messages)
        if messages is not request.messages:
            request = request.override(messages=messages)
        return await handler(request)


_UPLOAD_FILE_MARKER = "/api/upload/file/"


def _append_proxy_direct_param(url: str) -> str:
    """Append ``proxy=true`` to an app upload file URL, leaving others untouched.

    本站 /api/upload/file/ 默认 302 跳转到短时签名地址（保证历史消息链接永不过期），
    但部分供应商（如 DeepSeek）取图不跟随重定向。加上 ``proxy=true`` 后应用直接
    回传文件字节，供这类供应商拉取；会话状态里仍保存原始短 URL。
    """
    if not url or url.startswith("data:"):
        return url

    parsed = urlsplit(url)
    if parsed.scheme not in ("http", "https") or _UPLOAD_FILE_MARKER not in (parsed.path or ""):
        return url

    query = parse_qsl(parsed.query, keep_blank_values=True)
    if any(k == "proxy" and v == "true" for k, v in query):
        return url

    query.append(("proxy", "true"))
    return urlunsplit(parsed._replace(query=urlencode(query)))


def _with_proxy_direct_url(block: dict, url: str) -> dict:
    if block.get("type") == "image":
        source = block.get("source")
        if isinstance(source, dict) and source.get("type") == "url":
            return {**block, "source": {**source, "url": url}}

    image_url = block.get("image_url")
    if isinstance(image_url, dict):
        return {**block, "image_url": {**image_url, "url": url}}
    return {**block, "image_url": {"url": url}}


class ImageUrlProxyDirectMiddleware(AgentMiddleware):
    """Rewrite outbound app upload image URLs to stream bytes directly (?proxy=true)."""

    def _rewrite_content_blocks(self, content: Any) -> Any:
        if not isinstance(content, list):
            return content

        rewritten: list[Any] = []
        changed = False
        for block in content:
            url = _image_url_from_block(block)
            if not url or not isinstance(block, dict):
                rewritten.append(block)
                continue

            direct_url = _append_proxy_direct_param(url)
            if direct_url == url:
                rewritten.append(block)
                continue

            rewritten.append(_with_proxy_direct_url(block, direct_url))
            changed = True

        return rewritten if changed else content

    def _rewrite_messages(self, messages: list[Any]) -> list[Any]:
        rewritten_messages: list[Any] = []
        changed = False

        for message in messages:
            content = getattr(message, "content", None)
            rewritten_content = self._rewrite_content_blocks(content)
            if rewritten_content is content:
                rewritten_messages.append(message)
                continue

            changed = True
            if hasattr(message, "model_copy"):
                rewritten_messages.append(message.model_copy(update={"content": rewritten_content}))
            else:
                clone = message.copy()
                clone.content = rewritten_content
                rewritten_messages.append(clone)

        return rewritten_messages if changed else messages

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT]:
        messages = self._rewrite_messages(request.messages)
        if messages is not request.messages:
            request = request.override(messages=messages)
        return await handler(request)


def image_url_middleware_for_mode(mode: str | None) -> AgentMiddleware | None:
    """Return the outbound image URL middleware for a model's image_url_mode."""
    if mode == "base64":
        return ImageUrlToBase64Middleware()
    if mode == "proxy_direct":
        return ImageUrlProxyDirectMiddleware()
    return None
