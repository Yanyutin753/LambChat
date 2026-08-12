"""Google chat-model adapter with streaming inactivity timeouts."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import Field

from src.infra.llm.streaming import aiter_with_first_event_timeout


class LambChatGoogleChatModel(ChatGoogleGenerativeAI):
    """Require a timely first stream event without imposing a total deadline."""

    first_event_timeout: float | None = Field(default=None, exclude=True)
    non_streaming_timeout: float | None = Field(default=None, exclude=True)

    async def _astream(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: AsyncCallbackManagerForLLMRun | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ChatGenerationChunk]:
        kwargs.pop("timeout", None)
        source = super()._astream(messages, stop=stop, run_manager=run_manager, **kwargs)
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
        kwargs.setdefault("timeout", self.non_streaming_timeout)
        return await super()._agenerate(
            messages,
            stop=stop,
            run_manager=run_manager,
            **kwargs,
        )
