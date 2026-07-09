"""Subagent result handoff middleware."""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.messages import ToolMessage
from langgraph.types import Command

from src.infra.agent.middleware.main_agent_context import write_subagent_handoff_file
from src.infra.async_utils import run_blocking_io

logger = logging.getLogger(__name__)

_REPORT_TIMESTAMP_FORMAT = "%Y-%m-%d %H:%M:%S %z"
_ACTIVITY_LOG_RE = re.compile(r"Activity log saved to:\s*([^\]\s]+)")


class SubagentResultHandoffMiddleware(AgentMiddleware):
    """Move completed subagent final reports into a handoff file for the main agent."""

    def __init__(
        self,
        *,
        backend: Any,
        run_id_factory: Callable[[], str] | None = None,
    ) -> None:
        super().__init__()
        self._backend = backend
        self._run_id_factory = run_id_factory or (lambda: uuid.uuid4().hex[:8])

    def _get_backend(self, runtime: Any) -> Any:
        if callable(self._backend):
            return self._backend(runtime)
        return self._backend

    @staticmethod
    async def _content_to_text(content: Any) -> str:
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
                    parts.append(
                        await run_blocking_io(json.dumps, block, ensure_ascii=False, indent=2)
                    )
            return "\n".join(part for part in parts if part)
        if isinstance(content, (dict, tuple)):
            return await run_blocking_io(json.dumps, content, ensure_ascii=False, indent=2)
        if content is None:
            return ""
        return str(content)

    @staticmethod
    def _copy_tool_message_with_content(message: ToolMessage, content: str) -> ToolMessage:
        additional_kwargs = dict(message.additional_kwargs)
        additional_kwargs.setdefault("lambchat_original_content", message.content)
        return ToolMessage(
            content=content,
            tool_call_id=message.tool_call_id,
            name=message.name,
            id=message.id,
            artifact=message.artifact,
            status=message.status,
            additional_kwargs=additional_kwargs,
            response_metadata=message.response_metadata,
        )

    @staticmethod
    def _extract_command_tool_message(command: Command) -> ToolMessage | None:
        update = command.update
        if not isinstance(update, dict):
            return None
        messages = update.get("messages")
        if not isinstance(messages, list) or not messages:
            return None
        message = messages[0]
        return message if isinstance(message, ToolMessage) else None

    @staticmethod
    def _replace_command_tool_message(command: Command, message: ToolMessage) -> Command:
        update = command.update
        if not isinstance(update, dict):
            return command
        return Command(
            graph=command.graph,
            update={**update, "messages": [message]},
            resume=command.resume,
            goto=command.goto,
        )

    @staticmethod
    def _handoff_reference(path: str, report_text: str = "") -> str:
        reference = (
            f"Subagent report saved to: {path}\n"
            "Read this file before synthesizing or relying on the subagent result."
        )
        activity_paths = _ACTIVITY_LOG_RE.findall(report_text)
        if activity_paths:
            unique_paths = list(dict.fromkeys(activity_paths))
            reference += "\nActivity log saved to: " + ", ".join(unique_paths)
        return reference

    async def _write_report(self, request: Any, message: ToolMessage) -> str | None:
        args = getattr(request, "tool_call", {}).get("args", {}) or {}
        subagent_type = args.get("subagent_type", "unknown")
        description = args.get("description", "")
        report_text = (await self._content_to_text(message.content)).strip()
        if not report_text:
            return None

        run_id = self._run_id_factory()
        content = (
            f"# Subagent Report (run: {run_id})\n"
            f"Captured at: {time.strftime(_REPORT_TIMESTAMP_FORMAT)}\n\n"
            f"Subagent type: {subagent_type}\n\n"
            "## Assignment\n"
            f"{description}\n\n"
            "## Final Report\n"
            f"{report_text}\n"
        )
        backend = self._get_backend(getattr(request, "runtime", None))
        return await write_subagent_handoff_file(
            backend,
            dirname="subagent_reports",
            filename=f"subagent_report_{run_id}.md",
            content=content,
            log_context="SubagentResultHandoff",
        )

    async def awrap_tool_call(
        self,
        request: Any,
        handler: Callable[[Any], Awaitable[Any]],
    ) -> Any:
        result = await handler(request)
        tool_call = getattr(request, "tool_call", {}) or {}
        if tool_call.get("name") != "task":
            return result

        if isinstance(result, Command):
            message = self._extract_command_tool_message(result)
            if message is None:
                return result
            path = await self._write_report(request, message)
            if not path:
                return result
            return self._replace_command_tool_message(
                result,
                self._copy_tool_message_with_content(
                    message,
                    self._handoff_reference(path, await self._content_to_text(message.content)),
                ),
            )

        if isinstance(result, ToolMessage):
            path = await self._write_report(request, result)
            if not path:
                return result
            return self._copy_tool_message_with_content(
                result,
                self._handoff_reference(path, await self._content_to_text(result.content)),
            )

        return result
