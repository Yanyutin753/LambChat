"""Google chat-model adapter with streaming inactivity timeouts."""

from __future__ import annotations

from collections.abc import AsyncIterator
from copy import deepcopy
from typing import Any

from google.genai.types import HttpOptions
from langchain_core.callbacks import AsyncCallbackManagerForLLMRun
from langchain_core.messages import BaseMessage
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import Field

from src.infra.llm.quota import QuotaChatMixin, _QuotaResource
from src.infra.llm.streaming import aiter_with_first_event_timeout


class LambChatGoogleChatModel(QuotaChatMixin, ChatGoogleGenerativeAI):
    """Require a timely first stream event without imposing a total deadline."""

    first_event_timeout: float | None = Field(default=None, exclude=True)
    non_streaming_timeout: float | None = Field(default=None, exclude=True)
    stream_idle_timeout: float | None = Field(default=None, exclude=True)
    stream_gap_warn_timeout: float | None = Field(default=None, exclude=True)

    def _format_tools(self, tools: Any = None, functions: Any = None) -> list | None:
        # Gemini removes empty parameter schemas in place; keep shared tools intact.
        return super()._format_tools(deepcopy(tools), deepcopy(functions))

    def _prepare_request(self, messages: list[BaseMessage], **kwargs: Any) -> dict[str, Any]:
        request = super()._prepare_request(messages, **kwargs)
        contents = request.get("contents", [])
        if not any(
            part.inline_data is not None for content in contents for part in content.parts or []
        ):
            return request
        serialized = [
            content.model_dump(mode="json", by_alias=True, exclude_none=True)
            for content in contents
        ]
        for content in serialized:
            for part in content.get("parts", []):
                blob = part.get("inlineData") or part.get("inline_data")
                if blob and isinstance(blob.get("data"), str):
                    blob["data"] = blob["data"].translate(str.maketrans("-_", "+/"))
        config = request["config"]
        options = config.http_options or HttpOptions()
        # extra_body 在 SDK 编码后合并，避免其 URL-safe 字母表被兼容网关拒绝。
        config.http_options = options.model_copy(
            update={"extra_body": {**(options.extra_body or {}), "contents": serialized}}
        )
        return request

    @property
    def async_client(self):
        return _QuotaResource(super().async_client)

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
        kwargs.setdefault("timeout", self.non_streaming_timeout)
        return await super()._agenerate(
            messages,
            stop=stop,
            run_manager=run_manager,
            **kwargs,
        )
