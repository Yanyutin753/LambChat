"""Opt-in, isolated six-month memory capacity benchmark; no provider calls.

Run only through scripts/run_validation.py. Deterministic vectors measure retrieval
engineering, not embedding-model semantic quality. Raw timings are not an SLA.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import random
import sys
import time
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def peak_rss() -> int | None:
    try:
        import resource
    except ImportError:
        return None
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss


def source_hash() -> str:
    digest = hashlib.sha256()
    for path in [*sorted((ROOT / "src/infra/memory").rglob("*.py")), Path(__file__)]:
        digest.update(path.read_bytes())
    return digest.hexdigest()


def save(path: Path, value) -> None:
    with path.open("w") as handle:
        os.chmod(path, 0o600)
        json.dump(value, handle, ensure_ascii=False, indent=2, default=str)


def memory(index: int, now, dimensions: int, *, owner: str = "capacity-owner") -> dict:
    """Reproducible scopes, ages and prose; UUIDs are confined to the owned DB."""
    rng = random.Random(index)
    vector = [rng.uniform(-1.0, 1.0) for _ in range(dimensions)]
    vector[1] = 1.0
    is_project = index % 3 != 0
    scope = "project" if is_project else "user"
    timestamp = now - timedelta(days=index % 180)
    topic = ("采购记录", "Studio planning", "学習計画", "발주 기록", "Рабочие заметки")[index % 5]
    content = (
        f"{topic}: item {index}, review cycle {index % 12}, agreed quantity {index % 500 + 1}."
    )
    if index % 50 == 0:
        content += "\n" + "\n".join(
            f"Material line {line}: item {index * 71 + line}, units {(index + line) * 17 % 211}, route {line % 4}."
            for line in range(200)
        )
    return {
        "memory_id": uuid4().hex,
        "user_id": owner,
        "title": f"{topic} {index}",
        "summary": content[:100],
        "index_label": content[:100],
        "content": content,
        "content_storage_mode": "inline",
        "content_store_key": None,
        "scope": scope,
        "project_id": f"project-{index % 10}" if is_project else None,
        "memory_type": scope,
        "context": "project_constraint" if is_project else "user_preference",
        "source": "manual" if index % 5 == 0 else "auto_retained",
        "tags": [topic, "review"],
        "embedding": vector,
        "created_at": timestamp,
        "updated_at": timestamp,
        "access_count": 0,
        "accessed_at": timestamp,
        "source_refs": [],
    }


async def benchmark(output: Path, scales: list[int], dimensions: int) -> int:
    from pymongo import AsyncMongoClient

    from src.infra.memory.client.native.backend import NativeMemoryBackend
    from src.infra.memory.client.native.content import build_content_fields
    from src.infra.storage.mongodb import build_mongo_connection_string
    from src.infra.storage.mongodb_store import MongoDBStore
    from src.infra.utils.datetime import utc_now
    from src.kernel.config import settings

    if ROOT == output or ROOT in output.parents:
        raise ValueError("Capacity evidence must stay outside the repository")
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    fingerprint = source_hash()
    with (output / "started.json").open("x") as handle:
        os.chmod(output / "started.json", 0o600)
        json.dump(
            {"source_sha256": fingerprint, "scales": scales, "dimensions": dimensions}, handle
        )
    database_name = f"memory_capacity_{uuid4().hex}"
    original_db, original_vector = settings.MONGODB_DB, settings.NATIVE_MEMORY_VECTOR_BACKEND
    settings.MONGODB_DB, settings.NATIVE_MEMORY_VECTOR_BACKEND = database_name, "mongo"
    client = AsyncMongoClient(build_mongo_connection_string(), tz_aware=True, timeoutMS=120000)
    db = client[database_name]
    backend = NativeMemoryBackend()
    backend._collection = db.native_memories
    backend._store = MongoDBStore(client=client, db_name=database_name)
    now = utc_now()
    anchors = {}
    queries = {
        "default communication tone": (0, None, "preference"),
        "data expiry duration": (2, "project-1", "project"),
        "guarantee period": (3, None, "long"),
    }

    async def embed(query):
        vector = [0.0] * dimensions
        vector[queries.get(query, (1, None, None))[0]] = 1.0
        return vector

    backend._embedding_fn = embed
    report = {
        "database": database_name,
        "source_sha256": fingerprint,
        "span_days": 180,
        "dimensions": dimensions,
        "provider_calls": 0,
        "evidence_scope": "Actual Mongo/index/store/recall with deterministic vectors; no real embedding or LLM semantic claim",
        "results": [],
        "state": "started",
    }
    save(output / "report.json", report)
    try:
        await backend._create_indexes()
        for name, axis in (("preference", 0), ("project", 2), ("long", 3)):
            doc = memory(0, now, dimensions)
            doc.update(
                {
                    "title": name,
                    "summary": name,
                    "index_label": name,
                    "content": f"Half-year durable {name} fact.",
                    "updated_at": now - timedelta(days=180),
                    "created_at": now - timedelta(days=180),
                }
            )
            doc["embedding"] = [0.0] * dimensions
            doc["embedding"][axis] = 1.0
            if name == "project":
                doc.update(
                    scope="project",
                    project_id="project-1",
                    memory_type="project",
                    context="project_constraint",
                )
                doc["content"] = "Project archive retention is 45 days."
            if name == "preference":
                doc["content"] = "The user wants concise Chinese answers."
            doc.update(
                await build_content_fields(
                    backend, doc["user_id"], doc["memory_id"], doc["content"]
                )
            )
            if name == "long":
                body = (
                    "Supplier handling and packaging constraints. " * 180 + "Warranty is 37 months."
                )
                doc.update(
                    await build_content_fields(backend, doc["user_id"], doc["memory_id"], body)
                )
            anchors[name] = doc["memory_id"]
            await db.native_memories.insert_one(doc)
        foreign = [
            memory(index, now, dimensions, owner="capacity-other-user") for index in range(1000)
        ]
        for doc in foreign:
            doc["embedding"] = [1.0] + [0.0] * (dimensions - 1)
        await db.native_memories.insert_many(foreign)
        inserted = 3
        for scale in scales:
            seed_started = time.perf_counter()
            while inserted < scale:
                stop = min(inserted + 250, scale)
                batch = [memory(index, now, dimensions) for index in range(inserted, stop)]
                for doc in batch:
                    doc.update(
                        await build_content_fields(
                            backend, doc["user_id"], doc["memory_id"], doc["content"]
                        )
                    )
                await db.native_memories.insert_many(batch)
                inserted = stop
            stage = {
                "owner_memories": scale,
                "other_user_memories": 1000,
                "seed_seconds": time.perf_counter() - seed_started,
                "queries": [],
            }
            for query, (_axis, project_id, target) in queries.items():
                for repetition in range(2):
                    started = time.perf_counter()
                    recalled = await backend.recall(
                        "capacity-owner",
                        query,
                        max_results=5,
                        touch_access=False,
                        enable_rerank=False,
                        project_id=project_id,
                    )
                    hits = recalled.get("memories") or []
                    stage["queries"].append(
                        {
                            "query": query,
                            "repetition": repetition,
                            "elapsed_ms": (time.perf_counter() - started) * 1000,
                            "target_found": any(
                                hit["memory_id"] == anchors[target] for hit in hits
                            ),
                            "leaks": [
                                hit["memory_id"]
                                for hit in hits
                                if hit.get("user_id") != "capacity-owner"
                                or (
                                    hit.get("scope") == "project"
                                    and hit.get("project_id") != project_id
                                )
                            ],
                            "returned_characters": sum(len(hit.get("text", "")) for hit in hits),
                            "long_tail_found": any(
                                "Warranty is 37 months." in hit.get("text", "") for hit in hits
                            )
                            if target == "long"
                            else None,
                        }
                    )
            backend._index_cache.clear()
            started = time.perf_counter()
            index = await backend.build_memory_index("capacity-owner", project_id="project-1")
            stage.update(
                index_characters=len(index),
                index_ms=(time.perf_counter() - started) * 1000,
                collection_stats=await db.command("collStats", "native_memories"),
                python_peak_rss_native_units=peak_rss(),
            )
            report["results"].append(stage)
            save(output / "report.json", report)
            print(
                json.dumps(
                    {
                        "owner_memories": scale,
                        "target_found": [q["target_found"] for q in stage["queries"]],
                        "index_characters": len(index),
                    }
                ),
                flush=True,
            )
            if source_hash() != fingerprint:
                raise RuntimeError("Capacity benchmark source changed")
        passed = all(
            q["target_found"] and not q["leaks"] and q["long_tail_found"] is not False
            for stage in report["results"]
            for q in stage["queries"]
        )
        report["state"] = "pass" if passed else "fail"
        save(output / "report.json", report)
        return 0 if passed else 1
    except BaseException as error:
        report.update(state="error", error_type=type(error).__name__)
        save(output / "report.json", report)
        raise
    finally:
        # Keep only isolated synthetic rows for subsequent inspection; no credentials were copied.
        await backend.close()
        await client.close()
        settings.MONGODB_DB, settings.NATIVE_MEMORY_VECTOR_BACKEND = original_db, original_vector


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dimensions", type=int, default=1536)
    parser.add_argument("--scales", type=int, nargs="+", default=[1000, 10000, 50000])
    args = parser.parse_args()
    if (
        args.dimensions < 4
        or not args.scales
        or sorted(set(args.scales)) != args.scales
        or args.scales[0] < 3
    ):
        parser.error("Use dimensions >=4 and increasing unique scales >=3")
    return asyncio.run(benchmark(args.output.expanduser().resolve(), args.scales, args.dimensions))


if __name__ == "__main__":
    raise SystemExit(main())
