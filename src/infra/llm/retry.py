"""Retry helpers for LLM calls made outside the agent middleware stack."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable, Iterator
from typing import Any

import httpx
from langchain_core.callbacks import AsyncCallbackHandler
from langchain_core.messages import AIMessage
from langchain_core.runnables.config import ensure_config, merge_configs

from src.kernel.config import settings

try:
    import httpx2 as provider_httpx
except ImportError:
    import httpx as provider_httpx  # type: ignore[no-redef]

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


def _error_status(exc: BaseException | None) -> int | None:
    """Extract the first plausible HTTP status from an exception chain."""
    if exc is None:
        return None
    for current in _exception_chain(exc):
        candidate = (
            getattr(current, "status_code", None)
            or getattr(getattr(current, "response", None), "status_code", None)
            or getattr(current, "code", None)
        )
        if type(candidate) is int and 100 <= candidate <= 599:
            return candidate
    return None


def is_rate_limit_model_error(exc: BaseException) -> bool:
    """Return whether an LLM failure is a 429 rate limit.

    Rate-limit windows rarely clear within the retry backoff horizon, so droppable
    auxiliary features use this to skip retries instead of burning quota.
    """
    return _error_status(exc) == 429


def is_retryable_model_error(exc: BaseException) -> bool:
    """Return whether an LLM failure is transient and safe to retry."""
    for current in _exception_chain(exc):
        if isinstance(current, ValueError) and "No generations found in stream" in str(current):
            return True
        if isinstance(current, EmptyModelResponseError):
            return True
        if isinstance(current, (httpx.HTTPStatusError, provider_httpx.HTTPStatusError)):
            status = current.response.status_code
            if status in (408, 409, 429) or 500 <= status < 600:
                return True
        if isinstance(current, TimeoutError):
            return True
        if isinstance(current, (httpx.TransportError, provider_httpx.TransportError)):
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
        if isinstance(
            current, (httpx.HTTPStatusError, provider_httpx.HTTPStatusError)
        ) and current.response.status_code in (
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


_CONTENT_MODERATION_MARKERS = (
    "content exists risk",  # DeepSeek 风控拒绝
    "content filter",
    "content_policy_violation",
    "content management policy",
)


def content_moderation_message(exc: BaseException) -> str | None:
    """Classify upstream content-moderation rejections and return a user-facing message.

    这类 4xx 是对请求内容本身的终审判决:换通道重试没有意义,而上游原始 JSON
    (含 request_id 与内部错误结构)不应透传给用户。命中标记返回固定文案,
    否则返回 None 由调用方保持原有行为。
    """
    if _error_status(exc) not in (400, 403):
        return None
    for current in _exception_chain(exc):
        text = str(current).lower()
        if any(marker in text for marker in _CONTENT_MODERATION_MARKERS):
            return (
                "The message was blocked by the model provider's safety policy. "
                "Please rephrase it or switch to another model and try again."
            )
    return None


def _unwrap_model(model: Any) -> Any:
    """Follow wrapper layers (binding/sequence/parallel) down to the underlying chat model.

    ``with_structured_output`` 返回 RunnableSequence/RunnableParallel,模型元数据
    (名称/provider/协议/quota 标注)在包装层上不可见,失败日志会整体退化为
    ``model=unknown provider=unknown``(issue #1123)。
    """
    from langchain_core.runnables import RunnableParallel, RunnableSequence

    for _ in range(4):
        bound = getattr(model, "bound", None)
        if bound is not None:
            model = bound
            continue
        if isinstance(model, RunnableSequence):
            model = model.first
            continue
        if isinstance(model, RunnableParallel):
            branches = getattr(model, "steps__", None)
            if isinstance(branches, dict) and branches:
                model = next(iter(branches.values()))
                continue
        break
    return model


def model_failure_reason(exc: BaseException | None) -> str:
    """Classify a model failure into a bounded reason label."""
    if exc is None:
        return "invalid_output"
    if is_auth_model_error(exc):
        return "auth"
    if _error_status(exc) == 429:
        return "rate_limit"
    if is_retryable_model_error(exc):
        return "transient"
    return "error"


class EmptyModelResponseError(RuntimeError):
    """A completed model call returned no final answer or tool calls."""


def model_failure_context(model: Any, exc: BaseException | None = None) -> str:
    """Bounded diagnostic labels; never serialize clients, URLs or upstream error bodies."""
    model = _unwrap_model(model)

    def label(value: Any) -> str:
        if (
            isinstance(value, str)
            and re.fullmatch(r"[\w./:+-]{1,160}", value)
            and "://" not in value
        ):
            return value
        return "unknown"

    status = _error_status(exc)
    reason = model_failure_reason(exc)
    fields = {
        "model": model
        if isinstance(model, str)
        else getattr(model, "model_name", None) or getattr(model, "model", None),
        "model_config_id": getattr(model, "quota_model_config_id", None),
        "provider": getattr(model, "quota_provider", None),
        "protocol": getattr(model, "_llm_type", None),
        "status": str(status) if status is not None else "unknown",
        "reason": reason,
        "error_type": type(exc).__name__ if exc is not None else "invalid_output",
    }
    return " ".join(f"{key}={label(value)}" for key, value in fields.items())


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


def _is_output_limit_response(response: AIMessage) -> bool:
    metadata = response.response_metadata
    incomplete = metadata.get("incomplete_details")
    return (
        metadata.get("stop_reason") == "max_tokens"
        or metadata.get("finish_reason") == "length"
        or isinstance(incomplete, dict)
        and incomplete.get("reason") == "max_output_tokens"
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
    prepare_fallback_prompt: Callable[[str], Awaitable[Any]] | None = None,
    thinking: dict | None = None,
    tools: list | None = None,
    **kwargs: Any,
) -> Any:
    """Retry transient/empty calls, then use the configured fallback once.

    The same policy covers every protocol. Cancellation propagates immediately;
    once streamed content is delivered, failures propagate instead of replaying it.
    """
    retries = settings.LLM_MAX_RETRIES if max_retries is None else max(0, max_retries)
    base_delay = settings.LLM_RETRY_DELAY if retry_delay is None else max(0, retry_delay)
    if tools:
        try:
            model = model.bind_tools(tools)
        except NotImplementedError:
            logger.info("[%s] model does not support tool binding", operation)
    tracker = _ModelOutputTracker()
    config = ensure_config(kwargs.get("config"))
    if "config" in kwargs or config.get("callbacks"):
        kwargs["config"] = merge_configs(config, {"callbacks": [tracker]})

    for attempt in range(retries + 1):
        output_limited = False
        try:
            response = await model.ainvoke(prompt, **kwargs)
            if _empty_answer(response) and not tracker.emitted:
                output_limited = _is_output_limit_response(response)
                if output_limited:
                    logger.warning(
                        "[%s] output limit reached; not retrying the same budget", operation
                    )
                    if not fallback_model:
                        return response
                raise EmptyModelResponseError("Model returned no final answer")
            return response
        except Exception as exc:
            if tracker.emitted:
                raise
            retryable = not output_limited and retry_if(exc)
            if attempt >= retries or not retryable:
                if fallback_model and (retryable or output_limited or is_auth_model_error(exc)):
                    from src.infra.llm.client import LLMClient

                    logger.warning(
                        "[%s] primary failed: %s; switching to fallback %s",
                        operation,
                        model_failure_context(model, exc),
                        fallback_model,
                    )
                    # Cross-model histories lack the primary model's reasoning blocks.
                    fallback = await LLMClient.get_model(model=fallback_model, thinking=None)
                    fallback_prompt = (
                        await prepare_fallback_prompt(fallback_model)
                        if prepare_fallback_prompt is not None
                        else prompt
                    )
                    return await ainvoke_with_retry(
                        fallback,
                        fallback_prompt,
                        max_retries=retries,
                        retry_delay=base_delay,
                        operation=operation,
                        retry_if=retry_if,
                        tools=tools,
                        **kwargs,
                    )
                raise
            delay = min(base_delay * (2**attempt), 60.0)
            logger.warning(
                "[%s] model call failed: %s (attempt %d/%d); retrying in %.1fs",
                operation,
                model_failure_context(model, exc),
                attempt + 1,
                retries + 1,
                delay,
            )
            if delay > 0:
                await asyncio.sleep(delay)

    raise AssertionError("unreachable")
