"""Real MongoDB fences for late usage snapshots from competing finalizers."""

import asyncio
import os
from uuid import uuid4

import pytest
from pymongo import AsyncMongoClient

from src.infra.storage.mongodb import build_mongo_connection_string
from src.infra.usage.storage import UsageStorage
from src.kernel.config import settings


@pytest.mark.skipif(
    os.environ.get("TEST_MEMORY_MONGODB") != "1", reason="Explicit real MongoDB opt-in"
)
async def test_delayed_older_finalizer_cannot_overwrite_newer_usage():
    storage = UsageStorage()
    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True)
    storage._collection = client[settings.MONGODB_DB]["test_usage_revision_" + uuid4().hex]
    entered, release = asyncio.Event(), asyncio.Event()
    calls = 0

    async def session_metadata(session_id):
        nonlocal calls
        calls += 1
        if calls == 1:
            entered.set()
            await release.wait()
        return {}

    storage._get_session_metadata = session_metadata
    payload = dict(
        output_tokens=10,
        total_tokens=210,
        cache_read_tokens=0,
        cache_creation_tokens=0,
        input_includes_cache=True,
        usage_incomplete=False,
    )
    try:
        await storage.ensure_indexes()
        old = asyncio.create_task(
            storage.upsert_usage_log_from_trace_metadata(
                dict(trace_id="owned", session_id="s", status="cancelled", event_revision=1),
                dict(payload, input_tokens=100, total_tokens=110),
            )
        )
        await entered.wait()
        assert await storage.upsert_usage_log_from_trace_metadata(
            dict(trace_id="owned", session_id="s", status="cancelled", event_revision=2),
            dict(payload, input_tokens=200),
        )
        release.set()
        assert await old is False
        saved = await storage.collection.find_one({"trace_id": "owned"})
        assert saved["input_tokens"] == 200 and saved["total_tokens"] == 210
        assert await storage.collection.count_documents({"trace_id": "owned"}) == 1
        assert (
            await storage.upsert_usage_log_from_trace_metadata(
                dict(trace_id="owned", session_id="s", status="cancelled"),
                dict(payload, input_tokens=0, total_tokens=10),
            )
            is False
        )
        assert (await storage.collection.find_one({"trace_id": "owned"}))["input_tokens"] == 200
    finally:
        release.set()
        await storage.collection.drop()
        await client.close()
