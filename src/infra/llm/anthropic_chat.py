"""Anthropic chat-model adapter with a first-event streaming deadline."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.callbacks import AsyncCallbackManagerForLLMRun
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from pydantic import Field

from src.infra.llm.streaming import aiter_with_first_event_timeout

_CACHE_CONTROL = {"type": "ephemeral"}

# Anthropic requires >= ~1024 tokens between adjacent breakpoints; estimate
# tokens from chars at ~3.5 chars/token and require a healthy margin.
_MIN_CACHE_SEGMENT_CHARS = 3600


def _to_text_blocks(content: Any) -> list[dict[str, Any]] | None:
    """Normalize message content into a list of provider content blocks."""
    if isinstance(content, str):
        return [{"type": "text", "text": content}] if content else None
    if isinstance(content, list):
        blocks: list[dict[str, Any]] = []
        for block in content:
            if isinstance(block, dict):
                blocks.append(dict(block))
            elif isinstance(block, str) and block:
                blocks.append({"type": "text", "text": block})
        return blocks or None
    return None


def _mark_last_block(messages: list[BaseMessage], index: int) -> BaseMessage:
    """Return a copy of messages[index] with cache_control on its last block."""
    message = messages[index]
    blocks = _to_text_blocks(message.content)
    if not blocks:
        return message
    last = dict(blocks[-1])
    last["cache_control"] = dict(_CACHE_CONTROL)
    blocks[-1] = last
    return message.model_copy(update={"content": blocks})


def _message_chars(message: BaseMessage) -> int:
    """Rough size estimate (chars) of a message's text content."""
    blocks = _to_text_blocks(message.content)
    if blocks is None:
        return 0
    return sum(len(block.get("text") or "") for block in blocks if isinstance(block, dict))


def _apply_prompt_cache_control(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Add Anthropic prompt-cache breakpoints without mutating the input list.

    Breakpoints (3 of the 4 allowed):
        1. The last system message - caches the stable system prefix.
        2. The end of the previous turn (message right before the newest
           human message) - lets tool-loop iterations and retries reuse the
           conversation prefix up to the last completed turn. Skipped when
           the segment since that point is too small to be cacheable
           (Anthropic requires >= ~1024 tokens between breakpoints).
        3. The final message - caches the full conversation prefix so each
           subsequent turn reuses everything up to the previous turn.
    """
    result = list(messages)
    # 1. System message breakpoint.
    for index in range(len(result) - 1, -1, -1):
        if isinstance(result[index], SystemMessage):
            result[index] = _mark_last_block(result, index)
            break
    # 2. Previous-turn boundary breakpoint.
    last_human = next(
        (i for i in range(len(result) - 1, -1, -1) if isinstance(result[i], HumanMessage)),
        None,
    )
    if (
        last_human is not None
        and last_human > 0
        and not isinstance(result[last_human - 1], SystemMessage)
    ):
        boundary = last_human - 1
        segment_chars = sum(_message_chars(m) for m in result[boundary:-1])
        if segment_chars >= _MIN_CACHE_SEGMENT_CHARS:
            result[boundary] = _mark_last_block(result, boundary)
    # 3. Final message breakpoint (fall back to the nearest message that
    # actually has content blocks, e.g. pure tool-call AIMessages).
    for index in range(len(result) - 1, -1, -1):
        if _to_text_blocks(result[index].content):
            result[index] = _mark_last_block(result, index)
            break
    return result


class LambChatAnthropicChatModel(ChatAnthropic):
    """Time out only the first stream event, not the whole streamed response."""

    first_event_timeout: float | None = Field(default=None, exclude=True)
    non_streaming_timeout: float | None = Field(default=None, exclude=True)
    # Inject Anthropic prompt-cache breakpoints (system prefix + final message).
    enable_prompt_cache: bool = Field(default=True, exclude=True)

    def _prepare(self, messages: list[BaseMessage]) -> list[BaseMessage]:
        if self.enable_prompt_cache:
            return _apply_prompt_cache_control(messages)
        return messages

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        *,
        stream_usage: bool | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        source = super()._astream(
            self._prepare(messages),
            stop=stop,
            run_manager=run_manager,
            stream_usage=stream_usage,
            **kwargs,
        )
        async for chunk in aiter_with_first_event_timeout(
            source,
            timeout=self.first_event_timeout,
        ):
            yield chunk

    async def _agenerate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        async with asyncio.timeout(self.non_streaming_timeout):
            return await super()._agenerate(
                self._prepare(messages),
                stop=stop,
                run_manager=run_manager,
                **kwargs,
            )
