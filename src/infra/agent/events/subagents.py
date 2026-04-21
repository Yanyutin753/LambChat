"""Subagent task event handling for AgentEventProcessor."""

from __future__ import annotations

import uuid
from typing import Any

from src.infra.agent.events.tool_outputs import get_tool_status
from src.infra.agent.events.types import StreamEvent
from src.infra.logging import get_logger

logger = get_logger(__name__)


class SubagentEventMixin:
    checkpoint_to_agent: dict[str, tuple[str, str]]
    _presenter_emit: Any
    presenter: Any

    def _get_checkpoint_ns(self, metadata: dict[str, Any]) -> str:
        return metadata.get("langgraph_checkpoint_ns") or metadata.get("checkpoint_ns", "")

    def _get_lc_source(self, metadata: dict[str, Any]) -> str | None:
        return metadata.get("lc_source") or metadata.get("source")

    def _get_agent_context(self, checkpoint_ns: str) -> tuple[str | None, int]:
        if not checkpoint_ns or "|" not in checkpoint_ns:
            return None, 0

        first_segment, _, _ = checkpoint_ns.partition("|")
        agent_info = self.checkpoint_to_agent.get(first_segment)
        if agent_info:
            logger.debug(
                "Found subagent: segment=%s, agent_id=%s",
                first_segment[:30],
                agent_info[0],
            )
            return agent_info[0], 1

        logger.debug(
            "Subagent not found: segment=%s, known=%s",
            first_segment[:30],
            list(self.checkpoint_to_agent.keys())[:3],
        )
        return None, 1

    async def _handle_task_start(self, event: StreamEvent) -> None:
        data = event.get("data", {})
        inp: dict[str, Any] = data.get("input", {})

        subagent_type = inp.get("subagent_type", "unknown") if isinstance(inp, dict) else "unknown"
        description = inp.get("description", "")[:500] if isinstance(inp, dict) else ""
        run_id = event.get("run_id", uuid.uuid4().hex)

        metadata = event.get("metadata", {})
        checkpoint_ns = metadata.get("checkpoint_ns", "")
        checkpoint_uuid = checkpoint_ns.rpartition(":")[2] if checkpoint_ns else run_id
        instance_id = f"{subagent_type}_{checkpoint_uuid}"

        if "|" in checkpoint_ns:
            first_seg, _, _ = checkpoint_ns.partition("|")
            current_depth = (
                2 if first_seg in self.checkpoint_to_agent else checkpoint_ns.count("|") + 1
            )
        else:
            current_depth = 1

        if checkpoint_ns in self.checkpoint_to_agent:
            logger.debug("Overwriting existing checkpoint_to_agent entry: %s", checkpoint_ns[:60])

        self.checkpoint_to_agent[checkpoint_ns] = (instance_id, subagent_type)

        logger.info(
            "[Subagent] Task started: id=%s, ns=%s, depth=%d, total=%d",
            instance_id,
            checkpoint_ns,
            current_depth,
            len(self.checkpoint_to_agent),
        )

        await self._presenter_emit(
            self.presenter.present_agent_call(
                agent_id=instance_id,
                agent_name=subagent_type,
                input_message=description,
                depth=current_depth,
            )
        )

    def _resolve_agent_info(self, event: StreamEvent) -> tuple[str, int]:
        checkpoint_ns = self._get_checkpoint_ns(event.get("metadata", {}))
        agent_info = self.checkpoint_to_agent.pop(checkpoint_ns, None)
        if agent_info:
            return agent_info[0], checkpoint_ns.count("|") + 1 if checkpoint_ns else 1
        return "unknown", 1

    async def _handle_task_end(self, event: StreamEvent) -> None:
        data = event.get("data", {})
        out = data.get("output")
        result_text = str(out) if out is not None else ""

        out_update = getattr(out, "update", None) if out is not None else None
        if isinstance(out_update, dict):
            messages = out_update.get("messages", [])
            if messages:
                result_text = getattr(messages[0], "content", result_text)

        error_message = None
        tool_status = get_tool_status(out)
        if tool_status == "error":
            error_message = str(out) if out else "Tool execution failed"
        elif isinstance(out, dict) and (out.get("error") or out.get("status") == "error"):
            error_message = out.get("error") or out.get("message") or str(out)

        current_instance_id, current_depth = self._resolve_agent_info(event)

        logger.debug(
            "Subagent ended: id=%s, depth=%d, error=%s",
            current_instance_id,
            current_depth,
            error_message is not None,
        )

        await self._presenter_emit(
            self.presenter.present_agent_result(
                agent_id=current_instance_id,
                result=result_text,
                success=error_message is None,
                depth=current_depth,
                error=error_message,
            )
        )

    async def _handle_task_error(self, event: StreamEvent) -> None:
        error = event.get("data", {}).get("error")
        error_message = str(error) if error is not None else "Unknown error"
        current_instance_id, current_depth = self._resolve_agent_info(event)

        logger.warning(
            "Subagent error: id=%s, depth=%d, error=%s",
            current_instance_id,
            current_depth,
            error_message[:200],
        )

        await self._presenter_emit(
            self.presenter.present_agent_result(
                agent_id=current_instance_id,
                result="",
                success=False,
                depth=current_depth,
                error=error_message,
            )
        )
