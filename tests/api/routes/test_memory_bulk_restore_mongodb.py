"""Real HTTP route/Mongo recovery at the declared six-month capacity tier."""

import json
import os
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from pymongo import AsyncMongoClient

from src.api.deps import get_current_user_required
from src.api.routes import memory as routes
from src.infra.memory.client.native.backend import NativeMemoryBackend
from src.infra.storage.mongodb import build_mongo_connection_string
from src.infra.storage.mongodb_store import MongoDBStore
from src.kernel.schemas.user import TokenPayload


@pytest.mark.skipif(
    os.environ.get("TEST_MEMORY_BULK_RESTORE") != "1", reason="Opt-in 50k real Mongo restore"
)
async def test_fifty_thousand_memory_backup_preflight_restore_retry_and_export(monkeypatch):
    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True, timeoutMS=30000)
    database_name = f"memory_restore_{uuid4().hex}"
    db = client[database_name]
    backend = NativeMemoryBackend()
    backend._collection = db.native_memories
    backend._store = MongoDBStore(client=client, db_name=database_name)
    backend._maybe_embed = AsyncMock(return_value=None)
    backend._invalidate_cache = AsyncMock()
    monkeypatch.setattr(routes, "_get_backend", AsyncMock(return_value=backend))
    monkeypatch.setattr(routes.settings, "NATIVE_MEMORY_VECTOR_BACKEND", "mongo")
    monkeypatch.setattr(routes, "_get_memory_import_content_max_chars", lambda: 64_000)
    monkeypatch.setattr(routes, "_get_memory_import_total_content_max_chars", lambda: 2_000_000)
    monkeypatch.setattr(routes, "_get_memory_export_content_max_chars", lambda: 64_000)
    app = FastAPI()
    app.include_router(routes.router, prefix="/api/memory")
    app.dependency_overrides[get_current_user_required] = lambda: TokenPayload(
        sub="owner",
        username="owned-bulk-restore",
        roles=["user"],
    )
    backup = []
    for index in range(50_000):
        body = f"业务约定 {index}: archive for {index % 180 + 1} days."
        if index % 500 == 0:
            body += (
                "\n" + "Supplier archive record. " * 200 + f"\nWarranty tail: {index + 53} months."
            )
        backup.append(
            {
                "memory_id": uuid4().hex,
                "content": body,
                "title": f"Archive {index}",
                "summary": f"Durable contract {index}",
                "scope": "user",
                "memory_type": "user",
                "source": "auto_retained",
                "origin_session_ids": [f"source-day-{index % 180}"],
                "created_at": "2026-04-23T00:00:00+00:00",
                "updated_at": "2026-04-23T00:00:00+00:00",
            }
        )
    batches = [backup[start : start + 1000] for start in range(0, len(backup), 1000)]
    try:
        await db.native_memories.create_index("memory_id", unique=True)
        foreign = {
            "user_id": "other",
            "memory_id": uuid4().hex,
            "content": "Other user's private fact.",
        }
        await db.native_memories.insert_one(foreign)
        foreign_before = await db.native_memories.find_one({"user_id": "other"})
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://owned-test"
        ) as http:
            for batch in batches:
                response = await http.post(
                    "/api/memory/import?validate_only=true", json={"memories": batch}
                )
                assert response.status_code == 200
                assert response.json()["validated"] == 1000
            assert await db.native_memories.count_documents({"user_id": "owner"}) == 0
            backend._maybe_embed.assert_not_awaited()
            backend._invalidate_cache.assert_not_awaited()
            totals = {"imported": 0, "created": 0, "overwritten": 0}
            for batch in batches:
                response = await http.post("/api/memory/import", json={"memories": batch})
                assert response.status_code == 200
                for key in totals:
                    totals[key] += response.json()[key]
            assert totals == {"imported": 50_000, "created": 50_000, "overwritten": 0}
            assert await db.native_memories.count_documents({"user_id": "owner"}) == 50_000
            # An acknowledged-batch retry overwrites stable IDs instead of duplicating data.
            repeated = await http.post("/api/memory/import", json={"memories": batches[0]})
            assert repeated.json() == {
                "success": True,
                "imported": 1000,
                "created": 0,
                "overwritten": 1000,
            }
            assert await db.native_memories.count_documents({"user_id": "owner"}) == 50_000
            full = await http.get(f"/api/memory/{backup[0]['memory_id']}")
            assert full.json()["content"] == backup[0]["content"]
            exported = await http.get("/api/memory/export")
            assert exported.status_code == 200
            restored = json.loads(exported.content)["memories"]
            assert {row["memory_id"]: row["content"] for row in restored} == {
                row["memory_id"]: row["content"] for row in backup
            }
            assert all(not row.get("content_truncated") for row in restored)
            assert {row["memory_id"]: row["origin_session_ids"] for row in restored} == {
                row["memory_id"]: row["origin_session_ids"] for row in backup
            }
        assert await db.native_memories.find_one({"user_id": "other"}) == foreign_before
        assert backend._invalidate_cache.await_count == 51
    finally:
        await client.drop_database(database_name)
        await client.close()
