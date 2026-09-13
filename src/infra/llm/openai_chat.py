"""OpenAI chat-model adapter with a first-event streaming deadline."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any
from urllib.parse import urlparse

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_openai import ChatOpenAI
from pydantic import Field

from src.infra.llm.responses_cache import current_responses_prompt_cache_key
from src.infra.llm.streaming import aiter_with_first_event_timeout
from src.kernel.config import settings

_OPENAI_OFFICIAL_HOSTS = frozenset({"api.openai.com"})


def is_official_openai_base_url(base_url: Any) -> bool:
    """prompt_cache_key 只对官方端点注入：严格校验未知字段的第三方
    OpenAI 兼容网关可能因该字段 4xx（风险审查工单 2）。base_url 为空
    表示 SDK 默认官方端点；仅填域名的写法（api.openai.com/v1）urlparse
    会把整串归入 path，需回退按 `/` 截取主机段。"""
    if not base_url:
        return True
    raw = str(base_url)
    try:
        host = urlparse(raw).hostname or ""
    except ValueError:
        return False
    if not host and "://" not in raw:
        host = raw.split("/", 1)[0]
    return host.lower() in _OPENAI_OFFICIAL_HOSTS


class LambChatOpenAIChatModel(ChatOpenAI):
    """Time out only the first stream event, not the whole streamed response."""

    first_event_timeout: float | None = Field(default=None, exclude=True)
    non_streaming_timeout: float | None = Field(default=None, exclude=True)
    stream_idle_timeout: float | None = Field(default=None, exclude=True)

    def _get_request_payload(
        self, input_: Any, *, stop: list[str] | None = None, **kwargs: Any
    ) -> dict:
        payload = super()._get_request_payload(input_, stop=stop, **kwargs)
        # Codex 同款 KV 缓存路由：会话级 prompt_cache_key 让同前缀请求持续
        # 落在同一缓存机器。/v1/responses 与 /v1/chat/completions 两种线
        # 格式都注入（SDK 3.6.0 起后者同样支持该字段，替代 user 做缓存
        # 路由）；显式传入优先。同步路径在线程池中丢失上下文，属预期。
        # 仅官方端点注入：第三方网关严格校验未知字段时会 4xx（工单 2）。
        if payload.get("prompt_cache_key") is None:
            if getattr(settings, "LLM_KV_CACHE", True) and is_official_openai_base_url(
                getattr(self, "openai_api_base", None)
            ):
                key = current_responses_prompt_cache_key()
                if key:
                    payload["prompt_cache_key"] = key
        return payload

    async def _astream(self, *args: Any, **kwargs: Any) -> AsyncIterator[ChatGenerationChunk]:
        source = super()._astream(*args, **kwargs)
        async for chunk in aiter_with_first_event_timeout(
            source,
            timeout=self.first_event_timeout,
            idle_timeout=self.stream_idle_timeout,
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
