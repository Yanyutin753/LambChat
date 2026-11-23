"""OpenAI chat-model adapter with a first-event streaming deadline."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from hashlib import sha256
from typing import Any
from urllib.parse import urlparse
from uuid import uuid4

from langchain_core.callbacks import AsyncCallbackManagerForLLMRun
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGenerationChunk, ChatResult
from langchain_openai import ChatOpenAI
from pydantic import Field

from src.infra.llm.providers import is_zhipu_thinking_model
from src.infra.llm.quota import QuotaChatMixin
from src.infra.llm.responses_cache import current_responses_prompt_cache_key
from src.infra.llm.streaming import aiter_with_first_event_timeout
from src.infra.logging.context import TraceContext
from src.kernel.config import settings

_OPENAI_OFFICIAL_HOSTS = frozenset({"api.openai.com"})

# Responses API 的输出 item 自带这些只读字段，回传 input 时任何合规端点都不接受
_RESPONSES_INPUT_READONLY_FIELDS = ("status",)


def chat_file_url_references(messages: list[BaseMessage]) -> list[BaseMessage]:
    """Keep unsupported file URLs as references without rewriting saved history."""
    result = []
    for message in messages:
        if not isinstance(message.content, list):
            result.append(message)
            continue
        content: list[str | dict[str, Any]] = []
        changed = False
        for block in message.content:
            if (
                isinstance(block, dict)
                and block.get("type") == "file"
                and isinstance(block.get("url"), str)
                and "base64" not in block
                and "file_id" not in block
                and block.get("source_type") not in ("base64", "id")
            ):
                content.append(
                    {"type": "text", "text": f"File URL (contents not included): {block['url']}"}
                )
                changed = True
            else:
                content.append(block)
        result.append(message.model_copy(update={"content": content}) if changed else message)
    return result


def strip_readonly_responses_input_fields(payload: dict) -> dict:
    """剥离回传历史 item 顶层的只读输出字段（就地修改）。

    上游 Responses API 的输出 item（reasoning / function_call 等）带
    ``status`` 等只读字段，langchain 经 ``model_dump`` 原样存进消息历史，
    下一轮全量重放时被带回 ``input`` 数组，严格校验的端点会以 400
    ``unknown_parameter`` 拒绝整个请求（生产 2026-09-17：``input[13].status``，
    该会话每轮先 400 再 fallback，首字时间 ~7s）。``status`` 不是任何
    input item 的合法字段，剥离无条件执行。

    同时归一化 ``summary`` 形状：合法 input 的 reasoning item 要求
    ``summary`` 为数组；历史里存成字符串/字典等形状时，严格端点以 400
    ``expected an array`` 拒绝整个请求（生产 2026-11-17：
    ``input[3].summary``）。字符串或单个 summary_text 对象包成数组，
    缺失、null 或无法恢复的形状补为空数组；该字段不能省略。
    """
    input_items = payload.get("input")
    if not isinstance(input_items, list):
        return payload
    for item in input_items:
        if isinstance(item, dict):
            for field in _RESPONSES_INPUT_READONLY_FIELDS:
                item.pop(field, None)
            if item.get("type") == "reasoning":
                summary = item.get("summary")
                if isinstance(summary, str):
                    item["summary"] = [{"type": "summary_text", "text": summary}]
                elif (
                    isinstance(summary, dict)
                    and summary.get("type") == "summary_text"
                    and isinstance(summary.get("text"), str)
                ):
                    item["summary"] = [summary]
                elif not isinstance(summary, list):
                    item["summary"] = []
    return payload


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


class LambChatOpenAIChatModel(QuotaChatMixin, ChatOpenAI):
    """Time out only the first stream event, not the whole streamed response."""

    first_event_timeout: float | None = Field(default=None, exclude=True)
    non_streaming_timeout: float | None = Field(default=None, exclude=True)
    stream_idle_timeout: float | None = Field(default=None, exclude=True)
    stream_gap_warn_timeout: float | None = Field(default=None, exclude=True)
    opencode_session_header: bool = Field(default=False, exclude=True)

    def _get_request_payload(
        self, input_: Any, *, stop: list[str] | None = None, **kwargs: Any
    ) -> dict:
        messages = self._convert_input(input_).to_messages()
        if not self._use_responses_api({**self._default_params, **kwargs}):
            messages = chat_file_url_references(messages)
        payload = super()._get_request_payload(messages, stop=stop, **kwargs)
        if self.opencode_session_header:
            headers = payload.get("extra_headers") or {}
            if not any(header.lower() == "x-opencode-session" for header in headers):
                user_id = TraceContext.get_user_id()
                session_id = TraceContext.get_session_id()
                # Keep routing stable within a conversation without exposing internal IDs.
                if user_id and session_id:
                    route_id = sha256(f"{user_id}\0{session_id}".encode()).hexdigest()[:32]
                else:
                    route_id = uuid4().hex
                payload["extra_headers"] = {**headers, "x-opencode-session": f"ses_{route_id}"}
        # 历史回传的 reasoning/function_call 等输出 item 带 status 只读字段，
        # 严格校验的端点会整体 400（生产 2026-09-17：input[13].status），
        # 在统一出口剥离后再注入其余字段。
        strip_readonly_responses_input_fields(payload)
        from src.infra.llm.reasoning_patch import (
            is_deepseek_thinking_model,
            reasoning_text_from_message,
        )

        for source, message in zip(messages, payload.get("messages", [])):
            if message.get("role") != "assistant":
                continue
            if is_deepseek_thinking_model(self.model_name):
                # Missing cross-model reasoning is valid as an empty field.
                reasoning = reasoning_text_from_message(source)
                message["reasoning_content"] = reasoning
            elif is_zhipu_thinking_model(self.model_name):
                if reasoning := reasoning_text_from_message(source):
                    message["reasoning_content"] = reasoning
            elif not self.model_name.lower().startswith("deepseek"):
                message.pop("reasoning_content", None)
        if "input" in payload and is_deepseek_thinking_model(self.model_name):
            from langchain_openai.chat_models.base import _construct_responses_api_input

            # DeepSeek requires a nonempty field during tool continuation; missing history is whitespace.
            items = []
            for source in messages:
                if isinstance(source, AIMessage):
                    items.append(
                        {
                            "type": "reasoning",
                            "content": [
                                {
                                    "type": "reasoning_text",
                                    "text": reasoning_text_from_message(source) or " ",
                                }
                            ],
                        }
                    )
                items.extend(
                    item
                    for item in _construct_responses_api_input([source], store=False)
                    if item.get("type") != "reasoning"
                )
            payload["input"] = items
            payload.pop("include", None)
            strip_readonly_responses_input_fields(payload)
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
