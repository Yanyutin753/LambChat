"""DeepAgent middleware: retry, app-level prompt injection, sandbox MCP prompt, tool binary upload, deferred tool search, and subagent activity logging."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import mimetypes
import time
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
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage

from src.infra.tool.sandbox_mcp_prompt import build_sandbox_mcp_prompt
from src.kernel.config import settings

if TYPE_CHECKING:
    from langchain.agents.middleware.types import ExtendedModelResponse

    from src.infra.tool.deferred_manager import DeferredToolManager

from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)


def _is_retryable_error(exc: Exception) -> bool:
    """Check if an exception is a transient/retryable LLM error.

    Retries on: RateLimitError (429), 5xx server errors, timeouts,
    APIConnectionError (network/TLS/proxy failures), empty stream.
    Does NOT retry on: 401/403 auth errors, 400 bad request, 404 not found.
    """
    # LangChain empty stream: LLM returned no chunks at all
    if isinstance(exc, ValueError) and "No generations found in stream" in str(exc):
        return True

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
        parts = [p for p in (self._memory_guide, self._skills_prompt) if p]
        self._combined = "\n\n".join(parts).strip()

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


class MemoryIndexMiddleware(AgentMiddleware):
    """Injects the native memory index into the system prompt at request time.

    Uses ``NativeMemoryBackend.build_memory_index(user_id)`` which has its own
    5-minute per-user cache, so repeated calls are essentially free after the first.
    Only active when the native backend is selected and the index feature is enabled.
    """

    def __init__(self, *, user_id: str) -> None:
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

        from deepagents.middleware._utils import append_to_system_message

        new_system_message = append_to_system_message(request.system_message, index_str)
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
        from deepagents.middleware._utils import append_to_system_message

        # 1. 注入延迟工具名字列表 + 已发现工具状态（使用 manager 的脏标记缓存）
        prompt_section = self._deferred_manager.get_deferred_stubs_string()
        if prompt_section:
            new_system_message = append_to_system_message(request.system_message, prompt_section)
            request = request.override(system_message=new_system_message)

        # 2. 收集需要注入的已发现工具（search_tools 已在 nodes.py 注册到 ToolNode）
        discovered = self._deferred_manager.get_discovered_tools()
        if not discovered:
            return await handler(request)

        # 3. 合并到 request.tools（去重）
        existing_names = {
            t.name if hasattr(t, "name") else t.get("name", "") for t in request.tools
        }
        new_tools = [t for t in discovered if t.name not in existing_names]
        if new_tools:
            combined = list(request.tools) + new_tools
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

                    # MCP 工具可能返回 dict/list，需要安全序列化
                    if isinstance(result, str):
                        content = result
                    elif isinstance(result, (dict, list)):
                        content = json.dumps(result, ensure_ascii=False, default=str)
                    elif result is not None:
                        content = str(result)
                    else:
                        content = ""

                    return ToolMessage(
                        content=content,
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

    # ---- system message ---------------------------------------------------

    @staticmethod
    def _retag_system_message(system_message: Any, cache_control: dict) -> Any:
        """Strip stale cache_control from inner blocks and tag the final block."""
        if system_message is None:
            return system_message

        content = getattr(system_message, "content", None)
        if content is None:
            return system_message

        # Normalise to list-of-blocks form
        if isinstance(content, str):
            if not content:
                return system_message
            blocks: list = [{"type": "text", "text": content}]
        elif isinstance(content, list):
            if not content:
                return system_message
            blocks = list(content)
        else:
            return system_message

        # Remove cache_control from every block except the last
        for i, block in enumerate(blocks):
            if isinstance(block, dict) and "cache_control" in block:
                blocks[i] = {k: v for k, v in block.items() if k != "cache_control"}

        # Tag the last block
        last = blocks[-1]
        base = last if isinstance(last, dict) else {"type": "text", "text": str(last)}
        blocks[-1] = {**base, "cache_control": cache_control}

        return SystemMessage(content=blocks)

    # ---- tools ------------------------------------------------------------

    @staticmethod
    def _retag_tools(tools: list[Any] | None, cache_control: dict) -> list[Any] | None:
        """Re-tag the last tool with cache_control (handles newly appended tools)."""
        if not tools:
            return tools

        # Find and remove existing cache_control from tools
        cleaned = []
        last_tool_idx = -1
        for i, tool in enumerate(tools):
            if isinstance(tool, BaseTool):
                last_tool_idx = i
                extras = tool.extras or {}
                if "cache_control" in extras:
                    new_extras = {k: v for k, v in extras.items() if k != "cache_control"}
                    cleaned.append(tool.model_copy(update={"extras": new_extras}))
                    continue
            cleaned.append(tool)

        # Tag the last tool
        if last_tool_idx >= 0:
            tool = cleaned[last_tool_idx]
            if isinstance(tool, BaseTool):
                new_extras = {**(tool.extras or {}), "cache_control": cache_control}
                cleaned[last_tool_idx] = tool.model_copy(update={"extras": new_extras})

        return cleaned

    # ---- main entry -------------------------------------------------------

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT]:
        overrides: dict[str, Any] = {}

        new_system = self._retag_system_message(request.system_message, self._CACHE_CONTROL)
        if new_system is not request.system_message:
            overrides["system_message"] = new_system

        new_tools = self._retag_tools(request.tools, self._CACHE_CONTROL)
        if new_tools is not request.tools:
            overrides["tools"] = new_tools

        if overrides:
            request = request.override(**overrides)

        return await handler(request)


# ---------------------------------------------------------------------------
# Subagent Activity Middleware — auto-log + compress subagent activity
# ---------------------------------------------------------------------------

# Approximate chars per token (same heuristic as FilesystemMiddleware)
_CHARS_PER_TOKEN = 4

# Maximum uncompressed activity log size in tokens
_DEFAULT_ACTIVITY_TOKEN_LIMIT = 6000

# Keep the most recent N entries as full text during compression
_DEFAULT_KEEP_RECENT = 5

# Maximum chars for a single tool result snippet
_MAX_RESULT_SNIPPET = 800

# Maximum chars for a single LLM text snippet
_MAX_LLM_TEXT_SNIPPET = 600


class SubagentActivityMiddleware(AgentMiddleware):
    """Records all subagent activity (LLM reasoning + tool calls) to a log file.

    When the log exceeds a token threshold, older entries are compressed via a
    lightweight LLM summary.  The full log is written to the backend filesystem
    **once** — when the subagent produces its final response.

    Flow::

        awrap_model_call  → capture LLM text + tool_calls decision
        awrap_tool_call   → capture tool name, args, truncated result
        (log exceeds threshold) → compress old entries via LLM (in-memory only)
        awrap_model_call (final, no tool_calls) → backend.awrite() + inject log path
    """

    def __init__(
        self,
        *,
        backend: Any,
        token_limit: int = _DEFAULT_ACTIVITY_TOKEN_LIMIT,
        keep_recent: int = _DEFAULT_KEEP_RECENT,
    ) -> None:
        super().__init__()
        self._backend = backend  # BackendProtocol | BackendFactory
        self._token_limit = token_limit
        self._keep_recent = keep_recent
        self._run_id = uuid.uuid4().hex[:8]
        self._log_path = f"/workspace/subagent_logs/activity_{self._run_id}.md"
        self._entries: list[str] = []
        self._total_chars = 0
        self._compressed = False
        self._written = False

    def _get_backend(self, runtime: Any) -> Any:
        """Resolve backend instance (mirrors FilesystemMiddleware pattern)."""
        if callable(self._backend):
            return self._backend(runtime)
        return self._backend

    @staticmethod
    def _truncate(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        half = limit // 2 - 3
        return text[:half] + "\n...\n" + text[-half:]

    def _timestamp(self) -> str:
        return time.strftime("%H:%M:%S")

    # ------------------------------------------------------------------
    # Log entry builders
    # ------------------------------------------------------------------

    def _build_llm_entry(self, ai_message: AIMessage) -> str:
        ts = self._timestamp()
        parts: list[str] = [f"\n## [{ts}] LLM"]

        # Text content
        text = ""
        content = ai_message.content
        if isinstance(content, str):
            text = content.strip()
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    text += block.get("text", "")
            text = text.strip()

        if text:
            parts.append(f"> {self._truncate(text, _MAX_LLM_TEXT_SNIPPET)}")

        # Tool calls
        tool_calls = getattr(ai_message, "tool_calls", None)
        if tool_calls:
            names = [tc.get("name", "?") for tc in tool_calls]
            parts.append(f"→ Calling: {', '.join(names)}")

        return "\n".join(parts) if len(parts) > 1 else ""

    # Tool names where specific args hold large payloads — only record size + snippet
    # Note: execute command is intentionally NOT here — commands are usually short
    # and essential to understand what the subagent did.
    _LARGE_ARG_TOOLS: dict[str, frozenset[str]] = {
        "write_file": frozenset({"content"}),
        "edit_file": frozenset({"old_string", "new_string"}),
    }

    def _format_args(self, name: str, args: dict) -> str:
        """Smart args formatting for log entries.

        For tools with large payload args (write_file content, edit_file old/new_string,
        execute command), record arg size + short snippet instead of the full value.
        """
        if not args:
            return ""

        large_args = self._LARGE_ARG_TOOLS.get(name)
        if large_args:
            compact: dict[str, Any] = {}
            for k, v in args.items():
                if k in large_args and isinstance(v, str) and len(v) > 200:
                    compact[k] = f"<{len(v)} chars>"
                    compact[f"{k}_snippet"] = self._truncate(v, 200)
                else:
                    compact[k] = v
            return ", ".join(f"{k}={v!r}" for k, v in compact.items())

        return ", ".join(f"{k}={v!r}" for k, v in args.items())

    def _build_tool_entry(self, name: str, args: dict, result_preview: str) -> str:
        ts = self._timestamp()
        args_str = self._format_args(name, args)
        result_snippet = self._truncate(result_preview, _MAX_RESULT_SNIPPET)

        return f"\n## [{ts}] Tool: {name}\nArgs: {args_str}\nResult: {result_snippet}"

    # ------------------------------------------------------------------
    # Append + compress logic
    # ------------------------------------------------------------------

    def _append_entry(self, entry: str) -> None:
        if not entry:
            return
        self._entries.append(entry)
        self._total_chars += len(entry)

    async def _check_and_compress(self, runtime: Any) -> None:
        """Compress older entries in memory if log exceeds token limit.

        No file I/O here — the compressed log is written only once at the end.
        Guard: only compresses once per run to avoid re-compressing a summary.
        """
        if self._compressed:
            return  # Already compressed once — don't re-compress the summary

        estimated_tokens = self._total_chars // _CHARS_PER_TOKEN
        if estimated_tokens <= self._token_limit:
            return

        if len(self._entries) <= self._keep_recent:
            return  # Not enough entries to compress

        # Split: compress old, keep recent
        split_idx = len(self._entries) - self._keep_recent
        old_entries = self._entries[:split_idx]
        recent_entries = self._entries[split_idx:]

        old_text = "\n".join(old_entries)

        # Compress via LLM
        try:
            compressed_summary = await self._compress_with_llm(old_text)
        except Exception:
            logger.warning("[SubagentActivity] Compression failed, keeping raw entries")
            return

        # Rebuild entries (in-memory only)
        self._entries = [compressed_summary, *recent_entries]
        self._total_chars = sum(len(e) for e in self._entries)
        self._compressed = True

    async def _compress_with_llm(self, text: str) -> str:
        """Use a lightweight LLM to compress activity entries."""
        from langchain_core.messages import HumanMessage

        from src.infra.llm.client import LLMClient

        # Use the same API config but could use a cheaper model
        llm = LLMClient.get_model(
            api_base=settings.LLM_API_BASE,
            api_key=settings.LLM_API_KEY,
            model=settings.LLM_MODEL,
            temperature=0.3,
            max_tokens=1500,
        )

        prompt = (
            "Compress the following subagent activity log into a concise summary.\n"
            "Keep: key findings, decisions, file paths, important values.\n"
            "Drop: repetitive reasoning, verbose descriptions, duplicate info.\n"
            "Format as markdown bullet points under '## Summary of Earlier Activity'.\n\n"
            f"{text}"
        )

        response = await llm.ainvoke([HumanMessage(content=prompt)])
        summary = response.content if isinstance(response.content, str) else str(response.content)
        return f"\n## [COMPRESSED] Summary of Earlier Activity\n{summary.strip()}"

    def _render_log(self) -> str:
        """Render all entries into the final log markdown."""
        header = f"# Subagent Activity Log (run: {self._run_id})\n"
        return header + "\n".join(self._entries) + "\n"

    # ------------------------------------------------------------------
    # Middleware hooks
    # ------------------------------------------------------------------

    async def _persist_log(self, runtime: Any) -> bool:
        """Write the activity log to backend filesystem. Returns True on success."""
        if self._written or not self._entries:
            return self._written
        try:
            backend = self._get_backend(runtime)
            full_log = self._render_log()
            write_result = await backend.awrite(self._log_path, full_log)
            if write_result.error:
                logger.warning("[SubagentActivity] Write failed: %s", write_result.error)
                return False
            self._written = True
            logger.info(
                "[SubagentActivity] Log persisted to %s (%d chars)",
                self._log_path,
                self._total_chars,
            )
            return True
        except Exception:
            logger.warning("[SubagentActivity] Backend write failed", exc_info=True)
            return False

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT]:
        response = await handler(request)

        # Extract AIMessage from response
        messages: list = []
        if isinstance(response, AIMessage):
            messages = [response]
        elif hasattr(response, "result"):
            messages = response.result or []

        if not messages or not isinstance(messages[0], AIMessage):
            return response

        ai_message = messages[0]

        # Record LLM activity
        entry = self._build_llm_entry(ai_message)
        if entry:
            self._append_entry(entry)

        # Check for final response (no tool_calls) — persist + inject log path
        tool_calls = getattr(ai_message, "tool_calls", None)
        if not tool_calls:
            # Write log to backend exactly once
            await self._persist_log(request.runtime)

            # Inject log path into AI response
            log_ref = f"\n\n[Activity log saved to: {self._log_path}]"
            original_text = ai_message.text or ""

            new_content: str | list
            if isinstance(ai_message.content, list):
                new_content = [*ai_message.content, {"type": "text", "text": log_ref}]
            else:
                new_content = original_text + log_ref

            new_ai = AIMessage(
                content=new_content,
                tool_calls=ai_message.tool_calls,
                id=ai_message.id,
                additional_kwargs=ai_message.additional_kwargs,
                response_metadata=ai_message.response_metadata,
            )

            if hasattr(response, "result"):
                return type(response)(result=[new_ai])
            return new_ai  # type: ignore[return-value]

        # Not final — compress in memory if needed (no file write)
        await self._check_and_compress(request.runtime)
        return response

    async def awrap_tool_call(
        self,
        request: Any,
        handler: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        tool_name = request.tool_call.get("name", "")
        tool_args = request.tool_call.get("args", {})

        result = await handler(request)

        # Extract result preview
        result_preview = ""
        if isinstance(result, ToolMessage):
            content = result.content
            if isinstance(content, str):
                result_preview = content
            elif isinstance(content, list):
                texts: list[str] = []
                for block in content:
                    if isinstance(block, str):
                        texts.append(block)
                    elif isinstance(block, dict) and block.get("type") == "text":
                        texts.append(block.get("text", ""))
                result_preview = " ".join(texts)

        entry = self._build_tool_entry(tool_name, tool_args, result_preview)
        self._append_entry(entry)

        # Compress in memory if needed (no file write)
        await self._check_and_compress(request.runtime)

        return result
