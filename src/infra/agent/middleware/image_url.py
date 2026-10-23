"""Middleware for converting model image_url blocks to base64 data URLs."""

from __future__ import annotations

import asyncio
import mimetypes
from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

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
from src.kernel.errors import AppError, ErrorCode

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
    url = _image_url_from_block(block)
    if url:
        guessed = mimetypes.guess_type(urlsplit(url).path)[0]
        if guessed and guessed.startswith("image/"):
            return guessed
    return "image/jpeg"


class ImageUrlToBase64Middleware(AgentMiddleware):
    """Convert every outbound image_url block to a base64 data URL."""

    async def _convert_messages(self, messages: list[Any]) -> list[Any]:
        return await prepare_image_messages(messages, mode="base64")

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT]:
        messages = await prepare_image_messages(
            request.messages, mode="base64", **_request_image_context(request)
        )
        return await handler(
            request.override(messages=messages) if messages is not request.messages else request
        )


def _append_proxy_direct_param(url: str, *, base_url: str | None = None) -> str:
    """Append ``proxy=true`` to an app upload file URL, leaving others untouched.

    本站 /api/upload/file/ 默认 302 跳转到短时签名地址（保证历史消息链接永不过期），
    但部分供应商（如 DeepSeek）取图不跟随重定向。加上 ``proxy=true`` 后应用直接
    回传文件字节，供这类供应商拉取；会话状态里仍保存原始短 URL。
    """
    if not url or url.startswith("data:"):
        return url

    from src.infra.upload.access import upload_key_from_url

    if upload_key_from_url(url, base_url) is None:
        return url
    parsed = urlsplit(url)

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

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT]:
        messages = await prepare_image_messages(
            request.messages, mode="proxy_direct", **_request_image_context(request)
        )
        return await handler(
            request.override(messages=messages) if messages is not request.messages else request
        )


async def _resolve_storage_image_url(
    url: str,
    *,
    user_id: str | None = None,
    session_id: str | None = None,
    base_url: str | None = None,
) -> str:
    from src.infra.logging.context import TraceContext
    from src.infra.storage.s3.service import get_or_init_storage
    from src.infra.upload.access import authorize_file_url, upload_key_from_url

    key = upload_key_from_url(url, base_url)
    if key is None:
        return url
    authorized_url = await authorize_file_url(
        url,
        user_id if user_id is not None else TraceContext.get_user_id(),
        session_id if session_id is not None else TraceContext.get_session_id(),
        base_url=base_url,
    )
    try:
        storage = await get_or_init_storage()
        return (
            _append_proxy_direct_param(authorized_url, base_url=base_url)
            if storage.is_local
            else await storage.get_presigned_url(key)
        )
    except Exception as exc:
        logger.warning("Failed to resolve image storage URL: error_type=%s", type(exc).__name__)
        return _append_proxy_direct_param(authorized_url, base_url=base_url)


class ImageUrlStorageDirectMiddleware(AgentMiddleware):
    """Resolve app images to fresh storage URLs only for the outgoing request."""

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT]:
        messages = await prepare_image_messages(
            request.messages, mode="storage_direct", **_request_image_context(request)
        )
        return await handler(
            request.override(messages=messages) if messages is not request.messages else request
        )


def _request_image_context(request: Any) -> dict[str, Any]:
    from langchain_core.runnables import ensure_config

    from src.infra.logging.context import TraceContext
    from src.infra.tool.backend_utils import (
        get_base_url_from_runtime,
        get_session_id_from_runtime,
        get_user_id_from_runtime,
    )

    runtime = getattr(request, "runtime", None)
    context = getattr(runtime, "context", None)
    config = getattr(runtime, "config", None)
    runtime = SimpleNamespace(config=config if isinstance(config, dict) else ensure_config())
    return {
        "user_id": getattr(context, "user_id", None)
        or get_user_id_from_runtime(runtime)
        or TraceContext.get_user_id(),
        "session_id": getattr(context, "session_id", None)
        or get_session_id_from_runtime(runtime)
        or TraceContext.get_session_id(),
        "base_url": get_base_url_from_runtime(runtime),
    }


async def prepare_image_messages(
    messages: list[Any],
    *,
    mode: str | None = "url",
    user_id: str | None = None,
    session_id: str | None = None,
    base_url: str | None = None,
) -> list[Any]:
    """Authorize fresh outgoing copies; keep checkpoint URLs stable and deduplicate reads."""
    from src.infra.logging.context import TraceContext
    from src.infra.upload.access import authorize_file_url, upload_key_from_url
    from src.infra.upload.file_record import get_file_record_storage
    from src.kernel.config import settings

    base_url = base_url or settings.APP_BASE_URL
    user_id = user_id if user_id is not None else TraceContext.get_user_id()
    session_id = session_id if session_id is not None else TraceContext.get_session_id()
    blocks_by_url: dict[str, dict[str, Any]] = {}
    for message in messages:
        content = getattr(message, "content", None)
        if isinstance(content, list):
            for block in content:
                url = _image_url_from_block(block)
                if url and not url.startswith("data:"):
                    blocks_by_url.setdefault(url, block)
    if not blocks_by_url:
        return messages

    semaphore = asyncio.Semaphore(4)

    async def resolve(url, block):
        async with semaphore:
            try:
                key = upload_key_from_url(url, base_url)
                capture = key is not None and await get_file_record_storage().is_private_key(key)
                if mode == "base64" or capture:
                    try:
                        options = (
                            {"user_id": user_id, "session_id": session_id, "base_url": base_url}
                            if key is not None
                            else {}
                        )
                        data_url = await _download_image_url_as_data_url(
                            url, _mime_type_from_block(block), **options
                        )
                    except AppError:
                        raise
                    except Exception as exc:
                        logger.warning(
                            "Failed to inline model image: error_type=%s", type(exc).__name__
                        )
                        data_url = None
                    if data_url:
                        return data_url
                    if capture:
                        raise AppError(ErrorCode.FILE_NOT_FOUND)
                if mode == "storage_direct":
                    return await _resolve_storage_image_url(
                        url, user_id=user_id, session_id=session_id, base_url=base_url
                    )
                authorized = await authorize_file_url(url, user_id, session_id, base_url=base_url)
                if key is not None and base_url:
                    authorized = urljoin(base_url.rstrip("/") + "/", authorized)
                return (
                    _append_proxy_direct_param(authorized, base_url=base_url)
                    if mode == "proxy_direct"
                    else authorized
                )
            except Exception as exc:
                # Re-raise after TaskGroup drains so callers receive the original AppError.
                return exc

    async with asyncio.TaskGroup() as group:
        tasks = {
            url: group.create_task(resolve(url, block)) for url, block in blocks_by_url.items()
        }
    resolved = {url: task.result() for url, task in tasks.items()}
    for value in resolved.values():
        if isinstance(value, Exception):
            raise value
    changed = False
    outgoing = []
    for message in messages:
        content = getattr(message, "content", None)
        if not isinstance(content, list):
            outgoing.append(message)
            continue
        converted = []
        for block in content:
            url = _image_url_from_block(block)
            replacement = resolved.get(url) if url else None
            if isinstance(replacement, str) and replacement != url:
                block = (
                    _with_data_url(block, replacement)
                    if replacement.startswith("data:")
                    else _with_proxy_direct_url(block, replacement)
                )
            converted.append(block)
        if any(a is not b for a, b in zip(content, converted)):
            message = message.model_copy(update={"content": converted})
            changed = True
        outgoing.append(message)
    return outgoing if changed else messages


class ImageUrlAccessMiddleware(AgentMiddleware):
    """Refresh ordinary URL-mode uploads at the model boundary."""

    async def awrap_model_call(self, request, handler):
        messages = await prepare_image_messages(request.messages, **_request_image_context(request))
        return await handler(
            request.override(messages=messages) if messages is not request.messages else request
        )


def image_url_middleware_for_mode(mode: str | None) -> AgentMiddleware:
    """All model modes authorize local files, including the default URL mode."""
    if mode == "storage_direct":
        return ImageUrlStorageDirectMiddleware()
    if mode == "base64":
        return ImageUrlToBase64Middleware()
    if mode == "proxy_direct":
        return ImageUrlProxyDirectMiddleware()
    return ImageUrlAccessMiddleware()
