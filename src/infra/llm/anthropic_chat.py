"""Anthropic chat-model adapter with a first-event streaming deadline."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from langchain_anthropic import ChatAnthropic
from langchain_core.callbacks import AsyncCallbackManagerForLLMRun
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from pydantic import Field

from src.infra.llm.streaming import aiter_with_first_event_timeout


class LambChatAnthropicChatModel(ChatAnthropic):
    """Time out only the first stream event, not the whole streamed response."""

    first_event_timeout: float | None = Field(default=None, exclude=True)
    non_streaming_timeout: float | None = Field(default=None, exclude=True)

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
