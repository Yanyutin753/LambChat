"""Busy accounts and completed work must not monopolize background memory slots."""

import os
from datetime import timedelta
from unittest.mock import Mock
from uuid import uuid4

import pytest
from pymongo import AsyncMongoClient

from src.infra.memory import extraction
from src.infra.memory.evolution import reflector, scheduler
from src.infra.storage.mongodb import build_mongo_connection_string
from src.infra.utils.datetime import utc_now

pytestmark = pytest.mark.skipif(
    os.environ.get("TEST_MEMORY_MONGODB") != "1", reason="Opt-in real MongoDB"
)


@pytest.fixture
async def scheduling_db(monkeypatch):
    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True, timeoutMS=10000)
    name = f"memory_scheduler_fairness_{uuid4().hex}"
    db = client[name]
    monkeypatch.setattr(extraction.settings, "MONGODB_DB", name)
    monkeypatch.setattr("src.infra.storage.mongodb.get_mongo_client", lambda: client)
    monkeypatch.setattr(reflector, "_get_feedback_collection", lambda: db.feedback)
    monkeypatch.setattr(reflector, "_get_traces_collection", lambda: db.traces)
    monkeypatch.setattr(reflector, "_get_marks_collection", lambda: db.memory_evolution_marks)
    monkeypatch.setattr(extraction.settings, "ENABLE_MEMORY", True)
    monkeypatch.setattr(extraction.settings, "MEMORY_EXTRACTION_ENABLED", True)
    monkeypatch.setattr(extraction.settings, "MEMORY_EXTRACTION_INTERVAL_SECONDS", 900)
    try:
        yield db
    finally:
        await client.drop_database(name)
        await client.close()


async def test_one_busy_user_cannot_hide_other_users_idle_sessions(scheduling_db, monkeypatch):
    db = scheduling_db
    now = utc_now()
    await db.sessions.insert_many(
        [
            {"user_id": "busy", "is_active": True, "updated_at": now, "session_id": f"busy-{i}"}
            for i in range(201)
        ]
        + [{"user_id": "quiet", "is_active": True, "updated_at": now - timedelta(hours=1)}]
        + [
            {
                "user_id": "hidden",
                "is_active": True,
                "updated_at": now,
                "metadata": {"hidden_from_conversation_list": True},
            },
            {"user_id": "scheduled", "is_active": True, "updated_at": now, "session_id": "sch_one"},
            {"user_id": "inactive", "is_active": False, "updated_at": now},
        ]
    )
    kick = Mock()
    monkeypatch.setattr(extraction, "schedule_memory_extraction", kick)
    assert await extraction.run_scheduled_memory_extraction() == {"users": 2, "dispatched": 2}
    assert {call.args[0] for call in kick.call_args_list} == {"busy", "quiet"}


async def test_bounded_rounds_reach_every_user_without_waiting_days(scheduling_db, monkeypatch):
    now = utc_now()
    await scheduling_db.sessions.insert_many(
        [
            {"user_id": f"user-{i:03}", "is_active": True, "updated_at": now - timedelta(hours=1)}
            for i in range(125)
        ]
    )
    selections = []
    for step in range(3):
        kick = Mock()
        monkeypatch.setattr(extraction, "schedule_memory_extraction", kick)
        monkeypatch.setattr(
            extraction, "utc_now", lambda step=step: now + timedelta(seconds=900 * step)
        )
        assert await extraction.run_scheduled_memory_extraction() == {"users": 50, "dispatched": 50}
        selected = {call.args[0] for call in kick.call_args_list}
        assert len(selected) == 50
        selections.append(selected)
    assert len(set.union(*selections)) == 125


async def test_processed_feedback_does_not_fill_the_entire_user_cap(scheduling_db):
    now = utc_now()
    await scheduling_db.feedback.insert_many(
        [
            {
                "user_id": f"done-{i}",
                "rating": "down",
                "created_at": now - timedelta(hours=1),
                "evolution_processed": True,
            }
            for i in range(scheduler.MAX_USERS_PER_RUN)
        ]
        + [{"user_id": "waiting", "rating": "down", "created_at": now}]
    )
    assert await scheduler._collect_signal_user_ids(now - timedelta(hours=24)) == ["waiting"]


async def test_trace_slots_count_unique_users_with_unprocessed_owned_signals(scheduling_db):
    now = utc_now()
    await scheduling_db.traces.insert_many(
        [
            {"user_id": f"done-{i}", "run_id": f"done-{i}", "status": "error", "started_at": now}
            for i in range(scheduler.MAX_USERS_PER_RUN)
        ]
        + [
            {"user_id": "busy", "run_id": f"busy-{i}", "status": "error", "started_at": now}
            for i in range(101)
        ]
        + [{"user_id": "waiting", "run_id": "waiting-run", "status": "failed", "started_at": now}]
    )
    await scheduling_db.memory_evolution_marks.insert_many(
        [
            {"user_id": f"done-{i}", "run_id": f"done-{i}", "processed_at": now}
            for i in range(scheduler.MAX_USERS_PER_RUN)
        ]
        + [{"user_id": "foreign", "run_id": "waiting-run", "processed_at": now}]
    )
    assert set(await scheduler._collect_signal_user_ids(now - timedelta(hours=24))) == {
        "busy",
        "waiting",
    }


@pytest.mark.parametrize(
    "blocked", ["succeeded", "exhausted", "backoff", "leased", "running", "invalid_timestamp"]
)
async def test_recent_unavailable_sessions_cannot_hide_an_older_pending_session(
    scheduling_db, blocked
):
    db = scheduling_db
    now = utc_now()
    recent = now - timedelta(hours=1)
    await db.sessions.insert_many(
        [
            {
                "user_id": "owner",
                "session_id": f"recent-{i}",
                "is_active": True,
                "updated_at": recent,
            }
            for i in range(40)
        ]
        + [
            {
                "user_id": "owner",
                "session_id": "pending",
                "is_active": True,
                "updated_at": recent - timedelta(hours=1),
            }
        ]
    )
    if blocked == "running":
        await db.traces.insert_many(
            [
                {"user_id": "owner", "session_id": f"recent-{i}", "status": "running"}
                for i in range(40)
            ]
        )
    else:
        await db.memory_extraction_jobs.insert_many(
            [
                {
                    "user_id": "owner",
                    "session_id": f"recent-{i}",
                    "status": {
                        "backoff": "failed",
                        "leased": "claimed",
                        "invalid_timestamp": "succeeded",
                    }.get(blocked, blocked),
                    "attempts": 1,
                    "updated_at": None if blocked == "invalid_timestamp" else recent,
                    "next_retry_at": now + timedelta(hours=1) if blocked == "backoff" else None,
                    "lease_expires_at": now + timedelta(hours=1) if blocked == "leased" else None,
                }
                for i in range(40)
            ]
        )
    await extraction.ensure_extraction_job_indexes(db.memory_extraction_jobs)
    claimed = await extraction.claim_candidate_jobs(db, db.memory_extraction_jobs, "owner", limit=1)
    assert [session["session_id"] for session, _ in claimed] == ["pending"]


async def test_changed_or_retry_ready_sessions_remain_eligible(scheduling_db):
    db = scheduling_db
    now = utc_now()
    recent = now - timedelta(hours=1)
    statuses = ["succeeded", "succeeded_no_output", "exhausted", "failed", "claimed"]
    await db.sessions.insert_many(
        [
            {"user_id": "owner", "session_id": status, "is_active": True, "updated_at": recent}
            for status in statuses
        ]
    )
    await db.memory_extraction_jobs.insert_many(
        [
            {
                "user_id": "owner",
                "session_id": status,
                "status": status,
                "attempts": 1,
                "updated_at": recent - timedelta(hours=1),
                "next_retry_at": now - timedelta(minutes=1),
                "lease_expires_at": now - timedelta(minutes=1),
            }
            for status in statuses
        ]
    )
    await extraction.ensure_extraction_job_indexes(db.memory_extraction_jobs)
    claimed = await extraction.claim_candidate_jobs(db, db.memory_extraction_jobs, "owner", limit=5)
    assert {session["session_id"] for session, _ in claimed} == set(statuses)


async def test_direct_claim_cannot_reuse_another_owners_job(scheduling_db):
    db = scheduling_db
    now = utc_now()
    await db.memory_extraction_jobs.insert_one(
        {
            "user_id": "foreign",
            "session_id": "collision",
            "status": "failed",
            "attempts": 1,
            "lease_expires_at": now - timedelta(minutes=1),
        }
    )
    before = await db.memory_extraction_jobs.find_one({"session_id": "collision"})
    assert (
        await extraction.claim_session_job(
            db.memory_extraction_jobs, {"session_id": "collision", "updated_at": now}, "owner"
        )
        is None
    )
    assert await db.memory_extraction_jobs.find_one({"session_id": "collision"}) == before
