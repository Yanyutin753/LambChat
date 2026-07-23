"""Tool call interception middleware — MCP quota, deferred tool search, binary upload."""

from __future__ import annotations

import base64
import json
import logging
import mimetypes
import os
import shlex
import uuid
from collections.abc import Awaitable, Callable
from tempfile import SpooledTemporaryFile
from typing import TYPE_CHECKING, Any

from langchain.agents.middleware.types import (
    AgentMiddleware,
    ContextT,
    ModelRequest,
    ModelResponse,
    ResponseT,
)
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool

if TYPE_CHECKING:
    from src.infra.tool.deferred_manager import DeferredToolManager

from src.infra.agent.middleware._helpers import (
    _append_system_text_blocks,
    _normalize_prompt_text,
    _system_message_to_blocks,
    _tool_sort_key,
)
from src.infra.async_utils import run_blocking_io
from src.infra.tool.deferred_manager import DEFERRED_TOOL_SEARCH_GUIDE
from src.kernel.config import settings

logger = logging.getLogger(__name__)

_PROMPT_CACHE_VOLATILE_TOOL_EXTRA = "_lambchat_prompt_cache_volatile"
_BINARY_UPLOAD_SPOOL_MEMORY_LIMIT = 2 * 1024 * 1024
_BINARY_BLOCK_UPLOAD_MAX_BYTES = 50 * 1024 * 1024
_BINARY_BLOCK_UPLOAD_TOTAL_MAX_BYTES = 50 * 1024 * 1024
_BINARY_BLOCK_UPLOAD_MAX_BLOCKS = 4
_READ_FILE_BINARY_UPLOAD_MAX_BYTES = 50 * 1024 * 1024
_BASE64_DECODE_CHUNK_CHARS = 4 * 1024 * 1024


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


def _redact_failed_binary_block(block: dict[str, Any]) -> dict[str, Any]:
    redacted = {k: v for k, v in block.items() if k != "base64"}
    redacted["upload_error"] = "binary_upload_failed"
    return redacted


def _redact_oversized_binary_block(block: dict[str, Any]) -> dict[str, Any]:
    redacted = {k: v for k, v in block.items() if k != "base64"}
    redacted["upload_error"] = "binary_upload_too_large"
    return redacted


def _redact_excess_binary_block(block: dict[str, Any]) -> dict[str, Any]:
    redacted = {k: v for k, v in block.items() if k != "base64"}
    redacted["upload_error"] = "binary_upload_too_many_blocks"
    return redacted


def _estimated_base64_decoded_size(b64_data: str) -> int:
    stripped = b64_data.rstrip("=")
    return (len(stripped) * 3) // 4


def _decode_base64_to_file(b64_data: str, file, *, max_bytes: int) -> int:
    total = 0
    carry = ""
    for start in range(0, len(b64_data), _BASE64_DECODE_CHUNK_CHARS):
        chunk = carry + b64_data[start : start + _BASE64_DECODE_CHUNK_CHARS]
        decode_len = (len(chunk) // 4) * 4
        if decode_len == 0:
            carry = chunk
            continue
        decoded = base64.b64decode(chunk[:decode_len])
        file.write(decoded)
        total += len(decoded)
        if total > max_bytes:
            raise ValueError("binary_upload_too_large")
        carry = chunk[decode_len:]
    if carry:
        decoded = base64.b64decode(carry)
        file.write(decoded)
        total += len(decoded)
        if total > max_bytes:
            raise ValueError("binary_upload_too_large")
    file.seek(0)
    return total


def _write_bytes_to_file(data: bytes, file) -> int:
    file.write(data)
    size = len(data)
    file.seek(0)
    return size


def _coerce_file_size(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        size = int(value)
    except (TypeError, ValueError):
        return None
    return size if size >= 0 else None


async def _get_backend_file_size(backend: Any, file_path: str) -> int | None:
    async_method = getattr(backend, "aget_file_size", None)
    if callable(async_method):
        try:
            return _coerce_file_size(await async_method(file_path))
        except Exception as exc:
            logger.debug("aget_file_size failed for %s: %s", file_path, exc)

    sync_method = getattr(backend, "get_file_size", None)
    if callable(sync_method):
        try:
            return _coerce_file_size(await run_blocking_io(sync_method, file_path))
        except Exception as exc:
            logger.debug("get_file_size failed for %s: %s", file_path, exc)

    private_method = getattr(backend, "_file_size", None)
    if callable(private_method):
        try:
            return _coerce_file_size(await run_blocking_io(private_method, file_path))
        except Exception as exc:
            logger.debug("_file_size failed for %s: %s", file_path, exc)

    return None


async def _json_dumps_for_tool_message(value: Any) -> str:
    return await run_blocking_io(
        json.dumps,
        value,
        ensure_ascii=False,
        default=str,
    )


# ---------------------------------------------------------------------------
# MCP Quota Middleware
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Tool Result Binary Middleware
# ---------------------------------------------------------------------------


class ToolResultBinaryMiddleware(AgentMiddleware):
    """Upload base64 binary data and replace with URL before sending ToolMessage to LLM.

    Handles two scenarios:
    1. MCP tools returning image/file type base64 data → upload and replace with URL
    2. read_file tool reading binary files → download and upload to S3, return file link
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

        # Upload and replace base64 with URL. Return JSON text instead of a raw
        # content-block list so model providers do not parse MCP media blocks as
        # provider-native image/file blocks on the next LLM call.
        new_blocks: list[str | dict[str, Any]] = []
        uploaded_block_count = 0
        estimated_total_bytes = 0
        for block in content:
            if (
                isinstance(block, dict)
                and block.get("base64")
                and block.get("type") in _BINARY_BLOCK_TYPES
            ):
                b64_data = block.get("base64")
                estimated_bytes = (
                    _estimated_base64_decoded_size(b64_data) if isinstance(b64_data, str) else 0
                )
                if uploaded_block_count >= _BINARY_BLOCK_UPLOAD_MAX_BLOCKS:
                    new_blocks.append(_redact_excess_binary_block(block))
                    continue
                if estimated_total_bytes + estimated_bytes > _BINARY_BLOCK_UPLOAD_TOTAL_MAX_BYTES:
                    new_blocks.append(_redact_oversized_binary_block(block))
                    continue
                url = await self._upload_block(block)
                if url:
                    # Keep original structure, replace base64 with url
                    new_block = {k: v for k, v in block.items() if k != "base64"}
                    new_block["url"] = url
                    new_blocks.append(new_block)
                    uploaded_block_count += 1
                    estimated_total_bytes += estimated_bytes
                else:
                    new_blocks.append(_redact_failed_binary_block(block))
            else:
                new_blocks.append(block)

        return ToolMessage(
            content=await self._format_uploaded_blocks_for_llm(new_blocks),
            tool_call_id=result.tool_call_id,
            name=getattr(result, "name", None),
            status=getattr(result, "status", None),
            artifact=getattr(result, "artifact", None),
        )

    @staticmethod
    async def _format_uploaded_blocks_for_llm(blocks: list[str | dict[str, Any]]) -> str:
        text_parts: list[str] = []
        media_blocks: list[dict[str, Any]] = []

        for block in blocks:
            if isinstance(block, str):
                text_parts.append(block)
                continue
            if not isinstance(block, dict):
                text_parts.append(str(block))
                continue
            if block.get("type") == "text":
                text = block.get("text")
                if text is not None:
                    text_parts.append(str(text))
                continue
            media_blocks.append(block)

        payload: dict[str, Any] = {"text": "".join(text_parts)}
        if media_blocks:
            payload["blocks"] = media_blocks
        return await _json_dumps_for_tool_message(payload)

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

            known_size = await _get_backend_file_size(backend, file_path)
            if known_size is not None and known_size > _READ_FILE_BINARY_UPLOAD_MAX_BYTES:
                logger.warning(
                    "read_file binary upload refused oversized file before download: "
                    "%s size=%s max=%s",
                    file_path,
                    known_size,
                    _READ_FILE_BINARY_UPLOAD_MAX_BYTES,
                )
                return None

            # Download from sandbox backend
            file_bytes: bytes | None = None
            if hasattr(backend, "adownload_files"):
                try:
                    responses = await backend.adownload_files([file_path])
                    if responses and responses[0].content:
                        file_bytes = responses[0].content
                    del responses
                except Exception as e:
                    logger.debug("从沙箱后端下载文件失败 (adownload_files) %s: %s", file_path, e)

            if file_bytes is None and hasattr(backend, "download_files"):
                try:
                    responses = await run_blocking_io(backend.download_files, [file_path])
                    if responses and responses[0].content:
                        file_bytes = responses[0].content
                    del responses
                except Exception as e:
                    logger.debug("从沙箱后端下载文件失败 (download_files) %s: %s", file_path, e)

            if file_bytes is None:
                return None

            filename = file_path.rsplit("/", 1)[-1]
            mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
            file_size = len(file_bytes)
            if file_size > _READ_FILE_BINARY_UPLOAD_MAX_BYTES:
                logger.warning(
                    "read_file binary upload refused oversized file: %s size=%s max=%s",
                    file_path,
                    file_size,
                    _READ_FILE_BINARY_UPLOAD_MAX_BYTES,
                )
                return None

            # Upload to storage
            storage = await get_or_init_storage()
            with SpooledTemporaryFile(
                max_size=_BINARY_UPLOAD_SPOOL_MEMORY_LIMIT,
                mode="w+b",
            ) as spooled:
                file_size = await run_blocking_io(_write_bytes_to_file, file_bytes, spooled)
                del file_bytes
                upload_result = await storage.upload_file(
                    file=spooled,
                    folder="revealed_files",
                    filename=filename,
                    content_type=mime_type,
                    skip_size_limit=True,
                )

            base_url = self._base_url or getattr(settings, "APP_BASE_URL", "").rstrip("/")
            proxy_url = (
                f"{base_url}/api/upload/file/{upload_result.key}"
                if base_url
                else f"/api/upload/file/{upload_result.key}"
            )

            result_data = await _json_dumps_for_tool_message(
                {
                    "key": upload_result.key,
                    "url": proxy_url,
                    "name": filename,
                    "mime_type": upload_result.content_type or mime_type,
                    "size": file_size,
                    "_meta": {
                        "path": file_path,
                        "source": "read_file_binary_upload",
                    },
                },
            )

            logger.info(
                "read_file binary upload: %s → %s (%d bytes)",
                file_path,
                upload_result.key,
                file_size,
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
        b64_data = block.get("base64")
        if not b64_data or not isinstance(b64_data, str):
            return None

        if _estimated_base64_decoded_size(b64_data) > _BINARY_BLOCK_UPLOAD_MAX_BYTES:
            logger.warning(
                "Refusing oversized binary block upload: estimated=%s max=%s",
                _estimated_base64_decoded_size(b64_data),
                _BINARY_BLOCK_UPLOAD_MAX_BYTES,
            )
            return None

        try:
            from src.infra.storage.s3.service import get_or_init_storage

            storage = await get_or_init_storage()
        except Exception as e:
            logger.warning("Failed to initialize storage for binary upload: %s", e)
            return None

        try:
            mime_type = block.get("mime_type", "application/octet-stream")
            ext = mimetypes.guess_extension(mime_type) or ".bin"
            ext = ext.lstrip(".")
            filename = f"binary_{uuid.uuid4().hex[:8]}.{ext}"

            with SpooledTemporaryFile(
                max_size=_BINARY_UPLOAD_SPOOL_MEMORY_LIMIT,
                mode="w+b",
            ) as spooled:
                size = await run_blocking_io(
                    _decode_base64_to_file,
                    b64_data,
                    spooled,
                    max_bytes=_BINARY_BLOCK_UPLOAD_MAX_BYTES,
                )
                upload_result = await storage.upload_file(
                    file=spooled,
                    folder="tool_binaries",
                    filename=filename,
                    content_type=mime_type,
                    skip_size_limit=True,
                )

            base_url = self._base_url
            if not base_url:
                base_url = getattr(settings, "APP_BASE_URL", "").rstrip("/")

            url = (
                f"{base_url}/api/upload/file/{upload_result.key}"
                if base_url
                else f"/api/upload/file/{upload_result.key}"
            )
            logger.info("Middleware uploaded binary block: %s (%d bytes)", upload_result.key, size)
            return url
        except ValueError as e:
            if str(e) == "binary_upload_too_large":
                logger.warning(
                    "Refusing oversized binary block upload after decode exceeded %s bytes",
                    _BINARY_BLOCK_UPLOAD_MAX_BYTES,
                )
                return None
            logger.warning("Failed to upload binary block in middleware: %s", e)
            return None
        except Exception as e:
            logger.warning("Failed to upload binary block in middleware: %s", e)
            return None


# ---------------------------------------------------------------------------
# Deferred Tool Search Middleware
# ---------------------------------------------------------------------------


class ToolSearchMiddleware(AgentMiddleware):
    """Deferred tool loading middleware — manages on-demand MCP tool discovery and dynamic injection.

    Two core hooks:

    * ``awrap_model_call`` — before each LLM call:
      1. Injects the undiscovered deferred tool name list into the system prompt tail
      2. Injects ``search_tools`` tool + discovered tool schemas into ``request.tools``

    * ``awrap_tool_call`` — during tool execution:
      If the tool name is in the discovered set but not in the ToolNode registry,
      execute directly and return ToolMessage (factory skips validation for these tools).
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

        # Lazy init for search_tools (avoid importing potentially missing modules in __init__)
        self._search_tool: "BaseTool | None" = None

    def _get_search_tool(self) -> "BaseTool":
        """Lazily create search_tools tool instance."""
        if self._search_tool is None:
            from src.infra.tool.tool_search_tool import ToolSearchTool

            self._search_tool = ToolSearchTool(
                manager=self._deferred_manager,
                search_limit=self._search_limit,
            )
        return self._search_tool

    @staticmethod
    def _system_message_contains_search_guide(system_message: Any) -> bool:
        guide = _normalize_prompt_text(DEFERRED_TOOL_SEARCH_GUIDE)
        if not guide:
            return False

        text_parts: list[str] = []
        for block in _system_message_to_blocks(system_message):
            if not isinstance(block, dict):
                continue
            if block.get("type") != "text":
                continue
            text = block.get("text", "")
            if isinstance(text, str):
                text_parts.append(_normalize_prompt_text(text))
        return guide in "\n\n".join(text_parts)

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT]:
        """Inject deferred tool prompt and dynamic tool schemas."""
        # 1. Inject deferred tool name list + discovered tool state (uses manager's dirty flag cache)
        prompt_sections = self._deferred_manager.get_deferred_prompt_blocks()
        if prompt_sections and self._system_message_contains_search_guide(request.system_message):
            prompt_sections = prompt_sections[1:]
        if prompt_sections:
            new_system_message = _append_system_text_blocks(request.system_message, prompt_sections)
            request = request.override(system_message=new_system_message)

        # 2. Inject search_tools itself and discovered tools (ensures sub-agents share the same dynamic loading path)
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
        """Intercept deferred tool and search_tools calls, execute directly.

        Handles two tool types:
        1. search_tools — search and discover deferred tools (may not be registered in ToolNode)
        2. Discovered deferred MCP tools — execute directly and return ToolMessage
        """
        tool_name = request.tool_call.get("name", "")

        # Handle search_tools through this middleware even when ToolNode has a
        # registered search_tools instance. Sub-agents use forked managers, and
        # executing the registered parent tool would make the search invisible
        # to the sub-agent's next model call.
        search_tool = self._get_search_tool()
        if tool_name == search_tool.name:
            try:
                args = request.tool_call.get("args", {})
                result = await search_tool.ainvoke(args)
                content = (
                    result
                    if isinstance(result, str)
                    else await _json_dumps_for_tool_message(result)
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

        # Check if it's a discovered deferred tool
        if self._deferred_manager.is_discovered(tool_name) and request.tool is None:
            tool = self._deferred_manager.get_tool(tool_name)
            if tool is not None:
                try:
                    args = request.tool_call.get("args", {})
                    result = await tool.ainvoke(args)

                    # MCP tools with response_format="content_and_artifact"
                    # ainvoke() returns tuple (content, artifact), need to unpack
                    if isinstance(result, tuple) and len(result) == 2:
                        result = result[0]

                    # MCP content blocks ([{"type":"text","text":"..."}]) passed directly as list,
                    # preserving ToolMessage.content str | list[dict] format
                    if isinstance(result, list):
                        msg_content: str | list[Any] = result
                    elif isinstance(result, str):
                        msg_content = result
                    elif isinstance(result, dict):
                        msg_content = await _json_dumps_for_tool_message(result)
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

        # Non-deferred tool, pass through to original handler
        return await handler(request)
