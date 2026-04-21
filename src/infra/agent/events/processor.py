"""
DeepAgent event processor.

This module keeps the public `AgentEventProcessor` entry point while delegating
the heavier event-specific work to focused helper modules.
"""

from io import StringIO

from src.infra.agent.events.binary_uploads import upload_binary_blocks
from src.infra.agent.events.buffers import TextChunkBuffer
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
        "_presenter_emit",
        "_base_url",
        "_chunk_buffer",
        "_summary_chunk_buffer",
    )

    _CHUNK_FLUSH_SIZE = 200

    def __init__(self, presenter: Presenter, base_url: str = ""):
        self.presenter = presenter
        self.checkpoint_to_agent: dict[str, tuple[str, str]] = {}
        if not base_url:
            from src.kernel.config import settings

            base_url = getattr(settings, "APP_BASE_URL", "").rstrip("/")
        self._base_url = base_url
        self.thinking_ids: dict[str | None, str | None] = {}
        self._output_buffer = StringIO()
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.total_tokens = 0
        self.total_cache_creation_tokens = 0
        self.total_cache_read_tokens = 0
        self._presenter_emit = presenter.emit
        self._chunk_buffer = TextChunkBuffer(self._CHUNK_FLUSH_SIZE)
        self._summary_chunk_buffer = TextChunkBuffer(self._CHUNK_FLUSH_SIZE)

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

    def clear(self) -> None:
        """Release memory held by this session while preserving token counters."""
        self._output_buffer.close()
        self._output_buffer = StringIO()
        self.checkpoint_to_agent.clear()
        self.thinking_ids.clear()
        self._chunk_buffer.clear()
        self._summary_chunk_buffer.clear()

    async def process_event(self, event: StreamEvent) -> None:
        """Process a single LangChain stream event."""
        evt_type = event.get("event")
        tool_name = event.get("name", "")

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

        metadata = event.get("metadata", {})
        checkpoint_ns = self._get_checkpoint_ns(metadata)
        lc_source = self._get_lc_source(metadata)
        current_agent_id, current_depth = self._get_agent_context(checkpoint_ns)

        if current_depth:
            logger.debug(
                "[Subagent] %s/%s: agent=%s, depth=%d, ns=%s",
                evt_type,
                tool_name or "N/A",
                current_agent_id,
                current_depth,
                checkpoint_ns[:60] if checkpoint_ns else "N/A",
            )

        is_summarization = lc_source == "summarization"

        match evt_type:
            case "on_chat_model_end":
                await self.flush()
                self._handle_token_usage(event)
            case "on_chat_model_stream":
                if is_summarization:
                    await self._handle_summary_stream(event, current_agent_id, current_depth)
                else:
                    await self._handle_chat_stream(event, current_agent_id, current_depth)
            case "on_tool_start":
                await self.flush()
                await self._handle_tool_start(event, tool_name, current_agent_id, current_depth)
            case "on_tool_end":
                await self.flush()
                await self._handle_tool_end(event, tool_name, current_agent_id, current_depth)

    _extract_tool_output = staticmethod(extract_tool_output)
    _detect_tool_error = staticmethod(detect_tool_error)
    _get_tool_status = staticmethod(get_tool_status)
    _collect_blocks = staticmethod(collect_blocks)
    _normalize_content = staticmethod(normalize_content)
    _process_messages = staticmethod(process_messages)
    _MCP_MEDIA_TYPES = MCP_MEDIA_TYPES
    _MCP_SKIP_KEYS = MCP_SKIP_KEYS

    async def _upload_binary_blocks(self, result: dict) -> None:
        await upload_binary_blocks(result, self._base_url)


__all__ = ["AgentEventProcessor", "StreamEvent"]
