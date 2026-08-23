"""Drop image blocks whose uploaded file no longer exists before model calls.

模型请求历史会携带所有历史轮次的 image_url；部分上游网关（new-api）在计数 token 时
会逐个下载这些 URL，任何一个 404（文件已被清理）都会让整个请求失败
（count_token_failed）。该模块提供两个模型调用前的图片治理中间件：

- ``DeadAttachmentFilterMiddleware``：批量校验自有上传 URL 的存活性，剔除死链图片块。
- ``HistoricalImageCapMiddleware``：历史图片数超过上限时，将最旧的图片替换为含
  URL 的文本占位符（KV 缓存友好：迟滞触发 + 确定性替换，不触碰当前轮消息）。
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import unquote

from langchain.agents.middleware.types import (
    AgentMiddleware,
    ContextT,
    ModelRequest,
    ModelResponse,
    ResponseT,
)
from langchain_core.messages import HumanMessage

from src.infra.logging import get_logger
from src.infra.upload.file_record import FileRecordStorage
from src.kernel.config import settings

logger = get_logger(__name__)

_UPLOAD_URL_MARKER = "/api/upload/file/"
_UNAVAILABLE_NOTE = "[image attachment no longer available]"
_OMITTED_PLACEHOLDER = "[image omitted for context: {url}]"
_OMITTED_PLACEHOLDER_NO_URL = "[image omitted for context]"
_MAX_URL_LENGTH_IN_PLACEHOLDER = 512

ExistsChecker = Callable[[list[str]], Awaitable[set[str]]]


def _upload_key_from_url(url: str) -> str | None:
    """Extract the storage key from a LambChat upload file URL, else None."""
    marker_index = url.find(_UPLOAD_URL_MARKER)
    if marker_index < 0:
        return None
    key = url[marker_index + len(_UPLOAD_URL_MARKER) :]
    if not key or "/" not in key:
        return None
    # 丢掉查询串与锚点后解码（key 以 category/user_id/uuid.ext 形式存在）
    key = key.split("?", 1)[0].split("#", 1)[0]
    return unquote(key)


async def _default_exists_checker(keys: list[str]) -> set[str]:
    """Batch-check which storage keys still have file records."""
    collection = FileRecordStorage().collection
    cursor = collection.find({"key": {"$in": keys}}, {"key": 1, "_id": 0})
    docs = await cursor.to_list(length=len(keys))
    return {str(doc["key"]) for doc in docs if doc.get("key")}


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


def _has_text_block(blocks: list[Any]) -> bool:
    return any(
        isinstance(block, dict)
        and block.get("type") == "text"
        and str(block.get("text", "")).strip()
        for block in blocks
    )


class DeadAttachmentFilterMiddleware(AgentMiddleware):
    """Remove image blocks pointing at deleted uploads before each model call."""

    def __init__(self, exists_checker: ExistsChecker | None = None) -> None:
        super().__init__()
        self._exists_checker = exists_checker or _default_exists_checker
        self._alive_cache: dict[str, bool] = {}

    async def _filter_content_blocks(
        self,
        content: Any,
        dead_urls: set[str],
    ) -> Any:
        """Drop dead image blocks; keep everything else intact."""
        if not isinstance(content, list):
            return content

        filtered: list[Any] = []
        for block in content:
            url = _image_url_from_block(block)
            if url and url in dead_urls:
                continue
            filtered.append(block)

        if not _has_text_block(filtered):
            filtered.append({"type": "text", "text": _UNAVAILABLE_NOTE})
        return filtered

    async def _collect_dead_urls(self, messages: list[Any]) -> set[str]:
        """Find upload image URLs whose file records are gone (cached per instance)."""
        pending: dict[str, str] = {}
        for message in messages:
            content = getattr(message, "content", None)
            if not isinstance(content, list):
                continue
            for block in content:
                url = _image_url_from_block(block)
                if not url or url.startswith("data:"):
                    continue
                key = _upload_key_from_url(url)
                if key is None or key in self._alive_cache:
                    continue
                pending.setdefault(key, url)

        if not pending:
            return set()

        keys = list(pending)
        try:
            alive = await self._exists_checker(keys)
        except Exception as e:
            logger.warning(
                "DeadAttachmentFilter: existence check failed (%s); passing URLs through",
                type(e).__name__,
            )
            return set()

        dead_urls: set[str] = set()
        for key in keys:
            is_alive = key in alive
            self._alive_cache[key] = is_alive
            if not is_alive:
                dead_urls.add(pending[key])
        return dead_urls

    async def _filter_messages(self, messages: list[Any]) -> list[Any]:
        dead_urls = await self._collect_dead_urls(messages)
        if not dead_urls:
            return messages

        logger.warning(
            "DeadAttachmentFilter: dropping %d deleted attachment image block(s)", len(dead_urls)
        )
        filtered_messages: list[Any] = []
        for message in messages:
            content = getattr(message, "content", None)
            if not isinstance(content, list):
                filtered_messages.append(message)
                continue
            filtered_content = await self._filter_content_blocks(content, dead_urls)
            if filtered_content is content:
                filtered_messages.append(message)
            elif hasattr(message, "model_copy"):
                filtered_messages.append(
                    message.model_copy(update={"content": filtered_content})
                )
            else:
                clone = message.copy()
                clone.content = filtered_content
                filtered_messages.append(clone)
        return filtered_messages

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT]:
        messages = await self._filter_messages(request.messages)
        if messages is not request.messages:
            request = request.override(messages=messages)
        return await handler(request)


def _image_block_placeholder(url: str | None) -> dict[str, Any]:
    """Build the text block replacing an evicted image (URL kept when safe)."""
    if url and not url.startswith("data:") and len(url) <= _MAX_URL_LENGTH_IN_PLACEHOLDER:
        return {"type": "text", "text": _OMITTED_PLACEHOLDER.format(url=url)}
    return {"type": "text", "text": _OMITTED_PLACEHOLDER_NO_URL}


def _last_human_message_index(messages: list[Any]) -> int:
    for index in range(len(messages) - 1, -1, -1):
        if isinstance(messages[index], HumanMessage):
            return index
    return len(messages)


class HistoricalImageCapMiddleware(AgentMiddleware):
    """Cap historical image blocks, replacing the oldest with URL text placeholders.

    KV 缓存友好设计：
    - 迟滞触发：图片数超过 ``hard_limit`` 才执行一次淘汰（淘汰到 ``keep_limit``），
      两次淘汰之间请求前缀逐字节稳定，缓存命中不受影响。
    - 确定性：替换结果是消息列表的纯函数，同一历史每次变换结果相同。
    - 不触碰最后一条 HumanMessage（当前轮上下文永不淘汰）。
    - 占位符保留原 URL，模型需要时可按链接取回；纯文本块不会触发上游图片下载。
    """

    def __init__(
        self,
        *,
        hard_limit: int | None = None,
        keep_limit: int | None = None,
    ) -> None:
        super().__init__()
        self._hard_limit = hard_limit
        self._keep_limit = keep_limit

    def _limits(self) -> tuple[int, int]:
        hard = (
            int(self._hard_limit)
            if self._hard_limit is not None
            else int(getattr(settings, "HISTORY_IMAGE_HARD_LIMIT", 40))
        )
        keep = (
            int(self._keep_limit)
            if self._keep_limit is not None
            else int(getattr(settings, "HISTORY_IMAGE_KEEP_LIMIT", 20))
        )
        if keep < 1:
            keep = 1
        if hard <= keep:  # 上限不构成迟滞区间时不淘汰
            hard = 0
        return hard, keep

    def _cap_messages(self, messages: list[Any]) -> list[Any]:
        hard, keep = self._limits()
        if hard <= 0:
            return messages

        last_human = _last_human_message_index(messages)
        positions: list[tuple[int, int]] = []
        for message_index, message in enumerate(messages[:last_human]):
            content = getattr(message, "content", None)
            if not isinstance(content, list):
                continue
            for block_index, block in enumerate(content):
                if _image_url_from_block(block):
                    positions.append((message_index, block_index))

        if len(positions) <= hard:
            return messages

        evict = set(positions[: len(positions) - keep])

        by_message: dict[int, list[tuple[int, Any]]] = {}
        for message_index, block_index in evict:
            block = messages[message_index].content[block_index]
            url = _image_url_from_block(block)
            by_message.setdefault(message_index, []).append((block_index, url))

        logger.warning(
            "HistoricalImageCap: replacing %d of %d historical image block(s) with placeholders "
            "(keep=%d, hard=%d)",
            len(evict),
            len(positions),
            keep,
            hard,
        )
        capped: list[Any] = list(messages)
        for message_index, replacements in by_message.items():
            original = messages[message_index]
            content = list(original.content)
            for block_index, url in replacements:
                content[block_index] = _image_block_placeholder(url)
            if hasattr(original, "model_copy"):
                capped[message_index] = original.model_copy(update={"content": content})
            else:
                clone = original.copy()
                clone.content = content
                capped[message_index] = clone
        return capped

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT]:
        messages = self._cap_messages(request.messages)
        if messages is not request.messages:
            request = request.override(messages=messages)
        return await handler(request)
