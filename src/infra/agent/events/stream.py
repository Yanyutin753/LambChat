"""Chat, summary, and token usage stream handlers."""

from __future__ import annotations

from io import StringIO
from typing import Any

from src.infra.agent.events.buffers import BufferKey, TextChunkBuffer
from src.infra.agent.events.types import StreamEvent, get_value


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

    async def _flush_chunk_buffer(self) -> None:
        text, key = self._chunk_buffer.consume()
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

    async def _flush_summary_chunk_buffer(self) -> None:
        text, key = self._summary_chunk_buffer.consume()
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

    async def _append_text_chunk(
        self,
        text: str,
        depth: int,
        agent_id: str | None,
        text_id: str | None,
    ) -> None:
        key: BufferKey = (depth, agent_id, text_id)
        if self._chunk_buffer.key_changed(key):
            await self._flush_chunk_buffer()
        if self._chunk_buffer.append(text, key):
            await self._flush_chunk_buffer()

    async def _append_summary_chunk(
        self,
        text: str,
        depth: int,
        agent_id: str | None,
        summary_id: str | None,
    ) -> None:
        key: BufferKey = (depth, agent_id, summary_id)
        if self._summary_chunk_buffer.key_changed(key):
            await self._flush_summary_chunk_buffer()
        if self._summary_chunk_buffer.append(text, key):
            await self._flush_summary_chunk_buffer()

    def _handle_token_usage(self, event: StreamEvent) -> None:
        response = event.get("data", {}).get("output")
        if not response:
            return

        usage = getattr(response, "usage_metadata", None)
        if usage is None:
            metadata = getattr(response, "metadata", None)
            if metadata:
                usage = metadata.get("usage")

        if usage is None:
            return

        input_tok = get_value(usage, "input_tokens")
        output_tok = get_value(usage, "output_tokens")
        total_tok = get_value(usage, "total_tokens")

        if isinstance(input_tok, int):
            self.total_input_tokens += input_tok
        if isinstance(output_tok, int):
            self.total_output_tokens += output_tok
        if isinstance(total_tok, int):
            self.total_tokens += total_tok

        input_details = get_value(usage, "input_token_details", {})
        if input_details:
            cache_creation = get_value(input_details, "cache_creation")
            cache_read = get_value(input_details, "cache_read")
            if isinstance(cache_creation, int):
                self.total_cache_creation_tokens += cache_creation
            if isinstance(cache_read, int):
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
            await self._append_summary_chunk(content, current_depth, current_agent_id, summary_id)
            return

        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "text":
                    continue
                text = block.get("text", "")
                if text:
                    await self._append_summary_chunk(
                        text,
                        current_depth,
                        current_agent_id,
                        summary_id,
                    )

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
                self._output_buffer.write(content)
            await self._append_text_chunk(content, current_depth, current_agent_id, chunk_id)
            return

        if isinstance(content, list):
            present_thinking = self.presenter.present_thinking
            emit = self._presenter_emit

            for block in content:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type")
                if block_type == "thinking":
                    thinking_text = block.get("thinking", "")
                    if thinking_text:
                        await emit(
                            present_thinking(
                                thinking_text,
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
                            self._output_buffer.write(text)
                        await self._append_text_chunk(
                            text,
                            current_depth,
                            current_agent_id,
                            chunk_id,
                        )
