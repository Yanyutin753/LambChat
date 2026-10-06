"""Retry helpers for LLM calls made outside the agent middleware stack."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Iterator
from typing import Any

import httpx
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import AIMessage
from langchain_core.runnables.config import ensure_config, merge_configs

from src.kernel.config import settings

logger = logging.getLogger(__name__)


def _exception_chain(exc: BaseException) -> Iterator[BaseException]:
    """Walk wrapped and grouped exceptions without visiting an error twice."""
    pending = [exc]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        yield current

        if isinstance(current, BaseExceptionGroup):
            pending.extend(current.exceptions)
        if current.__cause__ is not None:
            pending.append(current.__cause__)
        elif current.__context__ is not None:
            pending.append(current.__context__)


def _is_provider_retryable_error(exc: BaseException) -> bool:
    for module_name in ("anthropic", "openai"):
        try:
            module = __import__(
                module_name,
                fromlist=[
                    "RateLimitError",
                    "APITimeoutError",
                    "APIConnectionError",
                    "APIStatusError",
                ],
            )
            if isinstance(
                exc,
                (module.RateLimitError, module.APITimeoutError, module.APIConnectionError),
            ):
                return True
            if isinstance(exc, module.APIStatusError):
                if exc.status_code in (408, 409, 429) or 500 <= exc.status_code < 600:
                    return True
                body = getattr(exc, "body", None)
                if isinstance(body, dict):
                    error = body.get("error", {})
                    if isinstance(error, dict):
                        code = error.get("code")
                        message = str(error.get("message", "")).lower()
                        if code == "1234":
                            return True
                        keywords = ("网络错误", "network error", "timeout", "overloaded")
                        if any(keyword in message for keyword in keywords):
                            return True
        except (ImportError, AttributeError):
            continue

    try:
        from google.genai import errors as google_errors

        if isinstance(exc, google_errors.ServerError):
            return True
        if isinstance(exc, google_errors.ClientError):
            return getattr(exc, "code", None) in (408, 409, 429)
    except (ImportError, AttributeError):
        pass
    return False


def is_retryable_model_error(exc: BaseException) -> bool:
    """Return whether an LLM failure is transient and safe to retry."""
    for current in _exception_chain(exc):
        if isinstance(current, ValueError) and "No generations found in stream" in str(current):
            return True
        if isinstance(current, EmptyModelResponseError):
            return True
        if isinstance(current, httpx.HTTPStatusError):
            status = current.response.status_code
            if status in (408, 409, 429) or 500 <= status < 600:
                return True
        if isinstance(current, TimeoutError):
            return True
        if isinstance(current, httpx.TransportError):
            return True
        if _is_provider_retryable_error(current):
            return True
    return False


def _is_provider_auth_error(exc: BaseException) -> bool:
    for module_name in ("anthropic", "openai"):
        try:
            module = __import__(
                module_name,
                fromlist=["AuthenticationError", "PermissionDeniedError", "APIStatusError"],
            )
            if isinstance(exc, (module.AuthenticationError, module.PermissionDeniedError)):
                return True
            if isinstance(exc, module.APIStatusError) and exc.status_code in (401, 403):
                return True
        except (ImportError, AttributeError):
            continue

    try:
        from google.genai import errors as google_errors

        if isinstance(exc, google_errors.ClientError) and getattr(exc, "code", None) in (401, 403):
            return True
    except (ImportError, AttributeError):
        pass
    return False


def is_auth_model_error(exc: BaseException) -> bool:
    """Return whether an LLM failure is an auth failure (HTTP 401/403).

    Auth failures are never transient for the same credential: retrying the
    same model is pointless, but switching to another model (a different key)
    can still succeed. Callers use this to trigger model fallback directly
    instead of surfacing the raw 401/403 to the user.
    """
    for current in _exception_chain(exc):
        if isinstance(current, httpx.HTTPStatusError) and current.response.status_code in (
            401,
            403,
        ):
            return True
        if _is_provider_auth_error(current):
            return True
        # 部分中转/包装层把上游鉴权失败重写成普通异常，仅保留 SDK 文案
        if "Error code: 401 -" in str(current) or "Error code: 403 -" in str(current):
            return True
    return False


class EmptyModelResponseError(RuntimeError):
    """A completed model call returned no final answer or tool calls."""


class _ModelOutputTracker(AsyncCallbackHandler):
    """Never replay an invocation after its stream has delivered content."""

    def __init__(self) -> None:
        self.emitted = False

    async def on_llm_new_token(
        self, token: str | list[str | dict[str, Any]], *, chunk: Any = None, **kwargs: Any
    ) -> None:
        message = getattr(chunk, "message", None)
        if token or (
            message is not None and (message.content or getattr(message, "tool_call_chunks", None))
        ):
            self.emitted = True


def _empty_answer(response: Any) -> bool:
    if not isinstance(response, AIMessage) or response.tool_calls:
        return False
    content = response.content
    if isinstance(content, str):
        return not content.strip()
    return not any(
        (isinstance(block, str) and block.strip())
        or (
            isinstance(block, dict)
            and block.get("type") == "text"
            and block.get("text", "").strip()
        )
        for block in content
    )


async def ainvoke_with_retry(
    model: Any,
    prompt: Any,
    *,
    max_retries: int | None = None,
    retry_delay: float | None = None,
    operation: str = "model",
    retry_if: Callable[[BaseException], bool] = is_retryable_model_error,
    fallback_model: str | None = None,
    thinking: dict | None = None,
    **kwargs: Any,
) -> Any:
    """Retry transient/empty calls, then use the configured fallback once.

    The same policy covers every protocol. Cancellation propagates immediately;
    once streamed content is delivered, failures propagate instead of replaying it.
    """
    retries = settings.LLM_MAX_RETRIES if max_retries is None else max(0, max_retries)
    base_delay = settings.LLM_RETRY_DELAY if retry_delay is None else max(0, retry_delay)
    tracker = _ModelOutputTracker()
    config = ensure_config(kwargs.get("config"))
    if "config" in kwargs or config.get("callbacks"):
        kwargs["config"] = merge_configs(config, {"callbacks": [tracker]})

    for attempt in range(retries + 1):
        try:
            response = await model.ainvoke(prompt, **kwargs)
            if _empty_answer(response) and not tracker.emitted:
                raise EmptyModelResponseError("Model returned no final answer")
            return response
        except Exception as exc:
            if tracker.emitted:
                raise
            retryable = retry_if(exc)
            if attempt >= retries or not retryable:
                if fallback_model and (retryable or is_auth_model_error(exc)):
                    from src.infra.llm.client import LLMClient

                    logger.warning(
                        "[%s] primary failed with %s; switching to fallback",
                        operation,
                        type(exc).__name__,
                    )
                    # Cross-model histories lack the primary model's reasoning blocks.
                    fallback = await LLMClient.get_model(model=fallback_model, thinking=None)
                    return await ainvoke_with_retry(
                        fallback,
                        prompt,
                        max_retries=retries,
                        retry_delay=base_delay,
                        operation=operation,
                        retry_if=retry_if,
                        **kwargs,
                    )
                raise
            delay = min(base_delay * (2**attempt), 60.0)
            logger.warning(
                "[%s] model call failed with %s (attempt %d/%d); retrying in %.1fs",
                operation,
                type(exc).__name__,
                attempt + 1,
                retries + 1,
                delay,
            )
            if delay > 0:
                await asyncio.sleep(delay)

    raise AssertionError("unreachable")
