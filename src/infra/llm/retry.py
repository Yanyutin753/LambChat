"""Retry helpers for LLM calls made outside the agent middleware stack."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Iterator
from typing import Any

import httpx

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
                if 500 <= exc.status_code < 600:
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
            return getattr(exc, "code", None) == 429
    except (ImportError, AttributeError):
        pass
    return False


def is_retryable_model_error(exc: BaseException) -> bool:
    """Return whether an LLM failure is transient and safe to retry."""
    for current in _exception_chain(exc):
        if isinstance(current, ValueError) and "No generations found in stream" in str(current):
            return True
        if isinstance(current, TimeoutError):
            return True
        if isinstance(current, httpx.TransportError):
            return True
        if _is_provider_retryable_error(current):
            return True
    return False


async def ainvoke_with_retry(
    model: Any,
    prompt: Any,
    *,
    max_retries: int | None = None,
    retry_delay: float | None = None,
    operation: str = "model",
    retry_if: Callable[[BaseException], bool] = is_retryable_model_error,
    **kwargs: Any,
) -> Any:
    """Invoke a model once plus ``max_retries`` retries on transient failures."""
    retries = settings.LLM_MAX_RETRIES if max_retries is None else max(0, max_retries)
    base_delay = settings.LLM_RETRY_DELAY if retry_delay is None else max(0, retry_delay)

    for attempt in range(retries + 1):
        try:
            return await model.ainvoke(prompt, **kwargs)
        except Exception as exc:
            if attempt >= retries or not retry_if(exc):
                raise
            delay = base_delay * (2**attempt)
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
