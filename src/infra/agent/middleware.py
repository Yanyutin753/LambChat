"""DeepAgent retry middleware for handling transient LLM errors and empty responses."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from langchain_core.messages import AIMessage
from langchain.agents.middleware import ModelRetryMiddleware
from langchain.agents.middleware.types import (
    AgentMiddleware,
    ContextT,
    ModelRequest,
    ModelResponse,
    ResponseT,
)

from src.kernel.config import settings

if TYPE_CHECKING:
    from langchain.agents.middleware.types import ExtendedModelResponse

logger = logging.getLogger(__name__)


def _is_retryable_error(exc: Exception) -> bool:
    """Check if an exception is a transient/retryable LLM error.

    Retries on: RateLimitError (429), 5xx server errors, timeouts,
    empty stream (No generations found in stream).
    Does NOT retry on: 401/403 auth errors, 400 bad request, 404 not found.
    """
    # LangChain empty stream: LLM returned no chunks at all
    if isinstance(exc, ValueError) and "No generations found in stream" in str(exc):
        return True

    for module in ("anthropic", "openai"):
        try:
            mod = __import__(
                module, fromlist=["RateLimitError", "APITimeoutError", "APIStatusError"]
            )
            if isinstance(exc, mod.RateLimitError):
                return True
            if isinstance(exc, mod.APITimeoutError):
                return True
            if isinstance(exc, mod.APIStatusError) and 500 <= exc.status_code < 600:
                return True
        except (ImportError, AttributeError):
            continue
    return False


def _is_empty_content(aimessage: AIMessage) -> bool:
    """Check if an AIMessage has no meaningful content.

    Tool-call-only responses and responses with non-empty text are NOT empty.
    Thinking-only responses (no text, no tool calls) ARE considered empty.
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


class EmptyContentRetryMiddleware(AgentMiddleware):
    """Middleware that retries model calls returning empty content."""

    def __init__(self, *, max_retries: int = 1, retry_delay: float = 1.0) -> None:
        super().__init__()
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.tools: list = []

    def _extract_messages(
        self,
        response: (ModelResponse[ResponseT] | AIMessage | ExtendedModelResponse[ResponseT]),
    ) -> list:
        """Extract AIMessage list from various response types."""
        if isinstance(response, AIMessage):
            return [response]
        if isinstance(response, ModelResponse):
            return response.result if response.result else []
        if hasattr(response, "model_response"):
            return response.model_response.result if response.model_response.result else []
        return []

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT] | AIMessage | ExtendedModelResponse[ResponseT]:
        last_response = None
        for attempt in range(self.max_retries + 1):
            response = await handler(request)
            last_response = response

            messages = self._extract_messages(response)
            if not messages or not isinstance(messages[0], AIMessage):
                break

            if not _is_empty_content(messages[0]):
                return response

            logger.warning(
                "Empty content in model response (attempt %d/%d)",
                attempt + 1,
                self.max_retries + 1,
            )
            if attempt < self.max_retries:
                await asyncio.sleep(self.retry_delay)

        return last_response  # type: ignore[return-value]


def create_retry_middleware() -> list[AgentMiddleware]:
    """Create the retry middleware stack for deep agents.

    Returns [ModelRetryMiddleware, EmptyContentRetryMiddleware]:
    - Outer layer: retries on 429/5xx/timeout with exponential backoff
    - Inner layer: retries on empty content responses
    """
    return [
        ModelRetryMiddleware(
            max_retries=settings.LLM_MAX_RETRIES,
            retry_on=_is_retryable_error,
            on_failure="continue",
            backoff_factor=2.0,
            initial_delay=settings.LLM_RETRY_DELAY,
            max_delay=60.0,
            jitter=True,
        ),
        EmptyContentRetryMiddleware(
            max_retries=settings.LLM_MAX_RETRIES, retry_delay=settings.LLM_RETRY_DELAY
        ),
    ]
