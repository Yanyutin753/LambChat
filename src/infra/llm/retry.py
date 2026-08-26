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
        if _is_provider_auth_error(current):
            return True
        # 部分中转/包装层把上游鉴权失败重写成普通异常，仅保留 SDK 文案
        if "Error code: 401 -" in str(current) or "Error code: 403 -" in str(current):
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
