"""Real MongoDB races: resumed or already-priced usage must beat a stale backfill."""

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


@pytest.mark.skipif(
    os.environ.get("TEST_MEMORY_MONGODB") != "1", reason="Enable configured local MongoDB tests"
)
@pytest.mark.parametrize(
    "identity", ["explicit", "id_only", "unique", "ambiguous", "missing", "mismatch", "zero"]
)
async def test_backfill_uses_original_model_config_without_guessing_same_value(
    monkeypatch, identity
):
    from src.infra.agent import model_storage as model_module
    from src.infra.pricing import service
    from src.infra.pricing.matching import PriceEntry, PriceIndex

    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True)
    name = f"test_usage_model_identity_{uuid4().hex}"
    collection = client[settings.MONGODB_DB][name]
    models = client[settings.MONGODB_DB][name + "_models"]
    usage = UsageStorage()
    usage._collection = collection
    store = model_module.ModelStorage()
    store._collection = models
    monkeypatch.setattr(model_module, "get_model_storage", lambda: store)
    monkeypatch.setattr(
        service,
        "get_price_index",
        AsyncMock(
            return_value=PriceIndex(
                [
                    PriceEntry(
                        provider="openai",
                        model_id="shared-model",
                        rates=PriceRates(input=1, output=2),
                    )
                ],
                {},
            )
        ),
    )
    try:
        await models.insert_many(
            [
                {
                    "id": "channel-a",
                    "value": "shared-model",
                    "label": "A",
                    "provider": "openai",
                    "enabled": True,
                    "pricing": {"input": 1, "output": 2, "cache_read": 0, "cache_write": 0},
                    "order": 0,
                },
                {
                    "id": "channel-b",
                    "value": "shared-model",
                    "label": "B",
                    "provider": "openai",
                    "enabled": True,
                    "pricing": {"input": 10, "output": 20, "cache_read": 0, "cache_write": 0},
                    "order": 1,
                },
            ]
        )
        doc = {
            "trace_id": "identity",
            "model": "shared-model",
            "input_tokens": 1_000_000,
            "output_tokens": 100_000,
            "cache_read_tokens": 0,
            "cache_creation_tokens": 0,
            "usage_incomplete": False,
            "input_includes_cache": True,
            "cost_available": False,
        }
        if identity == "unique":
            await models.delete_one({"id": "channel-a"})
        if identity == "zero":
            await models.delete_many({})
        if identity not in {"ambiguous", "unique", "zero"}:
            doc["model_id"] = "deleted-config" if identity == "missing" else "channel-b"
        if identity == "id_only":
            doc["model"] = ""
        if identity == "mismatch":
            doc["model"] = "different-model"
        await collection.insert_one(doc)
        result = await backfill._backfill_locked(usage=usage, dry_run=False, batch_size=10)
        stored = await collection.find_one({"trace_id": "identity"})
        if identity in {"explicit", "id_only", "unique"}:
            assert result["priced"] == 1 and stored["cost_usd"] == 12
        else:
            assert result["priced"] == 0 and stored["cost_available"] is False
    finally:
        await client[settings.MONGODB_DB].drop_collection(name)
        await client[settings.MONGODB_DB].drop_collection(name + "_models")
        await client.close()


@pytest.mark.skipif(
    os.environ.get("TEST_MEMORY_MONGODB") != "1", reason="Enable configured local MongoDB tests"
)
async def test_backfill_advances_past_unknown_first_batch(monkeypatch):
    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True)
    name = f"test_usage_pagination_{uuid4().hex}"
    collection = client[settings.MONGODB_DB][name]
    usage = UsageStorage()
    usage._collection = collection
    try:
        await collection.insert_many(
            [
                {"trace_id": "unknown", "started_at": "1", "usage_incomplete": True},
                {
                    "trace_id": "known",
                    "started_at": "2",
                    "model": "synthetic",
                    "usage_incomplete": False,
                    "input_includes_cache": True,
                    "input_tokens": 100,
                    "output_tokens": 10,
                    "cache_read_tokens": 0,
                    "cache_creation_tokens": 0,
                },
            ]
        )
        monkeypatch.setattr(
            backfill,
            "resolve_price",
            AsyncMock(
                return_value=SimpleNamespace(
                    rates=PriceRates(input=1, output=2, cache_read=0, cache_write=0)
                )
            ),
        )
        monkeypatch.setattr(backfill, "_resolve_config_id_by_value", AsyncMock(return_value=None))
        result = await backfill._backfill_locked(usage=usage, dry_run=False, batch_size=1)
        assert result["scanned"] == 2 and result["priced"] == 1
        assert result["still_unpriced"] == 1
        assert (await collection.find_one({"trace_id": "known"}))["cost_available"] is True
    finally:
        await client[settings.MONGODB_DB].drop_collection(name)
        await client.close()


@pytest.mark.skipif(
    os.environ.get("TEST_MEMORY_MONGODB") != "1", reason="Enable configured local MongoDB tests"
)
@pytest.mark.parametrize(
    "change", ["counts", "incomplete", "priced", "model", "model_id", "certificate"]
)
async def test_backfill_cannot_overwrite_a_trace_changed_during_price_resolution(
    monkeypatch, change
):
    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True)
    name = f"test_usage_backfill_cas_{uuid4().hex}"
    collection = client[settings.MONGODB_DB][name]
    usage = UsageStorage()
    usage._collection = collection
    try:
        await collection.insert_one(
            {
                "trace_id": "race",
                "model": "synthetic-model",
                "input_tokens": 100,
                "output_tokens": 10,
                "cache_read_tokens": 0,
                "cache_creation_tokens": 0,
                "cost_available": False,
                "usage_incomplete": False,
                "input_includes_cache": True,
            }
        )

        async def resolve(**kwargs):
            updates = (
                {"input_includes_cache": False}
                if change == "certificate"
                else {"model_id": "changed-config"}
                if change == "model_id"
                else {"model": "changed-model"}
                if change == "model"
                else {"input_tokens": 200}
                if change == "counts"
                else {"usage_incomplete": True}
                if change == "incomplete"
                else {"cost_available": True, "cost_usd": 99.0}
            )
            await collection.update_one({"trace_id": "race"}, {"$set": updates})
            return SimpleNamespace(rates=PriceRates(input=1, output=2, cache_read=0, cache_write=0))

        monkeypatch.setattr(backfill, "resolve_price", resolve)
        monkeypatch.setattr(backfill, "_resolve_config_id_by_value", AsyncMock(return_value=None))
        result = await backfill._backfill_locked(usage=usage, dry_run=False, batch_size=10)
        stored = await collection.find_one({"trace_id": "race"})
        assert result["priced"] == 0
        if change == "priced":
            assert stored["cost_usd"] == 99.0 and result["still_unpriced"] == 0
        else:
            assert stored["cost_available"] is False and "cost_usd" not in stored
            assert result["still_unpriced"] == 1
    finally:
        await client[settings.MONGODB_DB].drop_collection(name)
        await client.close()


@pytest.mark.skipif(
    os.environ.get("TEST_MEMORY_MONGODB") != "1", reason="Enable configured local MongoDB tests"
)
async def test_usage_aggregates_only_certified_costs_and_keeps_free_zero(monkeypatch):
    from datetime import datetime, timezone

    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True)
    name = f"test_usage_cost_certified_{uuid4().hex}"
    collection = client[settings.MONGODB_DB][name]
    usage = UsageStorage()
    usage._collection = collection
    base = {
        "user_id": "cost-owner",
        "model": "synthetic",
        "agent_name": "Agent",
        "started_at": datetime.now(timezone.utc),
        "status": "completed",
        "input_tokens": 100,
        "output_tokens": 10,
        "total_tokens": 110,
        "cache_read_tokens": 0,
        "cache_creation_tokens": 0,
        "cost_available": True,
    }
    try:
        await collection.insert_many(
            [
                {
                    **base,
                    "trace_id": "free",
                    "cost_usd": 0,
                    "usage_incomplete": False,
                    "input_includes_cache": True,
                    "cache_metrics_available": True,
                },
                {
                    **base,
                    "trace_id": "priced",
                    "cost_usd": 0.2,
                    "usage_incomplete": False,
                    "input_includes_cache": True,
                    "cache_metrics_available": True,
                },
                {**base, "trace_id": "incomplete", "cost_usd": 0.5, "usage_incomplete": True},
                {**base, "trace_id": "legacy", "cost_usd": 0.3},
            ]
        )
        stats = await usage.get_usage_stats_only(user_id="cost-owner")
        assert stats["total_cost_usd"] == 0.2
        assert stats["priced_requests"] == 2 and stats["unpriced_requests"] == 2
        assert stats["cache_unknown_requests"] == 2
        assert stats["usage_unknown_requests"] == 2
        dashboard = await usage.get_usage_dashboard(user_id="cost-owner")
        assert dashboard["summary"]["total_cost_usd"] == 0.2
        assert dashboard["summary"]["unpriced_requests"] == 2
        assert dashboard["top_models"][0]["cost_usd"] == 0.2
        assert dashboard["top_models"][0]["unpriced_requests"] == 2
        assert dashboard["top_models"][0]["cache_read_share"] == 0.0
        assert dashboard["top_models"][0]["zero_cache_requests"] == 2
        assert dashboard["summary"]["cache_read_share"] == 0.0
        assert dashboard["daily"][0]["cost_usd"] == 0.2
        assert dashboard["daily"][0]["unpriced_requests"] == 2
    finally:
        await client[settings.MONGODB_DB].drop_collection(name)
        await client.close()


@pytest.mark.skipif(
    os.environ.get("TEST_MEMORY_MONGODB") != "1", reason="Enable configured local MongoDB tests"
)
async def test_legacy_cost_certificate_is_required_by_every_cost_aggregate():
    from datetime import datetime, timezone

    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True)
    collection = client[settings.MONGODB_DB][f"test_raw_cost_{uuid4().hex}"]
    usage = UsageStorage()
    usage._collection = collection
    try:
        for index, certificate in enumerate([None, False, 1, True]):
            doc = {
                "trace_id": str(index),
                "user_id": "owner",
                "agent_name": "Agent",
                "model": "raw",
                "started_at": datetime.now(timezone.utc),
                "input_tokens": 100,
                "output_tokens": 10,
                "total_tokens": 110,
                "cost_available": True,
                "usage_incomplete": False,
                "cost_usd": 0.2,
            }
            if certificate is not None:
                doc["input_includes_cache"] = certificate
            await collection.insert_one(doc)
        stats = await usage.get_usage_stats_only()
        assert stats["total_cost_usd"] == 0.2
        assert stats["priced_requests"] == 1 and stats["unpriced_requests"] == 3
        listing = await usage.list_usage_logs()
        assert sum(row["cost_available"] for row in listing[0]) == 1
        dashboard = await usage.get_usage_dashboard()
        for row in [dashboard["summary"], *dashboard["daily"], *dashboard["top_models"]]:
            assert row.get("total_cost_usd", row.get("cost_usd")) == 0.2
            assert row["unpriced_requests"] == 3
    finally:
        await collection.drop()
        await client.close()
