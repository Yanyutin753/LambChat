"""OpenAI chat-model adapter with a first-event streaming deadline."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_openai import ChatOpenAI
from pydantic import Field

from src.infra.llm.streaming import aiter_with_first_event_timeout


class LambChatOpenAIChatModel(ChatOpenAI):
    """Time out only the first stream event, not the whole streamed response."""

    first_event_timeout: float | None = Field(default=None, exclude=True)
    non_streaming_timeout: float | None = Field(default=None, exclude=True)

    async def _astream(self, *args: Any, **kwargs: Any) -> AsyncIterator[ChatGenerationChunk]:
        source = super()._astream(*args, **kwargs)
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
