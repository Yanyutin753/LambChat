"""Opt-in production-provider embeddings, isolated Mongo and in-memory Qdrant.

LAMBCHAT_MEMORY_EMBEDDING_LIVE=1 requires a private embedding-only profile and a
fresh external output directory. No production memories or index are modified.
"""

import json
import os
import stat
from pathlib import Path

import pytest

from src.infra.llm.quota import bind_quota_user

ROOT = Path(__file__).resolve().parents[3]
CORPUS = ROOT / "tests/fixtures/memory_lifecycle/embedding_v1.json"
PROFILE_KEYS = {
    "NATIVE_MEMORY_EMBEDDING_API_BASE",
    "NATIVE_MEMORY_EMBEDDING_API_KEY",
    "NATIVE_MEMORY_EMBEDDING_MODEL",
    "NATIVE_MEMORY_EMBEDDING_DIMENSIONS",
}


@bind_quota_user
async def embedding_for_owner(backend, text: str, user_id: str):
    return await backend._maybe_embed(text)


def read_embedding_profile(path: Path) -> dict:
    path = path.expanduser().resolve()
    if path == ROOT or ROOT in path.parents:
        raise ValueError("Embedding credentials must stay outside the repository")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError("Embedding credentials require a private file")
    profile = json.loads(path.read_text())
    if not isinstance(profile, dict) or set(profile) != PROFILE_KEYS:
        raise ValueError("Invalid embedding profile")
    dimensions = profile["NATIVE_MEMORY_EMBEDDING_DIMENSIONS"]
    if (
        type(dimensions) is not int
        or dimensions <= 0
        or any(
            not isinstance(profile[key], str) or not profile[key].strip()
            for key in PROFILE_KEYS - {"NATIVE_MEMORY_EMBEDDING_DIMENSIONS"}
        )
    ):
        raise ValueError("Invalid embedding profile")
    return profile


def test_embedding_profile_allows_only_embedding_settings_in_private_files(tmp_path):
    profile = {
        "NATIVE_MEMORY_EMBEDDING_API_BASE": "https://example.invalid",
        "NATIVE_MEMORY_EMBEDDING_API_KEY": "synthetic-test-key",
        "NATIVE_MEMORY_EMBEDDING_MODEL": "synthetic-model",
        "NATIVE_MEMORY_EMBEDDING_DIMENSIONS": 1024,
    }
    path = tmp_path / "profile.json"
    path.write_text(json.dumps(profile))
    path.chmod(0o600)
    assert read_embedding_profile(path) == profile
    for invalid in [
        {**profile, "MONGODB_DB": "production"},
        {**profile, "NATIVE_MEMORY_EMBEDDING_API_KEY": ""},
        {**profile, "NATIVE_MEMORY_EMBEDDING_DIMENSIONS": True},
        {**profile, "NATIVE_MEMORY_EMBEDDING_DIMENSIONS": 0},
    ]:
        path.write_text(json.dumps(invalid))
        with pytest.raises(ValueError, match="embedding profile"):
            read_embedding_profile(path)
    path.write_text(json.dumps(profile))
    path.chmod(0o644)
    with pytest.raises(ValueError, match="private"):
        read_embedding_profile(path)
    with pytest.raises(ValueError, match="repository"):
        read_embedding_profile(ROOT / "profile.json")


def test_invalid_profile_is_rejected_before_database_connection_or_paid_marker(
    tmp_path, monkeypatch
):
    import runpy
    from unittest.mock import Mock

    profile = tmp_path / "invalid-profile.json"
    profile.write_text(json.dumps({"MONGODB_DB": "production"}))
    profile.chmod(0o600)
    output = tmp_path / "unused-output"
    monkeypatch.setenv("LAMBCHAT_MEMORY_LIVE", "1")
    monkeypatch.setenv("LAMBCHAT_MEMORY_LIVE_CASES", "en-unknown-information")
    monkeypatch.setenv("LAMBCHAT_MEMORY_LIVE_OUTPUT", str(output))
    monkeypatch.setenv("LAMBCHAT_MEMORY_LIVE_EMBEDDING_PROFILE", str(profile))
    connect = Mock(side_effect=AssertionError("Invalid profile must not reach a database"))
    monkeypatch.setattr("src.infra.storage.mongodb.build_mongo_connection_string", connect)
    runner = runpy.run_path(str(Path(__file__).with_name("test_live_lifecycle.py")))
    with pytest.raises(ValueError, match="embedding profile"):
        next(runner["live_environment"].__wrapped__())
    connect.assert_not_called()
    assert not output.exists()


@pytest.mark.skipif(os.environ.get("TEST_MEMORY_MONGODB") != "1", reason="Opt-in real MongoDB")
async def test_embedding_evaluation_keeps_real_quota_checks_and_settlement(monkeypatch):
    from uuid import uuid4

    import httpx
    from pymongo import AsyncMongoClient

    from src.infra.llm.quota import quota_user_id
    from src.infra.memory.client.native.backend import NativeMemoryBackend
    from src.infra.storage.mongodb import build_mongo_connection_string
    from src.kernel.config import settings

    name = f"memory_embedding_quota_{uuid4().hex}"
    monkeypatch.setattr(settings, "MONGODB_DB", name)
    client = AsyncMongoClient(build_mongo_connection_string(), timeoutMS=10000)
    monkeypatch.setattr("src.infra.storage.mongodb.get_mongo_client", lambda: client)
    monkeypatch.setattr("src.infra.usage.storage.get_mongo_client", lambda: client)
    db = client[name]
    user_id = str(
        (
            await db.users.insert_one(
                {
                    "username": "desktop_dev",
                    "email": "desktop_dev@example.com",
                    "password_hash": "unused",
                    "roles": ["memory_eval"],
                    "is_active": True,
                }
            )
        ).inserted_id
    )
    await db.roles.insert_one({"name": "memory_eval", "limits": {}})
    monkeypatch.setattr(settings, "NATIVE_MEMORY_EMBEDDING_API_BASE", "https://example.invalid")
    monkeypatch.setattr(settings, "NATIVE_MEMORY_EMBEDDING_API_KEY", "synthetic-test-key")
    calls = []

    async def handler(request):
        assert quota_user_id() == user_id
        assert await db.user_usage_quotas.find_one({"_id": user_id}) is not None
        calls.append(request.url.path)
        return httpx.Response(200, json={"data": [{"embedding": [1.0, 0.0]}]})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        httpx,
        "AsyncClient",
        lambda **kwargs: real_client(transport=httpx.MockTransport(handler), **kwargs),
    )
    backend = NativeMemoryBackend()
    backend._setup_embedding_fn()
    try:
        assert await embedding_for_owner(backend, "Durable fact", user_id) == [1.0, 0.0]
        assert calls == ["/v1/embeddings"]
        ledger = await db.user_usage_quotas.find_one({"_id": user_id})
        assert len(ledger["calls"]) == 1
        assert (
            await db[settings.MONGODB_USAGE_LOGS_COLLECTION].count_documents({"user_id": user_id})
            == 1
        )
        assert all(call["unknown"] and not call["pending"] for call in ledger["calls"].values())
    finally:
        await backend.close()
        await client.drop_database(name)
        await client.close()


@pytest.mark.skipif(
    os.environ.get("LAMBCHAT_MEMORY_EMBEDDING_LIVE") != "1", reason="Opt-in real embedding provider"
)
async def test_real_provider_multilingual_recall(monkeypatch):
    import hashlib
    import math
    import time
    from datetime import timedelta
    from uuid import uuid4

    from pymongo import AsyncMongoClient

    from src.infra.memory.client.native import vector_store
    from src.infra.memory.client.native.backend import NativeMemoryBackend
    from src.infra.storage.mongodb import build_mongo_connection_string
    from src.infra.utils.datetime import utc_now
    from src.kernel.config import settings

    profile = read_embedding_profile(Path(os.environ["LAMBCHAT_MEMORY_EMBEDDING_PROFILE"]))
    output = Path(os.environ["LAMBCHAT_MEMORY_EMBEDDING_OUTPUT"]).expanduser().resolve()
    if output == ROOT or ROOT in output.parents:
        raise ValueError("Embedding evidence must stay outside the repository")
    output.mkdir(parents=True, exist_ok=True, mode=0o700)

    def fingerprint():
        digest = hashlib.sha256()
        for path in [*sorted((ROOT / "src").rglob("*.py")), Path(__file__), CORPUS]:
            digest.update(path.read_bytes())
        return digest.hexdigest()

    frozen = fingerprint()
    with (output / "started.json").open("x") as handle:
        os.chmod(handle.name, 0o600)
        json.dump(
            {"source_sha256": frozen, "model": profile["NATIVE_MEMORY_EMBEDDING_MODEL"]}, handle
        )
    for key, value in profile.items():
        monkeypatch.setattr(settings, key, value)
    monkeypatch.setattr(settings, "NATIVE_MEMORY_VECTOR_BACKEND", "mongo")
    client = AsyncMongoClient(build_mongo_connection_string(), timeoutMS=10000)
    monkeypatch.setattr("src.infra.storage.mongodb.get_mongo_client", lambda: client)
    monkeypatch.setattr("src.infra.usage.storage.get_mongo_client", lambda: client)
    database_name = f"memory_embedding_eval_{uuid4().hex}"
    monkeypatch.setattr(settings, "MONGODB_DB", database_name)
    db = client[database_name]
    user_id = str(
        (
            await db.users.insert_one(
                {
                    "username": "desktop_dev",
                    "email": "desktop_dev@example.com",
                    "password_hash": "unused",
                    "roles": ["memory_eval"],
                    "is_active": True,
                }
            )
        ).inserted_id
    )
    await db.roles.insert_one({"name": "memory_eval", "limits": {}})
    backend = NativeMemoryBackend()
    backend._collection = db.native_memories
    backend._setup_embedding_fn()
    index = vector_store.QdrantVectorIndex(
        location=":memory:", dims=profile["NATIVE_MEMORY_EMBEDDING_DIMENSIONS"]
    )
    monkeypatch.setattr(vector_store, "_vector_index", index)
    corpus = json.loads(CORPUS.read_text())
    report = {
        "state": "started",
        "database": database_name,
        "source_sha256": frozen,
        "model": profile["NATIVE_MEMORY_EMBEDDING_MODEL"],
        "dimensions": profile["NATIVE_MEMORY_EMBEDDING_DIMENSIONS"],
        "provider_calls": [],
        "queries": [],
        "cost_usd": None,
        "scope": "Real provider embeddings; owned synthetic 180-day facts, Mongo and local in-memory Qdrant. Search timings exclude precomputed query embeddings; no production index writes or LLM answer claim.",
    }

    def save(name, value):
        with (output / name).open("w") as handle:
            os.chmod(handle.name, 0o600)
            json.dump(value, handle, ensure_ascii=False, indent=2, default=str)

    async def record_response(response):
        await response.aread()
        receipt = report["provider_calls"][-1]
        receipt["http_status"] = response.status_code
        try:
            usage = response.json().get("usage")
        except (ValueError, AttributeError):
            usage = None
        receipt["usage"] = (
            {
                key: value
                for key, value in (usage or {}).items()
                if key in {"prompt_tokens", "total_tokens"} and type(value) is int
            }
            if isinstance(usage, dict)
            else None
        )
        save("report.json", report)

    async def record_request(request):
        report["provider_calls"][-1]["http_started"] = True
        save("report.json", report)

    backend._httpx_client.event_hooks["request"].append(record_request)
    backend._httpx_client.event_hooks["response"].append(record_response)

    async def embed(text):
        assert fingerprint() == frozen, "Embedding evaluation source changed"
        call = {
            "text_sha256": hashlib.sha256(text.encode()).hexdigest(),
            "status": "started",
            "http_started": False,
        }
        report["provider_calls"].append(call)
        save("report.json", report)
        start = time.monotonic()
        try:
            vector = await embedding_for_owner(backend, text, user_id)
            call["status"] = "complete" if vector else "failed"
        except BaseException as exc:
            call.update(status="failed", failure_type=type(exc).__name__)
            raise
        finally:
            call["elapsed_ms"] = (time.monotonic() - start) * 1000
            save("report.json", report)
        assert vector and len(vector) == profile["NATIVE_MEMORY_EMBEDDING_DIMENSIONS"]
        assert all(type(value) in (int, float) and math.isfinite(value) for value in vector)
        assert any(vector)
        return vector

    try:
        facts = list(corpus["memories"])
        facts += [
            {
                "id": f"garden-{i}",
                "scope": "user",
                "project_id": None,
                "content": f"For fictional garden plot {i}, the owner prefers bamboo benches and a blue tiled path of width {i + 70} centimetres.",
            }
            for i in range(corpus["distractor_count"])
        ]
        now = utc_now()
        docs, aliases = [], {}
        for fact in facts:
            mid = aliases[fact["id"]] = uuid4().hex
            docs.append(
                {
                    "user_id": user_id,
                    "memory_id": mid,
                    "content": fact["content"],
                    "title": fact["content"][:25],
                    "summary": fact["content"][:100],
                    "tags": [],
                    "source": "manual",
                    "memory_type": "user",
                    "context": "user",
                    "scope": fact["scope"],
                    "project_id": fact["project_id"],
                    "created_at": now - timedelta(days=180),
                    "updated_at": now - timedelta(days=180),
                    "content_storage_mode": "inline",
                    "embedding": await embed(fact["content"]),
                }
            )
        docs.append({**docs[0], "user_id": "foreign", "memory_id": uuid4().hex})
        query_vectors = {case["query"]: await embed(case["query"]) for case in corpus["queries"]}
        save("vectors.json", {"memories": docs, "queries": query_vectors, "aliases": aliases})
        await db.native_memories.insert_many(docs)
        await index.ensure_collection()
        for doc in docs:
            assert await index.upsert(
                memory_id=doc["memory_id"],
                user_id=doc["user_id"],
                vector=doc["embedding"],
                memory_type=doc["memory_type"],
                context=doc["context"],
                updated_at=int(doc["updated_at"].timestamp()),
                scope=doc["scope"],
                project_id=doc["project_id"],
            )

        async def precomputed(query):
            return query_vectors[query]

        backend._embedding_fn = precomputed
        for engine in ("mongo", "qdrant"):
            monkeypatch.setattr(settings, "NATIVE_MEMORY_VECTOR_BACKEND", engine)
            for case in corpus["queries"]:
                assert fingerprint() == frozen, "Embedding evaluation source changed"
                start = time.monotonic()
                result = await backend.recall(
                    user_id,
                    case["query"],
                    max_results=3,
                    project_id=case["project_id"],
                    touch_access=False,
                )
                hits = result.get("memories", [])
                ids = [hit["memory_id"] for hit in hits]
                leaked = [
                    hit["memory_id"]
                    for hit in hits
                    if hit.get("user_id") != user_id
                    or (
                        hit.get("scope") == "project"
                        and hit.get("project_id") != case["project_id"]
                    )
                ]
                report["queries"].append(
                    {
                        "engine": engine,
                        "case": case["expected_id"],
                        "expected_memory_id": aliases[case["expected_id"]],
                        "returned_ids": ids,
                        "found": aliases[case["expected_id"]] in ids,
                        "leaks": leaked,
                        "elapsed_ms": (time.monotonic() - start) * 1000,
                    }
                )
                save("report.json", report)
        ledger = await db.user_usage_quotas.find_one({"_id": user_id})
        calls = (ledger or {}).get("calls", {})
        report["quota_calls"] = len(calls)
        report["auxiliary_usage_logs"] = await db[
            settings.MONGODB_USAGE_LOGS_COLLECTION
        ].count_documents({"user_id": user_id})
        report["quota_unknown_settled_calls"] = sum(
            call.get("unknown") is True and call.get("pending") is False for call in calls.values()
        )
        assert (
            report["quota_calls"]
            == report["quota_unknown_settled_calls"]
            == len(report["provider_calls"])
        )
        assert report["auxiliary_usage_logs"] == len(report["provider_calls"])
        assert all(call.get("http_started") for call in report["provider_calls"])
        assert all(q["found"] and not q["leaks"] for q in report["queries"])
        report["state"] = "pass"
    except BaseException as exc:
        report.update(state="fail", failure_type=type(exc).__name__)
        raise
    finally:
        save("report.json", report)
        await index.close()
        await backend.close()
        await client.drop_database(database_name)
        await client.close()
