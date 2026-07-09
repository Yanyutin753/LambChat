"""Subagent activity logging middleware."""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware.types import (
    AgentMiddleware,
    ContextT,
    ModelRequest,
    ModelResponse,
    ResponseT,
)
from langchain_core.messages import AIMessage, ToolMessage

from src.infra.agent.middleware.main_agent_context import (
    CompressibleMarkdownLog,
    format_messages_as_markdown,
    write_subagent_handoff_file,
)
from src.infra.async_utils import run_blocking_io

logger = logging.getLogger(__name__)

_CHARS_PER_TOKEN = 4
_DEFAULT_ACTIVITY_TOKEN_LIMIT = 50000
_DEFAULT_KEEP_RECENT = 6
_DEFAULT_MAX_LOG_CHARS = _DEFAULT_ACTIVITY_TOKEN_LIMIT * _CHARS_PER_TOKEN
_ACTIVITY_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S %z"
_MAX_RESULT_SNIPPET = 1000
_MAX_INLINE_PAYLOAD_CHARS = 2500


class SubagentActivityMiddleware(AgentMiddleware):
    """Record a subagent's model/tool activity to a backend-readable file."""

    def __init__(
        self,
        *,
        backend: Any,
        token_limit: int = _DEFAULT_ACTIVITY_TOKEN_LIMIT,
        keep_recent: int = _DEFAULT_KEEP_RECENT,
        max_log_chars: int = _DEFAULT_MAX_LOG_CHARS,
        run_id_factory: Callable[[], str] | None = None,
    ) -> None:
        super().__init__()
        self._backend = backend
        self._run_id = (run_id_factory or (lambda: uuid.uuid4().hex[:8]))()
        self._payload_counter = 0
        self._written_path: str | None = None
        self._log = CompressibleMarkdownLog(
            token_limit=token_limit,
            keep_recent=keep_recent,
            max_log_chars=max(int(max_log_chars), 1),
            compressed_heading="Summary of Earlier Activity",
            truncated_label="activity entries",
        )
        self._transcript_content: str | None = None

    def _get_backend(self, runtime: Any) -> Any:
        if callable(self._backend):
            return self._backend(runtime)
        return self._backend

    @staticmethod
    def _timestamp() -> str:
        return time.strftime(_ACTIVITY_TIMESTAMP_FORMAT)

    @staticmethod
    def _truncate(text: str, limit: int) -> str:
        if len(text) <= limit:
            return text
        half = max(limit // 2 - 3, 1)
        return text[:half] + "\n...\n" + text[-half:]

    @staticmethod
    async def _json_dumps(value: Any, *, indent: int | None = None) -> str:
        return await run_blocking_io(json.dumps, value, ensure_ascii=False, indent=indent)

    @classmethod
    async def _content_to_text(cls, content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, str):
                    parts.append(block)
                elif isinstance(block, dict) and block.get("type") == "text":
                    parts.append(str(block.get("text", "")))
                else:
                    parts.append(await cls._json_dumps(block, indent=2))
            return "\n".join(part for part in parts if part)
        if isinstance(content, (dict, tuple)):
            return await cls._json_dumps(content, indent=2)
        if content is None:
            return ""
        return str(content)

    async def _serialize_tool_result(self, result: Any) -> str:
        if isinstance(result, ToolMessage):
            return await self._content_to_text(result.content)
        if isinstance(result, (dict, list, tuple)):
            return await self._json_dumps(result, indent=2)
        if result is None:
            return ""
        return str(result)

    def _format_args(self, args: dict[str, Any]) -> str:
        if not args:
            return ""
        compact: dict[str, Any] = {}
        for key, value in args.items():
            if (
                key in {"content", "old_string", "new_string"}
                and isinstance(value, str)
                and len(value) > 240
            ):
                compact[key] = f"<{len(value)} chars>"
                compact[f"{key}_snippet"] = self._truncate(value, 240)
            else:
                compact[key] = value
        return ", ".join(f"{key}={value!r}" for key, value in compact.items())

    def _next_payload_filename(self, kind: str, label: str, extension: str = "txt") -> str:
        self._payload_counter += 1
        safe_label = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_") or kind
        return (
            f"payloads/{self._run_id}/{self._payload_counter:04d}_{kind}_{safe_label}.{extension}"
        )

    async def _write_payload(
        self,
        runtime: Any,
        *,
        kind: str,
        label: str,
        content: str,
    ) -> str | None:
        backend = self._get_backend(runtime)
        return await write_subagent_handoff_file(
            backend,
            dirname="subagent_activity",
            filename=self._next_payload_filename(kind, label),
            content=content,
            log_context="SubagentActivity",
        )

    def _append(self, entry: str) -> None:
        if entry:
            self._log.append(entry)

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

    @staticmethod
    def _messages_have_process_activity(messages: list[Any]) -> bool:
        for message in messages:
            if isinstance(message, ToolMessage):
                return True
            if isinstance(message, AIMessage) and getattr(message, "tool_calls", None):
                return True
        return False

    async def _capture_transcript_from_request(self, request: Any) -> None:
        messages = self._messages_from_request(request)
        if not messages or not self._messages_have_process_activity(messages):
            return
        content = await format_messages_as_markdown(messages)
        if content.strip():
            self._transcript_content = content

    async def _build_tool_entry(
        self,
        runtime: Any,
        name: str,
        args: dict[str, Any],
        result_text: str,
    ) -> str:
        result_snippet = result_text
        payload_path: str | None = None
        if len(result_text) > _MAX_INLINE_PAYLOAD_CHARS:
            payload_path = await self._write_payload(
                runtime,
                kind="tool",
                label=name,
                content=result_text,
            )
            result_snippet = self._truncate(result_text, _MAX_RESULT_SNIPPET)

        entry = (
            f"\n## [{self._timestamp()}] Tool: {name}\n"
            f"Args: {self._format_args(args)}\n"
            f"Result: {result_snippet}"
        )
        if payload_path:
            entry += f"\nFull payload: {payload_path}"
        return entry

    async def _build_model_entry(self, message: AIMessage) -> str:
        text = (await self._content_to_text(message.content)).strip()
        parts = [f"\n## [{self._timestamp()}] LLM"]
        if text:
            parts.append(f"> {self._truncate(text, 1200)}")
        tool_calls = getattr(message, "tool_calls", None)
        if tool_calls:
            names = [
                call.get("name", "?") if isinstance(call, dict) else str(call)
                for call in tool_calls
            ]
            parts.append(f"Tool calls: {', '.join(names)}")
        return "\n".join(parts) if len(parts) > 1 else ""

    async def _compress_with_llm(self, text: str) -> str:
        from langchain_core.messages import HumanMessage

        from src.infra.llm.client import LLMClient

        llm = await LLMClient.get_model(temperature=0.3)
        prompt = (
            "Compress the following subagent activity log into concise markdown bullets.\n"
            "Keep key findings, file paths, tool outcomes, decisions, and important values.\n\n"
            f"{text}"
        )
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        return response.content if isinstance(response.content, str) else str(response.content)

    async def _check_and_compress(self) -> None:
        try:
            await self._log.check_and_compress(self._compress_with_llm)
        except Exception:
            logger.warning("[SubagentActivity] Compression failed, keeping trimmed raw activity")

    async def _persist_log(self, runtime: Any) -> str | None:
        if self._written_path:
            return self._written_path
        content = self._transcript_content
        if not content and self._log.entries:
            content = self._log.render(f"# Subagent Activity Log (run: {self._run_id})\n")
        if not content:
            return None

        backend = self._get_backend(runtime)
        self._written_path = await write_subagent_handoff_file(
            backend,
            dirname="subagent_activity",
            filename=f"activity_{self._run_id}.md",
            content=content
            if content.startswith("#")
            else f"# Subagent Activity Log (run: {self._run_id})\n{content}",
            log_context="SubagentActivity",
        )
        return self._written_path

    @staticmethod
    def _copy_ai_message_with_content(message: AIMessage, content: str | list[Any]) -> AIMessage:
        return AIMessage(
            content=content,
            tool_calls=message.tool_calls,
            id=message.id,
            additional_kwargs=message.additional_kwargs,
            response_metadata=message.response_metadata,
        )

    @staticmethod
    def _append_reference(message: AIMessage, path: str) -> AIMessage:
        reference = f"\n\n[Activity log saved to: {path}]"
        if isinstance(message.content, list):
            content: str | list[Any] = [*message.content, {"type": "text", "text": reference}]
        else:
            content = f"{message.content or ''}{reference}"
        return SubagentActivityMiddleware._copy_ai_message_with_content(message, content)

    async def awrap_tool_call(
        self,
        request: Any,
        handler: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        result = await handler(request)
        tool_call = getattr(request, "tool_call", {}) or {}
        tool_args = tool_call.get("args", {}) or {}
        result_text = await self._serialize_tool_result(result)
        self._append(
            await self._build_tool_entry(
                getattr(request, "runtime", None),
                str(tool_call.get("name", "")),
                dict(tool_args) if isinstance(tool_args, dict) else {},
                result_text,
            )
        )
        await self._check_and_compress()
        return result

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT]:
        response = await handler(request)

        messages: list[Any] = []
        if isinstance(response, AIMessage):
            messages = [response]
        elif hasattr(response, "result"):
            messages = getattr(response, "result") or []

        if not messages or not isinstance(messages[0], AIMessage):
            return response

        ai_message = messages[0]

        if getattr(ai_message, "tool_calls", None):
            self._append(await self._build_model_entry(ai_message))
            await self._check_and_compress()
            return response

        await self._capture_transcript_from_request(request)
        path = await self._persist_log(getattr(request, "runtime", None))
        if not path:
            return response

        new_ai = self._append_reference(ai_message, path)
        if hasattr(response, "result"):
            return type(response)(result=[new_ai])
        return new_ai  # type: ignore[return-value]
