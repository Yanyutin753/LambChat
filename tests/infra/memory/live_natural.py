"""Passive evidence for isolated real-clock memory extraction acceptance."""

from __future__ import annotations

import json
import os
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone


def natural_settings(cases):
    natural = [
        case for case in cases if case.get("natural_idle") or case.get("natural_maintenance")
    ]
    if not natural:
        return {}
    case = natural[0]
    if (
        len(cases) != 1
        or not case.get("sources")
        or any(source.get("agent_id") != "quick" for source in case["sources"])
    ):
        raise ValueError("Natural acceptance requires one dedicated Quick-source case")
    kind = case.get("natural_maintenance")
    if kind is not None:
        if kind not in {"reflection", "compaction"} or case.get("natural_idle"):
            raise ValueError("Invalid natural maintenance mode")
        return {
            "MEMORY_EXTRACTION_ENABLED": False,
            "NATIVE_MEMORY_SELF_EVOLVE_ENABLED": kind == "reflection",
            "NATIVE_MEMORY_SELF_EVOLVE_INTERVAL_SECONDS": 60,
            "NATIVE_MEMORY_AUTO_COMPACT_ENABLED": kind == "compaction",
            "NATIVE_MEMORY_AUTO_COMPACT_INTERVAL_SECONDS": 60,
            "NATIVE_MEMORY_AUTO_COMPACT_THRESHOLD": 40,
            "NATIVE_MEMORY_AUTO_COMPACT_MIN_INTERVAL_SECONDS": 900,
        }
    return {
        "MEMORY_EXTRACTION_ENABLED": True,
        "MEMORY_EXTRACTION_IDLE_SECONDS": 60,
        "MEMORY_EXTRACTION_INTERVAL_SECONDS": 3,
    }


def observed_phase(messages, explicit, extraction_prompt):
    if explicit != "chat":
        return explicit
    from src.infra.memory.compaction_agent import _COMPACTION_SYSTEM_PROMPT
    from src.infra.memory.evolution.reflector import REFLECT_SYSTEM_PROMPT

    for batch in messages:
        if not batch or batch[0].type != "system":
            continue
        policy = batch[0].content
        if isinstance(policy, list):
            policy = "\n\n".join(
                block["text"]
                for block in policy
                if isinstance(block, dict)
                and block.get("type") == "text"
                and isinstance(block.get("text"), str)
                and block["text"]
            )
        if policy == extraction_prompt:
            return "background_extraction"
        if isinstance(policy, str) and policy.startswith(_COMPACTION_SYSTEM_PROMPT):
            return "background_compaction"
        if policy == REFLECT_SYSTEM_PROMPT:
            return "background_reflection"
    return explicit


def record_scheduler_fire(event, path, fingerprint):
    if (
        event.job_id not in {"memory.extraction", "memory.compaction", "memory.evolution"}
        or not event.scheduled_run_time
    ):
        return
    receipt = {
        "job_id": event.job_id,
        "source_sha256": fingerprint,
        "scheduled_at": event.scheduled_run_time.isoformat(),
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "result": event.retval,
        "exception": type(event.exception).__name__ if event.exception else None,
    }
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a") as handle:
        handle.write(json.dumps(receipt) + "\n")


def observe_lifespan(app, output, guard):
    from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED

    from src.infra.scheduler import get_runtime_scheduler

    original = app.router.lifespan_context

    @asynccontextmanager
    async def observed(app):
        async with original(app) as state:
            scheduler = get_runtime_scheduler()._scheduler
            assert scheduler is not None and scheduler.running

            def listener(event):
                record_scheduler_fire(event, output / "scheduler-fires.jsonl", guard.fingerprint)

            scheduler.add_listener(listener, EVENT_JOB_EXECUTED | EVENT_JOB_ERROR)
            try:
                yield state
            finally:
                scheduler.remove_listener(listener)

    app.router.lifespan_context = observed


def _rows(path):
    return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []


def wait_for_natural_extraction(env, owner, session_id, record):
    """Observe DB/jobs/receipts only; never invoke an extraction control endpoint."""
    from src.kernel.config import settings

    db = env["db"]
    user_id = env["users"][owner]["id"]
    session = db[settings.MONGODB_SESSIONS_COLLECTION].find_one(
        {"session_id": session_id, "user_id": user_id}
    )
    if session is None:
        from bson import ObjectId

        session = db[settings.MONGODB_SESSIONS_COLLECTION].find_one(
            {"_id": ObjectId(session_id), "user_id": user_id}
        )
    assert session is not None
    traces = list(db.traces.find({"session_id": session_id, "user_id": user_id}))
    assert traces and all(trace.get("agent_id") == "quick" for trace in traces)
    updated = session["updated_at"]
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    eligible_at = updated.timestamp() + 60
    initial = db.native_memories.count_documents({"user_id": user_id})
    assert initial == 0, "Source chat must not save memory through foreground tools"
    observed_early = False
    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        env["guard"].check()
        calls = [
            row
            for row in _rows(env["output"] / "model-calls.jsonl")
            if row["event"] == "start" and row.get("phase") == "background_extraction"
        ]
        if time.time() < eligible_at - 1:
            observed_early = True
            assert not calls
            assert db.native_memories.count_documents({"user_id": user_id}) == 0
        job = db.memory_extraction_jobs.find_one({"user_id": user_id, "session_id": session_id})
        if job and job.get("status") in {"succeeded", "succeeded_no_output", "failed"}:
            record(
                {
                    "kind": "natural_idle_extraction",
                    "job": job,
                    "early_idle_observed": observed_early,
                    "eligible_at": eligible_at,
                    "model_calls": calls,
                }
            )
            assert observed_early, "No pre-idle observation; cannot prove the idle boundary"
            assert job["status"] == "succeeded"
            assert len(calls) == 1 and calls[0]["time"] >= eligible_at
            assert job["extracted_updated_at"] == session["updated_at"]
            assert db.native_memories.count_documents({"user_id": user_id}) > 0
            break
        time.sleep(0.25)
    else:
        record({"kind": "natural_idle_timeout", "job": job})
        raise AssertionError("Natural scheduler did not complete extraction within 240 seconds")
    finished = time.time()
    deadline = time.monotonic() + 15
    fires = []
    while time.monotonic() < deadline:
        fires = [
            fire
            for fire in _rows(env["output"] / "scheduler-fires.jsonl")
            if datetime.fromisoformat(fire["scheduled_at"]).timestamp() > finished
        ]
        if len(fires) >= 2:
            break
        time.sleep(0.25)
    record({"kind": "natural_unchanged_ticks", "fires": fires})
    assert len(fires) >= 2 and all(fire["exception"] is None for fire in fires)
    assert (
        sum(
            row["event"] == "start" and row.get("phase") == "background_extraction"
            for row in _rows(env["output"] / "model-calls.jsonl")
        )
        == 1
    )
    assert db.memory_extraction_jobs.find_one({"user_id": user_id, "session_id": session_id}) == job


def wait_for_natural_maintenance(
    env, owner, record, *, kind, run_id=None, before_count=None, max_remaining=None
):
    """Read completed scheduler receipts and state; never dispatch a maintenance job."""
    assert kind in {"reflection", "compaction"}
    db = env["db"]
    user_id = env["users"][owner]["id"]
    job_id = "memory.evolution" if kind == "reflection" else "memory.compaction"
    phase = "background_" + kind
    query = {"user_id": user_id}
    if kind == "reflection":
        query.update(source="self_evolved", context="feedback_rule")
    else:
        query["source"] = {"$nin": ["manual", "self_evolved"]}

    def calls():
        return [
            row
            for row in _rows(env["output"] / "model-calls.jsonl")
            if row.get("event") == "start" and row.get("phase") == phase
        ]

    def fires():
        return [
            row
            for row in _rows(env["output"] / "scheduler-fires.jsonl")
            if row.get("job_id") == job_id
        ]

    deadline = time.monotonic() + 240
    while time.monotonic() < deadline:
        env["guard"].check()
        observed_fires = fires()
        count = db.native_memories.count_documents(query)
        feedback = (
            db.feedback.find_one({"user_id": user_id, "run_id": run_id})
            if kind == "reflection"
            else None
        )
        completed = (
            bool(feedback and feedback.get("evolution_processed") is True) and count == 1
            if kind == "reflection"
            else count < before_count and count <= max_remaining
        )
        result_key = "stored" if kind == "reflection" else "triggered"
        if completed and any(
            (fire.get("result") or {}).get(result_key) == 1 for fire in observed_fires
        ):
            observed_calls = calls()
            record(
                {
                    "kind": "natural_" + kind,
                    "fires": observed_fires,
                    "before_count": before_count,
                    "after_count": count,
                    "feedback": feedback,
                    "model_calls": observed_calls,
                }
            )
            assert observed_calls and all(fire["exception"] is None for fire in observed_fires)
            if kind == "reflection":
                assert len(observed_calls) == 1
            break
        time.sleep(0.25)
    else:
        record(
            {
                "kind": "natural_maintenance_timeout",
                "maintenance": kind,
                "fires": fires(),
                "model_calls": calls(),
                "remaining": db.native_memories.count_documents(query),
            }
        )
        raise AssertionError("Natural maintenance did not complete within 240 seconds")
    finished = time.time()
    deadline = time.monotonic() + 150
    while time.monotonic() < deadline:
        env["guard"].check()
        quiet = [
            fire
            for fire in fires()
            if datetime.fromisoformat(fire["scheduled_at"]).timestamp() > finished
        ]
        if len(quiet) >= 2:
            break
        time.sleep(0.25)
    record(
        {
            "kind": "natural_maintenance_unchanged_ticks",
            "maintenance": kind,
            "fires": quiet,
            "model_calls": len(calls()),
        }
    )
    assert len(quiet) >= 2 and all(fire["exception"] is None for fire in quiet)
    assert len(calls()) == len(observed_calls), "Unchanged periodic ticks repeated a model call"
    assert db.native_memories.count_documents(query) == count
