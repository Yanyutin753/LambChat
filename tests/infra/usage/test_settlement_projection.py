"""Settled call amounts survive projection without single-model repricing."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.pricing import backfill
from src.infra.usage.cost_certainty import _usage_cost_fields
from src.infra.usage.storage import UsageStorage
from src.infra.writer.present import create_presenter
from src.kernel.schemas.usage import UsageLog


@pytest.mark.parametrize("complete", [True, False])
@pytest.mark.parametrize("mixed", [True, False])
async def test_settlement_projection_preserves_amount_and_actual_models(
    monkeypatch, complete, mixed
):
    models = [{"model": "fallback", "model_id": "b", "provider": "openai"}]
    if mixed:
        models.append({"model": "primary", "model_id": "a", "provider": "anthropic"})
    data = create_presenter(session_id="s", agent_id="a").present_token_usage(
        model="selected",
        model_id="selected-id",
        unknown_usage_fields=["input_tokens"],
        settlement_usage={"cost_units": 123, "cost_complete": complete, "actual_models": models},
    )["data"]
    assert data["cost_source"] == "provider_settlement"
    assert "cost_rates" not in data
    assert data["model"] == ("mixed" if mixed else "fallback")
    assert data["model_id"] == ("" if mixed else "b")
    field = "cost_usd" if complete else "partial_cost_usd"
    assert data[field] == 123 / 1_000_000_000
    storage = UsageStorage()
    storage._collection = SimpleNamespace(update_one=AsyncMock())
    monkeypatch.setattr(storage, "_get_session_metadata", AsyncMock(return_value={}))
    await storage.upsert_usage_log_from_trace_metadata(
        {
            "trace_id": "t",
            "session_id": "s",
            "user_id": "u",
            "status": "cancelled",
            "event_revision": 5,
            "metadata": {"model": "selected", "model_id": "selected-id"},
        },
        data,
    )
    query, mutation = storage.collection.update_one.await_args.args
    doc = mutation["$set"]
    assert doc["model"] == data["model"]
    assert doc["model_id"] == data["model_id"]
    assert doc["status"] == "cancelled"
    assert doc["cost_complete"] is complete
    assert doc["cost_available"] is complete
    assert doc[field] == data[field]
    assert doc["cost_rates"] is None
    assert doc["actual_models"] == models
    assert query["$or"][1]["trace_event_revision"]["$lte"] == 5
    assert UsageLog(**doc).cost_units == 123
    assert _usage_cost_fields(doc)["cost_available"] is complete


async def test_settlement_receipts_cannot_be_backfilled_or_overwritten(monkeypatch):
    doc = {
        "trace_id": "t",
        "cost_source": "provider_settlement",
        "cost_units": 5,
        "cost_complete": False,
        "model": "mixed",
        "input_includes_cache": True,
    }
    usage = SimpleNamespace(list_unpriced_usage_logs=AsyncMock(side_effect=[[doc], []]))
    resolve = AsyncMock()
    monkeypatch.setattr(backfill, "resolve_price", resolve)
    result = await backfill._backfill_locked(usage=usage, dry_run=False, batch_size=1)
    assert result["priced"] == result["partial_priced"] == 0
    resolve.assert_not_awaited()
    storage = UsageStorage()
    storage._collection = SimpleNamespace(update_one=AsyncMock())
    assert not await storage.update_usage_cost("t", 9, expected_usage=doc)
    assert not await storage.update_usage_partial_cost("t", 9, expected_usage=doc)
    storage.collection.update_one.assert_not_awaited()
    # A stale legacy reader must also be fenced after a new receipt arrives.
    await storage.update_usage_cost("t", 9)
    assert storage.collection.update_one.await_args.args[0]["cost_source"] == {
        "$ne": "provider_settlement"
    }


def test_known_new_model_does_not_relabel_unknown_historical_models():
    models = [{"model": "new", "model_id": "b", "provider": "openai"}]
    data = create_presenter(session_id="s", agent_id="a").present_token_usage(
        settlement_usage={
            "cost_units": 13,
            "cost_complete": False,
            "actual_models": models,
            "model_identity_complete": False,
        },
    )["data"]
    assert data["model"] == "mixed"
    assert data["model_id"] == ""
    assert data["actual_models"] == models
    assert data["model_identity_complete"] is False


def test_usage_event_retains_call_receipts_for_restart_deduplication():
    carry = {
        "cost_receipts": {"call": {"charged_units": 9, "unknown": False}},
        "legacy_cost_units": 4,
        "legacy_cost_unknown": True,
        "legacy_actual_models": [],
    }
    data = create_presenter(session_id="s", agent_id="a").present_token_usage(
        settlement_usage={"cost_units": 13, "cost_complete": False, **carry},
    )["data"]
    for key, value in carry.items():
        assert data[key] == value
