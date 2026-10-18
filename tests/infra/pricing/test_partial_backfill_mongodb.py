"""Real MongoDB repair and snapshot races for partial historical costs."""

import os
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pymongo import AsyncMongoClient

from src.infra.pricing import backfill
from src.infra.pricing.calculator import PriceRates
from src.infra.storage.mongodb import build_mongo_connection_string
from src.infra.usage.storage import UsageStorage
from src.kernel.config import settings

pytestmark = pytest.mark.skipif(
    os.environ.get("TEST_MEMORY_MONGODB") != "1", reason="Explicit real MongoDB opt-in"
)


def _doc():
    return {
        "trace_id": "repair",
        "model": "original-model",
        "trace_event_revision": 8,
        "input_tokens": 100,
        "output_tokens": 10,
        "cache_read_tokens": 20,
        "cache_creation_tokens": 0,
        "unknown_usage_fields": ["cache_creation_tokens"],
        "usage_incomplete": True,
        "input_includes_cache": True,
        "cost_available": False,
        "cost_usd": 0.0,
    }


async def test_partial_backfill_repairs_affected_rows_idempotently_without_confirming(monkeypatch):
    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True)
    collection = client[settings.MONGODB_DB][f"test_partial_repair_{uuid4().hex}"]
    usage = UsageStorage()
    usage._collection = collection
    monkeypatch.setattr(backfill, "_resolve_config_id_by_value", AsyncMock(return_value=None))
    monkeypatch.setattr(
        backfill,
        "resolve_price",
        AsyncMock(
            return_value=SimpleNamespace(
                rates=PriceRates(input=1, output=2, cache_read=0, cache_write=10)
            )
        ),
    )
    try:
        await collection.insert_many(
            [
                _doc(),
                {"trace_id": "legacy", "cost_usd": 9.5, "cost_available": True},
            ]
        )
        for dry_run, expected_partial in ((True, 1), (False, 1), (False, 0), (True, 0)):
            result = await backfill._backfill_locked(usage=usage, dry_run=dry_run, batch_size=1)
            assert result["partial_priced"] == expected_partial
        stored = await collection.find_one({"trace_id": "repair"})
        assert stored["partial_cost_usd"] == pytest.approx(0.00002)
        assert stored["cost_usd"] == 0.0 and stored["cost_available"] is False
        assert stored["unknown_usage_fields"] == ["cache_creation_tokens"]
        stats = await usage.get_usage_stats_only()
        assert stats["partial_cost_usd"] == pytest.approx(0.00002)
        assert stats["total_cost_usd"] == 0.0 and stats["estimated_cost_usd"] == 9.5
        legacy = await collection.find_one({"trace_id": "legacy"})
        assert "input_includes_cache" not in legacy
    finally:
        await collection.drop()
        await client.close()


async def test_included_write_backfill_updates_certified_amount_and_projects_history_without_fake_count(
    monkeypatch,
):
    from src.api.routes.session_usage_projection import project_session_usage_costs

    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True)
    collection = client[settings.MONGODB_DB][f"test_included_repair_{uuid4().hex}"]
    usage = UsageStorage()
    usage._collection = collection
    original = dict(
        _doc(), session_id="session", user_id="owner", status="completed", total_tokens=110
    )
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
    try:
        await collection.insert_one(original.copy())
        result = await backfill._backfill_locked(usage=usage, dry_run=False, batch_size=10)
        assert result["priced"] == 1 and result["partial_priced"] == 0
        saved = await collection.find_one({"trace_id": "repair"})
        assert saved["cost_usd"] == pytest.approx(0.0001)
        assert saved["cost_available"] is True and saved["cost_complete"] is True
        assert saved["cost_rates"]["cache_write_included"] is True
        assert saved["usage_incomplete"] is True
        assert saved["unknown_usage_fields"] == ["cache_creation_tokens"]
        assert saved["cache_creation_tokens"] == original["cache_creation_tokens"]
        event_data = {
            key: original[key]
            for key in (
                "model",
                "input_tokens",
                "output_tokens",
                "total_tokens",
                "cache_read_tokens",
                "cache_creation_tokens",
                "usage_incomplete",
                "unknown_usage_fields",
                "input_includes_cache",
            )
            if key in original
        }
        events = [{"trace_id": "repair", "event_type": "token:usage", "data": event_data}]
        projected = await project_session_usage_costs(
            events, session_id="session", user_id="owner", usage_storage=usage
        )
        assert projected[0]["data"]["cost_usd"] == pytest.approx(0.0001)
        assert projected[0]["data"]["cost_breakdown"]["input"] == pytest.approx(0.00008)
        assert "cost_complete" not in events[0]["data"]
    finally:
        await collection.drop()
        await client.close()


@pytest.mark.parametrize(
    "change",
    [
        {"model": "changed"},
        {"model_id": "added"},
        {"input_tokens": 200},
        {"output_tokens": 20},
        {"cache_read_tokens": 30},
        {"cache_creation_tokens": 10},
        {"unknown_usage_fields": ["output_tokens"]},
        {"trace_event_revision": 9},
        {"usage_incomplete": False},
        {"input_includes_cache": 1},
        {"input_includes_cache": False},
        {"cost_available": True},
        {"partial_cost_usd": 99.0},
    ],
)
async def test_partial_backfill_cannot_overwrite_concurrent_usage_changes(monkeypatch, change):
    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True)
    collection = client[settings.MONGODB_DB][f"test_partial_race_{uuid4().hex}"]
    usage = UsageStorage()
    usage._collection = collection
    monkeypatch.setattr(backfill, "_resolve_config_id_by_value", AsyncMock(return_value=None))

    async def resolve(**kwargs):
        await collection.update_one({"trace_id": "repair"}, {"$set": change})
        return SimpleNamespace(rates=PriceRates(input=1, output=2, cache_read=0))

    monkeypatch.setattr(backfill, "resolve_price", resolve)
    try:
        await collection.insert_one(_doc())
        result = await backfill._backfill_locked(usage=usage, dry_run=False, batch_size=10)
        assert result["priced"] == 0 and result["partial_priced"] == 0
        stored = await collection.find_one({"trace_id": "repair"})
        assert stored.get("partial_cost_usd") == change.get("partial_cost_usd")
        assert stored["cost_usd"] == 0.0
    finally:
        await collection.drop()
        await client.close()
