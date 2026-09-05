"""Generic tool start/end event handling."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

import orjson
from langgraph.errors import GraphInterrupt

from src.infra.agent.events.binary_uploads import upload_binary_blocks
from src.infra.agent.events.tool_outputs import (
    detect_tool_error,
    extract_tool_output,
    normalize_content,
)
from src.infra.agent.events.types import StreamEvent
from src.infra.async_utils import run_blocking_io

_TOOL_RESULT_DISPLAY_MAX_CHARS = 100_000
_TOOL_RESULT_JSON_PARSE_MAX_CHARS = _TOOL_RESULT_DISPLAY_MAX_CHARS


def _clip_tool_result_text(text: str) -> str:
    if len(text) <= _TOOL_RESULT_DISPLAY_MAX_CHARS:
        return text
    return (
        text[:_TOOL_RESULT_DISPLAY_MAX_CHARS].rstrip()
        + f"\n\n[truncated from {len(text)} chars for display]"
    )


def _stable_tool_call_id(event: StreamEvent) -> str | None:
    """interrupt/resume 稳定的工具调用键：checkpoint_ns + 工具名 + 参数摘要。

    langgraph 的 on_tool_start/end 每次执行尝试都换 run_id——确认门
    （ask_human / 沙箱确认）挂起后图以**同任务**重放，checkpoint_ns 不变
    而 run_id 变化，同一逻辑执行会渲染成两张卡（一张永远等不到 result）。
    ns 是任务级命名空间，并行多工具共享同一任务 ns，故再拼工具名与参数
    摘要保证唯一。None = 事件未携带 ns（旧包装器/异常路径），调用方回退
    run_id 现状。
    """
    metadata = event.get("metadata") or {}
    ns = metadata.get("langgraph_checkpoint_ns") or metadata.get("checkpoint_ns")
    if not ns:
        return None
    args = (event.get("data") or {}).get("input")
    digest = hashlib.md5()  # 稳定键用途，非安全哈希
    digest.update(str(event.get("name") or "").encode())
    digest.update(b"\x00")
    if isinstance(args, dict):
        digest.update(json.dumps(args, sort_keys=True, ensure_ascii=False, default=str).encode())
    return f"{ns}|{digest.hexdigest()[:12]}"


def _parse_tool_result_json(raw: str) -> Any | None:
    try:
        parsed = orjson.loads(raw)
    except orjson.JSONDecodeError:
        try:
            parsed = json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return None
    except TypeError:
        return None

    if isinstance(parsed, dict):
        return parsed
    if isinstance(parsed, list):
        normalized = normalize_content(parsed)
        return normalized if isinstance(normalized, dict) else str(normalized)
    return None


class ToolEventMixin:
    _presenter_emit: Any
    _before_tool_start: Any
    presenter: Any
    _base_url: str
    _started_tool_call_ids: set[str]

    def _get_tool_call_id(self, event: StreamEvent) -> str:
        stable = _stable_tool_call_id(event)
        if stable:
            return stable
        return event.get("run_id") or f"tool_{uuid.uuid4().hex}"

    def _format_tool_error(self, tool_name: str, error: Any) -> str:
        if error is None:
            return f"[MCP Tool Error] {tool_name} failed: Unknown error"

        if isinstance(error, BaseException):
            error_type = type(error).__name__
            error_message = str(error) if str(error) else repr(error)
            return f"[MCP Tool Error] {tool_name} failed: [{error_type}] {error_message}"

        if isinstance(error, dict):
            error_type = error.get("type") or error.get("name") or "ToolError"
            error_message = error.get("message") or error.get("error") or str(error)
            return f"[MCP Tool Error] {tool_name} failed: [{error_type}] {error_message}"

        error_message = str(error) if str(error) else repr(error)
        if error_message.startswith("[MCP Tool Error]"):
            return error_message
        return f"[MCP Tool Error] {tool_name} failed: {error_message}"

    async def _handle_tool_start(
        self,
        event: StreamEvent,
        tool_name: str,
        current_agent_id: str | None,
        current_depth: int,
    ) -> None:
        inp: dict[str, Any] = event.get("data", {}).get("input", {})
        tool_call_id = self._get_tool_call_id(event)

        if tool_name == "write_todos":
            if isinstance(inp, dict):
                todos = inp.get("todos", [])
                if isinstance(todos, list) and todos:
                    await self._presenter_emit(
                        self.presenter.present_todo(
                            todos,
                            depth=current_depth,
                            agent_id=current_agent_id,
                        )
                    )
            return

        # For ask_human with allow_other, inject the _other textarea field
        # into the args so the frontend can render it in the tool call item.
        if tool_name == "ask_human" and inp.get("allow_other"):
            inp = {
                **inp,
                "fields": [
                    *(inp.get("fields") or []),
                    {
                        "name": "_other",
                        "label": "其他意见",
                        "type": "textarea",
                        "placeholder": "除上述选项外，您还有其他想法或建议吗？",
                        "required": False,
                    },
                ],
            }

        if self._before_tool_start is not None:
            await self._before_tool_start(tool_name, inp)

        self._started_tool_call_ids.add(tool_call_id)
        await self._presenter_emit(
            self.presenter.present_tool_start(
                tool_name,
                inp,
                tool_call_id=tool_call_id,
                depth=current_depth,
                agent_id=current_agent_id,
            )
        )

    async def _handle_tool_end(
        self,
        event: StreamEvent,
        tool_name: str,
        current_agent_id: str | None,
        current_depth: int,
    ) -> None:
        if tool_name == "write_todos":
            return

        data = event.get("data", {})
        out = data.get("output", "")
        tool_call_id = self._get_tool_call_id(event)

        raw = await run_blocking_io(extract_tool_output, out)
        is_error, error_message = await run_blocking_io(detect_tool_error, out, raw)

        result: Any = raw
        if (
            isinstance(raw, str)
            and raw
            and raw[0] in ("{", "[")
            and len(raw) <= _TOOL_RESULT_JSON_PARSE_MAX_CHARS
        ):
            parsed_result = await run_blocking_io(_parse_tool_result_json, raw)
            if parsed_result is not None:
                result = parsed_result

        if isinstance(result, dict) and "blocks" in result:
            await upload_binary_blocks(result, self._base_url)

        if isinstance(result, str):
            result = _clip_tool_result_text(result)

        await self._presenter_emit(
            self.presenter.present_tool_result(
                tool_name,
                result if isinstance(result, dict) else str(result),
                tool_call_id=tool_call_id,
                success=not is_error,
                error=error_message,
                depth=current_depth,
                agent_id=current_agent_id,
            )
        )
        self._started_tool_call_ids.discard(tool_call_id)

    async def _handle_tool_error(
        self,
        event: StreamEvent,
        tool_name: str,
        current_agent_id: str | None,
        current_depth: int,
    ) -> None:
        data = event.get("data", {})
        if isinstance(data.get("error"), GraphInterrupt):
            return

        inp: dict[str, Any] = data.get("input", {})
        tool_call_id = self._get_tool_call_id(event)

        if tool_call_id not in self._started_tool_call_ids:
            await self._presenter_emit(
                self.presenter.present_tool_start(
                    tool_name,
                    inp,
                    tool_call_id=tool_call_id,
                    depth=current_depth,
                    agent_id=current_agent_id,
                )
            )

        error_message = self._format_tool_error(tool_name, data.get("error"))
        await self._presenter_emit(
            self.presenter.present_tool_result(
                tool_name,
                error_message,
                tool_call_id=tool_call_id,
                success=False,
                error=error_message,
                depth=current_depth,
                agent_id=current_agent_id,
            )
        )
        self._started_tool_call_ids.discard(tool_call_id)
