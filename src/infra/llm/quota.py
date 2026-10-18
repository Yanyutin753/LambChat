"""Meter provider calls once, including detached auxiliary work and nested streaming."""

from __future__ import annotations

import asyncio
import inspect
import sys
import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar
from functools import wraps
from typing import Any, TypeGuard

from langchain_core.messages import AIMessageChunk
from langchain_core.runnables.config import var_child_runnable_config
from pydantic import Field

from src.infra.pricing.calculator import PriceRates, compute_cost
from src.infra.usage.quota import UsageQuota, user_budgets
from src.kernel.errors import AppError, ErrorCode

_owner: ContextVar[str | None] = ContextVar("usage_quota_owner", default=None)
_active: ContextVar[tuple | None] = ContextVar("usage_quota_call", default=None)
_raw_usage: ContextVar[list[bool | None] | None] = ContextVar(
    "usage_quota_raw_counts", default=None
)
_anthropic_stream_usage: ContextVar[dict | None] = ContextVar(
    "quota_anthropic_stream_usage", default=None
)


def _raw_value(value, key):
    return value.get(key) if isinstance(value, dict) else getattr(value, key, None)


def _record_raw_usage(usage, fields):
    observation = _raw_usage.get()
    if observation is not None:
        observation[0] = all(
            (count := _raw_value(usage, field)) is None or type(count) is int and count >= 0
            for field in fields
        )
        for source, keys in (
            (usage, ("cache_read_input_tokens", "cache_creation_input_tokens")),
            (_raw_value(usage, "prompt_tokens_details"), ("cached_tokens", "cache_write_tokens")),
            (_raw_value(usage, "input_tokens_details"), ("cached_tokens", "cache_write_tokens")),
            (
                _raw_value(usage, "cache_creation"),
                ("ephemeral_5m_input_tokens", "ephemeral_1h_input_tokens"),
            ),
        ):
            if any(
                (count := _raw_value(source, key)) is not None
                and (type(count) is not int or count < 0)
                for key in keys
            ):
                observation[0] = False


def _observe_response(response):
    event = _raw_value(response, "type")
    if event in {"response.completed", "response.incomplete"}:
        _record_raw_usage(
            _raw_value(_raw_value(response, "response"), "usage"), ("input_tokens", "output_tokens")
        )
    elif hasattr(response, "usage_metadata"):
        usage = response.usage_metadata
        _record_raw_usage(
            usage, ("prompt_token_count", "candidates_token_count", "cached_content_token_count")
        )
        for field in ("thoughts_token_count", "tool_use_prompt_token_count"):
            count = _raw_value(usage, field)
            if count is not None and (type(count) is not int or count < 0):
                if (observation := _raw_usage.get()) is not None:
                    observation[0] = False
    elif hasattr(response, "usage"):
        _record_raw_usage(response.usage, ("input_tokens", "output_tokens"))


def _observed_result(value):
    if hasattr(value, "parse"):
        return _QuotaResource(value)
    if hasattr(value, "__aiter__"):
        return _QuotaStream(value)
    _observe_response(value)
    return value


class _QuotaResource:
    """Observe this model's SDK responses without changing shared vendor functions."""

    def __init__(self, resource):
        self.resource = resource

    def __getattr__(self, name):
        value = getattr(self.resource, name)
        if name in {"responses", "with_raw_response", "models"}:
            return _QuotaResource(value)
        if name not in {"create", "parse", "generate_content", "generate_content_stream"}:
            return value

        def call(*args, **kwargs):
            result = value(*args, **kwargs)
            if inspect.isawaitable(result):

                async def resolve():
                    return _observed_result(await result)

                return resolve()
            return _observed_result(result)

        return call


class _QuotaStream:
    def __init__(self, stream):
        self.stream = stream

    def __getattr__(self, name):
        return getattr(self.stream, name)

    async def __aenter__(self):
        await self.stream.__aenter__()
        return self

    async def __aexit__(self, *args):
        return await self.stream.__aexit__(*args)

    async def __aiter__(self):
        async for chunk in self.stream:
            _observe_response(chunk)
            yield chunk


def is_quota_error(error: BaseException) -> TypeGuard[AppError]:
    return isinstance(error, AppError) and error.error_code in {
        ErrorCode.USAGE_QUOTA_EXCEEDED,
        ErrorCode.USAGE_QUOTA_UNAVAILABLE,
        ErrorCode.USAGE_QUOTA_UNPRICED,
    }


def bind_quota_user(function):
    """Bind the payer for foreground helpers and jobs launched with an empty context."""
    signature = inspect.signature(function)

    @wraps(function)
    async def bound(*args, **kwargs):
        user_id = signature.bind(*args, **kwargs).arguments.get("user_id")
        token = _owner.set(user_id)
        try:
            return await function(*args, **kwargs)
        finally:
            _owner.reset(token)

    return bound


def _usage_owner():
    config = var_child_runnable_config.get() or {}
    presenter = (config.get("configurable") or {}).get("presenter")
    payer = quota_user_id()
    presenter_user = getattr(getattr(presenter, "config", None), "user_id", None)
    if payer and presenter_user and payer != presenter_user:
        return None
    return getattr(presenter, "_usage_accounting_owner", None)


def _receipt(reservation, settlement):
    context = reservation.get("context") or {}
    return {
        "call_id": reservation["id"],
        "model": context.get("model") or "",
        "model_id": context.get("model_config_id") or "",
        "provider": context.get("provider") or "",
        **settlement,
    }


def _usage_context():
    from src.infra.logging.context import TraceContext

    config = (var_child_runnable_config.get() or {}).get("configurable") or {}
    payer = quota_user_id()
    if any(
        owner and payer and owner != payer
        for owner in (TraceContext.get_user_id(), config.get("user_id"))
    ):
        return {}
    return {
        "trace_id": TraceContext.get().trace_id or config.get("trace_id"),
        "session_id": TraceContext.get_session_id() or config.get("session_id"),
        "run_id": TraceContext.get_run_id() or config.get("run_id"),
    }


def quota_user_id() -> str | None:
    from src.infra.backend.context import current_user_id
    from src.infra.logging.context import TraceContext

    config = var_child_runnable_config.get() or {}
    return (
        _owner.get()
        or TraceContext.get_user_id()
        or (config.get("configurable") or {}).get("user_id")
        or current_user_id.get()
    )


async def _complete_storage(operation):
    """Finish an accounting write even when the caller is cancelled repeatedly."""
    task = asyncio.ensure_future(operation)
    cancelled = None
    while True:
        try:
            return await asyncio.shield(task), cancelled
        except asyncio.CancelledError as exc:
            if task.done():
                return task.result(), exc
            cancelled = exc


async def _reserve_call(ledger, user_id, budgets, amount, **kwargs):
    call_id = uuid.uuid4().hex
    try:
        reservation, cancelled = await _complete_storage(
            ledger.reserve(user_id, budgets, amount, call_id=call_id, **kwargs)
        )
    except (Exception, asyncio.CancelledError):
        # A lost Mongo acknowledgement can hide a committed, never-started reservation.
        await _complete_storage(ledger.cancel_unstarted(user_id, call_id))
        raise
    if cancelled is not None:
        # No provider code has run, so releasing this reservation is provably safe.
        await _complete_storage(ledger.settle(reservation, 0))
        raise cancelled
    return reservation


@asynccontextmanager
async def unpriced_usage():
    """Paid APIs without a reliable USD tariff cannot bypass a configured budget."""
    user_id = quota_user_id()
    if not user_id:
        raise AppError(ErrorCode.USAGE_QUOTA_UNAVAILABLE)
    budgets = await user_budgets(user_id)
    ledger = UsageQuota()
    reservation = await _reserve_call(ledger, user_id, budgets, None, context=_usage_context())
    owner = _usage_owner()
    if owner is not None:
        owner.begin_usage_receipt(_receipt(reservation, {"charged_units": 0, "unknown": True}))
    try:
        yield
    finally:

        async def settle_and_publish():
            settlement = await ledger.settle(reservation, None)
            if owner is not None and isinstance(settlement, dict):
                await owner.record_usage_receipt(_receipt(reservation, settlement))
            elif isinstance(settlement, dict):
                from src.infra.usage.auxiliary import write_auxiliary_usage

                await write_auxiliary_usage(reservation, settlement, status=status)

        error = sys.exception()
        status = (
            "cancelled"
            if isinstance(error, (asyncio.CancelledError, GeneratorExit))
            else "error"
            if error
            else "completed"
        )
        _, cancelled = await _complete_storage(settle_and_publish())
        if cancelled is not None:
            raise cancelled


def _has_unpriced_cache(value) -> bool:
    if isinstance(value, dict):
        cache = value.get("cache_control")
        return (
            isinstance(cache, dict)
            and cache.get("ttl") == "1h"
            or any(_has_unpriced_cache(item) for item in value.values())
        )
    return isinstance(value, (list, tuple)) and any(_has_unpriced_cache(item) for item in value)


def usage_price_supported(model, messages, kwargs) -> bool:
    """Keep configured token tariffs separate from unpriced request options."""
    options = {**(getattr(model, "model_kwargs", None) or {}), **kwargs}
    counts = [options.get("n", getattr(model, "n", None)), options.get("candidate_count")]
    if any(count is not None and (type(count) is not int or count != 1) for count in counts):
        return False
    if (
        options.get("generation_config") is not None
        or any(
            options.get(key) or getattr(model, key, None)
            for key in (
                "previous_response_id",
                "conversation",
                "cached_content",
                "use_previous_response_id",
            )
        )
        or options.get("model") is not None
    ):
        return False
    if options.get("service_tier", getattr(model, "service_tier", None)) not in (None, "default"):
        return False
    for extra in (getattr(model, "extra_body", None), options.get("extra_body")):
        if isinstance(extra, dict) and any(
            key in extra
            for key in (
                "max_tokens",
                "max_completion_tokens",
                "max_output_tokens",
                "n",
                "candidate_count",
                "generation_config",
                "messages",
                "input",
                "tools",
                "model",
                "service_tier",
                "previous_response_id",
                "conversation",
                "cached_content",
                "modalities",
                "response_modalities",
            )
        ):
            return False
    tools = options.get("tools") or []
    if any(
        not isinstance(tool, dict)
        or (
            tool.get("type", "function") not in {"function", "custom"}
            or any(
                key in tool
                for key in (
                    "google_search",
                    "google_search_retrieval",
                    "code_execution",
                    "url_context",
                    "google_maps",
                    "computer_use",
                )
            )
        )
        for tool in tools
    ):
        return False
    modalities = options.get("response_modalities", getattr(model, "response_modalities", None))
    if modalities and any(str(item).lower() != "text" for item in modalities):
        return False
    if options.get("modalities") and options["modalities"] != ["text"]:
        return False
    payload = [message.model_dump(mode="json") for message in messages]
    if _has_unpriced_cache([payload, options, getattr(model, "extra_body", None)]):
        return False
    return True


def message_cost(message, rates: PriceRates) -> float | None:
    usage = getattr(message, "usage_metadata", None) or {}
    details = usage.get("input_token_details") or {}
    creation = details.get("cache_creation")
    if any(key in details for key in ("ephemeral_5m_input_tokens", "ephemeral_1h_input_tokens")):
        short, long = (
            0
            if details.get("ephemeral_5m_input_tokens") is None
            else details["ephemeral_5m_input_tokens"],
            0
            if details.get("ephemeral_1h_input_tokens") is None
            else details["ephemeral_1h_input_tokens"],
        )
        if type(short) is not int or short < 0 or type(long) is not int or long != 0:
            return None
        if creation not in (None, 0, short):
            return None
        creation = short
    if all(
        value is None or type(value) is int and value == 0
        for value in (
            usage.get("input_tokens"),
            usage.get("output_tokens"),
            details.get("cache_read"),
            creation,
        )
    ):
        return 0.0
    # Provider-omitted counters count as zero; malformed supplied counters stay invalid.
    result = compute_cost(
        input_tokens=0 if usage.get("input_tokens") is None else usage["input_tokens"],
        output_tokens=0 if usage.get("output_tokens") is None else usage["output_tokens"],
        cache_read_tokens=0 if details.get("cache_read") is None else details["cache_read"],
        cache_creation_tokens=0 if creation is None else creation,
        rates=rates,
    )
    return result.total_usd if result else None


class QuotaChatMixin:
    """Concrete protocol adapters supply the next MRO hooks."""

    quota_provider: str | None = Field(default=None, exclude=True)
    quota_model_config_id: str | None = Field(default=None, exclude=True)

    def _generate(self, *args, **kwargs):
        raise AppError(ErrorCode.USAGE_QUOTA_UNAVAILABLE)

    def _stream(self, *args, **kwargs):
        raise AppError(ErrorCode.USAGE_QUOTA_UNAVAILABLE)

    def _create_chat_result(self, response, *args, **kwargs):
        _record_raw_usage(_raw_value(response, "usage"), ("prompt_tokens", "completion_tokens"))
        return super()._create_chat_result(response, *args, **kwargs)  # type: ignore[misc]

    def _convert_chunk_to_generation_chunk(self, chunk, *args, **kwargs):
        if chunk.get("usage") is not None:
            _record_raw_usage(chunk["usage"], ("prompt_tokens", "completion_tokens"))
        return super()._convert_chunk_to_generation_chunk(chunk, *args, **kwargs)  # type: ignore[misc]

    def _format_output(self, data, *args, **kwargs):
        _record_raw_usage(_raw_value(data, "usage"), ("input_tokens", "output_tokens"))
        return super()._format_output(data, *args, **kwargs)  # type: ignore[misc]

    def _make_message_chunk_from_anthropic_event(self, event, *args, **kwargs):
        kind = _raw_value(event, "type")
        stream_usage = _anthropic_stream_usage.get()
        if stream_usage is not None and kind in {"message_start", "message_delta"}:
            raw = (
                _raw_value(_raw_value(event, "message"), "usage")
                if kind == "message_start"
                else _raw_value(event, "usage")
            )
            merged = stream_usage.setdefault("raw", {})
            for field in (
                "input_tokens",
                "cache_read_input_tokens",
                "cache_creation_input_tokens",
                "cache_creation",
            ):
                if (value := _raw_value(raw, field)) is not None:
                    merged[field] = value
            merged["output_tokens"] = _raw_value(raw, "output_tokens")
            _record_raw_usage(merged, ("input_tokens", "output_tokens"))
            if (observation := _raw_usage.get()) is not None and observation[0] is True:
                from anthropic.types import Usage
                from langchain_anthropic.chat_models import _create_usage_metadata

                for field in ("input_tokens", "output_tokens"):
                    if merged.get(field) is None:
                        merged[field] = 0
                # message_start certifies a lower bound, not the final output count.
                stream_usage["message" if kind == "message_delta" else "partial_message"] = (
                    AIMessageChunk(
                        content="",
                        usage_metadata=_create_usage_metadata(Usage.model_construct(**merged)),
                    )
                )
        elif kind == "message_delta":
            _record_raw_usage(_raw_value(event, "usage"), ("input_tokens", "output_tokens"))
        return super()._make_message_chunk_from_anthropic_event(event, *args, **kwargs)  # type: ignore[misc]

    async def _quota_begin(self, messages, kwargs):
        from src.infra.pricing.service import resolve_price

        user_id = quota_user_id()
        if not user_id:
            raise AppError(ErrorCode.USAGE_QUOTA_UNAVAILABLE)
        budgets = await user_budgets(user_id)
        resolved = await resolve_price(
            value=getattr(self, "model_name", None) or getattr(self, "model", None),
            provider=self.quota_provider,
            model_config_id=self.quota_model_config_id,
        )
        rates = resolved.rates if resolved else PriceRates()
        if not usage_price_supported(self, messages, kwargs):
            rates = PriceRates()
        quota = UsageQuota()
        reservation = await _reserve_call(
            quota,
            user_id,
            budgets,
            0,
            context={
                **_usage_context(),
                "model": getattr(self, "model_name", None) or getattr(self, "model", None),
                "model_config_id": self.quota_model_config_id,
                "provider": self.quota_provider,
            },
        )
        owner = _usage_owner()
        if owner is not None:
            owner.begin_usage_receipt(_receipt(reservation, {"charged_units": 0, "unknown": True}))
        root = getattr(self, "root_async_client", None)
        if root is not None and not isinstance(root, _QuotaResource):
            self.root_async_client = _QuotaResource(root)
        return quota, reservation, rates, owner

    async def _quota_finish(
        self, ticket, message, *, usage_valid=True, partial=False, status="completed"
    ):
        if ticket is not None:
            quota, reservation, rates = ticket[:3]
            owner = ticket[3] if len(ticket) > 3 else _usage_owner()

            async def settle_and_publish():
                settlement = await quota.settle(
                    reservation,
                    message_cost(message, rates) if usage_valid else None,
                    **({"partial": True} if partial else {}),
                )
                # Native model-end callbacks may never arrive after cancellation.
                if owner is not None and isinstance(settlement, dict):
                    await owner.record_usage_receipt(_receipt(reservation, settlement))
                elif isinstance(settlement, dict):
                    from src.infra.usage.auxiliary import write_auxiliary_usage

                    await write_auxiliary_usage(
                        reservation, settlement, message if usage_valid else None, status=status
                    )

            _, cancelled = await _complete_storage(settle_and_publish())
            if cancelled is not None:
                raise cancelled

    async def _agenerate(self, messages, stop=None, run_manager=None, **kwargs):
        identity = (id(self), id(run_manager), id(asyncio.current_task()))
        if _active.get() == identity:
            return await super()._agenerate(messages, stop=stop, run_manager=run_manager, **kwargs)  # type: ignore[misc]
        ticket = await self._quota_begin(messages, kwargs)
        token = _active.set(identity)
        observation: list[bool | None] = [None]
        raw_token = _raw_usage.set(observation)
        message = None
        completed = False
        try:
            result = await super()._agenerate(  # type: ignore[misc]
                messages, stop=stop, run_manager=run_manager, **kwargs
            )
            if ticket is not None and len(result.generations) == 1:
                message = result.generations[0].message
            completed = True
            return result
        finally:
            _active.reset(token)
            _raw_usage.reset(raw_token)
            await self._quota_finish(
                ticket,
                message,
                usage_valid=message is not None and observation[0] is not False,
                status="completed"
                if completed
                else "cancelled"
                if isinstance(sys.exception(), (asyncio.CancelledError, GeneratorExit))
                else "error",
            )

    async def _astream(self, messages, stop=None, run_manager=None, **kwargs):
        identity = (id(self), id(run_manager), id(asyncio.current_task()))
        if _active.get() == identity:
            async for chunk in super()._astream(  # type: ignore[misc]
                messages, stop=stop, run_manager=run_manager, **kwargs
            ):
                yield chunk
            return
        ticket = await self._quota_begin(messages, kwargs)
        token = _active.set(identity)
        observation: list[bool | None] = [None]
        raw_token = _raw_usage.set(observation)
        anthropic_usage: dict[str, Any] = {}
        anthropic_token = _anthropic_stream_usage.set(anthropic_usage)
        message = None
        completed = False
        try:
            async for chunk in super()._astream(  # type: ignore[misc]
                messages, stop=stop, run_manager=run_manager, **kwargs
            ):
                if ticket is not None and chunk.message.usage_metadata:
                    usage = AIMessageChunk(content="", usage_metadata=chunk.message.usage_metadata)
                    message = usage if message is None else message + usage
                yield chunk
            completed = True
        finally:
            _active.reset(token)
            _raw_usage.reset(raw_token)
            _anthropic_stream_usage.reset(anthropic_token)
            message = anthropic_usage.get(
                "message", message or anthropic_usage.get("partial_message")
            )
            await self._quota_finish(
                ticket,
                message,
                usage_valid=(completed or message is not None) and observation[0] is not False,
                **({"partial": True} if not completed and message is not None else {}),
                status="completed"
                if completed
                else "cancelled"
                if isinstance(sys.exception(), (asyncio.CancelledError, GeneratorExit))
                else "error",
            )
