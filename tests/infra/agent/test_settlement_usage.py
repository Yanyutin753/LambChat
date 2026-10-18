"""The trace reports the same per-call amounts that quota actually settled."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

from langchain_core.runnables.config import var_child_runnable_config

from src.agents.core.node_utils import resolve_run_usage_carry
from src.infra.agent.events.processor import AgentEventProcessor
from src.infra.llm.quota import QuotaChatMixin
from src.infra.pricing.calculator import PriceRates
from src.infra.writer.present import create_presenter


def make_processor():
    presenter = create_presenter(session_id="s", agent_id="search", model="primary", model_id="p")
    presenter.emit = AsyncMock()
    return AgentEventProcessor(presenter)


def receipt(call_id, units, *, model="fallback", unknown=False):
    return dict(
        call_id=call_id,
        charged_units=units,
        unknown=unknown,
        model=model,
        model_id=model,
        provider="openai",
    )


async def test_mixed_model_receipts_use_settled_nanodollars_and_replace_partial():
    processor = make_processor()
    await processor.record_usage_receipt(receipt("one", 3, model="primary"))
    await processor.record_usage_receipt(receipt("two", 5, unknown=True))
    await processor.record_usage_receipt(receipt("two", 11))
    await processor.record_usage_receipt(receipt("two", 11))
    usage = processor.presenter.emit.call_args.args[0]["data"]
    assert usage["cost_source"] == "provider_settlement"
    assert usage["cost_units"] == 14
    assert usage["cost_usd"] == 14 / 1_000_000_000
    assert usage["cost_complete"] is True
    assert {model["model"] for model in usage["actual_models"]} == {"primary", "fallback"}
    assert usage["model"] != "primary"


async def test_resume_keeps_receipts_and_deduplicates_late_final():
    first = make_processor()
    await first.record_usage_receipt(receipt("call", 5, unknown=True))
    _, prior = resolve_run_usage_carry({"prior_usage": first.usage_totals()}, default_started_at=0)
    resumed = make_processor()
    resumed.seed_usage(prior)
    await resumed.record_usage_receipt(receipt("call", 9))
    await resumed.record_usage_receipt(receipt("call", 9))
    assert resumed.presenter.emit.call_args.args[0]["data"]["cost_units"] == 9


async def test_cancelled_receipt_emits_without_native_model_end():
    processor = make_processor()
    token = var_child_runnable_config.set({"configurable": {"presenter": processor.presenter}})
    try:
        ledger = SimpleNamespace(
            settle=AsyncMock(return_value={"charged_units": 7, "unknown": True})
        )
        reservation = {
            "id": "call",
            "context": {"model": "fallback", "model_config_id": "f", "provider": "openai"},
        }
        await QuotaChatMixin()._quota_finish(
            (ledger, reservation, PriceRates()), None, partial=True
        )
    finally:
        var_child_runnable_config.reset(token)
    usage = processor.presenter.emit.call_args.args[0]["data"]
    assert usage["partial_cost_usd"] == 7 / 1_000_000_000
    assert usage["cost_units"] == 7
    assert usage["cost_complete"] is False


async def test_unknown_then_known_and_late_partial_keep_charged_lower_bound():
    processor = make_processor()
    await processor.record_usage_receipt(receipt("call", 8, unknown=True))
    await processor.record_usage_receipt(receipt("call", 0, unknown=True))
    assert processor.presenter.emit.call_args.args[0]["data"]["cost_units"] == 8
    await processor.record_usage_receipt(receipt("call", 12))
    await processor.record_usage_receipt(receipt("call", 9, unknown=True))
    assert processor.presenter.emit.call_args.args[0]["data"]["cost_units"] == 12


async def test_legacy_carry_does_not_certify_old_estimates_as_settled_lower_bound():
    processor = make_processor()
    processor.seed_usage({"input_tokens": 100, "partial_cost_usd": 0.02})
    await processor.record_usage_receipt(receipt("new", 7))
    usage = processor.presenter.emit.call_args.args[0]["data"]
    assert usage["cost_units"] == 7
    assert usage["cost_complete"] is False


async def test_cancelled_provider_publishes_actual_receipt_before_propagating(monkeypatch):
    import asyncio

    from langchain_core.messages import AIMessageChunk, HumanMessage
    from langchain_core.outputs import ChatGenerationChunk

    from src.infra.usage.quota import usd_units

    class Provider:
        async def _astream(self, *args, **kwargs):
            yield ChatGenerationChunk(
                message=AIMessageChunk(
                    content="partial",
                    usage_metadata={
                        "input_tokens": 1,
                        "output_tokens": 1,
                        "total_tokens": 2,
                    },
                )
            )
            raise asyncio.CancelledError

    class Model(QuotaChatMixin, Provider):
        pass

    async def settle(ticket, cost, *, partial=False):
        return {"charged_units": usd_units(cost), "unknown": partial}

    processor = make_processor()
    model = Model()
    ledger = SimpleNamespace(settle=AsyncMock(side_effect=settle))
    reservation = {
        "id": "cancelled",
        "context": {"model": "fallback", "model_config_id": "f", "provider": "openai"},
    }
    monkeypatch.setattr(
        model,
        "_quota_begin",
        AsyncMock(return_value=(ledger, reservation, PriceRates(input=0.0001, output=0.0001))),
    )
    token = var_child_runnable_config.set({"configurable": {"presenter": processor.presenter}})
    try:
        import pytest

        with pytest.raises(asyncio.CancelledError):
            _ = [chunk async for chunk in model._astream([HumanMessage(content="hi")])]
    finally:
        var_child_runnable_config.reset(token)
    usage = processor.presenter.emit.call_args.args[0]["data"]
    # 0.2 nanodollars rounds once at settlement, not again after summing floats.
    assert usage["cost_units"] == 1
    assert usage["partial_cost_usd"] == 1e-9
    assert usage["actual_models"][0]["model"] == "fallback"


async def test_receipt_keeps_original_owner_after_outer_stream_cleanup():
    processor = make_processor()
    ledger = SimpleNamespace(settle=AsyncMock(return_value={"charged_units": 9, "unknown": False}))
    reservation = {
        "id": "late",
        "context": {"model": "fallback", "model_config_id": "f", "provider": "openai"},
    }
    processor.presenter._usage_accounting_owner = None
    await QuotaChatMixin()._quota_finish((ledger, reservation, PriceRates(), processor), None)
    assert processor.presenter.emit.call_args.args[0]["data"]["cost_units"] == 9


async def test_delivery_failure_keeps_receipt_without_retrying_successful_provider():
    processor = make_processor()
    processor._presenter_emit = AsyncMock(side_effect=RuntimeError("delivery unavailable"))
    ledger = SimpleNamespace(settle=AsyncMock(return_value={"charged_units": 9, "unknown": False}))
    reservation = {"id": "delivered", "context": {"model": "fallback"}}
    await QuotaChatMixin()._quota_finish((ledger, reservation, PriceRates(), processor), None)
    ledger.settle.assert_awaited_once()
    assert processor.usage_totals()["cost_receipts"]["delivered"]["charged_units"] == 9
    assert processor._token_usage_emitted is False
    processor._presenter_emit = AsyncMock()
    await processor.emit_token_usage()
    assert processor._presenter_emit.call_args.args[0]["data"]["cost_units"] == 9


async def test_foreground_payer_binding_keeps_receipts_but_empty_context_detaches():
    import asyncio
    import contextvars

    from src.infra.llm.quota import _usage_owner, bind_quota_user

    processor = make_processor()
    token = var_child_runnable_config.set({"configurable": {"presenter": processor.presenter}})

    @bind_quota_user
    async def helper(user_id):
        return _usage_owner()

    try:
        assert await helper("user") is processor
        task = asyncio.create_task(helper("user"), context=contextvars.Context())
        assert await task is None
        assert _usage_owner() is processor
    finally:
        var_child_runnable_config.reset(token)


async def test_summary_only_carry_keeps_floor_without_certifying_unknown_calls():
    processor = make_processor()
    _, prior = resolve_run_usage_carry(
        {
            "prior_usage": {
                "input_tokens": 100,
                "cost_source": "provider_settlement",
                "cost_units": 13,
                "actual_models": [{"model": "primary", "model_id": "p", "provider": "openai"}],
            }
        },
        default_started_at=0,
    )
    processor.seed_usage(prior)
    await processor.record_usage_receipt(receipt("new", 7))
    usage = processor.presenter.emit.call_args.args[0]["data"]
    assert usage["cost_units"] == 20
    assert usage["cost_complete"] is False
    assert usage["model"] == "mixed"
    assert {item["model"] for item in usage["actual_models"]} == {"primary", "fallback"}


async def test_handoff_twice_preserves_final_receipt_and_unknown_old_identity():
    from src.infra.agent.handoff import restore_handoff_usage

    first = make_processor()
    first.seed_usage(
        {
            "input_tokens": 100,
            "cost_source": "provider_settlement",
            "cost_units": 13,
            "actual_models": [{"model": "fallback", "model_id": "fallback", "provider": "openai"}],
            "model_identity_complete": False,
        }
    )
    await first.record_usage_receipt(receipt("call", 5, unknown=True))
    handoff = {"prior_usage": first.usage_totals()}
    await first.record_usage_receipt(receipt("call", 9))
    latest = first.presenter.emit.call_args.args[0]["data"]
    for _ in range(2):
        carry = restore_handoff_usage(handoff, latest)
        _, prior = resolve_run_usage_carry(carry, default_started_at=0)
        resumed = make_processor()
        resumed.seed_usage(prior)
        await resumed.record_usage_receipt(receipt("call", 9))
        await resumed.emit_token_usage()
        latest = resumed.presenter.emit.call_args.args[0]["data"]
        assert latest["cost_units"] == 22
        assert latest["cost_complete"] is False
        assert latest["model"] != "fallback"
        assert latest["actual_models"] == [
            {"model": "fallback", "model_id": "fallback", "provider": "openai"}
        ]
        handoff = {"prior_usage": resumed.usage_totals()}
