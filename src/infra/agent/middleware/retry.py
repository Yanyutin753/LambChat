"""Retry and fallback middleware for deep agents."""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Any

from langchain.agents.middleware import ModelRetryMiddleware
from langchain.agents.middleware.types import (
    AgentMiddleware,
    ContextT,
    ModelRequest,
    ModelResponse,
    ResponseT,
)
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, ToolMessage

from src.infra.agent.middleware.dead_attachment import (
    DeadAttachmentFilterMiddleware,
    HistoricalImageCapMiddleware,
)
from src.infra.llm.retry import is_retryable_model_error
from src.kernel.config import settings
from src.kernel.errors import AppError, ErrorCode

if TYPE_CHECKING:
    from langchain.agents.middleware.types import ExtendedModelResponse

logger = logging.getLogger(__name__)


def _is_retryable_error(exc: Exception) -> bool:
    """Compatibility wrapper around the canonical model retry predicate."""
    return is_retryable_model_error(exc)


def _is_empty_content(aimessage: AIMessage) -> bool:
    """Check if an AIMessage has no meaningful content.

    Tool-call-only responses and responses with non-empty text are NOT empty.
    Reasoning-only responses are still empty because the user has no final answer yet.
    """
    if getattr(aimessage, "tool_calls", None):
        return False

    content = getattr(aimessage, "content", None)
    if content is None or content == "":
        return True
    if isinstance(content, str):
        return not content.strip()
    if isinstance(content, list):
        return not any(
            block.get("type") == "text" and block.get("text", "").strip()
            for block in content
            if isinstance(block, dict)
        )
    return False


def _is_truncated_response(aimessage: AIMessage) -> bool:
    """Check if a response was truncated (incomplete) based on stop_reason or content cues.

    A response is considered truncated when:
    - stop_reason is not 'end_turn'/'tool_use'/'stop_sequence' (explicit truncation), or
    - stop_reason is absent but the text ends with an incomplete cue (colon, ellipsis)
      and there are no tool_calls (heuristic for connection-drop truncation).
    """
    # Explicit stop_reason check
    metadata = getattr(aimessage, "response_metadata", None)
    if isinstance(metadata, dict):
        stop_reason = metadata.get("stop_reason")
        if stop_reason is not None:
            return stop_reason not in ("end_turn", "tool_use", "stop_sequence")

    # Heuristic: text ends with incomplete cue and no tool_calls
    if getattr(aimessage, "tool_calls", None):
        return False
    content = getattr(aimessage, "content", None)
    text = ""
    if isinstance(content, str):
        text = content.strip()
    elif isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = (block.get("text", "") or "").strip()
                break
    if not text:
        return False
    return text.endswith(("：", ":", "……", "...", "…")) and len(text) > 2


def _extract_messages(
    response: ModelResponse[ResponseT] | AIMessage | ExtendedModelResponse[ResponseT] | Any,
) -> list[Any]:
    """Extract AIMessage list from various response types."""
    if isinstance(response, AIMessage):
        return [response]
    if isinstance(response, ModelResponse):
        return response.result if response.result else []
    if hasattr(response, "model_response"):
        return response.model_response.result if response.model_response.result else []
    return []


def _response_is_invalid(response: Any) -> bool:
    """Check whether a model response should be treated as failed."""
    messages = _extract_messages(response)
    if not messages or not isinstance(messages[0], AIMessage):
        return False
    return _is_empty_content(messages[0]) or _is_truncated_response(messages[0])


class ModelFallbackMiddleware(AgentMiddleware):
    """Middleware that falls back to an alternate model when the primary model fails.

    Wraps the inner retry stack. When all retries on the primary model are exhausted
    (ModelRetryMiddleware gives up via ``on_failure="error"``) and the inner
    handler raises an error, this middleware creates a fallback LLM and
    replays the request once.
    """

    def __init__(self, *, fallback_model: str, thinking: dict | None = None) -> None:
        super().__init__()
        self._fallback_model = fallback_model
        self._thinking = thinking
        self._fallback_llm: BaseChatModel | None = None

    async def _get_fallback_llm(self) -> BaseChatModel:
        """Lazily create the fallback LLM instance."""
        if self._fallback_llm is None:
            from src.infra.llm.client import LLMClient

            self._fallback_llm = await LLMClient.get_model(
                model=self._fallback_model,
                thinking=self._thinking,
            )
            logger.info("[ModelFallback] Created fallback LLM: %s", self._fallback_model)
        return self._fallback_llm

    async def _invoke_fallback(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
        reason: str,
    ) -> ModelResponse[ResponseT]:
        logger.warning(
            "[ModelFallback] Primary model failed: %s — falling back to %s",
            reason,
            self._fallback_model,
        )

        fallback_llm = await self._get_fallback_llm()
        new_request = request.override(model=fallback_llm)
        try:
            response = await handler(new_request)
        except Exception as fallback_exc:
            logger.error(
                "[ModelFallback] Fallback model %s also failed: %s",
                self._fallback_model,
                fallback_exc,
            )
            raise
        # 防御：兜底结果若仍是空正文（内层 EmptyContentRetry 负责上抛，这里
        # 兜住中间件栈被重构后的漏网路径），同样按失败上抛，绝不静默放行。
        fallback_messages = _extract_messages(response)
        if (
            fallback_messages
            and isinstance(fallback_messages[0], AIMessage)
            and _is_empty_content(fallback_messages[0])
        ):
            logger.error(
                "[ModelFallback] Fallback model %s also returned empty content",
                self._fallback_model,
            )
            raise AppError(ErrorCode.MODEL_EMPTY_RESPONSE)
        return response

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT]:
        try:
            response = await handler(request)
        except Exception as exc:
            return await self._invoke_fallback(request, handler, str(exc))

        if _response_is_invalid(response):
            messages = _extract_messages(response)
            ai_message = messages[0]
            reason = "truncated content" if _is_truncated_response(ai_message) else "empty content"
            return await self._invoke_fallback(request, handler, reason)

        return response


class EmptyContentRetryMiddleware(AgentMiddleware):
    """Middleware that retries model calls returning empty content."""

    def __init__(self, *, max_retries: int = 1, retry_delay: float = 1.0) -> None:
        super().__init__()
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT] | AIMessage | ExtendedModelResponse[ResponseT]:
        last_response = None
        for attempt in range(self.max_retries + 1):
            response = await handler(request)
            last_response = response

            messages = _extract_messages(response)
            if not messages or not isinstance(messages[0], AIMessage):
                break

            if not _is_empty_content(messages[0]) and not _is_truncated_response(messages[0]):
                return response

            reason = "truncated" if _is_truncated_response(messages[0]) else "empty"
            logger.warning(
                "%s content in model response (attempt %d/%d)",
                reason.capitalize(),
                attempt + 1,
                self.max_retries + 1,
            )
            if attempt < self.max_retries:
                await asyncio.sleep(self.retry_delay)

        # 重试耗尽仍是空正文（thinking-only / 完全空）→ 按模型调用失败上抛：
        # 外层 ModelFallback 换兜底模型重放；兜底也空时任务进入 error 终态。
        # 绝不静默返回空回答把 run 假装 completed（2026-09-05 生产事故：
        # 续跑后 4 次空正文被放行，done(completed) 但用户拿不到答案）。
        # 截断启发式命中的半截回答不上抛——部分内容已流出，保留给用户。
        final_messages = _extract_messages(last_response)
        if (
            final_messages
            and isinstance(final_messages[0], AIMessage)
            and _is_empty_content(final_messages[0])
        ):
            raise AppError(ErrorCode.MODEL_EMPTY_RESPONSE)
        return last_response  # type: ignore[return-value]


class UniqueResponseIdMiddleware(AgentMiddleware):
    """Ensure model response ids stay unique within the conversation.

    部分上游中转（如 ChatGPT 反代）会在同一会话的多次补全里返回重复或恒定的
    响应 id，甚至原样重放同一条 tool_call。deepagents 的 messages 通道
    （DeltaChannel reducer）按 id 去重——同 id 的新 AIMessage 会原位替换历史
    消息；重复的 tool_call id 则会被已有 ToolMessage"回答"。两者都会让
    model→tools 路由误判"所有 tool_calls 已被回答"，走进 destinations 里不存在
    的 ``"model"``，整个 run 以 ``KeyError: 'model'`` 崩溃（2026-08-25 生产
    6 例）。这里在响应进入 state 前改写冲突的响应 id 与 tool_call id。
    """

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT]:
        response = await handler(request)

        state_messages = (request.state or {}).get("messages", [])
        existing_ids = {message.id for message in state_messages if getattr(message, "id", None)}
        answered_call_ids = {
            message.tool_call_id for message in state_messages if isinstance(message, ToolMessage)
        }

        for message in _extract_messages(response):
            if not isinstance(message, AIMessage):
                continue
            if not message.id or message.id in existing_ids:
                message.id = str(uuid.uuid4())
            for tool_call in message.tool_calls:
                if tool_call["id"] in answered_call_ids:
                    tool_call["id"] = f"call_{uuid.uuid4().hex[:24]}"

        return response


def create_retry_middleware(
    fallback_model: str | None = None,
    thinking: dict | None = None,
) -> list[AgentMiddleware[Any, Any, Any]]:
    """Create the retry middleware stack for deep agents.

    Returns [DeadAttachmentFilterMiddleware, HistoricalImageCapMiddleware,
    ModelFallbackMiddleware?, ModelRetryMiddleware, EmptyContentRetryMiddleware,
    UniqueResponseIdMiddleware]:
    - Outermost layer: drops image blocks whose uploaded file was deleted
      (dead URLs make upstream token counting fail the whole request)
    - Cap layer: replaces overly numerous historical images with URL placeholders
    - Fallback layer (optional): falls back to an alternate model when primary fails
    - Middle layer: retries on 429/5xx/timeout with exponential backoff
    - Inner layer: retries on empty content responses
    - Innermost layer: rewrites replayed/empty response ids so add_messages
      always appends (prevents KeyError 'model' routing crashes)
    """
    stack: list[AgentMiddleware[Any, Any, Any]] = [
        DeadAttachmentFilterMiddleware(),
        HistoricalImageCapMiddleware(),
    ]

    if fallback_model:
        stack.append(ModelFallbackMiddleware(fallback_model=fallback_model, thinking=thinking))

    stack.extend(
        [
            ModelRetryMiddleware(
                max_retries=settings.LLM_MAX_RETRIES,
                retry_on=_is_retryable_error,
                on_failure="error",
                backoff_factor=2.0,
                initial_delay=settings.LLM_RETRY_DELAY,
                max_delay=60.0,
                jitter=True,
            ),
            EmptyContentRetryMiddleware(
                max_retries=settings.LLM_MAX_RETRIES, retry_delay=settings.LLM_RETRY_DELAY
            ),
            UniqueResponseIdMiddleware(),
        ]
    )
    return stack
