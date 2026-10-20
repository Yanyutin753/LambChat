"""Concurrent successful retention must not erase provenance or forgetting barriers."""

import asyncio
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from pymongo import AsyncMongoClient

from src.infra.memory.client.native import backend as backend_module
from src.infra.memory.client.native.backend import NativeMemoryBackend
from src.infra.memory.forgetting import source_watermark
from src.infra.session.conversation_history import ConversationHistoryService
from src.infra.session.manager import SessionManager
from src.infra.storage.mongodb import build_mongo_connection_string
from src.infra.utils.datetime import utc_now

pytestmark = pytest.mark.skipif(
    os.environ.get("TEST_MEMORY_MONGODB") != "1", reason="Opt-in real MongoDB"
)


@pytest.fixture
async def retain_lineage(monkeypatch):
    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True, timeoutMS=10000)
    name = f"memory_retain_lineage_{uuid4().hex}"
    db = client[name]
    backend = NativeMemoryBackend()
    backend._collection = db.native_memories
    backend._maybe_embed = AsyncMock(return_value=None)
    backend._invalidate_cache = AsyncMock()
    manager = SessionManager()
    manager.storage._collection = db.sessions
    history = ConversationHistoryService(
        trace_storage=SimpleNamespace(collection=db.traces), session_manager=manager
    )
    monkeypatch.setattr(backend_module, "ConversationHistoryService", lambda: history)
    monkeypatch.setattr(backend_module.settings, "NATIVE_MEMORY_VECTOR_BACKEND", "mongo")
    try:
        await db.sessions.insert_many(
            {"session_id": sid, "user_id": "other" if sid == "foreign" else "owner"}
            for sid in ("old", "a", "b", "foreign")
        )
        await db.traces.insert_many(
            {"session_id": sid, "run_id": sid, "status": "completed"}
            for sid in ("old", "a", "b", "foreign")
        )
        await db.native_memories.insert_one(
            {
                "user_id": "owner",
                "memory_id": "canonical",
                "revision_id": "initial",
                "content": "The workshop ships parcels on Tuesday.",
                "content_storage_mode": "inline",
                "source": "auto_retained",
                "source_refs": [{"session_id": "old", "run_id": "old"}],
                "origin_session_ids": ["old"],
                "scope": "user",
                "project_id": None,
                "updated_at": utc_now(),
                "title": "Parcels",
                "summary": "Tuesday parcels",
                "tags": ["parcels"],
                "context": "user",
                "memory_type": "user",
            }
        )
        yield backend, db, history
    finally:
        await client.drop_database(name)
        await client.close()


async def update(backend, label, **kwargs):
    return await backend.retain(
        "owner",
        f"The workshop ships parcels on {label}.",
        title="Parcels",
        summary=f"Shipping day {label}",
        tags=["parcels"],
        existing_memory_id="canonical",
        context="user",
        **kwargs,
    )


@pytest.mark.parametrize("with_refs", [False, True])
async def test_concurrent_successful_updates_keep_all_sources_for_forgetting(
    retain_lineage, with_refs
):
    backend, db, _history = retain_lineage
    ready = asyncio.Event()
    arrivals = 0

    async def pause_both(_content):
        nonlocal arrivals
        arrivals += 1
        if arrivals == 2:
            ready.set()
        await asyncio.wait_for(ready.wait(), 5)
        return None

    backend._maybe_embed = pause_both
    results = await asyncio.gather(
        *(
            update(
                backend,
                label,
                origin_session_id=label,
                **({"source_refs": [{"session_id": label, "run_id": label}]} if with_refs else {}),
            )
            for label in ("a", "b")
        )
    )
    assert all(result["success"] for result in results)
    current = await db.native_memories.find_one({"memory_id": "canonical"})
    assert set(current["origin_session_ids"]) == {"old", "a", "b"}
    if with_refs:
        assert {ref["session_id"] for ref in current["source_refs"]} == {"old", "a", "b"}
    assert (await backend.delete("owner", "canonical"))["success"]
    for label in ("old", "a", "b"):
        assert await source_watermark(db, "owner", label) is not None
        assert await source_watermark(db, "other", label) is None


@pytest.mark.parametrize("failure", [OSError, asyncio.CancelledError])
async def test_source_validation_outage_does_not_replace_content_or_erase_lineage(
    retain_lineage, failure
):
    backend, db, history = retain_lineage
    before = await db.native_memories.find_one({"memory_id": "canonical"})
    history.validate_source_refs = AsyncMock(side_effect=failure("history unavailable"))
    with pytest.raises(failure, match="history unavailable"):
        await update(backend, "Friday", source_refs=[{"session_id": "a", "run_id": "a"}])
    assert await db.native_memories.find_one({"memory_id": "canonical"}) == before
    backend._maybe_embed.assert_not_awaited()


async def test_rejected_foreign_reference_is_not_promoted_into_origin_sessions(retain_lineage):
    backend, db, _history = retain_lineage
    await db.native_memories.update_one(
        {"memory_id": "canonical"},
        {"$push": {"source_refs": {"session_id": "foreign", "run_id": "foreign"}}},
    )
    result = await update(
        backend,
        "Thursday",
        source_refs=[
            {"session_id": "a", "run_id": "a"},
            {"session_id": "foreign", "run_id": "foreign"},
        ],
    )
    assert result["success"]
    current = await db.native_memories.find_one({"memory_id": "canonical"})
    assert {ref["session_id"] for ref in current["source_refs"]} == {"old", "a"}
    assert set(current["origin_session_ids"]) == {"old", "a"}


async def test_concurrently_appended_source_without_origin_survives_and_is_forgotten(
    retain_lineage,
):
    backend, db, _history = retain_lineage

    async def append_during_embedding(_content):
        await db.native_memories.update_one(
            {"memory_id": "canonical"},
            {"$push": {"source_refs": {"session_id": "b", "run_id": "b"}}},
        )
        return None

    backend._maybe_embed = append_during_embedding
    assert (await update(backend, "Wednesday", source_refs=[{"session_id": "a", "run_id": "a"}]))[
        "success"
    ]
    current = await db.native_memories.find_one({"memory_id": "canonical"})
    assert [ref["session_id"] for ref in current["source_refs"]] == ["old", "b", "a"]
    assert set(current["origin_session_ids"]) == {"old", "a", "b"}
    assert (await backend.delete("owner", "canonical"))["success"]
    assert await source_watermark(db, "owner", "b") is not None


async def test_revision_guard_still_rejects_the_losing_concurrent_writer(retain_lineage):
    backend, db, _history = retain_lineage
    ready = asyncio.Event()
    arrivals = 0

    async def pause_both(_content):
        nonlocal arrivals
        arrivals += 1
        if arrivals == 2:
            ready.set()
        await asyncio.wait_for(ready.wait(), 5)
        return None

    backend._maybe_embed = pause_both
    results = await asyncio.gather(
        *(
            update(
                backend,
                label,
                origin_session_id=label,
                expected_revision={"revision_id": "initial"},
            )
            for label in ("a", "b")
        )
    )
    assert sum(result["success"] for result in results) == 1
    loser = next(result for result in results if not result["success"])
    assert loser["error"] == "memory_changed_since_inventory"
    winner = next(label for label, result in zip(("a", "b"), results) if result["success"])
    current = await db.native_memories.find_one({"memory_id": "canonical"})
    assert set(current["origin_session_ids"]) == {"old", winner}


@pytest.mark.parametrize("legacy_without_origins", [False, True])
async def test_reference_limit_refreshes_duplicates_and_keeps_all_forget_origins(
    retain_lineage, legacy_without_origins
):
    from src.infra.session.conversation_history_index import merge_source_refs

    backend, db, _history = retain_lineage
    labels = [f"source-{index}" for index in range(20)]
    refs = [{"session_id": label, "run_id": label} for label in labels]
    await db.sessions.insert_many({"session_id": label, "user_id": "owner"} for label in labels)
    await db.traces.insert_many(
        {"session_id": label, "run_id": label, "status": "completed"} for label in labels
    )
    await db.native_memories.update_one(
        {"memory_id": "canonical"},
        {
            "$set": {
                "source_refs": refs,
                "origin_session_ids": [] if legacy_without_origins else labels,
            }
        },
    )
    additions = [{"session_id": "a", "run_id": "a"}, refs[0]]
    assert (await update(backend, "Saturday", source_refs=additions))["success"]
    current = await db.native_memories.find_one({"memory_id": "canonical"})
    assert current["source_refs"] == [
        ref.model_dump() for ref in merge_source_refs(refs, additions)
    ]
    assert len(current["source_refs"]) == 20
    assert set(current["origin_session_ids"]) == {*labels, "a"}
    assert (await backend.delete("owner", "canonical"))["success"]
    for label in [*labels, "a"]:
        assert await source_watermark(db, "owner", label) is not None


async def test_dollar_prefixed_source_identifiers_remain_literal(retain_lineage):
    backend, db, _history = retain_lineage
    ref = {"session_id": "$user_id", "run_id": "$revision_id"}
    await db.sessions.insert_one({"session_id": ref["session_id"], "user_id": "owner"})
    await db.traces.insert_one({**ref, "status": "completed"})
    assert (await update(backend, "Sunday", source_refs=[ref]))["success"]
    current = await db.native_memories.find_one({"memory_id": "canonical"})
    assert current["source_refs"] == [{"session_id": "old", "run_id": "old"}, ref]
    assert set(current["origin_session_ids"]) == {"old", "$user_id"}
    assert (await backend.delete("owner", "canonical"))["success"]
    assert await source_watermark(db, "owner", "$user_id") is not None
    assert await source_watermark(db, "other", "$user_id") is None
