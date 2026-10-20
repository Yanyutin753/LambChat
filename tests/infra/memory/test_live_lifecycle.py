"""Opt-in real HTTP/LLM memory lifecycle evaluation in an owned database.

LAMBCHAT_MEMORY_LIVE=1 and LAMBCHAT_MEMORY_LIVE_OUTPUT=/absolute/private/path
enable paid tests. Optional LAMBCHAT_MEMORY_LIVE_CASES selects comma-separated
case IDs. Always run through scripts/run_validation.py. Output directories cannot
be reused. The isolated server and Redis stop at teardown; synthetic evidence is
retained, while copied provider configuration is removed from the test database.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import runpy
import secrets
import subprocess
import sys
import time
import unicodedata
from contextlib import ExitStack
from contextvars import ContextVar
from pathlib import Path
from uuid import uuid4

import httpx
import pytest
from fastapi import Request
from langchain_core.callbacks import AsyncCallbackHandler

ROOT = Path(__file__).resolve().parents[3]
CASES_PATH = ROOT / "tests/fixtures/memory_lifecycle/v1.json"
CAPACITY_CASES_PATH = ROOT / "tests/fixtures/memory_lifecycle/v2.json"
MAINTENANCE_CASES_PATH = ROOT / "tests/fixtures/memory_lifecycle/v3.json"
FORGET_CASES_PATH = ROOT / "tests/fixtures/memory_lifecycle/v4.json"
REFLECTION_CASES_PATH = ROOT / "tests/fixtures/memory_lifecycle/v5.json"
REFLECTION_HELDOUT_CASES_PATH = ROOT / "tests/fixtures/memory_lifecycle/v6.json"
LINEAGE_CASES_PATH = ROOT / "tests/fixtures/memory_lifecycle/v7.json"
LINEAGE_HELDOUT_CASES_PATH = ROOT / "tests/fixtures/memory_lifecycle/v8.json"
LINEAGE_BACKUP_CASES_PATH = ROOT / "tests/fixtures/memory_lifecycle/v9.json"
LINEAGE_TERMINAL_CASES_PATH = ROOT / "tests/fixtures/memory_lifecycle/v10.json"
NATURAL_CASES_PATH = ROOT / "tests/fixtures/memory_lifecycle/v11.json"
VECTOR_CASES_PATH = ROOT / "tests/fixtures/memory_lifecycle/v12.json"
NAMED_PROJECT_CASES_PATH = ROOT / "tests/fixtures/memory_lifecycle/v13.json"
NATURAL_MAINTENANCE_CASES_PATH = ROOT / "tests/fixtures/memory_lifecycle/v14.json"
NATURAL_MAINTENANCE_HELDOUT_CASES_PATH = ROOT / "tests/fixtures/memory_lifecycle/v15.json"
NATURAL_LITERAL_CASES_PATH = ROOT / "tests/fixtures/memory_lifecycle/v16.json"
FINAL_HELDOUT_CASES_PATH = ROOT / "tests/fixtures/memory_lifecycle/v17.json"
VECTOR_HELPERS_PATH = Path(__file__).with_name("live_vector_seed.py")
QDRANT_HELPERS_PATH = Path(__file__).with_name("live_qdrant.py")
NATURAL_HELPERS_PATH = Path(__file__).with_name("live_natural.py")
NATURAL_HELPERS = runpy.run_path(str(NATURAL_HELPERS_PATH))
CAPACITY_DATASET_PATH = ROOT / "scripts/benchmark_memory_six_months.py"
SUITE = {
    "version": 17,
    "cases": [
        *json.loads(CASES_PATH.read_text())["cases"],
        *json.loads(CAPACITY_CASES_PATH.read_text())["cases"],
        *json.loads(MAINTENANCE_CASES_PATH.read_text())["cases"],
        *json.loads(FORGET_CASES_PATH.read_text())["cases"],
        *json.loads(REFLECTION_CASES_PATH.read_text())["cases"],
        *json.loads(REFLECTION_HELDOUT_CASES_PATH.read_text())["cases"],
        *json.loads(LINEAGE_CASES_PATH.read_text())["cases"],
        *json.loads(LINEAGE_HELDOUT_CASES_PATH.read_text())["cases"],
        *json.loads(LINEAGE_BACKUP_CASES_PATH.read_text())["cases"],
        *json.loads(LINEAGE_TERMINAL_CASES_PATH.read_text())["cases"],
        *json.loads(NATURAL_CASES_PATH.read_text())["cases"],
        *json.loads(VECTOR_CASES_PATH.read_text())["cases"],
        *json.loads(NAMED_PROJECT_CASES_PATH.read_text())["cases"],
        *json.loads(NATURAL_MAINTENANCE_CASES_PATH.read_text())["cases"],
        *json.loads(NATURAL_MAINTENANCE_HELDOUT_CASES_PATH.read_text())["cases"],
        *json.loads(NATURAL_LITERAL_CASES_PATH.read_text())["cases"],
        *json.loads(FINAL_HELDOUT_CASES_PATH.read_text())["cases"],
    ],
}
EVALUATION_PHASE = ContextVar("memory_evaluation_phase", default="chat")


def source_fingerprint() -> str:
    digest = hashlib.sha256()
    for path in [
        *sorted((ROOT / "src").rglob("*.py")),
        *sorted((ROOT / "src/infra/memory/templates").rglob("*.md")),
        CASES_PATH,
        CAPACITY_CASES_PATH,
        MAINTENANCE_CASES_PATH,
        FORGET_CASES_PATH,
        REFLECTION_CASES_PATH,
        REFLECTION_HELDOUT_CASES_PATH,
        LINEAGE_CASES_PATH,
        LINEAGE_HELDOUT_CASES_PATH,
        LINEAGE_BACKUP_CASES_PATH,
        LINEAGE_TERMINAL_CASES_PATH,
        NATURAL_CASES_PATH,
        VECTOR_CASES_PATH,
        NAMED_PROJECT_CASES_PATH,
        NATURAL_MAINTENANCE_CASES_PATH,
        NATURAL_MAINTENANCE_HELDOUT_CASES_PATH,
        NATURAL_LITERAL_CASES_PATH,
        FINAL_HELDOUT_CASES_PATH,
        VECTOR_HELPERS_PATH,
        QDRANT_HELPERS_PATH,
        NATURAL_HELPERS_PATH,
        CAPACITY_DATASET_PATH,
        Path(__file__).with_name("test_live_embedding.py"),
        Path(__file__),
    ]:
        digest.update(str(path.relative_to(ROOT)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


@pytest.mark.parametrize(
    "relative",
    [
        "src/infra/memory/templates/memories/stage_one_system.md",
        "tests/fixtures/memory_lifecycle/v14.json",
        "tests/fixtures/memory_lifecycle/v15.json",
        "tests/fixtures/memory_lifecycle/v16.json",
        "tests/fixtures/memory_lifecycle/v17.json",
    ],
)
def test_source_fingerprint_covers_extraction_prompt_and_maintenance_fixture(monkeypatch, relative):
    template = ROOT / relative
    original_read = Path.read_bytes
    before = source_fingerprint()

    def changed_prompt(path):
        data = original_read(path)
        return data + b"\nchanged prompt" if path == template else data

    monkeypatch.setattr(Path, "read_bytes", changed_prompt)
    assert source_fingerprint() != before


def test_capacity_seed_ages_only_owned_facts_and_keeps_gold_out_of_noise():
    from datetime import datetime, timedelta, timezone

    now = datetime(2026, 10, 20, tzinfo=timezone.utc)

    class Collection:
        def __init__(self):
            self.docs = [
                {"user_id": "owner", "memory_id": "fact", "updated_at": now},
                {"user_id": "other", "memory_id": "untouched", "updated_at": now},
            ]

        def update_many(self, query, update):
            for doc in self.docs:
                if doc["user_id"] == query["user_id"]:
                    doc.update(update["$set"])

        def count_documents(self, query):
            return sum(doc["user_id"] == query["user_id"] for doc in self.docs)

        def insert_many(self, docs):
            self.docs.extend(docs)

    collection = Collection()
    result = seed_capacity_corpus(
        collection,
        {"a": {"id": "owner"}},
        {"a": ["alpha"]},
        {"a": 8},
        now=now,
    )

    assert collection.docs[0]["updated_at"] == now - timedelta(days=180)
    assert collection.docs[1]["updated_at"] == now
    assert result["a"]["memory_count"] == 8
    noise = [doc for doc in collection.docs if doc.get("capacity_noise") is True]
    assert len(noise) == 7
    assert all(doc["user_id"] == "owner" and doc["embedding"] is None for doc in noise)
    assert all(
        len(doc["content"]) <= 1200 and doc.get("project_id") in (None, "alpha") for doc in noise
    )
    assert len({doc["memory_id"] for doc in collection.docs}) == 9


def test_maintenance_seed_preserves_protected_content_and_source():
    calls = []
    bodies = {}

    def api(owner, method, path, body=None):
        calls.append((owner, method, path, body))
        if method == "POST":
            memory_id = str(len(bodies))
            bodies[memory_id] = {**body, "source": "manual"}
            return {"memory_id": memory_id}
        memory_id = path.rsplit("/", 1)[1]
        if method == "PUT":
            bodies[memory_id].update(body)
            return {"success": True}
        return bodies[memory_id].copy()

    seeded = seed_maintenance_memories(
        api,
        [
            {"owner": "a", "source": "auto_retained", "content": "Automatic durable rule."},
            {
                "owner": "a",
                "source": "manual",
                "content": "Pinned durable rule.",
                "protected": True,
            },
        ],
    )
    assert seeded[1]["before"]["content"] == "Pinned durable rule."
    assert seeded[1]["before"]["source"] == "manual"
    assert [call[3] for call in calls if call[1] == "PUT"] == [{"source": "auto_retained"}]
    assert all(
        "protected" not in body and "owner" not in body
        for _, method, _, body in calls
        if method == "POST"
    )


def seed_maintenance_memories(api, seeds):
    records = []
    for seed in seeds:
        owner = seed["owner"]
        payload = {
            key: value for key, value in seed.items() if key not in {"owner", "source", "protected"}
        }
        if "origin_session_ids" in payload:
            memory_id = uuid4().hex
            restored = api(
                owner,
                "POST",
                "/api/memory/import",
                {"memories": [{**payload, "memory_id": memory_id, "source": seed["source"]}]},
            )
            assert restored["success"] and restored["imported"] == 1
        else:
            memory_id = api(owner, "POST", "/api/memory/", payload)["memory_id"]
            if seed["source"] != "manual":
                api(owner, "PUT", f"/api/memory/{memory_id}", {"source": seed["source"]})
        records.append(
            {
                "owner": owner,
                "memory_id": memory_id,
                "before": api(owner, "GET", f"/api/memory/{memory_id}")
                if seed.get("protected")
                else None,
            }
        )
    return records


def archive_controlled_fixture(api, db, owner, user_id, journal, evidence):
    from src.infra.memory.client.native.content import memory_store_namespace
    from src.infra.storage.mongodb_store import COLLECTION_NAME

    if not db.name.startswith("memory_eval_"):
        raise ValueError("Controlled fixture staging requires an isolated evaluation database")
    original = list(db.native_memories.find({"user_id": user_id}))
    backup = api(owner, "GET", "/api/memory/export")
    exported = backup["memories"]
    if (
        len(exported) != len(original)
        or {row["memory_id"] for row in exported} != {row["memory_id"] for row in original}
        or any(row.get("content_truncated") is True for row in exported)
    ):
        raise ValueError("Original fixture archive is incomplete")
    namespace = list(memory_store_namespace(user_id))
    keys = {
        row.get("content_store_key")
        for row in original
        if row.get("content_storage_mode") == "store"
    }
    if any(not isinstance(key, str) or not key for key in keys):
        raise ValueError("Original fixture body reference is unavailable")
    bodies = list(db[COLLECTION_NAME].find({"namespace": namespace, "key": {"$in": list(keys)}}))
    if len(bodies) != len(keys) or {row["key"] for row in bodies} != keys:
        raise ValueError("Original fixture body archive is incomplete")
    evidence["controlled_legacy_reseed"] = {
        "archived_original_rows": original,
        "archived_full_export": backup,
        "archived_store_rows": bodies,
        "purpose": "Controlled restored duplicates; not a naturally produced duplicate count",
    }
    save_json(journal, evidence)
    if original:
        deleted = db.native_memories.delete_many(
            {
                "user_id": user_id,
                "$or": [
                    {"memory_id": row["memory_id"], "revision_id": row.get("revision_id")}
                    for row in original
                ],
            }
        )
        if deleted.deleted_count != len(original):
            raise ValueError("Original fixture changed during controlled staging")
    if bodies:
        db[COLLECTION_NAME].delete_many(
            {"namespace": namespace, "_id": {"$in": [row["_id"] for row in bodies]}}
        )


def seed_capacity_corpus(collection, users, projects, targets, *, now):
    from datetime import timedelta

    from scripts.benchmark_memory_six_months import memory

    result = {}
    for owner, target in targets.items():
        user_id = users[owner]["id"]
        collection.update_many(
            {"user_id": user_id},
            {
                "$set": {
                    "created_at": now - timedelta(days=180),
                    "updated_at": now - timedelta(days=180),
                }
            },
        )
        count = collection.count_documents({"user_id": user_id})
        noise_id = None
        while count < target:
            docs = []
            for index in range(count, min(count + 250, target)):
                doc = memory(index, now, 8, owner=user_id)
                # No fabricated vector may participate in real-provider semantic grading.
                doc.update(embedding=None, capacity_noise=True)
                doc["content"] = doc["content"][:1200]
                if doc.get("scope") == "project":
                    pids = projects.get(owner) or []
                    doc["project_id"] = pids[index % len(pids)] if pids else None
                    if not pids:
                        doc.update(scope="user", memory_type="user", context="user_preference")
                docs.append(doc)
            collection.insert_many(docs)
            noise_id = noise_id or docs[0]["memory_id"]
            count += len(docs)
        result[owner] = {
            "memory_count": count,
            "noise_id": noise_id,
            "simulated_age_days": 180,
            "noise_embeddings": None,
        }
    return result


def evaluation_username(case_id: str, owner: str) -> str:
    identity = json.dumps([case_id, owner], ensure_ascii=False).encode()
    return f"memory_eval_{hashlib.sha256(identity).hexdigest()[:24]}"


def validate_controlled_lineage_fixture(case: dict) -> None:
    from src.infra.memory.compaction_agent import COMPACTION_MIN_MEMORIES

    if case.get("lineage_sources") and len(case.get("seed_memories", [])) < COMPACTION_MIN_MEMORIES:
        raise ValueError(
            f"Controlled lineage fixture needs the policy minimum {COMPACTION_MIN_MEMORIES} records"
        )


def stable_after_reduction(
    result: dict, *, remaining: int, previous_deleted: int, new_model_events: int
) -> bool:
    from src.infra.memory.compaction_agent import COMPACTION_MIN_MEMORIES

    checked = result.get("checked")
    if any(
        isinstance(value, bool) or not isinstance(value, int)
        for value in (remaining, checked, previous_deleted, new_model_events)
    ):
        return False
    return (
        result.get("skipped") is True
        and result.get("reason") == "below_minimum"
        and not result.get("failed")
        and 0 <= remaining < COMPACTION_MIN_MEMORIES
        and checked == remaining
        and previous_deleted > 0
        and new_model_events == 0
    )


def save_json(path: Path, value) -> None:
    with path.open("w") as handle:
        os.chmod(path, 0o600)
        json.dump(value, handle, ensure_ascii=False, indent=2, default=str)


@pytest.mark.parametrize("answer", ['```json\n{"price":26}\n```', '{"price":26} note'])
def test_strict_json_rejects_wrapping_and_prose(answer):
    with pytest.raises(ValueError):
        answer_fields(answer, strict=True)


def test_strict_json_requires_exact_keys_and_literal_strings_without_regrading_old_cases():
    assert answer_fields('```json\n{"price":26}\n```') == {"price": 26}
    assert answer_matches({"name": "NORTH", "extra": 1}, {"name": "north"})
    assert not answer_matches({"name": "north", "extra": 1}, {"name": "north"}, strict=True)
    assert not answer_matches({"name": "NORTH"}, {"name": "north"}, strict=True)
    assert answer_matches(
        {"name": "north", "price": 26}, {"name": "north", "price": 26}, strict=True
    )


def answer_fields(answer: str, *, strict: bool = False) -> dict:
    text = answer.strip()
    if not strict and text.startswith("```json") and text.endswith("```"):
        text = text[7:-3].strip()
    elif not strict and text.startswith("```") and text.endswith("```"):
        text = text[3:-3].strip()
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise ValueError("answer must be a JSON object")
    return parsed


def raw_final_answer(events: list[dict]) -> str:
    parts: dict[str, str] = {}
    for event in events:
        data = event.get("data") or {}
        if event.get("event_type") == "message:chunk" and int(data.get("depth") or 0) == 0:
            content = data.get("content")
            if isinstance(content, str) and content:
                text_id = str(data.get("text_id") or "final")
                parts[text_id] = parts.get(text_id, "") + content
    return next(reversed(parts.values()), "")


def exact_text_matches(answer: str, expected: str) -> bool:
    return answer.replace("\r\n", "\n").strip() == expected.strip()


def answer_matches(actual: dict, expected: dict, *, strict: bool = False) -> bool:
    if strict and actual.keys() != expected.keys():
        return False

    def equivalent(left, right):
        if isinstance(right, str):
            if strict:
                return isinstance(left, str) and left == right
            return isinstance(left, str) and (
                unicodedata.normalize("NFKC", left).strip().casefold()
                == unicodedata.normalize("NFKC", right).strip().casefold()
            )
        if isinstance(right, bool) or right is None:
            return left is right
        return type(left) in (int, float) and left == right

    return all(key in actual and equivalent(actual[key], value) for key, value in expected.items())


def cancel_owned_run(client, session_id: str, run_id: str) -> dict:
    response = client.post(f"/api/chat/sessions/{session_id}/cancel", timeout=10)
    result = {"http_status": response.status_code, "terminal_status": None}
    if not response.is_success:
        return result
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        observed = client.get(
            f"/api/chat/sessions/{session_id}/status", params={"run_id": run_id}, timeout=5
        )
        observed.raise_for_status()
        status = observed.json()["status"]
        if status not in {"pending", "queued", "starting", "running", "recovering"}:
            result["terminal_status"] = status
            break
        time.sleep(0.5)
    return result


class FrozenSource(AsyncCallbackHandler):
    raise_error = True

    def __init__(self, output: Path):
        from src.infra.memory.extraction import load_stage_one_system_prompt

        self.output = output
        self.extraction_prompt = load_stage_one_system_prompt()
        self.fingerprint = json.loads((output / "started.json").read_text())["source_sha256"]

    def check(self):
        if source_fingerprint() != self.fingerprint:
            raise RuntimeError("Memory evaluation source changed; stop new provider requests")

    def record(self, event):
        with (self.output / "model-calls.jsonl").open("a") as handle:
            os.chmod(self.output / "model-calls.jsonl", 0o600)
            handle.write(json.dumps(event, ensure_ascii=False, default=str) + "\n")

    async def on_chat_model_start(self, serialized, messages, *, run_id, **kwargs):
        self.check()
        self.record(
            {
                "event": "start",
                "run_id": str(run_id),
                "time": time.time(),
                "phase": NATURAL_HELPERS["observed_phase"](
                    messages, EVALUATION_PHASE.get(), self.extraction_prompt
                ),
                "messages": [
                    [{"type": message.type, "content": message.content} for message in batch]
                    for batch in messages
                ],
            }
        )

    async def on_llm_end(self, response, *, run_id, **kwargs):
        messages = [
            generation.message
            for batch in response.generations
            for generation in batch
            if hasattr(generation, "message")
        ]
        self.record(
            {
                "event": "end",
                "run_id": str(run_id),
                "time": time.time(),
                "responses": [
                    {
                        "content": message.content,
                        "tool_calls": getattr(message, "tool_calls", []),
                        "usage": getattr(message, "usage_metadata", None),
                        "stop_reason": message.response_metadata.get("stop_reason"),
                    }
                    for message in messages
                ],
            }
        )

    async def on_llm_error(self, error, *, run_id, **kwargs):
        self.record(
            {
                "event": "error",
                "run_id": str(run_id),
                "error_type": type(error).__name__,
                "time": time.time(),
            }
        )


def serve(output: str, port: int):
    """Only the opt-in evaluator launches this private loopback test server."""
    import uvicorn
    from fastapi.responses import JSONResponse

    from src.infra.llm.client import LLMClient

    guard = FrozenSource(Path(output))
    original = LLMClient.get_model

    async def model_with_receipt(*args, **kwargs):
        guard.check()
        model = await original(*args, **kwargs)
        callbacks = model.callbacks or []
        if guard not in callbacks:
            model.callbacks = [*callbacks, guard]
        return model

    LLMClient.get_model = staticmethod(model_with_receipt)
    original_send = httpx.AsyncClient.send

    async def guarded_send(client, *args, **kwargs):
        guard.check()
        return await original_send(client, *args, **kwargs)

    httpx.AsyncClient.send = guarded_send

    from src.api.main import app
    from src.kernel.config import settings

    assert settings.MONGODB_DB.startswith("memory_eval_")
    if os.environ.get("MEMORY_EVAL_NATURAL") == "1":
        NATURAL_HELPERS["observe_lifespan"](app, Path(output), guard)

    @app.post("/__memory_eval__/extract")
    async def extract(request: Request):
        if not secrets.compare_digest(
            request.headers.get("x-memory-eval-token", ""), os.environ["MEMORY_EVAL_TOKEN"]
        ):
            return JSONResponse({"error": "unauthorized"}, status_code=403)
        from src.infra.memory.extraction import extract_session_memory
        from src.infra.memory.tools import _get_backend
        from src.infra.storage.mongodb import get_mongo_client

        body = await request.json()
        db = get_mongo_client()[settings.MONGODB_DB]
        session = await db[settings.MONGODB_SESSIONS_COLLECTION].find_one(
            {"session_id": body["session_id"], "user_id": body["user_id"]}
        )
        if session is None:
            from bson import ObjectId

            if ObjectId.is_valid(body["session_id"]):
                session = await db[settings.MONGODB_SESSIONS_COLLECTION].find_one(
                    {"_id": ObjectId(body["session_id"]), "user_id": body["user_id"]}
                )
        if session is None:
            return JSONResponse({"error": "session_not_found"}, status_code=404)
        session["session_id"] = body["session_id"]
        phase = EVALUATION_PHASE.set("extraction")
        try:
            result = await extract_session_memory(
                await _get_backend(), db, body["user_id"], session
            )
        finally:
            EVALUATION_PHASE.reset(phase)
        return {"status": result.status, "memory_id": result.memory_id, "error": result.error}

    @app.post("/__memory_eval__/compact")
    async def compact(request: Request):
        if not secrets.compare_digest(
            request.headers.get("x-memory-eval-token", ""), os.environ["MEMORY_EVAL_TOKEN"]
        ):
            return JSONResponse({"error": "unauthorized"}, status_code=403)
        from src.infra.memory.compaction_agent import MemoryCompactionAgent
        from src.infra.memory.tools import _get_backend

        body = await request.json()
        phase = EVALUATION_PHASE.set("compaction")
        try:
            return await MemoryCompactionAgent().compact_user_memories(
                await _get_backend(), body["user_id"]
            )
        finally:
            EVALUATION_PHASE.reset(phase)

    @app.post("/__memory_eval__/reflect")
    async def reflect(request: Request):
        if not secrets.compare_digest(
            request.headers.get("x-memory-eval-token", ""), os.environ["MEMORY_EVAL_TOKEN"]
        ):
            return JSONResponse({"error": "unauthorized"}, status_code=403)
        from src.infra.memory.evolution.reflector import SignalRun, evolve_user, reflect_on_run
        from src.infra.memory.tools import _get_backend

        body = await request.json()
        phase = EVALUATION_PHASE.set("reflection")
        try:
            backend = await _get_backend()
            if body.get("run_id"):
                return await reflect_on_run(
                    backend,
                    body["user_id"],
                    SignalRun(
                        run_id=body["run_id"],
                        session_id=body["session_id"],
                        kind="down",
                        comment=body["comment"],
                    ),
                )
            return await evolve_user(backend, body["user_id"])
        finally:
            EVALUATION_PHASE.reset(phase)

    @app.post("/__memory_eval__/final-text")
    async def final_text(request: Request):
        if not secrets.compare_digest(
            request.headers.get("x-memory-eval-token", ""), os.environ["MEMORY_EVAL_TOKEN"]
        ):
            return JSONResponse({"error": "unauthorized"}, status_code=403)
        from src.infra.session.trace_storage import get_trace_storage

        body = await request.json()
        storage = get_trace_storage()
        trace = await storage.collection.find_one(
            {"run_id": body["run_id"], "user_id": body["user_id"], "session_id": body["session_id"]}
        )
        if trace is None:
            return JSONResponse({"error": "trace_not_found"}, status_code=404)
        events = await storage.read_trace_events_compat(
            trace["trace_id"], event_types=["message:chunk"]
        )
        return {"text": raw_final_answer(events)}

    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


@pytest.fixture(scope="module")
def live_environment():
    if os.environ.get("LAMBCHAT_MEMORY_LIVE") != "1":
        pytest.skip("Opt-in paid lifecycle evaluation")
    from pymongo import MongoClient

    from scripts.e2e_conversation_schedules import free_port, stop
    from src.infra.auth.password import hash_password
    from src.infra.storage.mongodb import build_mongo_connection_string
    from src.kernel.config import settings

    selected = os.environ.get("LAMBCHAT_MEMORY_LIVE_CASES", "")
    if selected and set(selected.split(",")) - {case["case_id"] for case in SUITE["cases"]}:
        raise ValueError("Unknown live evaluation case ID")
    natural = NATURAL_HELPERS["natural_settings"](
        [case for case in SUITE["cases"] if not selected or case["case_id"] in selected.split(",")]
    )
    for case in SUITE["cases"]:
        if not selected or case["case_id"] in selected.split(","):
            validate_controlled_lineage_fixture(case)

    embedding_profile = {}
    if profile_path := os.environ.get("LAMBCHAT_MEMORY_LIVE_EMBEDDING_PROFILE"):
        import runpy

        read_profile = runpy.run_path(str(Path(__file__).with_name("test_live_embedding.py")))[
            "read_embedding_profile"
        ]
        embedding_profile = read_profile(Path(profile_path))

    vector_seed = None
    qdrant_binary = None
    if any(
        case.get("vector_seed")
        for case in SUITE["cases"]
        if not selected or case["case_id"] in selected.split(",")
    ):
        from tests.infra.memory.live_qdrant import capacity_qdrant_binary
        from tests.infra.memory.live_vector_seed import read_vector_seed

        vector_seed = read_vector_seed(
            os.environ.get("LAMBCHAT_MEMORY_LIVE_VECTOR_SEED_REPORT", ""), embedding_profile
        )
        qdrant_binary = capacity_qdrant_binary(50000)

    output = Path(os.environ["LAMBCHAT_MEMORY_LIVE_OUTPUT"]).expanduser().resolve()
    if ROOT == output or ROOT in output.parents:
        raise ValueError("Raw live evidence must stay outside the repository")
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    marker = output / "started.json"
    with marker.open("x") as handle:
        json.dump(
            {
                "source_sha256": source_fingerprint(),
                "suite_version": SUITE["version"],
                "created_at": time.time(),
                "vector_seed": vector_seed,
                "qdrant_binary_sha256": hashlib.sha256(qdrant_binary.read_bytes()).hexdigest()
                if qdrant_binary
                else None,
            },
            handle,
        )
    os.chmod(marker, 0o600)
    guard = FrozenSource(output)
    mongo = MongoClient(
        build_mongo_connection_string(), serverSelectionTimeoutMS=5000, timeoutMS=10000
    )
    database_name = f"memory_eval_{uuid4().hex}"
    db = mongo[database_name]
    source = mongo[settings.MONGODB_DB]
    save_json(output / "environment.json", {"database": database_name, "state": "preparing"})
    backend = redis = None
    clients = {}
    qdrant_stack = ExitStack()
    try:
        qdrant_url, qdrant_key = ":memory:", ""
        if qdrant_binary:
            from tests.infra.memory.live_qdrant import isolated_qdrant

            runner = qdrant_stack.enter_context(asyncio.Runner())
            manager = isolated_qdrant(qdrant_binary, output)
            qdrant_url, qdrant_key = runner.run(manager.__aenter__())
            qdrant_stack.callback(lambda: runner.run(manager.__aexit__(None, None, None)))
        for name in ("model_configs", "system_settings", "roles", "role_models"):
            documents = list(source[name].find())
            if documents:
                db[name].insert_many(documents)
        for key, value in {
            "ENABLE_MEMORY": True,
            "MEMORY_EXTRACTION_ENABLED": False,
            "NATIVE_MEMORY_AUTO_COMPACT_ENABLED": False,
            "NATIVE_MEMORY_SELF_EVOLVE_ENABLED": False,
            "NATIVE_MEMORY_QUERY_CONTEXT_ENABLED": False,
            "ENABLE_RECOMMEND_QUESTIONS": False,
            "ENABLE_SKILLS": False,
            "ENABLE_SCHEDULED_TASK": False,
            "LANGSMITH_TRACING": False,
            "LANGFUSE_ENABLED": False,
            "FEISHU_ENABLED": False,
            "TASK_BACKEND": "local",
            "LOG_FORMAT": "%(levelname)s %(message)s",
            **natural,
        }.items():
            db.system_settings.update_one({"_id": key}, {"$set": {"value": value}}, upsert=True)
        if embedding_profile:
            for key, value in {
                **embedding_profile,
                "NATIVE_MEMORY_VECTOR_BACKEND": "qdrant",
                "NATIVE_MEMORY_QDRANT_URL": qdrant_url,
                "NATIVE_MEMORY_QDRANT_API_KEY": qdrant_key,
            }.items():
                db.system_settings.update_one({"_id": key}, {"$set": {"value": value}}, upsert=True)
        case_users = {}
        for case in SUITE["cases"]:
            if selected and case["case_id"] not in selected.split(","):
                continue
            users = {}
            owners = sorted({item["owner"] for item in [*case["sources"], *case["queries"]]})
            for owner in owners:
                username = (
                    "desktop_dev"
                    if not case_users and owner == "a"
                    else evaluation_username(case["case_id"], owner)
                )
                password = secrets.token_urlsafe(24)
                roles = ["admin"] if username == "desktop_dev" else ["user"]
                user_id = db.users.insert_one(
                    {
                        "username": username,
                        "email": f"{username}@example.com",
                        "password_hash": hash_password(password),
                        "roles": roles,
                        "is_active": True,
                        "email_verified": True,
                    }
                ).inserted_id
                users[owner] = {
                    "id": str(user_id),
                    "username": username,
                    "password": password,
                    "roles": roles,
                }
            case_users[case["case_id"]] = users
        redis_port, port = free_port(), free_port()
        redis_binary = Path.home() / ".local/opt/redis/bin/redis-server"
        import shutil

        redis_path = shutil.which("redis-server") or str(redis_binary)
        token = secrets.token_urlsafe(32)
        with (output / "server.log").open("w") as server_log:
            redis = subprocess.Popen(
                [
                    redis_path,
                    "--bind",
                    "127.0.0.1",
                    "--port",
                    str(redis_port),
                    "--save",
                    "",
                    "--appendonly",
                    "no",
                ],
                stdout=server_log,
                stderr=subprocess.STDOUT,
            )
            bootstrap = (
                "import runpy,sys; "
                "runpy.run_path(sys.argv[1])['serve'](sys.argv[2], int(sys.argv[3]))"
            )
            backend = subprocess.Popen(
                [
                    sys.executable,
                    "-c",
                    bootstrap,
                    str(Path(__file__).resolve()),
                    str(output),
                    str(port),
                ],
                cwd=ROOT,
                stdout=server_log,
                stderr=subprocess.STDOUT,
                env={
                    **os.environ,
                    "MONGODB_DB": database_name,
                    "REDIS_URL": f"redis://127.0.0.1:{redis_port}/0",
                    "REDIS_PASSWORD": "",
                    "CHECKPOINT_BACKEND": "mongodb",
                    "ARQ_EMBEDDED_WORKER": "false",
                    "LOG_FORMAT": "%(levelname)s %(message)s",
                    "MEMORY_EVAL_TOKEN": token,
                    "MEMORY_EVAL_NATURAL": "1" if natural else "0",
                },
            )
            base_url = f"http://127.0.0.1:{port}"
            deadline = time.monotonic() + 60
            while time.monotonic() < deadline:
                assert backend.poll() is None, "Isolated server exited; inspect private server.log"
                try:
                    if httpx.get(base_url + "/health", timeout=1).status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                time.sleep(0.5)
            else:
                raise AssertionError("Isolated server startup timeout")
            for case_id, users in case_users.items():
                for owner, user in users.items():
                    client = httpx.Client(base_url=base_url, timeout=240)
                    response = client.post(
                        "/api/auth/login",
                        json={"username": user["username"], "password": user["password"]},
                        timeout=15,
                    )
                    assert response.status_code == 200, f"Login failed: HTTP {response.status_code}"
                    client.headers["Authorization"] = f"Bearer {response.json()['access_token']}"
                    clients[(case_id, owner)] = client
                    user.pop("password")
            save_json(
                output / "environment.json",
                {
                    "database": database_name,
                    "users": case_users,
                    "source_sha256": guard.fingerprint,
                    "models": list(
                        db.model_configs.find(
                            {"enabled": True},
                            {
                                "_id": 0,
                                "id": 1,
                                "value": 1,
                                "provider": 1,
                            },
                        )
                    ),
                    "embedding": {
                        "profile_provided": bool(embedding_profile),
                        "model": embedding_profile.get("NATIVE_MEMORY_EMBEDDING_MODEL"),
                        "dimensions": embedding_profile.get("NATIVE_MEMORY_EMBEDDING_DIMENSIONS"),
                        "index": "isolated real Qdrant server"
                        if qdrant_binary
                        else "isolated in-memory Qdrant"
                        if embedding_profile
                        else "local configured backend",
                    },
                    "background_maintenance": natural or "disabled; explicit Phase 1",
                    "hard_run_timeout_seconds": int(
                        os.environ.get("LAMBCHAT_MEMORY_LIVE_RUN_TIMEOUT", "600")
                    ),
                },
            )
            yield {
                "clients": clients,
                "db": db,
                "output": output,
                "guard": guard,
                "users": case_users,
                "control_token": token,
                "vector_seed": vector_seed,
                "qdrant": (qdrant_url, qdrant_key),
            }
    finally:
        try:
            for client in clients.values():
                client.close()
            stop(backend)
            stop(redis)
            for name in ("model_configs", "system_settings", "pats"):
                db[name].drop()
            mongo.close()
        finally:
            qdrant_stack.close()


def test_lifecycle_grading_preserves_null_boolean_and_numeric_distinctions():
    assert answer_matches({"price": 120}, {"price": 120})
    assert not answer_matches({"price": True}, {"price": 1})
    assert not answer_matches({}, {"unknown": None})
    assert not answer_matches({"permission": 1}, {"permission": True})
    assert answer_matches({"name": " Osaka "}, {"name": "Osaka"})
    assert answer_fields('```json\n{"value": null}\n```') == {"value": None}
    with pytest.raises(ValueError):
        answer_fields('["not an answer object"]')


def test_timeout_cleanup_cancels_and_observes_only_the_owned_run():
    from types import SimpleNamespace

    calls = []

    class Client:
        def post(self, path, **kwargs):
            calls.append(("cancel", path))
            return SimpleNamespace(status_code=200, is_success=True)

        def get(self, path, **kwargs):
            calls.append(("status", path, kwargs["params"]["run_id"]))
            return SimpleNamespace(
                raise_for_status=lambda: None, json=lambda: {"status": "cancelled"}
            )

    assert (
        cancel_owned_run(Client(), "owned-session", "owned-run")["terminal_status"] == "cancelled"
    )
    assert calls == [
        ("cancel", "/api/chat/sessions/owned-session/cancel"),
        ("status", "/api/chat/sessions/owned-session/status", "owned-run"),
    ]


@pytest.mark.parametrize(
    "answer",
    [
        '```json {"price": 120} ```',
        '``` {"price": 120} ```',
        '```json\n{"price": 120}\n```',
    ],
)
def test_grading_accepts_code_fences_after_history_whitespace_projection(answer):
    assert answer_fields(answer) == {"price": 120}


@pytest.mark.parametrize("case", SUITE["cases"], ids=lambda case: case["case_id"])
def test_real_memory_lifecycle(case, live_environment):
    selected = os.environ.get("LAMBCHAT_MEMORY_LIVE_CASES", "")
    if selected and case["case_id"] not in selected.split(","):
        pytest.skip("Not selected in this frozen cohort")
    case_id = case["case_id"]
    env = {
        **live_environment,
        "clients": {
            owner: client
            for (cid, owner), client in live_environment["clients"].items()
            if cid == case_id
        },
        "users": live_environment["users"][case_id],
    }
    journal = env["output"] / f"{case_id}.json"
    assert not journal.exists(), "An already started case cannot be replayed"
    evidence = {
        "case_id": case_id,
        "source_sha256": env["guard"].fingerprint,
        "stages": [],
        "outcome": "started",
    }
    save_json(journal, evidence)
    projects, sessions = {}, {}

    def api(owner, method, path, body=None):
        env["guard"].check()
        response = env["clients"][owner].request(method, path, json=body)
        assert response.is_success, f"{method} {path}: HTTP {response.status_code}"
        return response.json()

    def phase_calls(phase):
        path = env["output"] / "model-calls.jsonl"
        return (
            sum(
                row.get("event") == "start" and row.get("phase") == phase
                for row in (json.loads(line) for line in path.read_text().splitlines())
            )
            if path.exists()
            else 0
        )

    def reflect(body):
        response = env["clients"]["a"].post(
            "/__memory_eval__/reflect",
            headers={"x-memory-eval-token": env["control_token"]},
            json=body,
        )
        assert response.is_success, f"Reflection: HTTP {response.status_code}"
        return response.json()

    def extract(owner, session_id):
        response = env["clients"][owner].post(
            "/__memory_eval__/extract",
            headers={"x-memory-eval-token": env["control_token"]},
            json={"user_id": env["users"][owner]["id"], "session_id": session_id},
        )
        assert response.is_success, f"Extraction: HTTP {response.status_code}"
        return response.json()

    def session(item):
        key = (item["owner"], item["session"])
        if key not in sessions:
            project_key = (item["owner"], item["project"])
            if item["project"] and project_key not in projects:
                projects[project_key] = api(
                    item["owner"],
                    "POST",
                    "/api/projects",
                    {
                        "name": case.get("project_names", {}).get(
                            item["project"], f"memory-eval:{case_id}:{item['project']}"
                        )
                    },
                )["id"]
            metadata = {"project_id": projects[project_key]} if item["project"] else {}
            sessions[key] = api(
                item["owner"],
                "POST",
                "/api/sessions",
                {
                    "name": f"记忆验收:{case_id}:{item['session']}",
                    "metadata": metadata,
                },
            )["id"]
        return sessions[key]

    def chat(item, message):
        session_id = session(item)
        started_at = time.monotonic()
        submitted = api(
            item["owner"],
            "POST",
            f"/api/chat/stream?agent_id={item.get('agent_id', 'fast')}",
            {
                "session_id": session_id,
                "message": message,
            },
        )
        run_id = submitted["run_id"]
        evidence["stages"].append(
            {
                "kind": "chat",
                "session_id": session_id,
                "run_id": run_id,
                "input": message,
                "status": "started",
            }
        )
        save_json(journal, evidence)
        deadline = time.monotonic() + int(os.environ.get("LAMBCHAT_MEMORY_LIVE_RUN_TIMEOUT", "600"))
        while time.monotonic() < deadline:
            status = api(
                item["owner"], "GET", f"/api/chat/sessions/{session_id}/status?run_id={run_id}"
            )
            if status["status"] not in {"pending", "queued", "starting", "running", "recovering"}:
                evidence["stages"][-1]["status"] = status["status"]
                assert status["status"] == "completed", f"Run terminated as {status['status']}"
                trace = env["db"].traces.find_one({"run_id": run_id, "session_id": session_id})
                assert trace, "Completed chat has no persisted trace"
                text = (trace.get("conversation_search") or {}).get("assistant_final_text", "")
                evidence["stages"][-1].update(
                    {
                        "answer": text,
                        "trace": trace,
                        "elapsed_seconds": time.monotonic() - started_at,
                    }
                )
                save_json(journal, evidence)
                return text
            time.sleep(0.5)
        evidence["stages"][-1]["status"] = "hard_evaluation_deadline"
        try:
            evidence["stages"][-1]["cancellation"] = cancel_owned_run(
                env["clients"][item["owner"]], session_id, run_id
            )
        except Exception as error:
            evidence["stages"][-1]["cancel_error_type"] = type(error).__name__
        save_json(journal, evidence)
        raise AssertionError("Hard evaluation deadline reached; do not resubmit")

    try:
        for source in case["sources"]:
            for message in source["turns"]:
                chat(source, message)
            if source.get("feedback"):
                owner = source["owner"]
                user_id = env["users"][owner]["id"]
                assert env["db"].native_memories.count_documents({"user_id": user_id}) == 0
                signal = {
                    "user_id": user_id,
                    "session_id": session(source),
                    "run_id": evidence["stages"][-1]["run_id"],
                    "comment": source["feedback"],
                }
                evidence["feedback_source"] = signal
                api(
                    owner,
                    "POST",
                    "/api/feedback/",
                    {key: signal[key] for key in ("session_id", "run_id", "comment")}
                    | {"rating": "down"},
                )
                if case.get("natural_maintenance") == "reflection":

                    def record(stage):
                        evidence["stages"].append(stage)
                        save_json(journal, evidence)

                    NATURAL_HELPERS["wait_for_natural_maintenance"](
                        env,
                        owner,
                        record,
                        kind="reflection",
                        run_id=signal["run_id"],
                    )
                else:
                    for expected in (1, 0):
                        before = phase_calls("reflection")
                        result = reflect({"user_id": user_id})
                        evidence["stages"].append(
                            {
                                "kind": "explicit_reflection",
                                **result,
                                "model_calls": phase_calls("reflection") - before,
                            }
                        )
                        save_json(journal, evidence)
                        assert result == {"stored": expected}
                        assert phase_calls("reflection") - before == expected
                assert (
                    env["db"].feedback.find_one({"user_id": user_id, "run_id": signal["run_id"]})[
                        "evolution_processed"
                    ]
                    is True
                )
                assert (
                    env["db"].native_memories.count_documents(
                        {"user_id": user_id, "source": "self_evolved", "context": "feedback_rule"}
                    )
                    == 1
                )
            if case.get("natural_idle"):

                def record(stage):
                    evidence["stages"].append(stage)
                    save_json(journal, evidence)

                NATURAL_HELPERS["wait_for_natural_extraction"](
                    env, source["owner"], session(source), record
                )
                continue
            if source.get("skip_extraction"):
                continue
            call_log = env["output"] / "model-calls.jsonl"

            def extraction_calls():
                return (
                    sum(
                        row.get("event") == "start" and row.get("phase") == "extraction"
                        for row in (json.loads(line) for line in call_log.read_text().splitlines())
                    )
                    if call_log.exists()
                    else 0
                )

            before_extraction = extraction_calls()
            extraction = extract(source["owner"], session(source))
            evidence["stages"].append(
                {
                    "kind": "explicit_phase1",
                    **extraction,
                    "model_calls": extraction_calls() - before_extraction,
                }
            )
            save_json(journal, evidence)
            assert extraction["status"] in {"succeeded", "succeeded_no_output"}
            if "expected_extraction_status" in source:
                assert extraction["status"] == source["expected_extraction_status"]
            if "expected_extraction_model_calls" in source:
                assert (
                    evidence["stages"][-1]["model_calls"]
                    == source["expected_extraction_model_calls"]
                )
        if case.get("compact_owner"):
            owner = case["compact_owner"]
            user_id = env["users"][owner]["id"]
            seeds = case["seed_memories"]
            if case.get("lineage_sources"):
                archive_controlled_fixture(api, env["db"], owner, user_id, journal, evidence)
                seeds = []
                for seed in case["seed_memories"]:
                    payload = {
                        key: value for key, value in seed.items() if key != "source_sessions"
                    }
                    source_ids = [
                        sessions[(seed["owner"], label)] for label in seed["source_sessions"]
                    ]
                    payload["origin_session_ids"] = source_ids
                    payload["source_refs"] = [
                        {
                            "session_id": sid,
                            "run_id": next(
                                s["run_id"]
                                for s in reversed(evidence["stages"])
                                if s.get("kind") == "chat" and s["session_id"] == sid
                            ),
                        }
                        for sid in source_ids
                    ]
                    seeds.append(payload)
            seeded = seed_maintenance_memories(api, seeds)
            if case.get("lineage_sources"):
                assert env["db"].memory_forget_watermarks.count_documents({"user_id": user_id}) == 0
            count_query = {"user_id": user_id}
            if case.get("natural_maintenance") == "compaction":
                count_query["source"] = {"$nin": ["manual", "self_evolved"]}
            before_count = env["db"].native_memories.count_documents(count_query)
            if case.get("natural_maintenance") == "compaction":
                # The real scheduler may already be reducing rows while later protected seeds are saved.
                before_count = sum(
                    seed["owner"] == owner and seed["source"] not in {"manual", "self_evolved"}
                    for seed in seeds
                )
            evidence["seeded_memories"] = seeded
            if case.get("natural_maintenance") == "compaction":

                def record(stage):
                    evidence["stages"].append(stage)
                    save_json(journal, evidence)

                NATURAL_HELPERS["wait_for_natural_maintenance"](
                    env,
                    owner,
                    record,
                    kind="compaction",
                    before_count=before_count,
                    max_remaining=case["max_remaining_auto_memories"],
                )
            else:
                for attempt in range(case["max_compaction_passes"]):
                    env["guard"].check()
                    call_log = env["output"] / "model-calls.jsonl"
                    calls_before = (
                        len(call_log.read_text().splitlines()) if call_log.exists() else 0
                    )
                    stage = {"kind": "compaction", "attempt": attempt + 1, "status": "started"}
                    evidence["stages"].append(stage)
                    save_json(journal, evidence)
                    response = env["clients"][owner].post(
                        "/__memory_eval__/compact",
                        headers={"x-memory-eval-token": env["control_token"]},
                        json={"user_id": user_id},
                        timeout=600,
                    )
                    assert response.is_success, f"Compaction: HTTP {response.status_code}"
                    result = response.json()
                    stage.update(status="completed", result=result)
                    save_json(journal, evidence)
                    if result.get("reason") == "unchanged":
                        assert len(call_log.read_text().splitlines()) == calls_before
                        break
                    if result.get("reason") == "below_minimum":
                        from src.infra.memory.compaction_agent import _compaction_candidate_query

                        remaining = env["db"].native_memories.count_documents(
                            _compaction_candidate_query(user_id)
                        )
                        previous_deleted = sum(
                            s.get("result", {}).get("deleted", 0)
                            for s in evidence["stages"]
                            if s.get("kind") == "compaction" and s is not stage
                        )
                        assert stable_after_reduction(
                            result,
                            remaining=remaining,
                            previous_deleted=previous_deleted,
                            new_model_events=len(call_log.read_text().splitlines()) - calls_before,
                        )
                        break
                    assert not result.get("skipped"), "Compaction was skipped or failed"
                else:
                    raise AssertionError(
                        "Compaction did not stabilize within the frozen pass limit"
                    )
            after_count = env["db"].native_memories.count_documents(count_query)
            evidence["compaction_counts"] = {"before": before_count, "after": after_count}
            if case.get("lineage_sources"):
                kept = list(env["db"].native_memories.find({"user_id": user_id}))
                assert len(kept) == 1
                expected_sources = {sessions[(owner, label)] for label in case["lineage_sources"]}
                assert set(kept[0].get("origin_session_ids", [])) == expected_sources
                assert {
                    ref["session_id"] for ref in kept[0].get("source_refs", [])
                } == expected_sources
                evidence["lineage_canonical_after_compaction"] = {
                    "metadata": kept[0],
                    "full": api(owner, "GET", f"/api/memory/{kept[0]['memory_id']}"),
                }
                save_json(journal, evidence)
            assert after_count < before_count, "Redundant entries were not compacted"
            for record in seeded:
                if record["before"] is not None:
                    assert (
                        api(record["owner"], "GET", f"/api/memory/{record['memory_id']}")
                        == record["before"]
                    )
            save_json(journal, evidence)
        if case.get("vector_seed"):
            from src.infra.memory.client.native.vector_store import QdrantVectorIndex
            from tests.infra.memory.live_vector_seed import seed_project_map, seed_vectors

            for query in case["queries"]:
                session(query)
            seed = env["vector_seed"]
            source = env["db"].client[seed["database"]]
            source_owner = str(source.users.find_one({"username": "desktop_dev"})["_id"])
            seed_projects = seed_project_map(
                source.native_memories,
                source_owner,
                {label: pid for (owner, label), pid in projects.items() if owner == "a"},
                lambda label: api(
                    "a", "POST", "/api/projects", {"name": f"memory-eval:{case_id}:{label}"}
                )["id"],
            )

            async def load_seed():
                from unittest.mock import patch

                from src.kernel.config import settings

                with patch.object(settings, "NATIVE_MEMORY_QDRANT_API_KEY", env["qdrant"][1]):
                    index = QdrantVectorIndex(location=env["qdrant"][0], dims=seed["dimensions"])
                try:
                    return await seed_vectors(
                        source.native_memories,
                        env["db"].native_memories,
                        source_owner,
                        env["users"]["a"]["id"],
                        seed_projects,
                        index,
                        seed["dimensions"],
                    )
                finally:
                    await index.close()

            evidence["vector_seed"] = {**seed, **asyncio.run(load_seed())}
            save_json(journal, evidence)
        if case.get("capacity"):
            from datetime import datetime, timezone

            for query in case["queries"]:
                session(query)
            project_ids = {
                owner: [pid for (oid, _name), pid in projects.items() if oid == owner]
                for owner in env["users"]
            }
            evidence["capacity"] = seed_capacity_corpus(
                env["db"].native_memories,
                env["users"],
                project_ids,
                case["capacity"],
                now=datetime.now(timezone.utc),
            )
            for owner, seeded in evidence["capacity"].items():
                if seeded["noise_id"]:
                    # Exercise production invalidation after bulk loading; only an owned noise row changes.
                    api(
                        owner,
                        "PUT",
                        f"/api/memory/{seeded['noise_id']}",
                        {"tags": ["capacity-noise"]},
                    )
            save_json(journal, evidence)
        for query in case["queries"]:
            if query.get("forget_compacted_before"):
                user_id = env["users"][query["owner"]]["id"]
                kept = list(env["db"].native_memories.find({"user_id": user_id}))
                assert len(kept) == 1
                api(query["owner"], "DELETE", f"/api/memory/{kept[0]['memory_id']}")
                for label in case["lineage_sources"]:
                    before = phase_calls("extraction")
                    result = extract(query["owner"], sessions[(query["owner"], label)])
                    evidence["stages"].append(
                        {
                            "kind": "lineage_source_after_forget",
                            **result,
                            "model_calls": phase_calls("extraction") - before,
                        }
                    )
                    save_json(journal, evidence)
                    assert (
                        result["status"] == "succeeded_no_output"
                        and phase_calls("extraction") == before
                    )
            if query.get("forget_reflection_before"):
                user_id = env["users"][query["owner"]]["id"]
                lessons = list(
                    env["db"].native_memories.find({"user_id": user_id, "source": "self_evolved"})
                )
                assert len(lessons) == 1
                api(query["owner"], "DELETE", f"/api/memory/{lessons[0]['memory_id']}")
                before = phase_calls("reflection")
                result = reflect(evidence["feedback_source"])
                evidence["stages"].append(
                    {
                        "kind": "reflection_after_forget",
                        **result,
                        "model_calls": phase_calls("reflection") - before,
                    }
                )
                save_json(journal, evidence)
                assert result == {"stored": 0} and phase_calls("reflection") == before
                assert env["db"].native_memories.count_documents({"user_id": user_id}) == 0
            answer = chat(query, query["message"])
            if "expected_text" in query:
                stage = evidence["stages"][-1]
                response = env["clients"][query["owner"]].post(
                    "/__memory_eval__/final-text",
                    headers={"x-memory-eval-token": env["control_token"]},
                    json={
                        "run_id": stage["run_id"],
                        "session_id": stage["session_id"],
                        "user_id": env["users"][query["owner"]]["id"],
                    },
                )
                assert response.is_success
                raw_text = response.json()["text"]
                stage.update(raw_answer=raw_text, expected_text=query["expected_text"])
                save_json(journal, evidence)
                assert exact_text_matches(raw_text, query["expected_text"])
                continue
            actual = answer_fields(answer, strict=case.get("strict_json", False))
            evidence["stages"][-1].update({"actual": actual, "expected": query["expected"]})
            assert answer_matches(
                actual, query["expected"], strict=case.get("strict_json", False)
            ), "Answer differs; inspect case evidence"
        if case.get("expect_no_new_memories"):
            assert (
                env["db"].native_memories.count_documents({"user_id": env["users"]["a"]["id"]}) == 0
            )
        evidence["outcome"] = "pass"
    except Exception as error:
        evidence.update(outcome="fail", error_type=type(error).__name__)
        raise
    finally:
        evidence["memories"] = list(
            env["db"].native_memories.find(
                {
                    "user_id": {"$in": [user["id"] for user in env["users"].values()]},
                    "capacity_noise": {"$ne": True},
                },
                {"embedding": 0},
            )
        )
        save_json(journal, evidence)


def test_raw_final_answer_preserves_csv_rows_and_ignores_subagent_output():
    events = [
        {"event_type": "message:chunk", "data": {"text_id": "preamble", "content": "Checking."}},
        {
            "event_type": "message:chunk",
            "data": {"text_id": "final", "content": "item"},
        },
        {
            "event_type": "message:chunk",
            "data": {"text_id": "child", "depth": 1, "content": "Unrelated"},
        },
        {
            "event_type": "message:chunk",
            "data": {"text_id": "final", "content": ";cartons\nrice;18\nlentils;11"},
        },
    ]
    assert raw_final_answer(events) == "item;cartons\nrice;18\nlentils;11"


def test_exact_text_grade_rejects_intro_markdown_and_collapsed_rows():
    expected = "item;cartons\nrice;18\nlentils;11"
    assert exact_text_matches(expected + "\n", expected)
    assert exact_text_matches(expected.replace("\n", "\r\n"), expected)
    for invalid in [
        "Here is your report:\n" + expected,
        "```csv\n" + expected + "\n```",
        expected.replace("\n", " "),
    ]:
        assert not exact_text_matches(invalid, expected)


def test_long_multilingual_case_names_produce_valid_distinct_login_users():
    from src.kernel.schemas.user import UserBase

    case_id = "库存-zh-feedback-format-and-forget-heldout" * 10
    names = [evaluation_username(case_id, owner) for owner in ("a", "b")]
    assert len(set(names)) == 2
    assert evaluation_username(case_id, "a") == names[0]
    for name in names:
        UserBase(username=name, email=f"{name}@example.com")
        assert len(name) <= 50


def test_lineage_seed_restores_source_metadata_through_the_import_api():
    stored = {}
    calls = []

    def api(owner, method, path, body=None):
        calls.append((method, path))
        if method == "POST":
            assert path == "/api/memory/import"
            assert len(body["memories"]) == 1
            row = body["memories"][0]
            stored[row["memory_id"]] = row
            return {"success": True, "imported": 1, "created": 1, "overwritten": 0}
        assert method == "GET"
        return stored[path.rsplit("/", 1)[1]]

    records = seed_maintenance_memories(
        api,
        [
            {
                "owner": "a",
                "source": "auto_retained",
                "content": "Digest on Tuesday; previews disabled.",
                "origin_session_ids": ["owned-source"],
                "source_refs": [{"session_id": "owned-source", "run_id": "owned-run"}],
            }
        ],
    )
    restored = stored[records[0]["memory_id"]]
    assert restored["origin_session_ids"] == ["owned-source"]
    assert restored["source_refs"] == [{"session_id": "owned-source", "run_id": "owned-run"}]
    assert restored["source"] == "auto_retained"
    assert all(method != "PUT" for method, _ in calls)


@pytest.mark.parametrize("count", [0, 1, 2])
def test_controlled_lineage_fixture_rejects_below_policy_minimum_before_paid_calls(count):
    with pytest.raises(ValueError, match="minimum"):
        validate_controlled_lineage_fixture(
            {"lineage_sources": ["first", "second"], "seed_memories": [{}] * count}
        )
    validate_controlled_lineage_fixture(
        {"lineage_sources": ["first", "second"], "seed_memories": [{}] * 3}
    )


def test_fixture_preflight_runs_before_connection_or_started_marker(monkeypatch, tmp_path):
    from unittest.mock import Mock

    output = tmp_path / "must-not-start"
    monkeypatch.setenv("LAMBCHAT_MEMORY_LIVE", "1")
    monkeypatch.setenv("LAMBCHAT_MEMORY_LIVE_OUTPUT", str(output))
    monkeypatch.setenv("LAMBCHAT_MEMORY_LIVE_CASES", "en-compaction-preserves-both-source-lineages")
    connect = Mock(side_effect=AssertionError("Preflight must precede any connection"))
    monkeypatch.setattr("src.infra.storage.mongodb.build_mongo_connection_string", connect)
    with pytest.raises(ValueError, match="minimum"):
        next(live_environment.__wrapped__())
    connect.assert_not_called()
    assert not output.exists()


def test_below_minimum_is_terminal_only_after_real_reduction_without_more_calls():
    result = {"skipped": True, "reason": "below_minimum", "checked": 1}
    assert stable_after_reduction(result, remaining=1, previous_deleted=2, new_model_events=0)
    assert not stable_after_reduction(result, remaining=1, previous_deleted=0, new_model_events=0)
    assert not stable_after_reduction(result, remaining=1, previous_deleted=2, new_model_events=1)
    assert not stable_after_reduction(result, remaining=3, previous_deleted=2, new_model_events=0)
    for invalid in [
        {**result, "reason": "tool_failed"},
        {**result, "failed": 1},
        {**result, "checked": 2},
        {**result, "skipped": False},
    ]:
        assert not stable_after_reduction(
            invalid, remaining=1, previous_deleted=2, new_model_events=0
        )


def test_natural_compaction_protected_rows_exist_before_the_threshold_tick():
    from copy import deepcopy

    case = next(case for case in SUITE["cases"] if case.get("natural_maintenance") == "compaction")
    records = {}
    tick_snapshots = []

    def api(owner, method, path, payload=None):
        if method == "POST":
            memory_id = str(len(records) + 1)
            records[memory_id] = {**payload, "owner": owner, "source": "manual"}
            return {"memory_id": memory_id}
        memory_id = path.rsplit("/", 1)[-1]
        if method == "GET":
            return deepcopy(records[memory_id])
        assert method == "PUT"
        records[memory_id].update(payload)
        if (
            sum(
                record["owner"] == "a" and record["source"] == "auto_retained"
                for record in records.values()
            )
            == 40
        ):
            assert any(
                record["owner"] == "a" and record["source"] == "manual"
                for record in records.values()
            )
            assert any(record["owner"] == "b" for record in records.values())
            tick_snapshots.append(deepcopy(records))
        return {"success": True}

    saved = seed_maintenance_memories(api, case["seed_memories"])
    protected_ids = {record["memory_id"] for record in saved if record["before"] is not None}
    assert len(tick_snapshots) == 1 and len(protected_ids) == 2
    assert protected_ids.issubset(tick_snapshots[0])
