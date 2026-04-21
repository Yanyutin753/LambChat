"""Generic tool start/end event handling."""

from __future__ import annotations

import json
import uuid
from typing import Any

from src.infra.agent.events.binary_uploads import upload_binary_blocks
from src.infra.agent.events.tool_outputs import (
    detect_tool_error,
    extract_tool_output,
    normalize_content,
)
from src.infra.agent.events.types import StreamEvent


class ToolEventMixin:
    _presenter_emit: Any
    presenter: Any
    _base_url: str

    async def _handle_tool_start(
        self,
        event: StreamEvent,
        tool_name: str,
        current_agent_id: str | None,
        current_depth: int,
    ) -> None:
        inp: dict[str, Any] = event.get("data", {}).get("input", {})
        tool_call_id = event.get("run_id") or f"tool_{uuid.uuid4().hex}"

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
        tool_call_id = event.get("run_id") or f"tool_{uuid.uuid4().hex}"

        raw = extract_tool_output(out)
        is_error, error_message = detect_tool_error(out, raw)

        result: Any = raw
        if isinstance(raw, str) and raw and raw[0] in ("{", "["):
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, dict):
                    result = parsed
                elif isinstance(parsed, list):
                    normalized = normalize_content(parsed)
                    result = normalized if isinstance(normalized, dict) else str(normalized)
            except (json.JSONDecodeError, TypeError):
                pass

        if isinstance(result, dict) and "blocks" in result:
            await upload_binary_blocks(result, self._base_url)

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
