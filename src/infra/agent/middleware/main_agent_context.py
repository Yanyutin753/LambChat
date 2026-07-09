"""Main-agent context handoff middleware for subagents."""

from __future__ import annotations

import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware

from src.infra.async_utils import run_blocking_io

logger = logging.getLogger(__name__)

_CHARS_PER_TOKEN = 4
_DEFAULT_CONTEXT_TOKEN_LIMIT = 20000
_DEFAULT_KEEP_RECENT = 8
_DEFAULT_MAX_LOG_CHARS = _DEFAULT_CONTEXT_TOKEN_LIMIT * _CHARS_PER_TOKEN
_CONTEXT_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S %z"
_REDACTED = "[REDACTED]"
_SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|token|password|secret)"
    r"(\s*[:=]\s*)([^\s,;]+)"
)
_SENSITIVE_JSON_RE = re.compile(
    r'(?i)("(?:api[_-]?key|access[_-]?token|refresh[_-]?token|token|password|secret)"\s*:\s*")([^"]+)(")'
)
_AUTHORIZATION_BEARER_RE = re.compile(r"(?i)(authorization\s*:\s*bearer\s+)([^\s,;]+)")


def subagent_handoff_dir_for_backend(backend: Any, dirname: str) -> str:
    """Resolve a subagent handoff directory using the same backend workspace rules."""
    for candidate in (backend, getattr(backend, "default", None)):
        work_dir = getattr(candidate, "work_dir", None)
        if isinstance(work_dir, str) and work_dir.strip():
            return f"{work_dir.rstrip('/')}/{dirname.strip('/')}"
    return f"/{dirname.strip('/')}"


async def write_subagent_handoff_file(
    backend: Any,
    *,
    dirname: str,
    filename: str,
    content: str,
    log_context: str,
) -> str | None:
    """Write a subagent handoff file and return the backend-visible path."""
    path = f"{subagent_handoff_dir_for_backend(backend, dirname)}/{filename.strip('/')}"
    try:
        write_result = await backend.awrite(path, content)
        if getattr(write_result, "error", None):
            logger.warning("[%s] Write failed: %s", log_context, write_result.error)
            return None
        return str(getattr(write_result, "path", None) or path)
    except Exception:
        logger.warning("[%s] Backend write failed", log_context, exc_info=True)
        return None


class CompressibleMarkdownLog:
    """Small reusable markdown log with one-shot older-entry compression."""

    def __init__(
        self,
        *,
        token_limit: int,
        keep_recent: int,
        max_log_chars: int,
        compressed_heading: str,
        truncated_label: str = "entries",
    ) -> None:
        self._token_limit = token_limit
        self._keep_recent = keep_recent
        self._max_log_chars = max(int(max_log_chars), 1)
        self._compressed_heading = compressed_heading
        self._truncated_label = truncated_label
        self._entries: list[str] = []
        self._total_chars = 0
        self._compressed = False

    @property
    def entries(self) -> list[str]:
        return self._entries

    @property
    def total_chars(self) -> int:
        return self._total_chars

    @property
    def compressed(self) -> bool:
        return self._compressed

    def append(self, entry: str) -> None:
        if not entry:
            return
        self._entries.append(entry)
        self._total_chars += len(entry)
        self._trim_to_memory_cap()

    def _trim_to_memory_cap(self) -> None:
        if self._total_chars <= self._max_log_chars:
            return

        omitted_count = 0
        marker = f"\n## [TRUNCATED] Earlier {self._truncated_label} omitted to cap memory."

        while self._entries and self._total_chars + len(marker) > self._max_log_chars:
            removed = self._entries.pop(0)
            self._total_chars -= len(removed)
            omitted_count += 1

        if omitted_count <= 0:
            return

        marker = (
            f"\n## [TRUNCATED] {omitted_count} older {self._truncated_label} omitted to cap memory."
        )
        if self._entries and self._entries[0].startswith("\n## [TRUNCATED]"):
            self._total_chars -= len(self._entries[0])
            self._entries[0] = marker
            self._total_chars += len(marker)
        else:
            self._entries.insert(0, marker)
            self._total_chars += len(marker)

        while self._entries and self._total_chars > self._max_log_chars:
            removed = self._entries.pop(0)
            self._total_chars -= len(removed)

    async def check_and_compress(
        self,
        compressor: Callable[[str], Awaitable[str]],
    ) -> None:
        if self._compressed:
            return

        estimated_tokens = self._total_chars // _CHARS_PER_TOKEN
        if estimated_tokens <= self._token_limit:
            return
        if len(self._entries) <= self._keep_recent:
            return

        split_idx = len(self._entries) - self._keep_recent
        old_entries = self._entries[:split_idx]
        recent_entries = self._entries[split_idx:]
        old_text = "\n".join(old_entries)

        summary = await compressor(old_text)
        compressed_summary = f"\n## [COMPRESSED] {self._compressed_heading}\n{summary.strip()}"
        self._entries = [compressed_summary, *recent_entries]
        self._total_chars = sum(len(entry) for entry in self._entries)
        self._compressed = True

    def render(self, header: str) -> str:
        return header + "\n".join(self._entries) + "\n"


def redact_sensitive_text(text: str) -> str:
    """Best-effort redaction for common inline secret formats."""
    text = _AUTHORIZATION_BEARER_RE.sub(rf"\1{_REDACTED}", text)
    text = _SENSITIVE_JSON_RE.sub(rf"\1{_REDACTED}\3", text)
    return _SENSITIVE_ASSIGNMENT_RE.sub(rf"\1\2{_REDACTED}", text)


def _message_role(message: Any) -> str:
    explicit_type = getattr(message, "type", None)
    if isinstance(explicit_type, str) and explicit_type:
        return explicit_type
    name = type(message).__name__.removesuffix("Message")
    return name.lower() or "message"


async def _json_dumps_for_context(value: Any) -> str:
    import json

    return await run_blocking_io(json.dumps, value, ensure_ascii=False, indent=2)


async def _message_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return redact_sensitive_text(content)
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                block_type = block.get("type")
                if block_type == "text":
                    parts.append(str(block.get("text", "")))
                elif block_type:
                    parts.append(f"[{block_type} block]")
                else:
                    parts.append(await _json_dumps_for_context(block))
            else:
                parts.append(str(block))
        return redact_sensitive_text("\n".join(part for part in parts if part))
    if isinstance(content, (dict, tuple)):
        return redact_sensitive_text(await _json_dumps_for_context(content))
    if content is None:
        return ""
    return redact_sensitive_text(str(content))


async def format_messages_as_markdown(messages: list[Any]) -> str:
    entries: list[str] = []
    for index, message in enumerate(messages, start=1):
        role = _message_role(message)
        content = await _message_content_to_text(getattr(message, "content", ""))
        if not content and hasattr(message, "text"):
            text_attr = getattr(message, "text")
            content = text_attr() if callable(text_attr) else str(text_attr or "")

        entry_parts = [f"\n## {index}. {role}"]
        if content:
            entry_parts.append(content.strip())

        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls:
            names = [
                call.get("name", "?") if isinstance(call, dict) else str(call)
                for call in tool_calls
            ]
            entry_parts.append(f"Tool calls: {', '.join(names)}")

        entries.append("\n".join(entry_parts))

    return "\n".join(entries)


class MainAgentContextMiddleware(AgentMiddleware):
    """Writes parent message context before launching a subagent task."""

    def __init__(
        self,
        *,
        backend: Any,
        token_limit: int = _DEFAULT_CONTEXT_TOKEN_LIMIT,
        keep_recent: int = _DEFAULT_KEEP_RECENT,
        max_log_chars: int = _DEFAULT_MAX_LOG_CHARS,
        run_id_factory: Callable[[], str] | None = None,
    ) -> None:
        super().__init__()
        self._backend = backend
        self._token_limit = token_limit
        self._keep_recent = keep_recent
        self._max_log_chars = max_log_chars
        self._run_id_factory = run_id_factory or (lambda: uuid.uuid4().hex[:8])
        self._snapshot_cache: dict[tuple[Any, ...], str] = {}

    def _get_backend(self, runtime: Any) -> Any:
        if callable(self._backend):
            return self._backend(runtime)
        return self._backend

    @staticmethod
    def _cache_key(request: Any, messages: list[Any]) -> tuple[Any, ...]:
        runtime = getattr(request, "runtime", None)
        message_ids = tuple(getattr(message, "id", None) or id(message) for message in messages)
        return (id(runtime), id(messages), len(messages), message_ids)

    @staticmethod
    def _messages_from_request(request: Any) -> list[Any]:
        state = getattr(request, "state", None)
        if isinstance(state, dict) and isinstance(state.get("messages"), list):
            return state["messages"]

        runtime = getattr(request, "runtime", None)
        runtime_state = getattr(runtime, "state", None)
        if isinstance(runtime_state, dict) and isinstance(runtime_state.get("messages"), list):
            return runtime_state["messages"]
        return []

    async def _compress_with_llm(self, text: str) -> str:
        from langchain_core.messages import HumanMessage

        from src.infra.llm.client import LLMClient

        llm = await LLMClient.get_model(temperature=0.3)
        prompt = (
            "Compress the following main-agent conversation context for a subagent.\n"
            "Keep: user requests, main-agent decisions, constraints, file paths, tool outcomes, "
            "open questions, and the latest plan.\n"
            "Drop: duplicate wording, incidental chatter, and verbose reasoning.\n"
            "Format as concise markdown bullets.\n\n"
            f"{text}"
        )
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        return response.content if isinstance(response.content, str) else str(response.content)

    async def _write_context_file(self, request: Any) -> str | None:
        messages = self._messages_from_request(request)
        if not messages:
            return None

        cache_key = self._cache_key(request, messages)
        cached = self._snapshot_cache.get(cache_key)
        if cached:
            return cached

        log = CompressibleMarkdownLog(
            token_limit=self._token_limit,
            keep_recent=self._keep_recent,
            max_log_chars=self._max_log_chars,
            compressed_heading="Earlier Main-Agent Context",
        )
        rendered_messages = await format_messages_as_markdown(messages)
        for entry in rendered_messages.split("\n## "):
            if not entry.strip():
                continue
            log.append(entry if entry.startswith("\n## ") else "\n## " + entry)
        try:
            await log.check_and_compress(self._compress_with_llm)
        except Exception:
            logger.warning("[MainAgentContext] Compression failed, keeping trimmed raw context")

        run_id = self._run_id_factory()
        backend = self._get_backend(getattr(request, "runtime", None))
        header = (
            f"# Main Agent Conversation Context (snapshot: {run_id})\n"
            f"Captured at: {time.strftime(_CONTEXT_TIMESTAMP_FORMAT)}\n\n"
        )
        content = log.render(header)

        context_path = await write_subagent_handoff_file(
            backend,
            dirname="subagent_context",
            filename=f"main_agent_messages_{run_id}.md",
            content=content,
            log_context="MainAgentContext",
        )
        if not context_path:
            return None
        self._snapshot_cache[cache_key] = context_path
        return context_path

    @staticmethod
    def _description_with_context(description: str, context_path: str) -> str:
        if context_path in description:
            return description
        return (
            f"{description.rstrip()}\n\n"
            "## Main-Agent Context Snapshot\n"
            f"Read it when the assignment depends on prior user/main-agent context: {context_path}\n"
            "Treat this file as context only; the explicit task above remains your objective."
        )

    async def awrap_tool_call(
        self,
        request: Any,
        handler: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        tool_call = getattr(request, "tool_call", {}) or {}
        if tool_call.get("name") != "task":
            return await handler(request)

        args = dict(tool_call.get("args") or {})
        description = args.get("description")
        if not isinstance(description, str) or not description.strip():
            return await handler(request)

        context_path = await self._write_context_file(request)
        if not context_path:
            return await handler(request)

        args["description"] = self._description_with_context(description, context_path)
        updated_tool_call = {**tool_call, "args": args}
        if hasattr(request, "override"):
            request = request.override(tool_call=updated_tool_call)
        else:
            request.tool_call = updated_tool_call

        return await handler(request)
