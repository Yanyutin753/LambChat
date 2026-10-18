"""Real MongoDB billing categories, including BSON numeric/boolean distinctions."""

import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pymongo import AsyncMongoClient

from src.infra.storage.mongodb import build_mongo_connection_string
from src.infra.usage.storage import UsageStorage
from src.kernel.config import settings


@pytest.mark.skipif(
    os.environ.get("TEST_MEMORY_MONGODB") != "1", reason="Explicit real MongoDB opt-in"
)
async def test_mixed_cost_certainties_reach_every_aggregate_without_recertifying_history():
    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True)
    storage = UsageStorage()
    collection = client[settings.MONGODB_DB][f"test_cost_certainty_{uuid4().hex}"]
    storage._collection = collection
    common = dict(
        user_id="user",
        username="User",
        agent_name="Agent",
        team_id="team",
        team_name="Team",
        persona_preset_id="persona",
        persona_preset_name="Persona",
        model="model",
        source="scheduled_task",
        scheduled_task_trigger_type="interval",
        started_at=datetime(2026, 10, 18, tzinfo=timezone.utc),
        input_tokens=100,
        output_tokens=10,
        total_tokens=110,
        cache_read_tokens=0,
        cache_creation_tokens=0,
    )
    records = [
        dict(
            trace_id="confirmed",
            cost_usd=1.0,
            cost_available=True,
            usage_incomplete=False,
            input_includes_cache=True,
            partial_cost_usd=99.0,
        ),
        dict(
            trace_id="partial",
            partial_cost_usd=0.25,
            input_includes_cache=True,
            usage_incomplete=True,
            cost_available=False,
        ),
        dict(trace_id="legacy", cost_usd=3.5, cost_available=True),
        dict(
            trace_id="numeric-input",
            cost_usd=5.0,
            cost_available=True,
            usage_incomplete=False,
            input_includes_cache=1,
        ),
        dict(
            trace_id="numeric-incomplete",
            cost_usd=7.0,
            cost_available=True,
            usage_incomplete=0,
            input_includes_cache=True,
        ),
        dict(
            trace_id="numeric-available",
            cost_usd=11.0,
            cost_available=1,
            usage_incomplete=False,
            input_includes_cache=True,
        ),
        dict(trace_id="invalid-partial", partial_cost_usd=True, input_includes_cache=True),
        dict(trace_id="zero-partial", partial_cost_usd=0.0, input_includes_cache=True),
        dict(trace_id="infinite-partial", partial_cost_usd=float("inf"), input_includes_cache=True),
        dict(trace_id="nan-estimate", cost_usd=float("nan"), cost_available=True),
        *[
            dict(
                trace_id=f"invalid-confirmed-{index}",
                cost_usd=amount,
                cost_available=True,
                usage_incomplete=False,
                input_includes_cache=True,
            )
            for index, amount in enumerate([True, -1, float("nan"), float("inf"), "0.5"])
        ],
    ]
    try:
        await collection.insert_many([dict(common, **record) for record in records])
        stats = await storage.get_usage_stats_only()
        items, _, listing_stats = await storage.list_usage_logs()
        dashboard = await storage.get_usage_dashboard()
        user_summary = await storage.get_user_usage_summary("user")
        aggregates = [stats, listing_stats, dashboard["summary"], user_summary, *dashboard["daily"]]
        for field in (
            "top_agents",
            "top_teams",
            "top_personas",
            "top_models",
            "top_users",
            "sources",
            "triggers",
        ):
            assert len(dashboard[field]) == 1
            aggregates.extend(dashboard[field])
        for aggregate in aggregates:
            assert aggregate.get("total_cost_usd", aggregate.get("cost_usd")) == 1.0
            assert aggregate["partial_cost_usd"] == 0.25
            assert aggregate["partial_requests"] == 2
            assert aggregate["estimated_cost_usd"] == 15.5
            assert aggregate["estimated_requests"] == 3
        by_id = {item["trace_id"]: item for item in items}
        assert by_id["confirmed"]["partial_cost_usd"] is None
        assert by_id["legacy"]["estimated_cost_usd"] == 3.5
        assert by_id["partial"]["estimated_cost_usd"] is None
        assert by_id["numeric-available"]["cost_available"] is False
        assert by_id["invalid-partial"]["partial_cost_usd"] is None
        saved = await collection.find_one({"trace_id": "legacy"})
        assert "usage_incomplete" not in saved and "input_includes_cache" not in saved
        assert saved["cost_available"] is True
    finally:
        await collection.drop()
        await client.close()


@pytest.mark.skipif(
    os.environ.get("TEST_MEMORY_MONGODB") != "1", reason="Explicit real MongoDB opt-in"
)
async def test_settlement_certainty_matches_mongo_without_token_certificates():
    from src.infra.usage.cost_certainty import (
        PARTIAL_USAGE_CONDITION,
        PRICED_USAGE_CONDITION,
        _usage_cost_fields,
    )

    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True)
    collection = client[settings.MONGODB_DB][f"test_settlement_cost_{uuid4().hex}"]
    docs = [
        {
            "_id": "known",
            "cost_source": "provider_settlement",
            "cost_units": 500,
            "cost_usd": 0.0000005,
            "cost_complete": True,
        },
        {
            "_id": "partial",
            "cost_source": "provider_settlement",
            "cost_units": 250,
            "partial_cost_usd": 0.00000025,
            "cost_complete": False,
        },
        {
            "_id": "unknown",
            "cost_source": "provider_settlement",
            "cost_units": 0,
            "partial_cost_usd": 0.0,
            "cost_complete": False,
        },
    ]
    try:
        await collection.insert_many(docs)
        rows = await (
            await collection.aggregate(
                [
                    {
                        "$project": {
                            "priced": PRICED_USAGE_CONDITION,
                            "partial": PARTIAL_USAGE_CONDITION,
                        }
                    }
                ]
            )
        ).to_list()
        by_id = {doc["_id"]: _usage_cost_fields(doc) for doc in docs}
        for row in rows:
            assert row["priced"] is by_id[row["_id"]]["cost_available"]
            assert row["partial"] is (by_id[row["_id"]]["partial_cost_usd"] is not None)
    finally:
        await collection.drop()
        await client.close()
