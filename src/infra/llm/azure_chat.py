"""Azure OpenAI chat-model adapter with a first-event streaming deadline.

Azure 的连接语义与 openai base_url 不同：按 ``azure_endpoint``（资源级
URL）+ ``deployment_name`` + ``api_version`` 定位，认证走 api key（或
azure_ad_token）。endpoint 解析见 ``client._parse_azure_endpoint``。
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_openai import AzureChatOpenAI
from pydantic import Field

from src.infra.llm.streaming import aiter_with_first_event_timeout

_AZURE_DEFAULT_API_VERSION = "2024-10-21"


def parse_azure_endpoint(
    api_base: str,
) -> tuple[str, str]:
    """把用户填写的 Azure 地址解析成 (azure_endpoint, api_version)。

    支持 ``https://<resource>.openai.azure.com`` 直填，也兼容从门户复制
    带路径/查询的完整 URL（``?api-version=...`` 优先于内置默认版本）；
    无 scheme 时补 https。
    """
    from urllib.parse import parse_qs, urlsplit, urlunsplit

    raw = api_base.strip()
    if "://" not in raw:
        raw = f"https://{raw}"
    parts = urlsplit(raw)
    version = _AZURE_DEFAULT_API_VERSION
    query = parse_qs(parts.query)
    if "api-version" in query and query["api-version"]:
        version = query["api-version"][0]
    endpoint = urlunsplit((parts.scheme, parts.netloc, "", "", ""))
    return endpoint, version


class LambChatAzureChatModel(AzureChatOpenAI):
    """Time out only the first stream event, not the whole streamed response."""

    first_event_timeout: float | None = Field(default=None, exclude=True)
    non_streaming_timeout: float | None = Field(default=None, exclude=True)
    stream_idle_timeout: float | None = Field(default=None, exclude=True)
    stream_gap_warn_timeout: float | None = Field(default=None, exclude=True)

    async def _astream(self, *args: Any, **kwargs: Any) -> AsyncIterator[ChatGenerationChunk]:
        source = super()._astream(*args, **kwargs)
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
