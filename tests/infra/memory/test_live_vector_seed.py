"""Unpaid contracts for reusing real vectors in fresh Agent conversations."""

import runpy
from pathlib import Path

import pytest

HELPER = Path(__file__).with_name("live_vector_seed.py")


def test_seed_mapping_preserves_vectors_ages_and_only_remaps_owned_projects():
    helper = runpy.run_path(str(HELPER))
    vector = [0.2, 0.8]
    document = {
        "_id": "old-internal-id",
        "memory_id": "1" * 32,
        "user_id": "source-owner",
        "scope": "project",
        "project_id": "alpha",
        "content": "Archived policy",
        "embedding": vector,
        "updated_at": "original-date",
    }
    mapped = helper["map_seed_document"](document, "new-owner", {"alpha": "new-alpha"}, 2)
    assert mapped["user_id"] == "new-owner"
    assert mapped["memory_id"] != document["memory_id"]
    assert mapped["project_id"] == "new-alpha"
    assert mapped["embedding"] is vector
    assert mapped["updated_at"] == "original-date"
    assert "_id" not in mapped
    assert document["project_id"] == "alpha"
    with pytest.raises(ValueError, match="project"):
        helper["map_seed_document"](document, "new-owner", {}, 2)
    with pytest.raises(ValueError, match="dimensions"):
        helper["map_seed_document"](document, "new-owner", {"alpha": "x"}, 3)


def test_large_agent_seed_preflight_rejects_missing_profile_before_database_or_marker(
    monkeypatch, tmp_path
):
    from unittest.mock import Mock

    runner = runpy.run_path(str(Path(__file__).with_name("test_live_lifecycle.py")))
    monkeypatch.setenv("LAMBCHAT_MEMORY_LIVE", "1")
    monkeypatch.setenv("LAMBCHAT_MEMORY_LIVE_CASES", "multilingual-real-vector-agent-heldout")
    monkeypatch.setenv("LAMBCHAT_MEMORY_LIVE_OUTPUT", str(tmp_path / "must-not-start"))
    monkeypatch.delenv("LAMBCHAT_MEMORY_LIVE_EMBEDDING_PROFILE", raising=False)
    connect = Mock(side_effect=AssertionError("Invalid cohort must not reach MongoDB"))
    monkeypatch.setattr("src.infra.storage.mongodb.build_mongo_connection_string", connect)
    with pytest.raises(ValueError, match="embedding profile"):
        next(runner["live_environment"].__wrapped__())
    connect.assert_not_called()
    assert not (tmp_path / "must-not-start").exists()


def test_seed_report_rejects_wrong_database_or_embedding_model(tmp_path):
    import json

    helper = runpy.run_path(str(HELPER))
    path = tmp_path / "seed.json"
    path.touch(mode=0o600)
    profile = {"NATIVE_MEMORY_EMBEDDING_MODEL": "model", "NATIVE_MEMORY_EMBEDDING_DIMENSIONS": 2}
    report = {
        "state": "quality_pass_with_provider_failures",
        "database": "memory_real_capacity_synthetic",
        "model": "model",
        "dimensions": 2,
    }
    path.write_text(json.dumps(report))
    assert helper["read_vector_seed"](path, profile)["database"] == report["database"]
    for field, value in [("database", "production"), ("model", "other"), ("dimensions", 3)]:
        path.write_text(json.dumps({**report, field: value}))
        with pytest.raises(ValueError, match="Incompatible"):
            helper["read_vector_seed"](path, profile)


def test_seed_helper_and_corpus_are_covered_by_provider_freeze(monkeypatch):
    runner = runpy.run_path(str(Path(__file__).with_name("test_live_lifecycle.py")))
    before = runner["source_fingerprint"]()
    read = Path.read_bytes

    def changed(path):
        return read(path) + b"changed" if path == HELPER else read(path)

    monkeypatch.setattr(Path, "read_bytes", changed)
    assert runner["source_fingerprint"]() != before


@pytest.mark.skipif(
    __import__("os").environ.get("TEST_MEMORY_MONGODB") != "1", reason="Real MongoDB"
)
async def test_fifty_thousand_seed_preserves_source_and_excludes_foreign_rows():
    from datetime import datetime, timezone
    from uuid import uuid4

    from pymongo import MongoClient

    from src.infra.memory.client.native.vector_store import COLLECTION, QdrantVectorIndex
    from src.infra.storage.mongodb import build_mongo_connection_string

    helper = runpy.run_path(str(HELPER))
    mongo = MongoClient(build_mongo_connection_string(), timeoutMS=30000, tz_aware=True)
    name = f"memory_eval_seed_contract_{uuid4().hex}"
    db = mongo[name]
    index = QdrantVectorIndex(location=":memory:", dims=2)
    age = datetime(2026, 4, 1, tzinfo=timezone.utc)
    try:
        db.source.insert_many(
            {
                "memory_id": uuid4().hex,
                "user_id": "source" if position < 50000 else "foreign",
                "scope": "project" if position % 2 else "user",
                "project_id": "alpha" if position % 2 else None,
                "content": f"Synthetic durable fact {position}",
                "embedding": [0.2, 0.8],
                "updated_at": age,
            }
            for position in range(50001)
        )
        result = await helper["seed_vectors"](
            db.source, db.target, "source", "target", {"alpha": "isolated-alpha"}, index, 2
        )
        assert result == {
            "memory_count": 50000,
            "reembedded_seed_vectors": 0,
            "foreign_seed_rows_copied": 0,
        }
        assert db.source.count_documents({"user_id": "source"}) == 50000
        assert db.source.count_documents({"user_id": "foreign"}) == 1
        assert db.target.count_documents({"user_id": {"$ne": "target"}}) == 0
        assert db.target.count_documents({"project_id": "isolated-alpha"}) == 25000
        assert db.target.count_documents({"updated_at": age}) == 50000
        assert (await index._client.count(COLLECTION, exact=True)).count == 50000
        with pytest.raises(ValueError, match="empty target"):
            await helper["seed_vectors"](
                db.source, db.target, "source", "target", {"alpha": "isolated-alpha"}, index, 2
            )
    finally:
        await index.close()
        mongo.drop_database(name)
        mongo.close()


def test_seed_creates_distinct_isolated_mappings_for_all_source_projects():
    from unittest.mock import Mock

    helper = runpy.run_path(str(HELPER))
    source = Mock()
    source.distinct.return_value = [None, "alpha", "capacity-project-0", "capacity-project-1"]
    created = []

    def create(label):
        created.append(label)
        return f"isolated:{label}"

    existing = {"alpha": "existing-alpha"}
    projects = helper["seed_project_map"](source, "source-owner", existing, create)
    assert projects == {
        "alpha": "existing-alpha",
        "capacity-project-0": "isolated:capacity-project-0",
        "capacity-project-1": "isolated:capacity-project-1",
    }
    assert existing == {"alpha": "existing-alpha"}
    assert created == ["capacity-project-0", "capacity-project-1"]
    source.distinct.assert_called_once_with("project_id", {"user_id": "source-owner"})


@pytest.mark.parametrize(
    "fields",
    [
        {"content_storage_mode": "store", "content_store_key": "old-owner-body"},
        {"content_store_key": "old-owner-body"},
        {"storage_mode": "store"},
    ],
)
def test_seed_rejects_store_backed_body_references(fields):
    helper = runpy.run_path(str(HELPER))
    document = {"content": "Inline preview", "embedding": [0.2, 0.8], **fields}
    with pytest.raises(ValueError, match="self-contained inline"):
        helper["map_seed_document"](document, "new-owner", {}, 2)
