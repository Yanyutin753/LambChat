from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langchain_core.outputs import ChatGeneration, ChatGenerationChunk, ChatResult

from src.infra.llm import quota
from src.infra.llm.quota import QuotaChatMixin, bind_quota_user, message_cost
from src.infra.pricing.calculator import PriceRates
from src.kernel.errors import AppError

RATES = PriceRates(input=1, output=2, cache_read=0.1, cache_write_included=True)
USAGE = {
    "input_tokens": 10,
    "output_tokens": 2,
    "total_tokens": 12,
    "input_token_details": {"cache_read": 0},
}


def test_missing_usage_and_cache_fields_default_to_zero():
    assert message_cost(AIMessage(content="ok"), RATES) == 0
    assert message_cost(None, PriceRates()) == 0
    assert message_cost(AIMessage(content="ok", usage_metadata=USAGE), RATES) == 0.000014
    assert (
        message_cost(
            AIMessage(content="ok", usage_metadata={**USAGE, "input_token_details": {}}), RATES
        )
        == 0.000014
    )


async def test_missing_cache_tariff_still_settles_known_input_and_output():
    rates = PriceRates(input=2, output=10)
    message = AIMessage(
        content="ok",
        usage_metadata={
            "input_tokens": 100,
            "output_tokens": 10,
            "total_tokens": 110,
            "input_token_details": {"cache_read": 80},
        },
    )
    ledger = SimpleNamespace(
        settle=AsyncMock(return_value={"charged_units": 140_000, "unknown": True})
    )
    owner = SimpleNamespace(record_usage_receipt=AsyncMock())
    reservation = {"id": "call", "context": {"model": "fallback"}}
    await QuotaChatMixin()._quota_finish((ledger, reservation, rates, owner), message)
    ledger.settle.assert_awaited_once_with(reservation, 0.00014, partial=True)
    assert owner.record_usage_receipt.await_args.args[0]["model"] == "fallback"


async def test_no_tariff_cannot_become_a_known_zero_cost():
    ledger = SimpleNamespace(settle=AsyncMock(return_value={"charged_units": 0, "unknown": True}))
    owner = SimpleNamespace(record_usage_receipt=AsyncMock())
    reservation = {"id": "call", "context": {}}
    message = AIMessage(content="ok", usage_metadata=USAGE)
    await QuotaChatMixin()._quota_finish((ledger, reservation, PriceRates(), owner), message)
    assert ledger.settle.await_args.args == (reservation, None)


def test_anthropic_ttl_cache_writes_are_not_charged_as_ordinary_input():
    rates = PriceRates(input=1, output=2, cache_read=0.1, cache_write=1.25)
    usage = {
        **USAGE,
        "input_token_details": {
            "cache_read": 0,
            "cache_creation": 0,
            "ephemeral_5m_input_tokens": 8,
            "ephemeral_1h_input_tokens": 0,
        },
    }
    assert message_cost(AIMessage(content="ok", usage_metadata=usage), rates) == 0.000016
    usage["input_token_details"]["ephemeral_1h_input_tokens"] = 1
    # No 1h tariff exists in PriceRates; retaining a hold is safer than underbilling.
    assert message_cost(AIMessage(content="ok", usage_metadata=usage), rates) is None


class Provider:
    calls = 0

    async def _astream(self, *args, **kwargs):
        self.calls += 1
        yield ChatGenerationChunk(message=AIMessageChunk(content="ok", usage_metadata=USAGE))

    async def _agenerate(self, messages, **kwargs):
        # Providers may implement ainvoke by consuming their own stream.
        chunks = [chunk async for chunk in self._astream(messages, **kwargs)]
        return ChatResult(generations=[ChatGeneration(message=chunks[0].message)])


class Metered(QuotaChatMixin, Provider):
    pass


async def test_nested_streaming_is_reserved_and_settled_once(monkeypatch):
    model = Metered()
    begin, finish = AsyncMock(return_value="ticket"), AsyncMock()
    monkeypatch.setattr(model, "_quota_begin", begin)
    monkeypatch.setattr(model, "_quota_finish", finish)
    await model._agenerate([HumanMessage(content="hi")])
    assert model.calls == 1
    begin.assert_awaited_once()
    finish.assert_awaited_once()


async def test_denied_call_never_reaches_provider(monkeypatch):
    model = Metered()
    monkeypatch.setattr(
        model, "_quota_begin", AsyncMock(side_effect=AppError(quota.ErrorCode.USAGE_QUOTA_EXCEEDED))
    )
    with pytest.raises(AppError):
        await model._agenerate([HumanMessage(content="hi")])
    assert model.calls == 0


async def test_detached_owner_overrides_foreground_identity_and_is_restored():
    @bind_quota_user
    async def detached(user_id):
        assert quota.quota_user_id() == user_id

    before = quota.quota_user_id()
    await detached("background-owner")
    assert quota.quota_user_id() == before


async def test_all_protocol_adapters_share_quota_barrier():
    from src.infra.llm.anthropic_chat import LambChatAnthropicChatModel
    from src.infra.llm.azure_chat import LambChatAzureChatModel
    from src.infra.llm.google_chat import LambChatGoogleChatModel
    from src.infra.llm.openai_chat import LambChatOpenAIChatModel

    for model in (
        LambChatAnthropicChatModel,
        LambChatAzureChatModel,
        LambChatGoogleChatModel,
        LambChatOpenAIChatModel,
    ):
        assert issubclass(model, QuotaChatMixin)
        assert "quota_model_config_id" in model.model_fields


@pytest.mark.parametrize(
    "raw,known",
    [
        ({"prompt_tokens": 10, "completion_tokens": 0}, True),
        ({"prompt_tokens": 10}, True),
        ({"prompt_tokens": None, "completion_tokens": 2}, True),
        ({"prompt_tokens": True, "completion_tokens": 2}, False),
        ({"prompt_tokens": 10, "completion_tokens": -1}, False),
    ],
)
def test_raw_chat_counts_distinguish_missing_from_explicit_zero(raw, known):
    from src.infra.llm.openai_chat import LambChatOpenAIChatModel

    model = LambChatOpenAIChatModel(model="gpt-4o", api_key="fake")
    observation = [None]
    token = quota._raw_usage.set(observation)
    try:
        model._create_chat_result(
            {
                "choices": [
                    {"message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}
                ],
                "usage": {**raw, "prompt_tokens_details": {"cached_tokens": 0}},
            }
        )
        assert observation[0] is known
    finally:
        quota._raw_usage.reset(token)


@pytest.mark.parametrize("kind", ["responses", "google"])
@pytest.mark.parametrize(
    "output,known", [(None, True), (False, False), (-1, False), (0, True), (2, True)]
)
async def test_raw_async_resource_preserves_count_completeness(kind, output, known):
    if kind == "responses":
        raw = SimpleNamespace(usage=SimpleNamespace(input_tokens=10, output_tokens=output))
    else:
        raw = SimpleNamespace(
            usage_metadata=SimpleNamespace(
                prompt_token_count=10,
                candidates_token_count=output,
                cached_content_token_count=0,
                thoughts_token_count=None,
                tool_use_prompt_token_count=None,
            )
        )

    class Resource:
        async def generate_content(self):
            return raw

        async def create(self):
            return SimpleNamespace(parse=lambda: raw)

    observation = [None]
    token = quota._raw_usage.set(observation)
    try:
        resource = quota._QuotaResource(Resource())
        if kind == "responses":
            response = await resource.create()
            assert response.parse() is raw
        else:
            assert await resource.generate_content() is raw
        assert observation[0] is known
    finally:
        quota._raw_usage.reset(token)


async def test_raw_async_resource_stream_observes_completed_response_and_closes():
    raw = SimpleNamespace(usage=SimpleNamespace(input_tokens=10, output_tokens=0))

    class Stream:
        closed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            self.closed = True

        async def __aiter__(self):
            yield SimpleNamespace(type="response.created", response=SimpleNamespace(usage=None))
            yield SimpleNamespace(type="response.completed", response=raw)

    stream = Stream()
    resource = quota._QuotaResource(SimpleNamespace(create=AsyncMock(return_value=stream)))
    observation = [None]
    token = quota._raw_usage.set(observation)
    try:
        async with await resource.create() as response:
            chunks = [chunk async for chunk in response]
        assert len(chunks) == 2
        assert observation[0] is True
        assert stream.closed
    finally:
        quota._raw_usage.reset(token)


async def test_cached_model_does_not_stack_raw_async_resource_observers(monkeypatch):
    from src.infra.llm.openai_chat import LambChatOpenAIChatModel

    model = LambChatOpenAIChatModel(model="gpt-4o", api_key="fake", max_tokens=100)
    monkeypatch.setattr(quota, "quota_user_id", lambda: "owner")
    monkeypatch.setattr(quota, "user_budgets", AsyncMock(return_value=(None, None)))
    monkeypatch.setattr(
        "src.infra.pricing.service.resolve_price",
        AsyncMock(return_value=SimpleNamespace(rates=RATES)),
    )
    monkeypatch.setattr(
        quota, "UsageQuota", lambda: SimpleNamespace(reserve=AsyncMock(return_value={}))
    )
    await model._quota_begin([HumanMessage(content="hi")], {})
    observer = model.root_async_client
    assert isinstance(observer, quota._QuotaResource)
    await model._quota_begin([HumanMessage(content="hi")], {})
    assert model.root_async_client is observer


@pytest.mark.parametrize(
    "raw,cost",
    [
        ({"prompt_tokens": 10}, 0.000014),
        ({"prompt_tokens": 10, "completion_tokens": 2}, 0.000014),
    ],
)
async def test_missing_raw_fields_keep_reported_normalized_usage(monkeypatch, raw, cost):
    class IncompleteProvider:
        async def _agenerate(self, *args, **kwargs):
            quota._record_raw_usage(raw, ("prompt_tokens", "completion_tokens"))
            return ChatResult(
                generations=[ChatGeneration(message=AIMessage(content="ok", usage_metadata=USAGE))]
            )

    class Model(QuotaChatMixin, IncompleteProvider):
        pass

    model = Model()
    ledger = SimpleNamespace(settle=AsyncMock())
    monkeypatch.setattr(
        model, "_quota_begin", AsyncMock(return_value=(ledger, {"id": "call"}, RATES))
    )
    await model._agenerate([HumanMessage(content="hi")])
    assert ledger.settle.await_args.args[1] == cost


@pytest.mark.parametrize("input_tokens,known", [(None, True), (True, False), (0, True), (10, True)])
def test_anthropic_raw_counts_do_not_certify_sdk_zero_defaults(input_tokens, known):
    from src.infra.llm.anthropic_chat import LambChatAnthropicChatModel

    model = LambChatAnthropicChatModel(model="claude-sonnet-4-5", api_key="fake")
    data = SimpleNamespace(
        usage=SimpleNamespace(
            input_tokens=input_tokens,
            output_tokens=2,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        ),
        model_dump=lambda: {"content": [{"type": "text", "text": "ok"}], "usage": {}},
    )
    observation = [None]
    token = quota._raw_usage.set(observation)
    try:
        model._format_output(data)
        assert observation[0] is known
    finally:
        quota._raw_usage.reset(token)


@pytest.mark.parametrize(
    "initial_input,cache_read,cost",
    [
        (10, 0, 0.000014),
        (None, 0, 0.000004),
        (10, False, None),
    ],
)
async def test_anthropic_stream_combines_start_input_with_final_output(
    monkeypatch, initial_input, cache_read, cost
):
    from langchain_anthropic import ChatAnthropic

    from src.infra.llm.anthropic_chat import LambChatAnthropicChatModel

    events = [
        SimpleNamespace(
            type="message_start",
            message=SimpleNamespace(
                model="claude-sonnet-4-5",
                usage=SimpleNamespace(
                    input_tokens=initial_input,
                    output_tokens=1,
                    cache_read_input_tokens=cache_read,
                    cache_creation_input_tokens=0,
                ),
            ),
        ),
        SimpleNamespace(
            type="message_delta",
            usage=SimpleNamespace(output_tokens=2),
            delta=SimpleNamespace(
                stop_reason="end_turn", stop_sequence=None, model_dump=lambda: {}
            ),
        ),
    ]

    async def source(self, *args, **kwargs):
        for event in events:
            message, _ = self._make_message_chunk_from_anthropic_event(
                event,
                stream_usage=True,
                coerce_content_to_string=True,
            )
            yield ChatGenerationChunk(message=message)

    monkeypatch.setattr(ChatAnthropic, "_astream", source)
    model = LambChatAnthropicChatModel(model="claude-sonnet-4-5", api_key="fake")
    ledger = SimpleNamespace(settle=AsyncMock())
    monkeypatch.setattr(
        LambChatAnthropicChatModel,
        "_quota_begin",
        AsyncMock(return_value=(ledger, {"id": "call"}, RATES)),
    )
    chunks = [chunk async for chunk in model._astream([HumanMessage(content="hi")])]
    assert len(chunks) == 2
    assert ledger.settle.await_args.args[1] == cost


def test_raw_bool_cache_count_cannot_be_coerced_to_free_usage():
    observation = [None]
    token = quota._raw_usage.set(observation)
    try:
        quota._record_raw_usage(
            {
                "prompt_tokens": 10,
                "completion_tokens": 2,
                "prompt_tokens_details": {"cached_tokens": False},
            },
            ("prompt_tokens", "completion_tokens"),
        )
        assert observation[0] is False
    finally:
        quota._raw_usage.reset(token)


async def test_cancelled_stream_settles_received_usage(monkeypatch):
    import asyncio

    class PartialProvider:
        async def _astream(self, *args, **kwargs):
            yield ChatGenerationChunk(
                message=AIMessageChunk(content="partial", usage_metadata=USAGE)
            )
            raise asyncio.CancelledError

    class Model(QuotaChatMixin, PartialProvider):
        pass

    model = Model()
    ledger = SimpleNamespace(settle=AsyncMock())
    monkeypatch.setattr(
        model, "_quota_begin", AsyncMock(return_value=(ledger, {"id": "call"}, RATES))
    )
    with pytest.raises(asyncio.CancelledError):
        _ = [chunk async for chunk in model._astream([HumanMessage(content="hi")])]
    assert ledger.settle.await_args.args[1] == 0.000014


async def test_by_value_model_preserves_pricing_override_identity(monkeypatch):
    from src.infra.llm.client import LLMClient
    from src.infra.llm.openai_chat import LambChatOpenAIChatModel

    model = LambChatOpenAIChatModel(model="quota-model", api_key="fake", max_tokens=100)
    models = [
        {"id": "priced-config", "value": "quota-model", "provider": "openai", "max_tokens": 100}
    ]
    monkeypatch.setattr(
        "src.infra.llm.models_service.get_available_models", AsyncMock(return_value=models)
    )
    monkeypatch.setattr(
        "src.infra.llm.models_service.get_default_model", AsyncMock(return_value="quota-model")
    )
    monkeypatch.setattr(LLMClient, "_model_cache", {})
    monkeypatch.setattr(LLMClient, "_create_model", lambda *args, **kwargs: model)
    result = await LLMClient.get_model(model="quota-model", api_key="fake")
    assert result.quota_model_config_id == "priced-config"


async def test_unpriced_paid_api_checks_budget_without_rejecting_unknown_price(monkeypatch):
    monkeypatch.setattr(quota, "quota_user_id", lambda: "limited")
    monkeypatch.setattr(quota, "user_budgets", AsyncMock(return_value=(1, None)))
    ledger = SimpleNamespace(reserve=AsyncMock(return_value={}), settle=AsyncMock())
    monkeypatch.setattr(quota, "UsageQuota", lambda: ledger)
    async with quota.unpriced_usage():
        ledger.reserve.assert_awaited_once()
    assert ledger.reserve.await_args.args == ("limited", (1, None), None)
    ledger.settle.assert_awaited_once_with({}, None)


@pytest.mark.parametrize("rates", [RATES, PriceRates()])
@pytest.mark.parametrize(
    "options",
    [
        {},
        {"model": "other-model"},
        {"service_tier": "priority"},
        {"extra_body": {"model": "other-model"}},
        {"tools": [{"type": "web_search"}]},
        {"tools": [{"google_search": {}}]},
        {"response_modalities": ["audio"]},
    ],
)
async def test_model_without_token_cap_checks_budget_and_settles_actual_cost(
    monkeypatch, rates, options
):
    monkeypatch.setattr(quota, "quota_user_id", lambda: "limited")
    monkeypatch.setattr(quota, "user_budgets", AsyncMock(return_value=(1, None)))
    monkeypatch.setattr(
        "src.infra.pricing.service.resolve_price",
        AsyncMock(return_value=SimpleNamespace(rates=rates)),
    )
    ledger = SimpleNamespace(reserve=AsyncMock(return_value={}), settle=AsyncMock())
    monkeypatch.setattr(quota, "UsageQuota", lambda: ledger)
    model = Metered()
    ticket = await model._quota_begin([HumanMessage(content="hi")], options)
    assert ledger.reserve.await_args.args == ("limited", (1, None), 0)
    await model._quota_finish(ticket, AIMessage(content="ok", usage_metadata=USAGE))
    assert ledger.settle.await_args.args[1] == (
        0.000014 if rates.is_priced() and not options else None
    )


async def test_missing_payer_rejects_model_and_raw_paid_api(monkeypatch):
    monkeypatch.setattr(quota, "quota_user_id", lambda: None)
    with pytest.raises(AppError):
        await Metered()._quota_begin([HumanMessage(content="hi")], {})
    with pytest.raises(AppError):
        async with quota.unpriced_usage():
            pytest.fail("ownerless paid request reached provider")


@pytest.mark.parametrize("hook", ["_generate", "_stream"])
def test_synchronous_provider_hooks_cannot_bypass_quota(hook):
    class SyncProvider:
        def _generate(self, *args, **kwargs):
            pytest.fail("sync provider was called without quota")

        def _stream(self, *args, **kwargs):
            pytest.fail("sync stream was called without quota")

    class Model(QuotaChatMixin, SyncProvider):
        pass

    with pytest.raises(AppError):
        getattr(Model(), hook)([HumanMessage(content="hi")])


async def test_cancel_during_reservation_refunds_proven_unstarted_call(monkeypatch):
    import asyncio

    committed, release = asyncio.Event(), asyncio.Event()

    async def reserve(*args, **kwargs):
        committed.set()
        await release.wait()
        return {"id": "committed-ticket"}

    ledger = SimpleNamespace(reserve=reserve, settle=AsyncMock())
    monkeypatch.setattr(quota, "quota_user_id", lambda: "owner")
    monkeypatch.setattr(quota, "user_budgets", AsyncMock(return_value=(1, 5)))
    monkeypatch.setattr(quota, "UsageQuota", lambda: ledger)
    monkeypatch.setattr(
        "src.infra.pricing.service.resolve_price",
        AsyncMock(return_value=SimpleNamespace(rates=RATES)),
    )
    model = Metered()
    model.max_tokens = 100
    task = asyncio.create_task(model._quota_begin([HumanMessage(content="hi")], {}))
    await committed.wait()
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    ledger.settle.assert_awaited_once_with({"id": "committed-ticket"}, 0)
    assert model.calls == 0


async def test_repeated_cancellation_cannot_interrupt_settlement(monkeypatch):
    import asyncio

    started, release = asyncio.Event(), asyncio.Event()
    settled = []

    async def settle(*args):
        started.set()
        await release.wait()
        settled.append(args)

    model = Metered()
    task = asyncio.create_task(
        model._quota_finish(
            (SimpleNamespace(settle=settle), {"id": "call"}, RATES),
            AIMessage(content="ok", usage_metadata=USAGE),
        )
    )
    await started.wait()
    task.cancel()
    await asyncio.sleep(0)
    task.cancel()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert settled == [({"id": "call"}, 0.000014)]


@pytest.mark.parametrize("streaming", [False, True])
async def test_interrupted_call_without_receipt_stays_unknown(monkeypatch, streaming):
    import asyncio

    class InterruptedProvider:
        async def _agenerate(self, *args, **kwargs):
            raise asyncio.CancelledError

        async def _astream(self, *args, **kwargs):
            yield ChatGenerationChunk(message=AIMessageChunk(content="partial"))
            raise asyncio.CancelledError

    class Model(QuotaChatMixin, InterruptedProvider):
        pass

    model = Model()
    ledger = SimpleNamespace(settle=AsyncMock())
    monkeypatch.setattr(
        model, "_quota_begin", AsyncMock(return_value=(ledger, {"id": "call"}, RATES))
    )
    with pytest.raises(asyncio.CancelledError):
        if streaming:
            _ = [chunk async for chunk in model._astream([HumanMessage(content="hi")])]
        else:
            await model._agenerate([HumanMessage(content="hi")])
    ledger.settle.assert_awaited_once_with({"id": "call"}, None)


async def test_anthropic_cancel_charges_reported_start_usage(monkeypatch):
    import asyncio

    from langchain_anthropic import ChatAnthropic

    from src.infra.llm.anthropic_chat import LambChatAnthropicChatModel

    async def source(self, *args, **kwargs):
        event = SimpleNamespace(
            type="message_start",
            message=SimpleNamespace(
                model="claude-sonnet-4-5",
                usage=SimpleNamespace(
                    input_tokens=10,
                    output_tokens=1,
                    cache_read_input_tokens=0,
                    cache_creation_input_tokens=0,
                ),
            ),
        )
        message, _ = self._make_message_chunk_from_anthropic_event(
            event,
            stream_usage=True,
            coerce_content_to_string=True,
        )
        yield ChatGenerationChunk(message=message)
        raise asyncio.CancelledError

    monkeypatch.setattr(ChatAnthropic, "_astream", source)
    model = LambChatAnthropicChatModel(model="claude-sonnet-4-5", api_key="fake")
    ledger = SimpleNamespace(settle=AsyncMock())
    monkeypatch.setattr(
        LambChatAnthropicChatModel,
        "_quota_begin",
        AsyncMock(return_value=(ledger, {"id": "call"}, RATES)),
    )
    with pytest.raises(asyncio.CancelledError):
        _ = [chunk async for chunk in model._astream([HumanMessage(content="hi")])]
    ledger.settle.assert_awaited_once_with({"id": "call"}, 0.000012, partial=True)


def test_quota_preflight_skip_reason_classifies_quota_and_inactive_user():
    from src.infra.llm.quota import quota_preflight_skip_reason
    from src.kernel.errors import AppError, ErrorCode

    assert (
        quota_preflight_skip_reason(AppError(ErrorCode.USAGE_QUOTA_UNAVAILABLE))
        == "usage_quota_unavailable"
    )
    assert quota_preflight_skip_reason(AppError(ErrorCode.UNAUTHORIZED)) == "user_inactive"
    assert quota_preflight_skip_reason(RuntimeError("boom")) is None


@pytest.mark.parametrize("include_usage", [False, True])
async def test_empty_stream_does_not_certify_zero_usage(monkeypatch, include_usage):
    class Source:
        async def _astream(self, *args, **kwargs):
            if include_usage:
                yield ChatGenerationChunk(
                    message=AIMessageChunk(
                        content="",
                        usage_metadata={"input_tokens": 0, "output_tokens": 0, "total_tokens": 0},
                    )
                )

    class Model(QuotaChatMixin, Source):
        pass

    model = Model()
    finish = AsyncMock()
    monkeypatch.setattr(model, "_quota_begin", AsyncMock(return_value="ticket"))
    monkeypatch.setattr(model, "_quota_finish", finish)
    # A fallback can run inside the primary's exception handler.
    try:
        raise RuntimeError("primary failed")
    except RuntimeError:
        _ = [chunk async for chunk in model._astream([])]
    assert finish.await_args.kwargs["usage_valid"] is include_usage
    assert finish.await_args.kwargs["status"] == ("completed" if include_usage else "error")
    if not include_usage:
        assert str(finish.await_args.kwargs["error"]) == "No generations found in stream."


async def test_failed_attempt_receipt_preserves_outcome_without_assuming_zero_cost():
    ledger = SimpleNamespace(settle=AsyncMock(return_value={"charged_units": 0, "unknown": True}))
    owner = SimpleNamespace(record_usage_receipt=AsyncMock())
    reservation = {"id": "attempt", "context": {"model": "primary", "operation": "llm"}}
    from httpx import HTTPStatusError, Request, Response

    request = Request("POST", "https://example.test/messages")
    response = Response(429, headers={"X-Oneapi-Request-Id": "gateway-attempt-1"})
    error = HTTPStatusError("private provider response body", request=request, response=response)
    await QuotaChatMixin()._quota_finish(
        (ledger, reservation, PriceRates(), owner),
        None,
        usage_valid=False,
        status="error",
        error=error,
    )
    ledger.settle.assert_awaited_once_with(reservation, None)
    receipt = owner.record_usage_receipt.await_args.args[0]
    assert receipt["status"] == "error"
    assert receipt["http_status"] == 429
    assert receipt["provider_request_id"] == "gateway-attempt-1"
    assert receipt["operation"] == "llm"
    assert receipt["unknown"] is True
    assert "private provider response body" not in repr(receipt)


@pytest.mark.parametrize(
    ("status", "body", "expected_cost"),
    [
        (200, {"results": [{"url": "https://example.test"}]}, 0.00075),
        (200, {"results": []}, 0),
        (200, {"unexpected": []}, None),
        (429, {}, 0),
    ],
)
async def test_deepseek_search_settles_each_http_attempt(monkeypatch, status, body, expected_cost):
    import httpx

    from src.infra.tool.web_search_providers import ProviderRequestError, deepseek_search

    reservation = {"id": "search-attempt", "context": {"provider": "deepseek"}}
    ledger = SimpleNamespace(
        reserve=AsyncMock(return_value=reservation),
        settle=AsyncMock(return_value={"charged_units": 0, "unknown": expected_cost is None}),
    )
    owner = SimpleNamespace(begin_usage_receipt=lambda _: None, record_usage_receipt=AsyncMock())
    monkeypatch.setattr(quota, "quota_user_id", lambda: "user")
    monkeypatch.setattr(quota, "user_budgets", AsyncMock())
    monkeypatch.setattr(quota, "UsageQuota", lambda: ledger)
    monkeypatch.setattr(quota, "_usage_owner", lambda: owner)

    def respond(request):
        return httpx.Response(status, json=body, headers={"X-Request-ID": "search-123"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        if status != 200 or "results" not in body:
            with pytest.raises(ProviderRequestError):
                await deepseek_search(client, "key", "test", 3, None)
        else:
            await deepseek_search(client, "key", "test", 3, None)

    assert ledger.settle.await_args.args == (reservation, expected_cost)
    receipt = owner.record_usage_receipt.await_args.args[0]
    assert receipt["http_status"] == status
    assert receipt["provider_request_id"] == "search-123"


async def test_model_retry_keeps_each_gateway_receipt(monkeypatch):
    import httpx

    from src.infra.llm.retry import ainvoke_with_retry

    attempts = iter((429, 200))

    class Source:
        async def ainvoke(self, prompt, **kwargs):
            return await self._agenerate(prompt)

        async def _agenerate(self, messages, **kwargs):
            status = next(attempts)
            request = httpx.Request("POST", "https://example.test")
            response = httpx.Response(
                status, request=request, headers={"X-Oneapi-Request-ID": f"gateway-{status}"}
            )
            await quota.observe_model_http_response(response)
            response.raise_for_status()
            return ChatResult(generations=[ChatGeneration(message=AIMessage(content="ok"))])

    class Model(QuotaChatMixin, Source):
        pass

    model = Model()
    ledger = SimpleNamespace(settle=AsyncMock(return_value={"charged_units": 0, "unknown": True}))
    owner = SimpleNamespace(record_usage_receipt=AsyncMock())
    monkeypatch.setattr(
        model,
        "_quota_begin",
        AsyncMock(
            side_effect=[(ledger, {"id": call}, RATES, owner) for call in ("first", "retry")]
        ),
    )
    await ainvoke_with_retry(model, [], max_retries=1, retry_delay=0, retry_if=lambda _: True)
    receipts = [call.args[0] for call in owner.record_usage_receipt.await_args_list]
    assert [(r["call_id"], r["status"], r["gateway_request_id"]) for r in receipts] == [
        ("first", "error", "gateway-429"),
        ("retry", "completed", "gateway-200"),
    ]


async def test_anthropic_gateway_raw_response_captures_wire_receipt(monkeypatch):
    import httpx
    from langchain_anthropic import ChatAnthropic

    from src.infra.llm.anthropic_chat import LambChatAnthropicChatModel

    raw = SimpleNamespace(
        http_response=httpx.Response(200, headers={"X-Oneapi-Request-ID": "anthropic-gateway"})
    )
    monkeypatch.setattr(ChatAnthropic, "_acreate", AsyncMock(return_value=raw))
    model = LambChatAnthropicChatModel(model="glm-5.3", api_key="test")
    observed = {}
    token = quota._wire_receipt.set(observed)
    try:
        assert await model._acreate({"stream": True}) is raw
    finally:
        quota._wire_receipt.reset(token)

    assert observed["gateway_request_id"] == "anthropic-gateway"
    assert observed["http_status"] == 200


async def test_anthropic_gateway_error_captures_response_before_sdk_translation(monkeypatch):
    import httpx
    from langchain_anthropic import ChatAnthropic

    from src.infra.llm.anthropic_chat import LambChatAnthropicChatModel

    request = httpx.Request("POST", "https://example.test")
    response = httpx.Response(429, headers={"X-Oneapi-Request-ID": "anthropic-error"})
    error = httpx.HTTPStatusError("rate limited", request=request, response=response)
    monkeypatch.setattr(ChatAnthropic, "_acreate", AsyncMock(side_effect=error))
    model = LambChatAnthropicChatModel(model="glm-5.3", api_key="test")
    observed = {}
    token = quota._wire_receipt.set(observed)
    try:
        with pytest.raises(httpx.HTTPStatusError) as exc_info:
            await model._acreate({"stream": True})
        assert exc_info.value is error
    finally:
        quota._wire_receipt.reset(token)
    assert observed["gateway_request_id"] == "anthropic-error"
    assert observed["http_status"] == 429


def test_aux_model_call_skip_reason_classifies_rate_limit_quota_and_other():
    import anthropic
    import httpx

    from src.kernel.errors import ErrorCode

    request = httpx.Request("POST", "https://api.invalid/v1/messages")
    rate_limit = anthropic.RateLimitError(
        "rate limited",
        response=httpx.Response(429, request=request),
        body={"error": {"type": "1302", "message": "rate limited"}},
    )
    assert quota.aux_model_call_skip_reason(rate_limit) == "rate_limit"
    assert (
        quota.aux_model_call_skip_reason(AppError(ErrorCode.USAGE_QUOTA_EXCEEDED))
        == "usage_quota_exceeded"
    )
    assert quota.aux_model_call_skip_reason(ValueError("boom")) is None
