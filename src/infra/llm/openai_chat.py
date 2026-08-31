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

from src.infra.llm.responses_cache import current_responses_prompt_cache_key
from src.infra.llm.streaming import aiter_with_first_event_timeout
from src.kernel.config import settings


class LambChatOpenAIChatModel(ChatOpenAI):
    """Time out only the first stream event, not the whole streamed response."""

    first_event_timeout: float | None = Field(default=None, exclude=True)
    non_streaming_timeout: float | None = Field(default=None, exclude=True)

    def _get_request_payload(
        self, input_: Any, *, stop: list[str] | None = None, **kwargs: Any
    ) -> dict:
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        # Codex 同款 KV 缓存路由：会话级 prompt_cache_key 让同前缀请求持续
        # 落在同一缓存机器。/v1/responses 与 /v1/chat/completions 两种线
        # 格式都注入（SDK 3.6.0 起后者同样支持该字段，替代 user 做缓存
        # 路由）；显式传入优先。同步路径在线程池中丢失上下文，属预期。
        if payload.get("prompt_cache_key") is None:
            if getattr(settings, "LLM_KV_CACHE", True):
                key = current_responses_prompt_cache_key()
                if key:
                    payload["prompt_cache_key"] = key
        return payload

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
