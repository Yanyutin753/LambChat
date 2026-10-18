"""An explicit complete-cost receipt can coexist with an unknown free cache-write count."""

import os
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pymongo import AsyncMongoClient

from src.infra.storage.mongodb import build_mongo_connection_string
from src.infra.usage.storage import UsageStorage
from src.kernel.config import settings
from src.kernel.schemas.usage import UsageLog


def _usage(certificate=True):
    return dict(
        input_tokens=100,
        output_tokens=10,
        total_tokens=110,
        cache_read_tokens=20,
        cache_creation_tokens=0,
        input_includes_cache=True,
        usage_incomplete=True,
        unknown_usage_fields=["cache_creation_tokens"],
        cost_usd=0.0001,
        cost_complete=certificate,
        cost_rates=dict(input=1, output=2, cache_read=0, cache_write=0, cache_write_included=True),
    )


@pytest.mark.parametrize("certificate", [True, False, None, 1])
async def test_free_write_cost_certificate_is_strict_and_does_not_certify_missing_token_count(
    certificate,
):
    storage = UsageStorage()
    storage._collection = SimpleNamespace(update_one=AsyncMock())
    await storage.upsert_usage_log_from_trace_metadata(
        {"trace_id": "free-write"}, _usage(certificate)
    )
    doc = storage._collection.update_one.call_args.args[1]["$set"]
    assert doc["cost_available"] is (certificate is True)
    assert doc["cost_complete"] is (certificate is True)
    assert doc["usage_incomplete"] is True
    assert doc["unknown_usage_fields"] == ["cache_creation_tokens"]
    assert doc["partial_cost_usd"] is None
    assert doc["cost_rates"] == _usage()["cost_rates"]


@pytest.mark.parametrize("write_rate", [None, 0])
async def test_included_known_write_count_preserves_complete_cost_with_no_separate_write_price(
    write_rate,
):
    storage = UsageStorage()
    storage._collection = SimpleNamespace(update_one=AsyncMock())
    usage = _usage()
    usage.update(
        cache_creation_tokens=10,
        usage_incomplete=False,
        unknown_usage_fields=[],
        cost_usd=0.000194,
        cost_rates=dict(
            input=2,
            output=3,
            cache_read=0.2,
            cache_write=write_rate,
            cache_write_included=True,
        ),
    )
    await storage.upsert_usage_log_from_trace_metadata({"trace_id": "included-known-write"}, usage)
    doc = storage._collection.update_one.call_args.args[1]["$set"]
    assert doc["cost_available"] is True
    assert doc["cost_complete"] is True
    assert doc["cost_usd"] == usage["cost_usd"]
    assert doc["cost_rates"] == usage["cost_rates"]
    for field in (
        "input_tokens",
        "output_tokens",
        "total_tokens",
        "cache_read_tokens",
        "cache_creation_tokens",
    ):
        assert doc[field] == usage[field]
    assert doc["usage_incomplete"] is False
    assert doc["unknown_usage_fields"] == []


@pytest.mark.parametrize("field", ["input_tokens", "output_tokens", "cache_read_tokens"])
async def test_complete_cost_receipt_cannot_override_an_unknown_required_counter(field):
    storage = UsageStorage()
    storage._collection = SimpleNamespace(update_one=AsyncMock())
    usage = _usage()
    usage["unknown_usage_fields"].append(field)
    await storage.upsert_usage_log_from_trace_metadata({"trace_id": "invalid-receipt"}, usage)
    doc = storage._collection.update_one.call_args.args[1]["$set"]
    assert doc["cost_available"] is False
    assert doc["cost_complete"] is False


def test_usage_api_preserves_the_independent_complete_cost_receipt():
    payload = UsageLog(
        trace_id="t",
        session_id="s",
        user_id="u",
        cost_complete=True,
        cost_rates=_usage()["cost_rates"],
    ).model_dump()
    assert payload["cost_complete"] is True
    assert payload["cost_rates"] == _usage()["cost_rates"]


def test_cost_complete_schema_cannot_coerce_a_numeric_certificate():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        UsageLog(trace_id="t", session_id="s", user_id="u", cost_complete=1)


@pytest.mark.parametrize(
    "write_rate, write_tokens", [(1, 20), (False, 20), (float("nan"), 20), (0, 90)]
)
async def test_new_cost_receipt_cannot_override_conflicting_known_cache_counts_or_policy(
    write_rate, write_tokens
):
    storage = UsageStorage()
    storage._collection = SimpleNamespace(update_one=AsyncMock())
    usage = _usage()
    usage.update(unknown_usage_fields=["total_tokens"], cache_creation_tokens=write_tokens)
    usage["cost_rates"]["cache_write"] = write_rate
    await storage.upsert_usage_log_from_trace_metadata({"trace_id": "conflicting-receipt"}, usage)
    doc = storage._collection.update_one.call_args.args[1]["$set"]
    assert doc["cost_available"] is False and doc["cost_complete"] is False


@pytest.mark.parametrize("included", [None, False, 1])
async def test_missing_write_count_receipt_requires_literal_included_write_billing_flag(included):
    storage = UsageStorage()
    storage._collection = SimpleNamespace(update_one=AsyncMock())
    usage = _usage()
    usage["cost_rates"]["cache_write_included"] = included
    await storage.upsert_usage_log_from_trace_metadata({"trace_id": "invalid-free-rate"}, usage)
    doc = storage._collection.update_one.call_args.args[1]["$set"]
    assert doc["cost_available"] is False and doc["cost_complete"] is False


@pytest.mark.skipif(
    os.environ.get("TEST_MEMORY_MONGODB") != "1", reason="Explicit real MongoDB opt-in"
)
async def test_every_aggregate_accepts_only_valid_literal_complete_cost_receipts():
    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True)
    collection = client[settings.MONGODB_DB][f"test_complete_cost_{uuid4().hex}"]
    storage = UsageStorage()
    storage._collection = collection
    common = dict(
        user_id="owner",
        agent_name="Agent",
        model="model",
        team_id="team",
        persona_preset_id="persona",
        source="scheduled_task",
        scheduled_task_trigger_type="interval",
        started_at=datetime(2026, 10, 18, tzinfo=timezone.utc),
    )
    try:
        docs = []
        for index, certificate in enumerate([True, False, None, 1]):
            docs.append(
                dict(common, **_usage(certificate), trace_id=str(index), cost_available=True)
            )
        invalid = dict(common, **_usage(), trace_id="unknown-output", cost_available=True)
        invalid["unknown_usage_fields"] = ["cache_creation_tokens", "output_tokens"]
        docs.append(invalid)
        await collection.insert_many(docs)
        stats = await storage.get_usage_stats_only()
        dashboard = await storage.get_usage_dashboard()
        for aggregate in (
            stats,
            dashboard["summary"],
            *dashboard["daily"],
            *dashboard["top_models"],
        ):
            assert aggregate.get("total_cost_usd", aggregate.get("cost_usd")) == pytest.approx(
                0.0001
            )
            assert aggregate["priced_requests"] == 1
        assert stats["usage_unknown_requests"] == 5
        assert stats["unknown_usage_fields"] == ["output_tokens", "cache_creation_tokens"]
    finally:
        await collection.drop()
        await client.close()
