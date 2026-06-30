"""
DeepAgent event processor.

This module keeps the public `AgentEventProcessor` entry point while delegating
the heavier event-specific work to focused helper modules.
"""

import logging
from io import StringIO
from typing import Any

from src.infra.agent.events.binary_uploads import upload_binary_blocks
from src.infra.agent.events.buffers import TextChunkBuffer
from src.infra.agent.events.debug_logger import debug_log_event
from src.infra.agent.events.stream import StreamEventMixin
from src.infra.agent.events.subagents import SubagentEventMixin
from src.infra.agent.events.tool_events import ToolEventMixin
from src.infra.agent.events.tool_outputs import (
    MCP_MEDIA_TYPES,
    MCP_SKIP_KEYS,
    collect_blocks,
    detect_tool_error,
    extract_tool_output,
    get_tool_status,
    normalize_content,
    process_messages,
)
from src.infra.agent.events.types import TOOL_TASK, StreamEvent
from src.infra.logging import get_logger
from src.infra.writer.present import Presenter

logger = get_logger(__name__)

_CONTEXT_EVENT_TYPES = frozenset(
    ("on_chat_model_stream", "on_tool_start", "on_tool_end", "on_tool_error")
)

RUBRIC_GRADER = "rubric_grader"
INTERNAL_STREAM_SOURCES = frozenset(("image_analysis_tool",))
OUTPUT_TEXT_COPY_MAX_CHARS = 8_000


class AgentEventProcessor(SubagentEventMixin, StreamEventMixin, ToolEventMixin):
    """
    Process DeepAgent stream events and forward presenter-ready events.

    The processor is session-scoped. Call `flush()` before reading final output,
    and call `clear()` or `finalize()` when the session is no longer needed.
    Token counters are intentionally retained after `clear()` for existing
    callers that emit usage after stream cleanup.
    """

    __slots__ = (
        "presenter",
        "checkpoint_to_agent",
        "thinking_ids",
        "_output_buffer",
        "total_input_tokens",
        "total_output_tokens",
        "total_tokens",
        "total_cache_creation_tokens",
        "total_cache_read_tokens",
        "_token_usage_emitted",
        "_output_buffer_chars",
        "_presenter_emit",
        "_base_url",
        "_chunk_buffer",
        "_summary_chunk_buffer",
        "_agent_context_cache",
        "_subagent_display_names",
        "_subagent_avatars",
        "_started_tool_call_ids",
        "_rubric_grader_active",
        "_rubric_grader_id",
    )

    _CHUNK_FLUSH_SIZE = 200

    def __init__(
        self,
        presenter: Presenter,
        base_url: str = "",
        subagent_display_names: dict[str, str] | None = None,
        subagent_avatars: dict[str, str] | None = None,
    ):
        self.presenter = presenter
        self.checkpoint_to_agent: dict[str, tuple[str, str]] = {}
        if not base_url:
            from src.kernel.config import settings

            base_url = getattr(settings, "APP_BASE_URL", "").rstrip("/")
        self._base_url = base_url
        self.thinking_ids: dict[str | None, str | None] = {}
        self._output_buffer = StringIO()
        self._output_buffer_chars = 0
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_tokens = 0
        self.total_cache_creation_tokens = 0
        self.total_cache_read_tokens = 0
        self._token_usage_emitted = False
        self._presenter_emit = presenter.emit
        self._chunk_buffer = TextChunkBuffer(self._CHUNK_FLUSH_SIZE)
        self._summary_chunk_buffer = TextChunkBuffer(self._CHUNK_FLUSH_SIZE)
        self._agent_context_cache: dict[str, tuple[str | None, int]] = {}
        self._subagent_display_names = subagent_display_names or {}
        self._subagent_avatars = subagent_avatars or {}
        self._started_tool_call_ids: set[str] = set()
        self._rubric_grader_active: bool = False
        self._rubric_grader_id: str | None = None

    @property
    def output_text(self) -> str:
        """Return accumulated top-level assistant output text."""
        return self._output_buffer.getvalue()

    async def flush(self) -> None:
        """Flush pending stream chunks without clearing counters or output text."""
        await self._flush_chunk_buffer()
        await self._flush_summary_chunk_buffer()

    async def finalize(self) -> None:
        """Flush pending chunks and release session-scoped buffers."""
        await self.flush()
        self.clear()

    async def emit_token_usage(
        self,
        *,
        duration: float = 0.0,
        model_id: str | None = None,
        model: str | None = None,
    ) -> bool:
        """Emit accumulated token usage once, preserving counters for late cleanup paths."""
        if self._token_usage_emitted:
            return False

        if not (
            self.total_input_tokens > 0 or self.total_output_tokens > 0 or self.total_tokens > 0
        ):
            return False

        total_tokens = self.total_tokens or self.total_input_tokens + self.total_output_tokens
        event = self.presenter.present_token_usage(
            input_tokens=self.total_input_tokens,
            output_tokens=self.total_output_tokens,
            total_tokens=total_tokens,
            duration=duration,
            cache_creation_tokens=self.total_cache_creation_tokens,
            cache_read_tokens=self.total_cache_read_tokens,
            model_id=model_id,
            model=model,
        )
        await self._presenter_emit(event)
        self._token_usage_emitted = True
        return True

    def clear(self) -> None:
        """Release memory held by this session while preserving token counters."""
        self._output_buffer.close()
        self._output_buffer = StringIO()
        self._output_buffer_chars = 0
        self.checkpoint_to_agent.clear()
        self.thinking_ids.clear()
        self._agent_context_cache.clear()
        self._chunk_buffer.clear()
        self._summary_chunk_buffer.clear()
        self._started_tool_call_ids.clear()

    async def process_event(self, event: StreamEvent) -> None:
        """Process a single LangChain stream event."""
        await debug_log_event(event, self._debug_log_context())
        evt_type = event.get("event")
        event_name = event.get("name", "")

        # ── Rubric grader chain detection ──
        # The RubricMiddleware runs a grader sub-agent inside the graph.
        # Detect its chain start/end so we can emit agent:call / agent:result
        # and suppress all internal events to avoid polluting the main stream.
        if event_name == RUBRIC_GRADER:
            match evt_type:
                case "on_chain_start":
                    self._rubric_grader_active = True
                    run_id = event.get("run_id", "")
                    self._rubric_grader_id = f"rubric_grader_{run_id[:8]}"
                    await self._presenter_emit(
                        self.presenter.present_agent_call(
                            agent_id=self._rubric_grader_id,
                            agent_name="Rubric Grader",
                            input_message="Evaluating against rubric criteria",
                            depth=1,
                        )
                    )
                    return
                case "on_chain_end":
                    sr = self._extract_rubric_result(event)
                    success = sr.get("result", "completed") != "failed"
                    result_text = sr.get("result", "completed")
                    explanation = sr.get("explanation", "")
                    if explanation:
                        result_text = f"{result_text}\n{explanation}"
                    await self._presenter_emit(
                        self.presenter.present_agent_result(
                            agent_id=self._rubric_grader_id or "rubric_grader",
                            result=result_text,
                            success=success,
                            depth=1,
                        )
                    )
                    self._rubric_grader_active = False
                    self._rubric_grader_id = None
                    return

        tool_name = event_name

        if tool_name == TOOL_TASK:
            match evt_type:
                case "on_tool_start":
                    await self._handle_task_start(event)
                    return
                case "on_tool_end":
                    await self._handle_task_end(event)
                    return
                case "on_tool_error":
                    await self._handle_task_error(event)
                    return

        if evt_type == "on_chat_model_end":
            await self.flush()
            metadata = event.get("metadata", {})
            checkpoint_ns = self._get_checkpoint_ns(metadata)
            current_agent_id, current_depth = self._get_agent_context(checkpoint_ns)
            await self._handle_chat_model_end_output(event, current_agent_id, current_depth)
            await self.flush()
            self._handle_token_usage(event)
            return

        if evt_type not in _CONTEXT_EVENT_TYPES:
            return

        # Hide grader internals from the public stream. The chain start/end
        # events above already provide user-visible grading status; routing
        # the internal GraderResponse tool call makes the UI look stuck in a
        # tool loop while the middleware is just validating structured output.
        if self._rubric_grader_active:
            return

        metadata = event.get("metadata", {})
        if self._is_internal_stream_event(metadata):
            return

        context_checkpoint_ns = self._get_checkpoint_ns(metadata)
        current_agent_id, current_depth = self._get_agent_context(context_checkpoint_ns)

        if current_depth and logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "[Subagent] %s/%s: agent=%s, depth=%d, ns=%s",
                evt_type,
                tool_name or "N/A",
                current_agent_id,
                current_depth,
                context_checkpoint_ns[:60] if context_checkpoint_ns else "N/A",
            )

        match evt_type:
            case "on_chat_model_stream":
                if self._get_lc_source(metadata) == "summarization":
                    await self._handle_summary_stream(event, current_agent_id, current_depth)
                else:
                    await self._handle_chat_stream(event, current_agent_id, current_depth)
            case "on_tool_start":
                await self.flush()
                await self._handle_tool_start(event, tool_name, current_agent_id, current_depth)
            case "on_tool_end":
                await self.flush()
                await self._handle_tool_end(event, tool_name, current_agent_id, current_depth)
            case "on_tool_error":
                await self.flush()
                await self._handle_tool_error(event, tool_name, current_agent_id, current_depth)

    _extract_tool_output = staticmethod(extract_tool_output)
    _detect_tool_error = staticmethod(detect_tool_error)
    _get_tool_status = staticmethod(get_tool_status)
    _collect_blocks = staticmethod(collect_blocks)
    _normalize_content = staticmethod(normalize_content)
    _process_messages = staticmethod(process_messages)
    _MCP_MEDIA_TYPES = MCP_MEDIA_TYPES
    _MCP_SKIP_KEYS = MCP_SKIP_KEYS

    def _debug_log_context(self) -> dict[str, Any]:
        """Return LambChat run identity for raw stream-event debug logs."""
        config = getattr(self.presenter, "config", None)
        return {
            "trace_id": getattr(self.presenter, "trace_id", None),
            "run_id": getattr(self.presenter, "run_id", None),
            "session_id": getattr(config, "session_id", None),
            "agent_id": getattr(config, "agent_id", None),
            "agent_name": getattr(config, "agent_name", None),
        }

    @staticmethod
    def _is_internal_stream_event(metadata: dict[str, Any]) -> bool:
        source = metadata.get("lc_source") or metadata.get("source")
        return bool(metadata.get("internal_tool_call") or source in INTERNAL_STREAM_SOURCES)

    async def _upload_binary_blocks(self, result: dict) -> None:
        await upload_binary_blocks(result, self._base_url)

    @staticmethod
    def _extract_rubric_result(event: StreamEvent) -> dict:
        """Extract the structured rubric evaluation from a grader chain-end event."""
        output: Any = event.get("data", {}).get("output", {})
        if not isinstance(output, dict):
            return {}
        sr = output.get("structured_response")
        if sr is None:
            return {}
        if isinstance(sr, dict):
            return sr
        # Pydantic model or similar object
        return {k: getattr(sr, k, "") for k in ("result", "explanation", "criteria")}


__all__ = ["AgentEventProcessor", "INTERNAL_STREAM_SOURCES", "StreamEvent"]
