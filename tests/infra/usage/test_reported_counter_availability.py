"""Reported counters stay visible independently of financial certification."""

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pymongo import AsyncMongoClient

from src.infra.storage.mongodb import build_mongo_connection_string
from src.infra.usage.formatting import _empty_dashboard, _empty_stats, _format_dashboard
from src.infra.usage.storage import UsageStorage
from src.kernel.config import settings
from src.kernel.schemas.usage import UsageDashboardResponse, UsageStats

TOKEN_FIELDS = [
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "cache_read_tokens",
    "cache_creation_tokens",
]


def test_aggregate_response_preserves_only_the_unreported_counter_names():
    counts = {"unreported_cache_creation_tokens_requests": 1, "usage_unknown_requests": 1}
    dashboard = UsageDashboardResponse.model_validate(
        _format_dashboard(
            {
                "summary": [counts],
                "daily": [dict(counts, _id="2026-10-18")],
                "models": [dict(counts, _id="model")],
            }
        )
    ).model_dump()
    for surface in (dashboard["summary"], dashboard["daily"][0], dashboard["top_models"][0]):
        assert surface["unknown_usage_fields"] == ["cache_creation_tokens"]
        assert surface["usage_unknown_requests"] == 1


def test_empty_stats_and_schemas_default_to_no_unreported_fields():
    for surface in (_empty_stats(), _empty_dashboard()["summary"], UsageStats().model_dump()):
        assert surface["unknown_usage_fields"] == []


@pytest.mark.skipif(
    os.environ.get("TEST_MEMORY_MONGODB") != "1", reason="Explicit real MongoDB opt-in"
)
@pytest.mark.parametrize(
    "scenario, expected",
    [
        ("legacy", []),
        ("write_only", ["cache_creation_tokens"]),
        ("missing_write", ["cache_creation_tokens"]),
        ("zero", []),
        ("bool_input", ["input_tokens"]),
        ("float_output", ["output_tokens"]),
        ("negative_total", ["total_tokens"]),
        ("string_read", ["cache_read_tokens"]),
        ("incomplete_no_fields", TOKEN_FIELDS),
        ("incomplete_empty_fields", TOKEN_FIELDS),
    ],
)
async def test_real_aggregates_separate_reported_counts_from_certified_usage(scenario, expected):
    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True)
    collection = client[settings.MONGODB_DB][f"test_reported_counts_{uuid4().hex}"]
    storage = UsageStorage()
    storage._collection = collection
    record = dict(
        trace_id="reported",
        user_id="owner",
        agent_name="Agent",
        model="model",
        started_at=datetime(2026, 10, 18, tzinfo=timezone.utc),
        input_tokens=100,
        output_tokens=10,
        total_tokens=110,
        cache_read_tokens=20,
        cache_creation_tokens=0,
    )
    if scenario == "write_only":
        record.update(
            usage_incomplete=True,
            unknown_usage_fields=["cache_creation_tokens"],
            input_includes_cache=True,
            cache_metrics_available=True,
        )
    elif scenario == "missing_write":
        record.pop("cache_creation_tokens")
    elif scenario == "zero":
        record.update({field: 0 for field in TOKEN_FIELDS})
    elif scenario == "bool_input":
        record["input_tokens"] = True
    elif scenario == "float_output":
        record["output_tokens"] = 10.0
    elif scenario == "negative_total":
        record["total_tokens"] = -1
    elif scenario == "string_read":
        record["cache_read_tokens"] = "20"
    elif scenario.startswith("incomplete_"):
        record["usage_incomplete"] = True
        if scenario == "incomplete_empty_fields":
            record["unknown_usage_fields"] = []
    try:
        await collection.insert_one(record)
        stats = await storage.get_usage_stats_only()
        _, _, listing_stats = await storage.list_usage_logs()
        dashboard = await storage.get_usage_dashboard()
        surfaces = [
            stats,
            listing_stats,
            dashboard["summary"],
            *dashboard["daily"],
            *dashboard["top_models"],
        ]
        for surface in surfaces:
            assert surface["unknown_usage_fields"] == expected
            assert surface["usage_unknown_requests"] == 1
        assert stats["total_cost_usd"] == 0.0
        if scenario == "legacy":
            assert stats["total_input_tokens"] == 100
            assert stats["total_output_tokens"] == 10
            assert stats["cache_unknown_requests"] == 1
        if scenario == "write_only":
            assert stats["total_input_tokens"] == 100
            assert stats["total_output_tokens"] == 10
            assert stats["total_cache_read_tokens"] == 20
    finally:
        await collection.drop()
        await client.close()


@pytest.mark.skipif(
    os.environ.get("TEST_MEMORY_MONGODB") != "1", reason="Explicit real MongoDB opt-in"
)
@pytest.mark.parametrize("invalid_count", [float("nan"), float("inf")])
async def test_nonfinite_record_cannot_poison_valid_reported_token_totals(invalid_count):
    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True)
    collection = client[settings.MONGODB_DB][f"test_nonfinite_counts_{uuid4().hex}"]
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
    valid = dict(
        input_tokens=100,
        output_tokens=10,
        total_tokens=110,
        cache_read_tokens=20,
        cache_creation_tokens=5,
    )
    try:
        await collection.insert_many(
            [
                dict(common, **valid, trace_id="valid"),
                dict(
                    common, **{field: invalid_count for field in TOKEN_FIELDS}, trace_id="invalid"
                ),
            ]
        )
        stats = await storage.get_usage_stats_only()
        _, _, listing_stats = await storage.list_usage_logs()
        user_summary = await storage.get_user_usage_summary("owner")
        dashboard = await storage.get_usage_dashboard()
        for aggregate in (stats, listing_stats, user_summary):
            assert aggregate["total_input_tokens"] == 100
            assert aggregate["total_output_tokens"] == 10
            assert aggregate["total_tokens"] == 110
            assert aggregate["unknown_usage_fields"] == TOKEN_FIELDS
        assert stats["total_cache_read_tokens"] == 20
        assert stats["total_cache_creation_tokens"] == 5
        summary = dashboard["summary"]
        assert summary["total_input_tokens"] == 100
        assert summary["total_output_tokens"] == 10
        assert summary["total_tokens"] == 110
        assert summary["total_cache_read_tokens"] == 20
        for key in (
            "daily",
            "top_agents",
            "top_teams",
            "top_personas",
            "top_models",
            "top_users",
            "sources",
            "triggers",
        ):
            assert len(dashboard[key]) == 1
            aggregate = dashboard[key][0]
            assert aggregate["tokens"] == 110
            assert aggregate["input_tokens"] == 100
            assert aggregate["cache_read_tokens"] == 20
            assert aggregate["cache_creation_tokens"] == 5
            assert aggregate["unknown_usage_fields"] == TOKEN_FIELDS
        UsageStats.model_validate(stats).model_dump_json()
        UsageDashboardResponse.model_validate(dashboard).model_dump_json()
    finally:
        await collection.drop()
        await client.close()
