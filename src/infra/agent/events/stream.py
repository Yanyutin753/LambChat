"""Chat, summary, and token usage stream handlers."""

from __future__ import annotations

from io import StringIO
from typing import Any

from src.infra.agent.events.buffers import BufferKey, TextChunkBuffer
from src.infra.agent.events.types import StreamEvent, get_value


def _first_int(*values: Any) -> int | None:
    for value in values:
        if isinstance(value, int):
            return value
    return None


class StreamEventMixin:
    _chunk_buffer: TextChunkBuffer
    _summary_chunk_buffer: TextChunkBuffer
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

    def _message_content_text(self, content: Any) -> str:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text" and block.get("text"):
                        parts.append(str(block["text"]))
                    elif block.get("content"):
                        parts.append(str(block["content"]))
                elif block:
                    parts.append(str(block))
            return "".join(parts)
        return "" if content is None else str(content)

    async def _handle_chat_model_end_output(
        self,
        event: StreamEvent,
        current_agent_id: str | None,
        current_depth: int,
    ) -> None:
        response = event.get("data", {}).get("output")
        if not response:
            return
        content = getattr(response, "content", None)
        text = self._message_content_text(content)
        if not text:
            return
        text_id = getattr(response, "id", None)
        if current_depth == 0 and self._output_buffer_chars <= 0:
            self._append_output_text(text)
        ready_flushes = self._buffer_text_chunk(text, current_depth, current_agent_id, text_id)
        if ready_flushes:
            for ready in ready_flushes:
                await self._emit_text_flush(*ready)

    async def _flush_chunk_buffer(self) -> None:
        text, key = self._chunk_buffer.consume()
        await self._emit_text_flush(text, key)

    async def _flush_summary_chunk_buffer(self) -> None:
        text, key = self._summary_chunk_buffer.consume()
        await self._emit_summary_flush(text, key)

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

    def _handle_token_usage(self, event: StreamEvent) -> None:
        response = event.get("data", {}).get("output")
        if not response:
            return

        usage = getattr(response, "usage_metadata", None)
        if usage is None:
            response_metadata = getattr(response, "response_metadata", None)
            if response_metadata:
                usage = response_metadata.get("token_usage") or response_metadata.get("usage")
        if usage is None:
            metadata = getattr(response, "metadata", None)
            if metadata:
                usage = metadata.get("token_usage") or metadata.get("usage")

        if usage is None:
            return

        input_tok = _first_int(
            get_value(usage, "input_tokens", None),
            get_value(usage, "prompt_tokens", None),
            get_value(usage, "prompt_token_count", None),
        )
        output_tok = _first_int(
            get_value(usage, "output_tokens", None),
            get_value(usage, "completion_tokens", None),
            get_value(usage, "candidates_token_count", None),
        )
        total_tok = _first_int(
            get_value(usage, "total_tokens", None),
            get_value(usage, "total_token_count", None),
        )

        if isinstance(input_tok, int):
            self.total_input_tokens += input_tok
        if isinstance(output_tok, int):
            self.total_output_tokens += output_tok
        if isinstance(total_tok, int):
            self.total_tokens += total_tok

        input_details = get_value(usage, "input_token_details", {})
        if not input_details:
            input_details = get_value(usage, "prompt_tokens_details", {})
        cache_creation = None
        cache_read = None
        if input_details:
            cache_creation = _first_int(
                get_value(input_details, "cache_creation", None),
                get_value(input_details, "cache_creation_input_tokens", None),
            )
            cache_read = _first_int(
                get_value(input_details, "cache_read", None),
                get_value(input_details, "cached_tokens", None),
                get_value(input_details, "cached_content_token_count", None),
            )

        if cache_read is None:
            cache_read = _first_int(
                get_value(usage, "cached_content_token_count", None),
                get_value(usage, "cache_read_input_tokens", None),
            )
        if cache_creation is None:
            cache_creation = _first_int(get_value(usage, "cache_creation_input_tokens", None))

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

        content = chunk.content
        chunk_id = chunk.id

        if isinstance(content, str) and content:
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
                await self._presenter_emit(
                    self.presenter.present_thinking(
                        rc,
                        thinking_id=chunk_id,
                        depth=current_depth,
                        agent_id=current_agent_id,
                    )
                )
            return

        if isinstance(content, list):
            present_thinking = self.presenter.present_thinking
            emit = self._presenter_emit

            for block in content:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")
                if block_type in ("thinking", "reasoning"):
                    reasoning_text = block.get("thinking") or block.get("reasoning", "")
                    if reasoning_text:
                        await emit(
                            present_thinking(
                                reasoning_text,
                                thinking_id=chunk_id,
                                depth=current_depth,
                                agent_id=current_agent_id,
                            )
                        )
                elif block_type == "text":
                    text = block.get("text", "")
                    if text:
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
