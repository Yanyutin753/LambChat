"""Anthropic chat-model adapter with a first-event streaming deadline."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.callbacks import AsyncCallbackManagerForLLMRun
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from pydantic import Field

from src.infra.llm.quota import QuotaChatMixin
from src.infra.llm.streaming import aiter_with_first_event_timeout

_CACHE_CONTROL = {"type": "ephemeral"}


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
    """Copy the message and mark its last eligible block, preserving reasoning."""
    message = messages[index]
    blocks = _to_text_blocks(message.content)
    if not blocks:
        return message
    target = next(
        (
            i
            for i in range(len(blocks) - 1, -1, -1)
            if blocks[i].get("type") not in {"thinking", "redacted_thinking", "reasoning"}
            and (blocks[i].get("type") != "text" or blocks[i].get("text"))
        ),
        None,
    )
    if target is None:
        return message
    last = dict(blocks[target])
    last["cache_control"] = dict(_CACHE_CONTROL)
    blocks[target] = last
    return message.model_copy(update={"content": blocks})


def _apply_prompt_cache_control(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Add Anthropic prompt-cache breakpoints without mutating the input list.

    Breakpoints (3 of the 4 allowed):
        1. The last system message - caches the stable system prefix.
        2. The end of the previous turn (message right before the newest
           human message) - lets tool-loop iterations and retries reuse the
           conversation prefix up to the last completed turn. Eligibility
           depends on that entire prefix, not the size of the last answer.
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
        for boundary in range(last_human - 1, -1, -1):
            if isinstance(result[boundary], SystemMessage):
                break
            marked = _mark_last_block(result, boundary)
            if marked is not result[boundary]:
                result[boundary] = marked
                break
    # 3. Final message breakpoint (fall back to the nearest message that
    # actually has content blocks, e.g. pure tool-call AIMessages).
    for index in range(len(result) - 1, -1, -1):
        marked = _mark_last_block(result, index)
        if marked is not result[index]:
            result[index] = marked
            break
    return result


class LambChatAnthropicChatModel(QuotaChatMixin, ChatAnthropic):
    """Time out only the first stream event, not the whole streamed response."""

    first_event_timeout: float | None = Field(default=None, exclude=True)
    non_streaming_timeout: float | None = Field(default=None, exclude=True)
    stream_idle_timeout: float | None = Field(default=None, exclude=True)
    stream_gap_warn_timeout: float | None = Field(default=None, exclude=True)
    # Inject Anthropic prompt-cache breakpoints (system prefix + final message).
    enable_prompt_cache: bool = Field(default=True, exclude=True)

    def _get_request_payload(
        self, input_: Any, *, stop: list[str] | None = None, **kwargs: Any
    ) -> dict:
        from src.infra.llm.reasoning_patch import is_deepseek_thinking_model

        messages = self._convert_input(input_).to_messages()
        if is_deepseek_thinking_model(self.model):
            normalized = []
            for message in messages:
                if isinstance(message, AIMessage):
                    content = _to_text_blocks(message.content) or []
                    if not any(
                        b.get("type") in ("thinking", "redacted_thinking")
                        or (
                            b.get("type") == "reasoning"
                            and message.response_metadata.get("model_provider") == "anthropic"
                        )
                        for b in content
                    ):
                        # Preserve actual reasoning across protocols; missing history is empty.
                        block = {
                            "type": "thinking",
                            "thinking": message.additional_kwargs.get("reasoning_content", ""),
                            "signature": "",
                        }
                        message = message.model_copy(update={"content": [block, *content]})
                normalized.append(message)
            messages = normalized
        prepared = messages
        if "cache_control" not in kwargs and "cache_control" not in self.model_kwargs:
            prepared = self._prepare(
                messages, tools=kwargs.get("tools", self.model_kwargs.get("tools"))
            )
        payload = super()._get_request_payload(prepared, stop=stop, **kwargs)
        # Respect caller-owned policy; defaults share at most four block markers.
        if prepared is not messages:
            bound_tools = payload.get("tools")
            if bound_tools and isinstance(bound_tools[-1], dict):
                last = bound_tools[-1]
                if "cache_control" not in last:
                    payload["tools"] = [
                        *bound_tools[:-1],
                        {**last, "cache_control": dict(_CACHE_CONTROL)},
                    ]
        return payload

    def _prepare(self, messages: list[BaseMessage], *, tools: Any = None) -> list[BaseMessage]:
        explicit = any(
            "cache_control" in block
            for message in messages
            for block in _to_text_blocks(message.content) or []
        ) or any(isinstance(tool, dict) and "cache_control" in tool for tool in tools or [])
        if self.enable_prompt_cache and not explicit:
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
            messages,
            stop=stop,
            run_manager=run_manager,
            stream_usage=stream_usage,
            **kwargs,
        )
        async for chunk in aiter_with_first_event_timeout(
            source,
            timeout=self.first_event_timeout,
            idle_timeout=self.stream_idle_timeout,
            gap_warn_timeout=self.stream_gap_warn_timeout,
            gap_warn_context=getattr(self, "model_name", "") or "",
            gap_describe=lambda chunk: getattr(getattr(chunk, "message", None), "id", None) or "",
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
                messages,
                stop=stop,
                run_manager=run_manager,
                **kwargs,
            )
