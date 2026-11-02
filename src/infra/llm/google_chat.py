"""Google chat-model adapter with streaming inactivity timeouts."""

from __future__ import annotations

from collections.abc import AsyncIterator
from copy import deepcopy
from typing import Any

from google.genai.types import HttpOptions
from langchain_core.callbacks import AsyncCallbackManagerForLLMRun
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import Field

from src.infra.llm.quota import QuotaChatMixin, _QuotaResource
from src.infra.llm.reasoning_patch import reasoning_text_from_message
from src.infra.llm.streaming import aiter_with_first_event_timeout

# langchain_google_genai 认定的原生来源；其余 provider 的思考块无法以 Gemini
# thought part 回放，会在消息转换时被静默丢弃（_REASONING_BLOCK_TYPES）。
_NATIVE_MODEL_PROVIDERS = frozenset({"google_genai", "google_vertexai"})
_DROPPED_REASONING_BLOCK_TYPES = frozenset({"reasoning", "thinking", "reasoning_content"})


def _downgrade_foreign_reasoning(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Replay foreign-provider reasoning as plain text for the Gemini lane.

    A session whose earlier turns ran on the anthropic/openai lanes carries
    thinking blocks or ``reasoning_content`` kwargs that Gemini cannot replay
    as thought parts; without this they are dropped silently and the model
    loses its own prior reasoning. Native Gemini thoughts are left untouched.
    """
    normalized: list[BaseMessage] = []
    for message in messages:
        replacement = None
        if isinstance(message, AIMessage):
            provider = message.response_metadata.get("model_provider")
            if provider is not None and provider not in _NATIVE_MODEL_PROVIDERS:
                replacement = _foreign_reasoning_as_text_blocks(message)
        normalized.append(replacement if replacement is not None else message)
    return normalized


def _foreign_reasoning_as_text_blocks(message: AIMessage) -> AIMessage | None:
    content = message.content
    reasoning = reasoning_text_from_message(message)
    if isinstance(content, str):
        removed = False
        blocks: list[Any] = [{"type": "text", "text": content}] if content else []
    elif isinstance(content, list):
        blocks = [
            block
            for block in content
            if not (isinstance(block, dict) and block.get("type") in _DROPPED_REASONING_BLOCK_TYPES)
        ]
        removed = len(blocks) != len(content)
    else:
        return None
    if not removed and not reasoning.strip():
        return None
    if reasoning.strip():
        new_content = [{"type": "text", "text": reasoning}, *blocks]
    else:
        new_content = blocks
    if new_content == content:
        return None
    return message.model_copy(update={"content": new_content})


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
        request = super()._prepare_request(_downgrade_foreign_reasoning(messages), **kwargs)
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
