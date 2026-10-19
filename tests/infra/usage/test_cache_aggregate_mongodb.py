"""Real MongoDB cache-rate aggregation; opt in with TEST_MEMORY_MONGODB=1."""

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pymongo import AsyncMongoClient

from src.infra.storage.mongodb import build_mongo_connection_string
from src.infra.usage.storage import UsageStorage
from src.kernel.config import settings

pytestmark = pytest.mark.skipif(
    os.environ.get("TEST_MEMORY_MONGODB") != "1", reason="Enable configured local MongoDB tests"
)


@pytest.mark.parametrize(
    "scenario, expected_unknown, expected_share",
    [
        ("mixed_zero", 1, 0.4),
        ("all_certified", 0, 0.4),
        ("legacy", 2, 0.4),
        ("all_zero", 0, 0.0),
        ("unknown_union", 2, 0.4),
    ],
)
async def test_cache_aggregates_use_available_counts(scenario, expected_unknown, expected_share):
    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True)
    collection = client[settings.MONGODB_DB][f"test_cache_aggregate_{uuid4().hex}"]
    storage = UsageStorage()
    storage._collection = collection
    try:
        for index in range(2):
            usage = {
                "input_tokens": 100,
                "output_tokens": 1,
                "total_tokens": 101,
                "cache_read_tokens": 0 if index == 0 or scenario == "all_zero" else 80,
                "cache_creation_tokens": 100 if index == 0 else 0,
                "unknown_usage_fields": [],
                "input_includes_cache": scenario == "all_certified" or index == 1,
            }
            if scenario == "all_zero" and index == 0:
                usage.pop("cache_creation_tokens")
                usage["unknown_usage_fields"] = ["cache_creation_tokens"]
            if scenario == "unknown_union" and index == 0:
                usage["unknown_usage_fields"] = ["input_tokens", "cache_read_tokens"]
            await storage.upsert_usage_log_from_trace_metadata(
                {
                    "trace_id": f"cache-{index}",
                    "user_id": "user",
                    "agent_id": "agent",
                    "started_at": datetime(2026, 10, 18, tzinfo=timezone.utc),
                    "metadata": {
                        "agent_name": "Agent",
                        "team_id": "team",
                        "team_name": "Team",
                        "persona_preset_id": "persona",
                        "persona_preset_name": "Persona",
                        "model": "model",
                        "username": "User",
                        "source": "scheduled_task",
                        "scheduled_task_trigger_type": "interval",
                    },
                },
                usage,
            )
        if scenario == "legacy":
            await collection.update_many(
                {}, {"$unset": {"input_includes_cache": "", "cache_metrics_available": ""}}
            )
        if scenario == "unknown_union":
            await collection.update_one(
                {"trace_id": "cache-1"}, {"$set": {"input_includes_cache": False}}
            )
        stats = await storage.get_usage_stats_only()
        assert stats["cache_unknown_requests"] == expected_unknown
        listing = await storage.list_usage_logs()
        assert listing[2]["cache_unknown_requests"] == expected_unknown
        dashboard = await storage.get_usage_dashboard()
        aggregates = [dashboard["summary"], *dashboard["daily"]]
        for key in (
            "top_agents",
            "top_teams",
            "top_personas",
            "top_models",
            "top_users",
            "sources",
            "triggers",
        ):
            assert len(dashboard[key]) == 1
            aggregates.extend(dashboard[key])
        for aggregate in aggregates:
            assert aggregate["cache_unknown_requests"] == expected_unknown
            assert aggregate["cache_read_share"] == expected_share
    finally:
        await collection.drop()
        await client.close()
