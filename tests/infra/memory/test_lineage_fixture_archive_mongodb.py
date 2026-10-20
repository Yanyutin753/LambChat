"""Exercise destructive evaluation staging without provider calls or production data."""

import json
import os
import runpy
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
from pymongo import MongoClient

from src.infra.memory.client.native.content import memory_store_namespace
from src.infra.storage.mongodb import build_mongo_connection_string
from src.infra.storage.mongodb_store import COLLECTION_NAME

RUNNER = Path(__file__).with_name("test_live_lifecycle.py")


@pytest.mark.skipif(os.environ.get("TEST_MEMORY_MONGODB") != "1", reason="Opt-in real MongoDB")
@pytest.mark.parametrize("mode", ["inline", "store", "truncated", "missing"])
def test_archive_prepares_owned_fixture_and_preserves_full_body_and_foreign_data(tmp_path, mode):
    module = runpy.run_path(str(RUNNER.resolve()))
    client = MongoClient(build_mongo_connection_string(), timeoutMS=10000)
    name = f"memory_eval_archive_{uuid4().hex}"
    db = client[name]
    full = (
        "Durable archival shipping condition. " * 100 if mode != "inline" else ""
    ) + "Unique tail: quartz 77."
    namespace = list(memory_store_namespace("owner"))
    foreign_namespace = list(memory_store_namespace("other"))
    try:
        db.native_memories.insert_many(
            [
                {
                    "user_id": "owner",
                    "memory_id": "owned",
                    "revision_id": "original",
                    "content": full[:1200],
                    "content_storage_mode": "inline" if mode == "inline" else "store",
                    "content_store_key": "shared-body" if mode != "inline" else None,
                },
                {"user_id": "other", "memory_id": "foreign", "content": "Another owner's fact."},
            ]
        )
        if mode not in {"inline", "missing"}:
            db[COLLECTION_NAME].insert_one(
                {
                    "_id": {"namespace": namespace, "key": "shared-body"},
                    "namespace": namespace,
                    "key": "shared-body",
                    "value": {"text": full},
                }
            )
        db[COLLECTION_NAME].insert_one(
            {
                "_id": {"namespace": foreign_namespace, "key": "shared-body"},
                "namespace": foreign_namespace,
                "key": "shared-body",
                "value": {"text": "Foreign body."},
            }
        )
        foreign_row = db.native_memories.find_one({"user_id": "other"})
        foreign_body = db[COLLECTION_NAME].find_one({"namespace": foreign_namespace})
        original = db.native_memories.find_one({"user_id": "owner"})
        original_body = db[COLLECTION_NAME].find_one({"namespace": namespace})

        def api(owner, method, path, body=None):
            assert (owner, method, path) == ("a", "GET", "/api/memory/export")
            return {
                "version": 1,
                "memories": [
                    {
                        "memory_id": "owned",
                        "content": full,
                        "content_truncated": mode == "truncated",
                    }
                ],
            }

        evidence = {}
        journal = tmp_path / "archive.json"
        if mode in {"truncated", "missing"}:
            with pytest.raises(ValueError):
                module["archive_controlled_fixture"](api, db, "a", "owner", journal, evidence)
            assert db.native_memories.find_one({"user_id": "owner"}) == original
            assert db[COLLECTION_NAME].find_one({"namespace": namespace}) == original_body
        else:
            module["archive_controlled_fixture"](api, db, "a", "owner", journal, evidence)
            archived = json.loads(journal.read_text())["controlled_legacy_reseed"]
            assert archived["archived_full_export"]["memories"][0]["content"] == full
            if mode == "store":
                assert archived["archived_store_rows"][0]["value"]["text"] == full
            assert db.native_memories.count_documents({"user_id": "owner"}) == 0
            assert db[COLLECTION_NAME].count_documents({"namespace": namespace}) == 0
        assert db.native_memories.find_one({"user_id": "other"}) == foreign_row
        assert db[COLLECTION_NAME].find_one({"namespace": foreign_namespace}) == foreign_body
        assert db.memory_forget_watermarks.count_documents({}) == 0
    finally:
        client.drop_database(name)
        client.close()


def test_archive_refuses_a_non_evaluation_database_before_reading_anything(tmp_path):
    module = runpy.run_path(str(RUNNER.resolve()))
    api = Mock(side_effect=AssertionError("Must not call API"))
    with pytest.raises(ValueError):
        module["archive_controlled_fixture"](
            api, SimpleNamespace(name="production"), "a", "owner", tmp_path / "never.json", {}
        )
    api.assert_not_called()
