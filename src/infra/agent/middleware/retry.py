"""Retry and fallback middleware for deep agents."""

from __future__ import annotations

import asyncio
import logging
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
from langchain_core.messages import AIMessage

from src.kernel.config import settings

if TYPE_CHECKING:
    from langchain.agents.middleware.types import ExtendedModelResponse

logger = logging.getLogger(__name__)


def _is_retryable_error(exc: Exception) -> bool:
    """Check if an exception is a transient/retryable LLM error.

    Retries on: RateLimitError (429), 5xx server errors, timeouts,
    APIConnectionError (network/TLS/proxy failures), empty stream,
    and API proxy errors with custom error codes (e.g. code "1234").
    Does NOT retry on: 401/403 auth errors, 400 bad request, 404 not found.
    """
    # LangChain empty stream: LLM returned no chunks at all
    if isinstance(exc, ValueError) and "No generations found in stream" in str(exc):
        return True

    # httpx transient network errors (peer closed, incomplete chunked read, etc.)
    try:
        import httpx

        if isinstance(exc, httpx.RemoteProtocolError):
            return True
    except ImportError:
        pass

    for module in ("anthropic", "openai"):
        try:
            mod = __import__(
                module,
                fromlist=[
                    "RateLimitError",
                    "APITimeoutError",
                    "APIConnectionError",
                    "APIStatusError",
                ],
            )
            if isinstance(exc, mod.RateLimitError):
                return True
            if isinstance(exc, mod.APITimeoutError):
                return True
            if isinstance(exc, mod.APIConnectionError):
                return True
            if isinstance(exc, mod.APIStatusError):
                # Standard 5xx server errors
                if 500 <= exc.status_code < 600:
                    return True
                # API proxy errors with custom error codes (e.g. Chinese proxies
                # returning code "1234" with "网络错误" for transient network issues)
                body = getattr(exc, "body", None)
                if isinstance(body, dict):
                    error_obj = body.get("error", {})
                    if isinstance(error_obj, dict):
                        error_code = error_obj.get("code")
                        error_msg = str(error_obj.get("message", "")).lower()
                        # Known proxy error codes that indicate transient issues
                        if error_code in ("1234",):
                            return True
                        # Network-related keywords in proxy error messages
                        network_keywords = ("网络错误", "network error", "timeout", "overloaded")
                        if any(kw in error_msg for kw in network_keywords):
                            return True
        except (ImportError, AttributeError):
            continue
    return False


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
                streaming=False,
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
            return await handler(new_request)
        except Exception as fallback_exc:
            logger.error(
                "[ModelFallback] Fallback model %s also failed: %s",
                self._fallback_model,
                fallback_exc,
            )
            raise

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

        return last_response  # type: ignore[return-value]


def create_retry_middleware(
    fallback_model: str | None = None,
    thinking: dict | None = None,
) -> list[AgentMiddleware]:
    """Create the retry middleware stack for deep agents.

    Returns [ModelFallbackMiddleware?, ModelRetryMiddleware, EmptyContentRetryMiddleware]:
    - Outer layer (optional): falls back to an alternate model when primary fails
    - Middle layer: retries on 429/5xx/timeout with exponential backoff
    - Inner layer: retries on empty content responses
    """
    stack: list[AgentMiddleware] = []

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
        ]
    )
    return stack
