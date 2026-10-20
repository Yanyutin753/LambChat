"""Reuse retained synthetic vectors without repeating provider ingestion."""

import hashlib
import json
import stat
from pathlib import Path
from uuid import UUID, uuid4

from qdrant_client.models import PointStruct

ROOT = Path(__file__).resolve().parents[3]


def read_vector_seed(path, profile):
    if not profile:
        raise ValueError("Large Agent evaluation requires an embedding profile")
    path = Path(path).expanduser().resolve()
    if ROOT == path or ROOT in path.parents or stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise ValueError("Vector seed report must be private and external")
    report = json.loads(path.read_text())
    database = report.get("database", "")
    if (
        not database.startswith("memory_real_capacity_")
        or report.get("state") not in {"pass", "quality_pass_with_provider_failures"}
        or report.get("model") != profile["NATIVE_MEMORY_EMBEDDING_MODEL"]
        or report.get("dimensions") != profile["NATIVE_MEMORY_EMBEDDING_DIMENSIONS"]
    ):
        raise ValueError("Incompatible isolated vector seed")
    return {
        "database": database,
        "dimensions": report["dimensions"],
        "report_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def seed_project_map(source, source_owner, existing, create):
    projects = dict(existing)
    for label in source.distinct("project_id", {"user_id": source_owner}):
        if label is not None and label not in projects:
            projects[label] = create(label)
    return projects


def map_seed_document(document, owner, projects, dimensions):
    if len(document.get("embedding") or []) != dimensions:
        raise ValueError("Seed vector dimensions differ from configured embedding model")
    project = document.get("project_id")
    if project is not None and project not in projects:
        raise ValueError("Seed project has no isolated target mapping")
    if (
        not isinstance(document.get("content"), str)
        or document.get("content_store_key")
        or document.get("content_storage_mode", document.get("storage_mode", "inline")) != "inline"
    ):
        raise ValueError("Vector seed requires self-contained inline synthetic content")
    return {
        **{key: value for key, value in document.items() if key != "_id"},
        "memory_id": uuid4().hex,
        "user_id": owner,
        "project_id": projects[project] if project is not None else None,
        "capacity_noise": True,
    }


async def seed_vectors(source, target, source_owner, owner, projects, index, dimensions):
    from src.infra.memory.client.native.vector_store import COLLECTION

    query = {"user_id": source_owner}
    if source.count_documents(query) != 50000 or target.count_documents({"user_id": owner}):
        raise ValueError("Vector seed requires exactly 50000 source rows and an empty target owner")
    await index.ensure_collection()
    batch = []
    count = 0

    async def flush():
        target.insert_many(batch)
        await index._client.upsert(
            collection_name=COLLECTION,
            points=[
                PointStruct(
                    id=UUID(hex=doc["memory_id"]),
                    vector=doc["embedding"],
                    payload={
                        key: doc.get(key)
                        for key in ("user_id", "memory_type", "context", "scope", "project_id")
                    },
                )
                for doc in batch
            ],
            wait=True,
        )

    for document in source.find(query, {"_id": 0}):
        batch.append(map_seed_document(document, owner, projects, dimensions))
        count += 1
        if len(batch) == 256:
            await flush()
            batch.clear()
    if batch:
        await flush()
    assert count == target.count_documents({"user_id": owner}) == 50000
    return {"memory_count": count, "reembedded_seed_vectors": 0, "foreign_seed_rows_copied": 0}
