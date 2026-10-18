"""Repair certified incomplete records without promoting their partial bill."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.pricing import backfill
from src.infra.pricing.calculator import PriceRates
from src.infra.usage.storage import UsageStorage
from src.kernel.schemas.pricing import PricingBackfillResponse


class _Usage:
    def __init__(self, doc):
        self.doc = deepcopy(doc)
        self.partial_updates = []
        self.update_usage_cost = AsyncMock(side_effect=AssertionError("Must stay partial"))

    async def list_unpriced_usage_logs(self, *, limit, exclude_trace_ids):
        return [] if self.doc["trace_id"] in exclude_trace_ids else [deepcopy(self.doc)]

    async def update_usage_partial_cost(self, trace_id, cost_usd, *, expected_usage):
        self.partial_updates.append((trace_id, cost_usd, expected_usage))
        self.doc["partial_cost_usd"] = cost_usd
        return True


def _doc():
    return dict(
        trace_id="repair",
        model="original-model",
        model_id="",
        trace_event_revision=8,
        input_tokens=100,
        output_tokens=10,
        cache_read_tokens=20,
        cache_creation_tokens=0,
        unknown_usage_fields=["cache_creation_tokens"],
        usage_incomplete=True,
        input_includes_cache=True,
        cost_usd=0.0,
        cost_available=False,
    )


@pytest.mark.parametrize("dry_run", [False, True])
@pytest.mark.parametrize("output_rate", [0, 2])
async def test_backfill_repairs_only_independent_components_and_preserves_unknowns(
    monkeypatch, dry_run, output_rate
):
    usage = _Usage(_doc())
    monkeypatch.setattr(backfill, "_resolve_config_id_by_value", AsyncMock(return_value=None))
    price = AsyncMock(
        return_value=SimpleNamespace(
            rates=PriceRates(input=1, output=output_rate, cache_read=0, cache_write=10)
        )
    )
    monkeypatch.setattr(backfill, "resolve_price", price)
    result = await backfill._backfill_locked(usage=usage, dry_run=dry_run, batch_size=10)
    assert result["partial_priced"] == 1
    assert result["priced"] == 0 and result["still_unpriced"] == 1
    assert usage.doc["usage_incomplete"] is True and usage.doc["cost_available"] is False
    assert usage.doc["cost_usd"] == 0.0
    if dry_run:
        assert usage.partial_updates == []
    else:
        _, amount, snapshot = usage.partial_updates[0]
        assert amount == pytest.approx(10 * output_rate / 1_000_000)
        for key in (
            "model",
            "model_id",
            "trace_event_revision",
            "unknown_usage_fields",
            "input_tokens",
            "output_tokens",
            "cache_read_tokens",
            "cache_creation_tokens",
        ):
            assert snapshot[key] == _doc()[key]


async def test_repeated_partial_backfill_does_not_count_unchanged_zero_as_new(monkeypatch):
    usage = _Usage(dict(_doc(), partial_cost_usd=0.0))
    monkeypatch.setattr(backfill, "_resolve_config_id_by_value", AsyncMock(return_value=None))
    monkeypatch.setattr(
        backfill,
        "resolve_price",
        AsyncMock(
            return_value=SimpleNamespace(
                rates=PriceRates(input=0, output=0, cache_read=0, cache_write=1)
            )
        ),
    )
    result = await backfill._backfill_locked(usage=usage, dry_run=False, batch_size=10)
    assert result["partial_priced"] == 0
    assert usage.partial_updates == []


async def test_complete_counts_with_missing_cache_price_can_be_partially_backfilled(monkeypatch):
    usage = _Usage(dict(_doc(), unknown_usage_fields=[], usage_incomplete=False))
    monkeypatch.setattr(backfill, "_resolve_config_id_by_value", AsyncMock(return_value=None))
    monkeypatch.setattr(
        backfill,
        "resolve_price",
        AsyncMock(return_value=SimpleNamespace(rates=PriceRates(input=1, output=2))),
    )
    result = await backfill._backfill_locked(usage=usage, dry_run=False, batch_size=10)
    assert result["partial_priced"] == 1 and result["priced"] == 0
    assert usage.partial_updates[0][1] == pytest.approx(0.0001)


async def test_partial_storage_cas_matches_original_snapshot_without_changing_certification():
    storage = UsageStorage()
    collection = SimpleNamespace(
        update_one=AsyncMock(return_value=SimpleNamespace(matched_count=1))
    )
    storage._collection = collection
    snapshot = _doc()
    assert await storage.update_usage_partial_cost("repair", 0.00002, expected_usage=snapshot)
    query, update = collection.update_one.call_args.args
    assert query["input_includes_cache"] == {"$eq": True, "$type": "bool"}
    for key in (
        "model",
        "model_id",
        "trace_event_revision",
        "unknown_usage_fields",
        "input_tokens",
        "output_tokens",
        "cache_read_tokens",
        "cache_creation_tokens",
    ):
        assert query[key] == snapshot[key]
    assert update == {"$set": {"partial_cost_usd": 0.00002}}


def test_partial_backfill_summary_is_preserved_by_response_schema():
    assert PricingBackfillResponse(partial_priced=3).model_dump()["partial_priced"] == 3


async def test_free_cache_write_backfill_confirms_amount_without_filling_unknown_write_count(
    monkeypatch,
):
    usage = _Usage(_doc())
    usage.update_usage_cost = AsyncMock(return_value=True)
    monkeypatch.setattr(backfill, "_resolve_config_id_by_value", AsyncMock(return_value=None))
    monkeypatch.setattr(
        backfill,
        "resolve_price",
        AsyncMock(
            return_value=SimpleNamespace(
                rates=PriceRates(
                    input=1, output=2, cache_read=0, cache_write=0, cache_write_included=True
                )
            )
        ),
    )
    result = await backfill._backfill_locked(usage=usage, dry_run=False, batch_size=10)
    assert result["priced"] == 1 and result["partial_priced"] == 0
    assert usage.partial_updates == []
    args, kwargs = usage.update_usage_cost.call_args
    assert args == ("repair", pytest.approx(0.0001))
    assert kwargs["cost_complete"] is True
    assert kwargs["cost_rates"] == dict(
        input=1, output=2, cache_read=0, cache_write=0, cache_write_included=True
    )
    assert kwargs["expected_usage"]["unknown_usage_fields"] == ["cache_creation_tokens"]
    assert kwargs["expected_usage"]["trace_event_revision"] == 8
    assert usage.doc["usage_incomplete"] is True
