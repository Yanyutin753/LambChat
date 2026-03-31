"""DeepAgent middleware: retry, app-level prompt injection, sandbox MCP prompt, and tool binary upload."""

from __future__ import annotations

import asyncio
import base64
import logging
import mimetypes
import uuid
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from langchain.agents.middleware import ModelRetryMiddleware
from langchain.agents.middleware.types import (
    AgentMiddleware,
    ContextT,
    ModelRequest,
    ModelResponse,
    ResponseT,
)
from langchain_core.messages import AIMessage, ToolMessage

from src.infra.tool.sandbox_mcp_prompt import build_sandbox_mcp_prompt
from src.kernel.config import settings

if TYPE_CHECKING:
    from langchain.agents.middleware.types import ExtendedModelResponse

logger = logging.getLogger(__name__)


def _is_retryable_error(exc: Exception) -> bool:
    """Check if an exception is a transient/retryable LLM error.

    Retries on: RateLimitError (429), 5xx server errors, timeouts,
    empty stream (No generations found in stream).
    Does NOT retry on: 401/403 auth errors, 400 bad request, 404 not found.
    """
    # LangChain empty stream: LLM returned no chunks at all
    if isinstance(exc, ValueError) and "No generations found in stream" in str(exc):
        return True

    for module in ("anthropic", "openai"):
        try:
            mod = __import__(
                module, fromlist=["RateLimitError", "APITimeoutError", "APIStatusError"]
            )
            if isinstance(exc, mod.RateLimitError):
                return True
            if isinstance(exc, mod.APITimeoutError):
                return True
            if isinstance(exc, mod.APIStatusError) and 500 <= exc.status_code < 600:
                return True
        except (ImportError, AttributeError):
            continue
    return False


def _is_empty_content(aimessage: AIMessage) -> bool:
    """Check if an AIMessage has no meaningful content.

    Tool-call-only responses and responses with non-empty text are NOT empty.
    Thinking-only responses (no text, no tool calls) ARE considered empty.
    """
    if getattr(aimessage, "tool_calls", None):
        return False

    content = getattr(aimessage, "content", None)
    if content is None or content == "":
        return True
    if isinstance(content, str):
        return not content.strip()
    if isinstance(content, list):
        return not any(
            block.get("type") == "text" and block.get("text", "").strip()
            for block in content
            if isinstance(block, dict)
        )
    return False


class EmptyContentRetryMiddleware(AgentMiddleware):
    """Middleware that retries model calls returning empty content."""

    def __init__(self, *, max_retries: int = 1, retry_delay: float = 1.0) -> None:
        super().__init__()
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.tools: list = []

    def _extract_messages(
        self,
        response: (ModelResponse[ResponseT] | AIMessage | ExtendedModelResponse[ResponseT]),
    ) -> list:
        """Extract AIMessage list from various response types."""
        if isinstance(response, AIMessage):
            return [response]
        if isinstance(response, ModelResponse):
            return response.result if response.result else []
        if hasattr(response, "model_response"):
            return response.model_response.result if response.model_response.result else []
        return []

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT] | AIMessage | ExtendedModelResponse[ResponseT]:
        last_response = None
        for attempt in range(self.max_retries + 1):
            response = await handler(request)
            last_response = response

            messages = self._extract_messages(response)
            if not messages or not isinstance(messages[0], AIMessage):
                break

            if not _is_empty_content(messages[0]):
                return response

            logger.warning(
                "Empty content in model response (attempt %d/%d)",
                attempt + 1,
                self.max_retries + 1,
            )
            if attempt < self.max_retries:
                await asyncio.sleep(self.retry_delay)

        return last_response  # type: ignore[return-value]


class AppPromptMiddleware(AgentMiddleware):
    """Injects per-session dynamic content (skills, memory guide) into the system prompt tail.

    These sections vary per user / feature-flag configuration.  By injecting them via
    middleware instead of baking into the base prompt string, they end up at the TAIL of
    the final system message — after deepagent's BASE_AGENT_PROMPT and all built-in
    middleware injections — which maximises KV cache hit rates.
    """

    def __init__(self, *, skills_prompt: str = "", memory_guide: str = "") -> None:
        super().__init__()
        self._skills_prompt = skills_prompt
        self._memory_guide = memory_guide
        self._combined = (self._memory_guide + "\n\n" + self._skills_prompt).strip()

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT]:
        if not self._combined:
            return await handler(request)
        from deepagents.middleware._utils import append_to_system_message

        new_system_message = append_to_system_message(request.system_message, self._combined)
        request = request.override(system_message=new_system_message)
        return await handler(request)


class SandboxMCPMiddleware(AgentMiddleware):
    """Injects sandbox MCP tool descriptions into the system prompt at request time.

    By injecting via middleware (instead of baking into the base system prompt string),
    the sandbox MCP tools end up at the TAIL of the final system message — after
    deepagent's BASE_AGENT_PROMPT and all other middleware injections (memory, subagent,
    summarization, etc.).  This maximizes KV cache hit rates because changes to MCP tools
    only invalidate the tail of the cache, not the stable prefix.

    ``build_sandbox_mcp_prompt`` has its own per-user 30-minute cache, so repeated
    ``awrap_model_call`` invocations within a session are essentially free.
    """

    def __init__(self, *, backend: Any, user_id: str) -> None:
        super().__init__()
        self._backend = backend
        self._user_id = user_id

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT]:
        from deepagents.middleware._utils import append_to_system_message

        prompt = await build_sandbox_mcp_prompt(self._backend, self._user_id)
        if prompt:
            new_system_message = append_to_system_message(request.system_message, prompt)
            request = request.override(system_message=new_system_message)
        return await handler(request)


def create_retry_middleware() -> list[AgentMiddleware]:
    """Create the retry middleware stack for deep agents.

    Returns [ModelRetryMiddleware, EmptyContentRetryMiddleware]:
    - Outer layer: retries on 429/5xx/timeout with exponential backoff
    - Inner layer: retries on empty content responses
    """
    return [
        ModelRetryMiddleware(
            max_retries=settings.LLM_MAX_RETRIES,
            retry_on=_is_retryable_error,
            on_failure="continue",
            backoff_factor=2.0,
            initial_delay=settings.LLM_RETRY_DELAY,
            max_delay=60.0,
            jitter=True,
        ),
        EmptyContentRetryMiddleware(
            max_retries=settings.LLM_MAX_RETRIES, retry_delay=settings.LLM_RETRY_DELAY
        ),
    ]


# MCP content block types that may carry binary data
_BINARY_BLOCK_TYPES = frozenset(("image", "file"))


class ToolResultBinaryMiddleware(AgentMiddleware):
    """在 ToolMessage 送回 LLM 前，上传 base64 二进制数据并替换为 URL。

    当工具（如 MCP 工具）返回 image/file 类型的 base64 数据时：
    1. 将二进制数据上传到对象存储
    2. 用包含 URL 的文本块替换原始 base64 块
    3. LLM 收到的是可访问的 URL，而非原始 base64

    这样 LLM 就能在后续工具调用（如 analyze_image）中使用正确的 URL。
    """

    def __init__(self, *, base_url: str = "") -> None:
        super().__init__()
        self._base_url = base_url

    async def awrap_tool_call(
        self,
        request: Any,
        handler: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        result = await handler(request)

        # Only process ToolMessage results
        if not isinstance(result, ToolMessage):
            return result

        content = result.content
        if not isinstance(content, list):
            return result

        # Quick check: any base64 blocks?
        if not any(
            isinstance(b, dict) and b.get("base64") and b.get("type") in _BINARY_BLOCK_TYPES
            for b in content
        ):
            return result

        # Upload and replace base64 with URL, keeping original block structure
        new_blocks: list[str | dict[str, Any]] = []
        for block in content:
            if (
                isinstance(block, dict)
                and block.get("base64")
                and block.get("type") in _BINARY_BLOCK_TYPES
            ):
                url = await self._upload_block(block)
                if url:
                    # Keep original structure, replace base64 with url
                    new_block = {k: v for k, v in block.items() if k != "base64"}
                    new_block["url"] = url
                    new_blocks.append(new_block)
                else:
                    new_blocks.append(block)
            else:
                new_blocks.append(block)

        return ToolMessage(
            content=new_blocks,
            tool_call_id=result.tool_call_id,
            name=getattr(result, "name", None),
            status=getattr(result, "status", None),
            artifact=getattr(result, "artifact", None),
        )

    async def _upload_block(self, block: dict) -> str | None:
        """Upload a single binary block to storage, return the access URL."""
        try:
            from src.api.routes.upload import get_or_init_storage

            storage = await get_or_init_storage()
        except Exception as e:
            logger.warning("Failed to initialize storage for binary upload: %s", e)
            return None

        b64_data = block.get("base64")
        if not b64_data or not isinstance(b64_data, str):
            return None

        try:
            raw_bytes = base64.b64decode(b64_data)
            mime_type = block.get("mime_type", "application/octet-stream")
            ext = mimetypes.guess_extension(mime_type) or ".bin"
            ext = ext.lstrip(".")
            filename = f"binary_{uuid.uuid4().hex[:8]}.{ext}"

            upload_result = await storage.upload_bytes(
                data=raw_bytes,
                folder="tool_binaries",
                filename=filename,
                content_type=mime_type,
            )

            base_url = self._base_url
            if not base_url:
                base_url = getattr(settings, "APP_BASE_URL", "").rstrip("/")

            url = (
                f"{base_url}/api/upload/file/{upload_result.key}"
                if base_url
                else f"/api/upload/file/{upload_result.key}"
            )
            logger.info(
                "Middleware uploaded binary block: %s (%d bytes)", upload_result.key, len(raw_bytes)
            )
            return url
        except Exception as e:
            logger.warning("Failed to upload binary block in middleware: %s", e)
            return None
