"""Subagent activity middleware — auto-log + compress subagent activity."""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from langchain.agents.middleware.types import (
    AgentMiddleware,
    ContextT,
    ModelRequest,
    ModelResponse,
    ResponseT,
)
from langchain_core.messages import AIMessage, ToolMessage

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Approximate chars per token (same heuristic as FilesystemMiddleware)
_CHARS_PER_TOKEN = 4

# Maximum uncompressed activity log size in tokens
_DEFAULT_ACTIVITY_TOKEN_LIMIT = 50000

# Keep the most recent N entries as full text during compression
_DEFAULT_KEEP_RECENT = 5

# Timestamp format for activity log entries, including timezone offset.
_ACTIVITY_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S %z"

# Maximum chars for a single tool result snippet
_MAX_RESULT_SNIPPET = 800

# Externalize payloads larger than this into separate files, keeping the log readable
_MAX_INLINE_PAYLOAD_CHARS = 2000


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
        self._payload_dir = f"/workspace/subagent_logs/payloads/{self._run_id}"
        self._entries: list[str] = []
        self._total_chars = 0
        self._compressed = False
        self._written = False
        self._payload_counter = 0

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
        return time.strftime(_ACTIVITY_TIMESTAMP_FORMAT)

    def _next_payload_path(self, kind: str, label: str, extension: str = "txt") -> str:
        """Build a stable, unique payload path for this subagent run."""
        self._payload_counter += 1
        safe_label = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_") or kind
        return f"{self._payload_dir}/{self._payload_counter:04d}_{kind}_{safe_label}.{extension}"

    async def _write_payload(
        self,
        runtime: Any,
        *,
        kind: str,
        label: str,
        content: str,
        extension: str = "txt",
    ) -> str | None:
        """Persist a full payload for later inspection and return its path."""
        try:
            backend = self._get_backend(runtime)
            payload_path = self._next_payload_path(kind, label, extension)
            write_result = await backend.awrite(payload_path, content)
            if write_result.error:
                logger.warning("[SubagentActivity] Payload write failed: %s", write_result.error)
                return None
            return payload_path
        except Exception:
            logger.warning("[SubagentActivity] Payload write failed", exc_info=True)
            return None

    @staticmethod
    def _serialize_tool_result(result: Any) -> str:
        """Normalize tool results into text for logging / payload storage."""
        if isinstance(result, ToolMessage):
            content = result.content
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                parts: list[str] = []
                for block in content:
                    if isinstance(block, str):
                        parts.append(block)
                    elif isinstance(block, dict):
                        if block.get("type") == "text":
                            parts.append(str(block.get("text", "")))
                        else:
                            parts.append(json.dumps(block, ensure_ascii=False))
                return "\n".join(part for part in parts if part)
            if isinstance(content, dict):
                return json.dumps(content, ensure_ascii=False, indent=2)
            return str(content)
        if isinstance(result, (dict, list, tuple)):
            return json.dumps(result, ensure_ascii=False, indent=2)
        if result is None:
            return ""
        return str(result)

    # ------------------------------------------------------------------
    # Log entry builders
    # ------------------------------------------------------------------

    async def _build_llm_entry(self, runtime: Any, ai_message: AIMessage) -> str:
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
            parts.append(f"> {text}")

        # Tool calls
        tool_calls = getattr(ai_message, "tool_calls", None)
        if tool_calls:
            names = [tc.get("name", "?") for tc in tool_calls]
            parts.append(f"Tool calls: {', '.join(names)}")

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

    async def _build_tool_entry(self, runtime: Any, name: str, args: dict, result_text: str) -> str:
        ts = self._timestamp()
        args_str = self._format_args(name, args)
        result_snippet = result_text
        payload_path: str | None = None
        if len(result_text) > _MAX_INLINE_PAYLOAD_CHARS:
            payload_path = await self._write_payload(
                runtime,
                kind="tool",
                label=name,
                content=result_text,
                extension="txt",
            )
            result_snippet = self._truncate(result_text, _MAX_RESULT_SNIPPET)

        entry = f"\n## [{ts}] Tool: {name}\nArgs: {args_str}\nResult: {result_snippet}"
        if payload_path:
            entry += f"\nFull payload: {payload_path}"
        return entry

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
        llm = await LLMClient.get_model(
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
        entry = await self._build_llm_entry(request.runtime, ai_message)
        if entry:
            self._append_entry(entry)

        # Check for final response (no tool_calls) — persist + inject log path
        tool_calls = getattr(ai_message, "tool_calls", None)
        if not tool_calls:
            # Write log to backend exactly once
            await self._persist_log(request.runtime)

            # Inject log path into AI response
            log_ref = (
                f"\n\n[Activity log saved to: {self._log_path}] For more details, check this file."
            )
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
        result_text = self._serialize_tool_result(result)
        entry = await self._build_tool_entry(request.runtime, tool_name, tool_args, result_text)
        self._append_entry(entry)

        # Compress in memory if needed (no file write)
        await self._check_and_compress(request.runtime)

        return result
