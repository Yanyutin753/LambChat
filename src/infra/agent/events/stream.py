"""Chat, summary, and token usage stream handlers."""

from __future__ import annotations

from io import StringIO
from typing import Any

from src.infra.agent.events.buffers import BufferKey, TextChunkBuffer
from src.infra.agent.events.types import StreamEvent, get_value

# 工具生命周期不走标准 tool:start 通道（由专用事件渲染），参数流式会悬空
TOOL_ARGS_STREAM_SKIP_NAMES = frozenset(("ask_human", "task", "write_todos"))


def _first_int(*values: Any) -> int | None:
    for value in values:
        if isinstance(value, int):
            return value
    return None


def _usage_sources(response: Any) -> list[Any]:
    """Return normalized usage first, followed by raw provider fallbacks."""
    sources: list[Any] = []
    usage_metadata = getattr(response, "usage_metadata", None)
    if usage_metadata is not None:
        sources.append(usage_metadata)

    for container_name in ("response_metadata", "metadata"):
        container = getattr(response, container_name, None)
        if not container:
            continue
        raw_usage = get_value(container, "token_usage", None) or get_value(container, "usage", None)
        if raw_usage is not None and all(raw_usage is not source for source in sources):
            sources.append(raw_usage)
    return sources


def _first_usage_int(sources: list[Any], aliases: tuple[str, ...]) -> int | None:
    for source in sources:
        value = _first_int(*(get_value(source, alias, None) for alias in aliases))
        if value is not None:
            return value
    return None


def _first_cache_usage_int(sources: list[Any], aliases: tuple[str, ...]) -> int | None:
    """Read one semantic cache metric without summing equivalent aliases."""
    for source in sources:
        for details_name in ("input_token_details", "prompt_tokens_details"):
            details = get_value(source, details_name, None)
            if not details:
                continue
            value = _first_int(*(get_value(details, alias, None) for alias in aliases))
            if value is not None:
                return value
        value = _first_int(*(get_value(source, alias, None) for alias in aliases))
        if value is not None:
            return value
    return None


class StreamEventMixin:
    _chunk_buffer: TextChunkBuffer
    _summary_chunk_buffer: TextChunkBuffer
    _thinking_chunk_buffer: TextChunkBuffer
    _tool_args_buffers: dict[int | str, TextChunkBuffer]
    _tool_args_meta: dict[int | str, tuple[str, str | None]]
    _CHUNK_FLUSH_SIZE: int
    _output_buffer: StringIO
    _presenter_emit: Any
    presenter: Any
    thinking_ids: dict[str | None, str | None]
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    total_cache_creation_tokens: int
    total_cache_read_tokens: int
    _output_buffer_chars: int

    def _append_output_text(self, text: str) -> None:
        from src.infra.agent.events.processor import OUTPUT_TEXT_COPY_MAX_CHARS

        if not text or self._output_buffer_chars >= OUTPUT_TEXT_COPY_MAX_CHARS:
            return

        remaining = OUTPUT_TEXT_COPY_MAX_CHARS - self._output_buffer_chars
        clipped = text[:remaining]
        self._output_buffer.write(clipped)
        self._output_buffer_chars += len(clipped)

    async def _flush_chunk_buffer(self) -> None:
        text, key = self._chunk_buffer.consume()
        await self._emit_text_flush(text, key)

    async def _flush_summary_chunk_buffer(self) -> None:
        text, key = self._summary_chunk_buffer.consume()
        await self._emit_summary_flush(text, key)

    async def _flush_thinking_chunk_buffer(self) -> None:
        text, key = self._thinking_chunk_buffer.consume()
        await self._emit_thinking_flush(text, key)

    async def _flush_tool_args_buffers(self) -> None:
        """Emit and release all pending tool-args buffers (model stream ended)."""
        if not self._tool_args_buffers:
            return
        for key, buffer in self._tool_args_buffers.items():
            text, buffer_key = buffer.consume()
            if not text or buffer_key is None:
                continue
            depth, agent_id, tool_call_id = buffer_key
            name, _ = self._tool_args_meta.get(key, (tool_call_id or "", tool_call_id))
            await self._presenter_emit(
                self.presenter.present_tool_args_delta(
                    name,
                    tool_call_id,
                    text,
                    depth=depth,
                    agent_id=agent_id,
                )
            )
        self._tool_args_buffers.clear()
        self._tool_args_meta.clear()

    def _reset_tool_args_buffers(self) -> None:
        """Drop pending tool-args buffers without emitting (new model run)."""
        self._tool_args_buffers.clear()
        self._tool_args_meta.clear()

    async def _handle_tool_args_chunks(
        self,
        tool_call_chunks: list[Any],
        depth: int,
        agent_id: str | None,
    ) -> None:
        """Stream LLM tool-call argument deltas as tool:args:chunk events."""
        for tc in tool_call_chunks:
            if not isinstance(tc, dict):
                continue
            index = tc.get("index")
            key: int | str | None = index if isinstance(index, int) else None
            call_id = tc.get("id") or None
            if key is None:
                key = call_id
            if key is None:
                continue

            name = tc.get("name") or None
            if name:
                if name in TOOL_ARGS_STREAM_SKIP_NAMES:
                    continue
                existing_name, existing_id = self._tool_args_meta.get(key, (name, call_id))
                self._tool_args_meta[key] = (name, call_id or existing_id)

            meta = self._tool_args_meta.get(key)
            if meta is None:
                # 未见过工具名的增量无法归属（也无从渲染），等待 tool:start 兜底
                continue
            tool_name, tool_call_id = meta

            delta = tc.get("args") or ""
            if not delta:
                continue
            buffer = self._tool_args_buffers.get(key)
            if buffer is None:
                from src.kernel.config import settings

                buffer = TextChunkBuffer(
                    self._CHUNK_FLUSH_SIZE, settings.STREAM_CHUNK_FLUSH_INTERVAL
                )
                self._tool_args_buffers[key] = buffer
            buffer_key: BufferKey = (depth, agent_id, tool_call_id)
            if buffer.append(delta, buffer_key):
                text, flushed_key = buffer.consume()
                await self._emit_tool_args_flush(tool_name, text, flushed_key)

    async def _emit_tool_args_flush(
        self,
        tool_name: str,
        text: str,
        key: BufferKey | None,
    ) -> None:
        if not text or key is None:
            return
        depth, agent_id, tool_call_id = key
        await self._presenter_emit(
            self.presenter.present_tool_args_delta(
                tool_name,
                tool_call_id,
                text,
                depth=depth,
                agent_id=agent_id,
            )
        )

    async def _emit_text_flush(self, text: str, key: BufferKey | None) -> None:
        if not text or key is None:
            return

        depth, agent_id, text_id = key
        await self._presenter_emit(
            self.presenter.present_text(
                text,
                text_id=text_id,
                depth=depth,
                agent_id=agent_id,
            )
        )

    async def _emit_summary_flush(self, text: str, key: BufferKey | None) -> None:
        if not text or key is None:
            return

        depth, agent_id, summary_id = key
        await self._presenter_emit(
            self.presenter.present_summary(
                text,
                summary_id=summary_id,
                depth=depth,
                agent_id=agent_id,
            )
        )

    async def _emit_thinking_flush(self, text: str, key: BufferKey | None) -> None:
        if not text or key is None:
            return

        depth, agent_id, thinking_id = key
        await self._presenter_emit(
            self.presenter.present_thinking(
                text,
                thinking_id=thinking_id,
                depth=depth,
                agent_id=agent_id,
            )
        )

    def _buffer_text_chunk(
        self,
        text: str,
        depth: int,
        agent_id: str | None,
        text_id: str | None,
    ) -> list[tuple[str, BufferKey | None]] | None:
        key: BufferKey = (depth, agent_id, text_id)
        ready_flushes = []
        ready = self._chunk_buffer.consume_ready(key)
        if ready is not None:
            ready_flushes.append(ready)
        if self._chunk_buffer.append(text, key):
            ready_flushes.append(self._chunk_buffer.consume())
        return ready_flushes or None

    def _buffer_summary_chunk(
        self,
        text: str,
        depth: int,
        agent_id: str | None,
        summary_id: str | None,
    ) -> list[tuple[str, BufferKey | None]] | None:
        key: BufferKey = (depth, agent_id, summary_id)
        ready_flushes = []
        ready = self._summary_chunk_buffer.consume_ready(key)
        if ready is not None:
            ready_flushes.append(ready)
        if self._summary_chunk_buffer.append(text, key):
            ready_flushes.append(self._summary_chunk_buffer.consume())
        return ready_flushes or None

    def _buffer_thinking_chunk(
        self,
        text: str,
        depth: int,
        agent_id: str | None,
        thinking_id: str | None,
    ) -> list[tuple[str, BufferKey | None]] | None:
        key: BufferKey = (depth, agent_id, thinking_id)
        ready_flushes = []
        ready = self._thinking_chunk_buffer.consume_ready(key)
        if ready is not None:
            ready_flushes.append(ready)
        if self._thinking_chunk_buffer.append(text, key):
            ready_flushes.append(self._thinking_chunk_buffer.consume())
        return ready_flushes or None

    def _handle_token_usage(self, event: StreamEvent) -> None:
        response = event.get("data", {}).get("output")
        if not response:
            return

        usage_sources = _usage_sources(response)
        if not usage_sources:
            return

        input_tok = _first_usage_int(
            usage_sources,
            ("input_tokens", "prompt_tokens", "prompt_token_count"),
        )
        output_tok = _first_usage_int(
            usage_sources,
            ("output_tokens", "completion_tokens", "candidates_token_count"),
        )
        total_tok = _first_usage_int(
            usage_sources,
            ("total_tokens", "total_token_count"),
        )

        if isinstance(input_tok, int):
            self.total_input_tokens += input_tok
        if isinstance(output_tok, int):
            self.total_output_tokens += output_tok
        if isinstance(total_tok, int):
            self.total_tokens += total_tok

        cache_creation = _first_cache_usage_int(
            usage_sources,
            ("cache_creation", "cache_creation_input_tokens", "cache_write_tokens"),
        )
        cache_read = _first_cache_usage_int(
            usage_sources,
            (
                "cache_read",
                "cached_tokens",
                "cache_read_input_tokens",
                "prompt_cache_hit_tokens",
                "cached_content_token_count",
                "total_cached_tokens",
            ),
        )

        if cache_creation is not None:
            self.total_cache_creation_tokens += cache_creation
        if cache_read is not None:
            self.total_cache_read_tokens += cache_read

    async def _handle_summary_stream(
        self,
        event: StreamEvent,
        current_agent_id: str | None,
        current_depth: int,
    ) -> None:
        data = event.get("data", {})
        chunk = data.get("chunk")
        if not chunk:
            return

        content = chunk.content
        summary_id = chunk.id

        if isinstance(content, str) and content:
            ready_flushes = self._buffer_summary_chunk(
                content,
                current_depth,
                current_agent_id,
                summary_id,
            )
            if ready_flushes:
                for ready in ready_flushes:
                    await self._emit_summary_flush(*ready)
            return

        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "text":
                    continue
                text = block.get("text", "")
                if text:
                    ready_flushes = self._buffer_summary_chunk(
                        text,
                        current_depth,
                        current_agent_id,
                        summary_id,
                    )
                    if ready_flushes:
                        for ready in ready_flushes:
                            await self._emit_summary_flush(*ready)

    async def _handle_chat_stream(
        self,
        event: StreamEvent,
        current_agent_id: str | None,
        current_depth: int,
    ) -> None:
        data = event.get("data", {})
        chunk = data.get("chunk")
        if not chunk:
            return

        # 参数增量与文本可以同 chunk（非流式响应走流式管道时合并产出），
        # 两类缓冲互不干扰，处理完参数增量后继续走文本分支。
        tool_call_chunks = getattr(chunk, "tool_call_chunks", None)
        if isinstance(tool_call_chunks, list) and tool_call_chunks:
            await self._handle_tool_args_chunks(tool_call_chunks, current_depth, current_agent_id)

        content = chunk.content
        chunk_id = chunk.id

        if isinstance(content, str) and content:
            await self._flush_thinking_chunk_buffer()
            if current_depth == 0:
                self._append_output_text(content)
            ready_flushes = self._buffer_text_chunk(
                content,
                current_depth,
                current_agent_id,
                chunk_id,
            )
            if ready_flushes:
                for ready in ready_flushes:
                    await self._emit_text_flush(*ready)
            return

        if isinstance(content, str) and not content:
            rc = getattr(chunk, "additional_kwargs", {}).get("reasoning_content")
            if rc:
                ready_flushes = self._buffer_thinking_chunk(
                    rc,
                    current_depth,
                    current_agent_id,
                    chunk_id,
                )
                if ready_flushes:
                    for ready in ready_flushes:
                        await self._emit_thinking_flush(*ready)
            return

        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")
                if block_type in ("thinking", "reasoning"):
                    reasoning_text = block.get("thinking") or block.get("reasoning", "")
                    if reasoning_text:
                        ready_flushes = self._buffer_thinking_chunk(
                            reasoning_text,
                            current_depth,
                            current_agent_id,
                            chunk_id,
                        )
                        if ready_flushes:
                            for ready in ready_flushes:
                                await self._emit_thinking_flush(*ready)
                elif block_type == "text":
                    text = block.get("text", "")
                    if text:
                        await self._flush_thinking_chunk_buffer()
                        self.thinking_ids[current_agent_id] = None
                        if current_depth == 0:
                            self._append_output_text(text)
                        ready_flushes = self._buffer_text_chunk(
                            text,
                            current_depth,
                            current_agent_id,
                            chunk_id,
                        )
                        if ready_flushes:
                            for ready in ready_flushes:
                                await self._emit_text_flush(*ready)
