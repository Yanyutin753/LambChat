"""DeepAgent middleware: retry, app-level prompt injection, sandbox MCP prompt, tool binary upload, and deferred tool search."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import mimetypes
import os
import shlex
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
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage

from src.infra.tool.sandbox_mcp_prompt import build_sandbox_mcp_prompt
from src.kernel.config import settings

if TYPE_CHECKING:
    from langchain.agents.middleware.types import ExtendedModelResponse

    from src.infra.tool.deferred_manager import DeferredToolManager

from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)


def _normalize_prompt_text(text: str) -> str:
    """Normalize injected prompt sections so equivalent content has the same shape."""
    return "\n".join(line.rstrip() for line in text.strip().splitlines()).strip()


def _system_message_to_blocks(system_message: Any) -> list[Any]:
    """Convert a system message payload into mutable content blocks."""
    if system_message is None:
        return []

    content = getattr(system_message, "content", None)
    if content is None:
        return []

    if isinstance(content, str):
        normalized = _normalize_prompt_text(content)
        return [{"type": "text", "text": normalized}] if normalized else []

    if isinstance(content, list):
        return list(content)

    return []


def _append_system_text_block(system_message: Any, text: str) -> SystemMessage:
    """Append a deterministic text block to the system message."""
    normalized = _normalize_prompt_text(text)
    blocks = _system_message_to_blocks(system_message)
    if normalized:
        blocks.append({"type": "text", "text": normalized})
    return SystemMessage(content=blocks)


def _tool_sort_key(tool: Any) -> tuple[str, str]:
    """Stable ordering for dynamically appended tools."""
    name = getattr(tool, "name", "") or ""
    server = getattr(tool, "server", "") or ""
    return (server, name)


def _is_retryable_error(exc: Exception) -> bool:
    """Check if an exception is a transient/retryable LLM error.

    Retries on: RateLimitError (429), 5xx server errors, timeouts,
    APIConnectionError (network/TLS/proxy failures), empty stream,
    and API proxy errors with custom error codes (e.g. code "1234").
    Does NOT retry on: 401/403 auth errors, 400 bad request, 404 not found.
    """
    # LangChain empty stream: LLM returned no chunks at all
    if isinstance(exc, ValueError) and "No generations found in stream" in str(exc):
        return True

    # httpx transient network errors (peer closed, incomplete chunked read, etc.)
    try:
        import httpx

        if isinstance(exc, httpx.RemoteProtocolError):
            return True
    except ImportError:
        pass

    for module in ("anthropic", "openai"):
        try:
            mod = __import__(
                module,
                fromlist=[
                    "RateLimitError",
                    "APITimeoutError",
                    "APIConnectionError",
                    "APIStatusError",
                ],
            )
            if isinstance(exc, mod.RateLimitError):
                return True
            if isinstance(exc, mod.APITimeoutError):
                return True
            if isinstance(exc, mod.APIConnectionError):
                return True
            if isinstance(exc, mod.APIStatusError):
                # Standard 5xx server errors
                if 500 <= exc.status_code < 600:
                    return True
                # API proxy errors with custom error codes (e.g. Chinese proxies
                # returning code "1234" with "网络错误" for transient network issues)
                body = getattr(exc, "body", None)
                if isinstance(body, dict):
                    error_obj = body.get("error", {})
                    if isinstance(error_obj, dict):
                        error_code = error_obj.get("code")
                        error_msg = str(error_obj.get("message", "")).lower()
                        # Known proxy error codes that indicate transient issues
                        if error_code in ("1234",):
                            return True
                        # Network-related keywords in proxy error messages
                        network_keywords = ("网络错误", "network error", "timeout", "overloaded")
                        if any(kw in error_msg for kw in network_keywords):
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


def _is_truncated_response(aimessage: AIMessage) -> bool:
    """Check if a response was truncated (incomplete) based on stop_reason or content cues.

    A response is considered truncated when:
    - stop_reason is not 'end_turn'/'tool_use'/'stop_sequence' (explicit truncation), or
    - stop_reason is absent but the text ends with an incomplete cue (colon, ellipsis)
      and there are no tool_calls (heuristic for connection-drop truncation).
    """
    # Explicit stop_reason check
    metadata = getattr(aimessage, "response_metadata", None)
    if isinstance(metadata, dict):
        stop_reason = metadata.get("stop_reason")
        if stop_reason is not None:
            return stop_reason not in ("end_turn", "tool_use", "stop_sequence")

    # Heuristic: text ends with incomplete cue and no tool_calls
    if getattr(aimessage, "tool_calls", None):
        return False
    content = getattr(aimessage, "content", None)
    text = ""
    if isinstance(content, str):
        text = content.strip()
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = (block.get("text", "") or "").strip()
                break
    if not text:
        return False
    return text.endswith(("：", ":", "……", "...", "…")) and len(text) > 2


class ModelFallbackMiddleware(AgentMiddleware):
    """Middleware that falls back to an alternate model when the primary model fails.

    Wraps the inner retry stack. When all retries on the primary model are exhausted
    (ModelRetryMiddleware gives up via ``on_failure="continue"``) and the inner
    handler raises a retryable error, this middleware creates a fallback LLM and
    replays the request once.
    """

    def __init__(self, *, fallback_model: str, thinking: dict | None = None) -> None:
        super().__init__()
        self._fallback_model = fallback_model
        self._thinking = thinking
        self._fallback_llm: BaseChatModel | None = None

    async def _get_fallback_llm(self) -> BaseChatModel:
        """Lazily create the fallback LLM instance."""
        if self._fallback_llm is None:
            from src.infra.llm.client import LLMClient

            self._fallback_llm = await LLMClient.get_model(
                model=self._fallback_model,
                thinking=self._thinking,
            )
            logger.info("[ModelFallback] Created fallback LLM: %s", self._fallback_model)
        return self._fallback_llm

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT]:
        try:
            return await handler(request)
        except Exception as exc:
            if not _is_retryable_error(exc):
                raise

            logger.warning(
                "[ModelFallback] Primary model failed after retries: %s — falling back to %s",
                exc,
                self._fallback_model,
            )

            fallback_llm = await self._get_fallback_llm()
            # Replay with the fallback model
            new_request = request.override(model=fallback_llm)
            try:
                return await handler(new_request)
            except Exception as fallback_exc:
                logger.error(
                    "[ModelFallback] Fallback model %s also failed: %s",
                    self._fallback_model,
                    fallback_exc,
                )
                raise


class EmptyContentRetryMiddleware(AgentMiddleware):
    """Middleware that retries model calls returning empty content."""

    def __init__(self, *, max_retries: int = 1, retry_delay: float = 1.0) -> None:
        super().__init__()
        self.max_retries = max_retries
        self.retry_delay = retry_delay

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

            if not _is_empty_content(messages[0]) and not _is_truncated_response(messages[0]):
                return response

            reason = "truncated" if _is_truncated_response(messages[0]) else "empty"
            logger.warning(
                "%s content in model response (attempt %d/%d)",
                reason.capitalize(),
                attempt + 1,
                self.max_retries + 1,
            )
            if attempt < self.max_retries:
                await asyncio.sleep(self.retry_delay)

        return last_response  # type: ignore[return-value]


class SectionPromptMiddleware(AgentMiddleware):
    """Append one or more deterministic prompt sections as separate system blocks.

    Each section becomes its own content block in the system message, enabling
    fine-grained KV cache breakpoints.  Sections are normalized (trailing
    whitespace stripped) at construction time and batch-appended in a single
    pass to avoid O(n²) block-list rebuilding.
    """

    def __init__(self, *, sections: list[str] | tuple[str, ...]) -> None:
        super().__init__()
        self._sections = tuple(
            _normalize_prompt_text(section) for section in sections if section.strip()
        )

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT]:
        if not self._sections:
            return await handler(request)

        # Batch-append all sections in one pass (avoids repeated _system_message_to_blocks)
        blocks = _system_message_to_blocks(request.system_message)
        blocks.extend({"type": "text", "text": section} for section in self._sections)
        request = request.override(system_message=SystemMessage(content=blocks))
        return await handler(request)


class MemoryIndexMiddleware(AgentMiddleware):
    """Injects the native memory index into the system prompt at request time.

    Uses ``NativeMemoryBackend.build_memory_index(user_id)`` which has its own
    5-minute per-user cache, so repeated calls are essentially free after the first.
    Only active when the native backend is selected and the index feature is enabled.
    """

    def __init__(self, *, user_id: str | None) -> None:
        super().__init__()
        self._user_id = user_id

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT]:
        if not self._user_id:
            return await handler(request)

        index_str = await _build_memory_index_for_user(self._user_id)
        if not index_str:
            return await handler(request)

        new_system_message = _append_system_text_block(request.system_message, index_str)
        request = request.override(system_message=new_system_message)
        return await handler(request)


async def _build_memory_index_for_user(user_id: str) -> str:
    """Build memory index string for a user. Returns empty string on any failure."""
    try:
        from src.infra.memory.tools import _get_backend

        backend = await _get_backend()
        if backend is None or backend.name != "native":
            return ""

        from src.infra.memory.client.native import NativeMemoryBackend

        if not isinstance(backend, NativeMemoryBackend):
            return ""
        index = await backend.build_memory_index(user_id)
        return index if index else ""
    except Exception:
        logger.warning("[Memory] Failed to build memory index for user %s", user_id, exc_info=True)
        return ""


class SandboxMCPMiddleware(AgentMiddleware):
    """Injects sandbox tool descriptions into the system prompt at request time.

    By injecting via middleware (instead of baking into the base system prompt string),
    the sandbox tools end up at the TAIL of the final system message — after
    deepagent's BASE_AGENT_PROMPT and all other middleware injections (memory, subagent,
    summarization, etc.).  This maximizes KV cache hit rates because changes to sandbox tools
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
        prompt = await build_sandbox_mcp_prompt(self._backend, self._user_id)
        if prompt:
            new_system_message = _append_system_text_block(request.system_message, prompt)
            request = request.override(system_message=new_system_message)
        return await handler(request)


def _extract_mcporter_call_target(command: str) -> str | None:
    """Extract the target from a mcporter call command."""
    try:
        tokens = shlex.split(command)
    except ValueError:
        tokens = command.split()

    for index, token in enumerate(tokens):
        if token == "mcporter" and index + 2 < len(tokens) and tokens[index + 1] == "call":
            return tokens[index + 2]
        if "mcporter call " in token:
            nested = _extract_mcporter_call_target(token)
            if nested:
                return nested
    return None


def _server_from_mcporter_target(target: str) -> str | None:
    for separator in (".", ":"):
        if separator in target:
            server = target.split(separator, 1)[0]
            return server or None
    return target or None


class MCPQuotaMiddleware(AgentMiddleware):
    """Enforce quotas for sandbox MCP calls routed through execute/mcporter."""

    def __init__(self, *, user_id: str | None) -> None:
        super().__init__()
        self._user_id = user_id

    async def awrap_tool_call(
        self,
        request: Any,
        handler: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        tool_name = request.tool_call.get("name", "")
        tool_args = request.tool_call.get("args", {})
        if tool_name != "execute" or not isinstance(tool_args, dict):
            return await handler(request)

        command = tool_args.get("command")
        if not isinstance(command, str):
            return await handler(request)

        target = _extract_mcporter_call_target(command)
        server_name = _server_from_mcporter_target(target) if target else None
        if not server_name:
            return await handler(request)

        from src.infra.mcp.quota import (
            check_and_consume_system_mcp_quota,
            quota_error_json,
        )

        quota_result = await check_and_consume_system_mcp_quota(
            user_id=self._user_id,
            server_name=server_name,
        )
        if quota_result.allowed:
            return await handler(request)

        return ToolMessage(
            content=quota_error_json(server_name, quota_result),
            tool_call_id=request.tool_call.get("id", ""),
            name=tool_name,
        )


def create_retry_middleware(
    fallback_model: str | None = None,
    thinking: dict | None = None,
) -> list[AgentMiddleware]:
    """Create the retry middleware stack for deep agents.

    Returns [ModelFallbackMiddleware?, ModelRetryMiddleware, EmptyContentRetryMiddleware]:
    - Outer layer (optional): falls back to an alternate model when primary fails
    - Middle layer: retries on 429/5xx/timeout with exponential backoff
    - Inner layer: retries on empty content responses
    """
    stack: list[AgentMiddleware] = []

    if fallback_model:
        stack.append(ModelFallbackMiddleware(fallback_model=fallback_model, thinking=thinking))

    stack.extend(
        [
            ModelRetryMiddleware(
                max_retries=settings.LLM_MAX_RETRIES,
                retry_on=_is_retryable_error,
                on_failure="error",
                backoff_factor=2.0,
                initial_delay=settings.LLM_RETRY_DELAY,
                max_delay=60.0,
                jitter=True,
            ),
            EmptyContentRetryMiddleware(
                max_retries=settings.LLM_MAX_RETRIES, retry_delay=settings.LLM_RETRY_DELAY
            ),
        ]
    )
    return stack


# MCP content block types that may carry binary data
_BINARY_BLOCK_TYPES = frozenset(("image", "file"))

# Binary file extensions — read_file should upload these to S3 instead of returning garbled text
_BINARY_EXTENSIONS = frozenset(
    (
        # Images
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".bmp",
        ".ico",
        ".svg",
        ".avif",
        ".tiff",
        ".tif",
        # Videos
        ".mp4",
        ".webm",
        ".mov",
        ".avi",
        ".wmv",
        ".mkv",
        ".ogv",
        # Audio
        ".mp3",
        ".wav",
        ".ogg",
        ".aac",
        ".flac",
        ".m4a",
        ".opus",
        # Documents
        ".pdf",
        ".doc",
        ".docx",
        ".xls",
        ".xlsx",
        ".ppt",
        ".pptx",
    )
)


class ToolResultBinaryMiddleware(AgentMiddleware):
    """在 ToolMessage 送回 LLM 前，上传 base64 二进制数据并替换为 URL。

    处理两类场景：
    1. MCP 工具返回 image/file 类型的 base64 数据 → 上传并替换为 URL
    2. read_file 工具读取二进制文件 → 下载并上传到 S3，返回文件链接
    """

    def __init__(self, *, base_url: str = "") -> None:
        super().__init__()
        self._base_url = base_url

    async def awrap_tool_call(
        self,
        request: Any,
        handler: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        tool_name = request.tool_call.get("name", "")
        tool_args = request.tool_call.get("args", {})

        # --- read_file binary interception ---
        if tool_name == "read_file":
            file_path = tool_args.get("file_path", "") if isinstance(tool_args, dict) else ""
            if file_path and self._is_binary_file(file_path):
                uploaded = await self._handle_read_file_binary(request, file_path)
                if uploaded is not None:
                    return uploaded

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

    @staticmethod
    def _is_binary_file(file_path: str) -> bool:
        """Check if a file path has a binary extension."""
        ext = os.path.splitext(file_path)[1].lower()
        return ext in _BINARY_EXTENSIONS

    async def _handle_read_file_binary(self, request: Any, file_path: str) -> ToolMessage | None:
        """Download a binary file from the sandbox, upload to S3, return URL info."""
        try:
            from src.infra.storage.s3.service import get_or_init_storage
            from src.infra.tool.backend_utils import get_backend_from_runtime

            backend = get_backend_from_runtime(request.runtime)
            if backend is None:
                return None

            # Download from sandbox backend
            file_bytes: bytes | None = None
            if hasattr(backend, "adownload_files"):
                try:
                    responses = await backend.adownload_files([file_path])
                    if responses and responses[0].content:
                        file_bytes = responses[0].content
                except Exception:
                    pass

            if file_bytes is None and hasattr(backend, "download_files"):
                try:
                    responses = await asyncio.to_thread(backend.download_files, [file_path])
                    if responses and responses[0].content:
                        file_bytes = responses[0].content
                except Exception:
                    pass

            if file_bytes is None:
                return None

            # Upload to storage
            storage = await get_or_init_storage()
            filename = file_path.rsplit("/", 1)[-1]
            mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
            upload_result = await storage.upload_bytes(
                data=file_bytes,
                folder="revealed_files",
                filename=filename,
                content_type=mime_type,
            )

            base_url = self._base_url or getattr(settings, "APP_BASE_URL", "").rstrip("/")
            proxy_url = (
                f"{base_url}/api/upload/file/{upload_result.key}"
                if base_url
                else f"/api/upload/file/{upload_result.key}"
            )

            result_data = json.dumps(
                {
                    "key": upload_result.key,
                    "url": proxy_url,
                    "name": filename,
                    "mime_type": upload_result.content_type or mime_type,
                    "size": len(file_bytes),
                    "_meta": {
                        "path": file_path,
                        "source": "read_file_binary_upload",
                    },
                },
                ensure_ascii=False,
            )

            logger.info(
                "read_file binary upload: %s → %s (%d bytes)",
                file_path,
                upload_result.key,
                len(file_bytes),
            )

            return ToolMessage(
                content=result_data,
                tool_call_id=request.tool_call.get("id", ""),
                name="read_file",
            )
        except Exception as e:
            logger.warning("read_file binary upload failed: %s", e)
            return None

    async def _upload_block(self, block: dict) -> str | None:
        """Upload a single binary block to storage, return the access URL."""
        try:
            from src.infra.storage.s3.service import get_or_init_storage

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


# ---------------------------------------------------------------------------
# Deferred Tool Search Middleware
# ---------------------------------------------------------------------------


class ToolSearchMiddleware(AgentMiddleware):
    """延迟工具加载中间件 — 管理 MCP 工具的按需发现和动态注入。

    两个核心钩子:

    * ``awrap_model_call`` — 每次 LLM 调用前:
      1. 将未发现的延迟工具名列表注入系统提示尾部
      2. 将 ``search_tools`` 工具 + 已发现工具的 schema 注入 ``request.tools``

    * ``awrap_tool_call`` — 工具执行时:
      如果工具名在已发现集合中但不在 ToolNode 注册表内，
      直接执行并返回 ToolMessage（factory 会跳过这类工具的验证）。
    """

    def __init__(
        self,
        *,
        deferred_manager: "DeferredToolManager",
        search_limit: int = 10,
    ) -> None:
        super().__init__()
        self._deferred_manager = deferred_manager
        self._search_limit = search_limit

        # 延迟初始化 search_tools（避免在 __init__ 中 import 可能不存在的模块）
        self._search_tool: "BaseTool | None" = None

    def _get_search_tool(self) -> "BaseTool":
        """延迟创建 search_tools 工具实例"""
        if self._search_tool is None:
            from src.infra.tool.tool_search_tool import ToolSearchTool

            self._search_tool = ToolSearchTool(
                manager=self._deferred_manager,
                search_limit=self._search_limit,
            )
        return self._search_tool

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT]:
        """注入延迟工具提示和动态工具 schema"""
        # 1. 注入延迟工具名字列表 + 已发现工具状态（使用 manager 的脏标记缓存）
        prompt_section = self._deferred_manager.get_deferred_stubs_string()
        if prompt_section:
            new_system_message = _append_system_text_block(request.system_message, prompt_section)
            request = request.override(system_message=new_system_message)

        # 2. 注入 search_tools 本身和已发现工具，确保子代理与主代理走同一动态加载链路。
        search_tool = self._get_search_tool()
        discovered = self._deferred_manager.get_discovered_tools()
        existing_names = {
            t.name if hasattr(t, "name") else t.get("name", "") for t in request.tools
        }
        new_tools = []
        if search_tool.name not in existing_names:
            new_tools.append(search_tool)
        new_tools.extend(t for t in discovered if t.name not in existing_names)
        if new_tools:
            combined = list(request.tools) + sorted(new_tools, key=_tool_sort_key)
            request = request.override(tools=combined)

        return await handler(request)

    async def awrap_tool_call(
        self,
        request: Any,
        handler: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        """拦截延迟工具和 search_tools 的调用，直接执行

        处理两类工具：
        1. search_tools — 搜索并发现延迟的工具（可能未注册在 ToolNode 中）
        2. 已发现的延迟 MCP 工具 — 直接执行并返回 ToolMessage
        """
        tool_name = request.tool_call.get("name", "")

        # 处理 search_tools 调用（安全网：即使已注册到 ToolNode 也不影响）
        search_tool = self._get_search_tool()
        if tool_name == search_tool.name and request.tool is None:
            try:
                args = request.tool_call.get("args", {})
                result = await search_tool.ainvoke(args)
                content = (
                    result
                    if isinstance(result, str)
                    else json.dumps(result, ensure_ascii=False, default=str)
                )
                return ToolMessage(
                    content=content,
                    tool_call_id=request.tool_call.get("id", ""),
                    name=tool_name,
                )
            except Exception as e:
                logger.warning(
                    "[ToolSearchMiddleware] Error executing search_tools: %s", e, exc_info=True
                )
                return ToolMessage(
                    content=f"Error executing tool {tool_name}: {e}",
                    tool_call_id=request.tool_call.get("id", ""),
                    name=tool_name,
                    status="error",
                )

        # 检查是否为已发现的延迟工具
        if self._deferred_manager.is_discovered(tool_name) and request.tool is None:
            tool = self._deferred_manager.get_tool(tool_name)
            if tool is not None:
                try:
                    args = request.tool_call.get("args", {})
                    result = await tool.ainvoke(args)

                    # MCP 工具使用 response_format="content_and_artifact" 时
                    # ainvoke() 返回 tuple (content, artifact)，需要解包
                    if isinstance(result, tuple) and len(result) == 2:
                        result = result[0]

                    # MCP content blocks ([{"type":"text","text":"..."}]) 直接作为 list 传递，
                    # 保持 ToolMessage.content 的 str | list[dict] 格式
                    if isinstance(result, list):
                        msg_content: str | list[Any] = result
                    elif isinstance(result, str):
                        msg_content = result
                    elif isinstance(result, dict):
                        msg_content = json.dumps(result, ensure_ascii=False, default=str)
                    elif result is not None:
                        msg_content = str(result)
                    else:
                        msg_content = ""

                    return ToolMessage(
                        content=msg_content,
                        tool_call_id=request.tool_call.get("id", ""),
                        name=tool_name,
                    )
                except Exception as e:
                    logger.warning(
                        "[ToolSearchMiddleware] Error executing discovered tool %s: %s",
                        tool_name,
                        e,
                        exc_info=True,
                    )
                    return ToolMessage(
                        content=f"Error executing tool {tool_name}: {e}",
                        tool_call_id=request.tool_call.get("id", ""),
                        name=tool_name,
                        status="error",
                    )

        # 非延迟工具，透交给原始 handler
        return await handler(request)


# ---------------------------------------------------------------------------
# Prompt Caching Middleware — KV cache optimization
# ---------------------------------------------------------------------------


class PromptCachingMiddleware(AgentMiddleware):
    """Re-tags cache breakpoints AFTER all user middleware has injected dynamic content.

    Problem
    -------
    deepagents' built-in ``AnthropicPromptCachingMiddleware`` runs **before** user
    middleware (AppPrompt, MemoryIndex, SandboxMCP, ToolSearch).  It tags the *then*
    last system-message content block with ``cache_control``, but user middleware
    subsequently appends more blocks (skills, memory, MCP tools, deferred stubs).
    The original cache breakpoint ends up in the middle of the final system message,
    so all dynamic content is re-processed every turn.

    Solution
    --------
    This middleware runs **last** in the user middleware chain (innermost layer).
    It walks the final system message and tools, then:

    1. Moves ``cache_control`` to the **actual** last content block so the full
       system message is one contiguous cache segment.
    2. Re-tags the **last tool** with ``cache_control`` (important when
       ``ToolSearchMiddleware`` has appended new tools).

    Result: between consecutive turns within the same session, the entire stable
    prefix (base prompt + workflow + skills + memory + MCP) is served from KV
    cache — only the changed tail (e.g. deferred-tool stubs) is re-processed.
    """

    _CACHE_CONTROL = {"type": "ephemeral"}
    _MAX_CACHED_SYSTEM_BLOCKS = 4
    _MAX_CACHED_TOOLS = 4

    @staticmethod
    def _is_anthropic_model(model: Any) -> bool:
        """Return True when request.model is backed by langchain-anthropic."""
        seen: set[int] = set()
        current = model
        while current is not None and id(current) not in seen:
            seen.add(id(current))
            cls = type(current)
            if cls.__module__.startswith("langchain_anthropic"):
                return True

            # RunnableBinding and similar wrappers keep the underlying model on
            # ``bound``.  Some adapters use ``model`` for the wrapped runnable.
            next_model = getattr(current, "bound", None)
            if next_model is None:
                next_model = getattr(current, "_bound", None)
            if next_model is None:
                candidate = getattr(current, "model", None)
                next_model = candidate if not isinstance(candidate, str) else None
            current = next_model
        return False

    # ---- system message ---------------------------------------------------

    @staticmethod
    def _retag_system_message(
        system_message: Any, cache_control: dict, *, max_cached_blocks: int = 4
    ) -> Any:
        """Strip stale cache_control from inner blocks and tag the final block."""
        if system_message is None:
            return system_message

        blocks = _system_message_to_blocks(system_message)
        if not blocks:
            return system_message

        # Remove cache_control from every block
        for i, block in enumerate(blocks):
            if isinstance(block, dict) and "cache_control" in block:
                blocks[i] = {k: v for k, v in block.items() if k != "cache_control"}

        # Tag the last N blocks so semi-stable sections remain cacheable
        start_idx = max(len(blocks) - max_cached_blocks, 0)
        for i in range(start_idx, len(blocks)):
            block = blocks[i]
            base = block if isinstance(block, dict) else {"type": "text", "text": str(block)}
            blocks[i] = {**base, "cache_control": cache_control}

        return SystemMessage(content=blocks)

    # ---- tools ------------------------------------------------------------

    @staticmethod
    def _retag_tools(
        tools: list[Any] | None, cache_control: dict, *, max_cached_tools: int = 4
    ) -> list[Any] | None:
        """Re-tag the last tool with cache_control (handles newly appended tools)."""
        if not tools:
            return tools

        # Find and remove existing cache_control from tools
        cleaned = []
        tool_indices: list[int] = []
        for i, tool in enumerate(tools):
            if isinstance(tool, BaseTool):
                tool_indices.append(i)
                extras = tool.extras or {}
                if "cache_control" in extras:
                    new_extras = {k: v for k, v in extras.items() if k != "cache_control"}
                    cleaned.append(tool.model_copy(update={"extras": new_extras}))
                    continue
            cleaned.append(tool)

        # Tag the last N tools
        for idx in tool_indices[-max_cached_tools:]:
            tool = cleaned[idx]
            if isinstance(tool, BaseTool):
                new_extras = {**(tool.extras or {}), "cache_control": cache_control}
                cleaned[idx] = tool.model_copy(update={"extras": new_extras})

        return cleaned

    # ---- main entry -------------------------------------------------------

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT]:
        if not self._is_anthropic_model(getattr(request, "model", None)):
            return await handler(request)

        overrides: dict[str, Any] = {}

        new_system = self._retag_system_message(
            request.system_message,
            self._CACHE_CONTROL,
            max_cached_blocks=self._MAX_CACHED_SYSTEM_BLOCKS,
        )
        if new_system is not request.system_message:
            overrides["system_message"] = new_system

        new_tools = self._retag_tools(
            request.tools,
            self._CACHE_CONTROL,
            max_cached_tools=self._MAX_CACHED_TOOLS,
        )
        if new_tools is not request.tools:
            overrides["tools"] = new_tools

        if overrides:
            request = request.override(**overrides)

        return await handler(request)
