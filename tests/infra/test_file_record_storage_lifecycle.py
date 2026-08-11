from __future__ import annotations

import asyncio
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import ANY

import pytest

from src.api import main as api_main
from src.infra.upload import file_record
from src.infra.upload.file_record import AttachmentClaimError, FileRecordStorage


class _IndexCursor:
    def __init__(self, indexes: list[dict]) -> None:
        self._indexes = indexes

    def __aiter__(self):
        self._iterator = iter(self._indexes)
        return self

    async def __anext__(self):
        try:
            return next(self._iterator)
        except StopIteration:
            raise StopAsyncIteration from None


class _LifecycleCollection:
    def __init__(self, indexes: list[dict] | None = None) -> None:
        self.indexes = indexes or []
        self.created_indexes: list[tuple[object, dict]] = []
        self.dropped_indexes: list[str] = []
        self.find_queries: list[dict] = []
        self.find_one_and_update_calls: list[tuple[dict, dict, dict]] = []
        self.update_one_calls: list[tuple[dict, dict]] = []
        self.update_many_calls: list[tuple[dict, dict]] = []
        self.delete_one_calls: list[dict] = []
        self.claim_results: list[dict | None] = []

    def list_indexes(self):
        return _IndexCursor(self.indexes)

    async def create_index(self, keys, **kwargs):
        self.created_indexes.append((keys, kwargs))
        return kwargs.get("name", "generated")

    async def drop_index(self, name: str):
        self.dropped_indexes.append(name)

    async def find_one(self, query: dict):
        self.find_queries.append(query)
        return None

    async def find_one_and_update(self, query: dict, update: dict, **kwargs):
        self.find_one_and_update_calls.append((query, update, kwargs))
        result = self.claim_results.pop(0) if self.claim_results else None
        if isinstance(result, BaseException):
            raise result
        return result

    async def update_one(self, query: dict, update: dict):
        self.update_one_calls.append((query, update))
        return SimpleNamespace(modified_count=1)

    async def update_many(self, query: dict, update: dict):
        self.update_many_calls.append((query, update))
        return SimpleNamespace(modified_count=1)

    async def delete_one(self, query: dict):
        self.delete_one_calls.append(query)
        return SimpleNamespace(deleted_count=1)


async def _noop_async() -> None:
    return None


@pytest.mark.asyncio
async def test_index_migration_creates_owner_hash_unique_index_before_dropping_legacy_hash_index() -> (
    None
):
    collection = _LifecycleCollection(
        [
            {"name": "_id_", "key": {"_id": 1}},
            {"name": "hash_1", "key": {"hash": 1}, "unique": True},
        ]
    )
    storage = FileRecordStorage()
    storage._collection = collection

    await storage.initialize_indexes()

    assert collection.created_indexes[0] == (
        [("uploaded_by", 1), ("hash", 1)],
        {"name": "uploaded_by_hash_unique_idx", "unique": True, "background": True},
    )
    assert collection.dropped_indexes == ["hash_1"]
    assert collection.created_indexes[1] == (
        "key",
        {"unique": True, "background": True},
    )


@pytest.mark.asyncio
async def test_hash_lookup_is_scoped_to_uploaded_by() -> None:
    collection = _LifecycleCollection()
    storage = FileRecordStorage()
    storage._collection = collection
    storage.ensure_indexes_if_needed = _noop_async

    await storage.find_by_hash("same-content", "owner-a")

    assert collection.find_queries == [
        {
            "hash": "same-content",
            "uploaded_by": "owner-a",
            "deleting_at": {"$exists": False},
        }
    ]


@pytest.mark.asyncio
async def test_claim_owned_references_rolls_back_only_prior_claims_when_a_key_is_not_claimable() -> (
    None
):
    collection = _LifecycleCollection()
    collection.claim_results = [{"key": "owned"}, None]
    storage = FileRecordStorage()
    storage._collection = collection
    storage.ensure_indexes_if_needed = _noop_async

    with pytest.raises(AttachmentClaimError) as exc_info:
        await storage.claim_owned_references(["owned", "foreign"], "owner-a")

    assert str(exc_info.value) == "Attachment is unavailable"
    assert [call[0] for call in collection.find_one_and_update_calls] == [
        {"key": "owned", "uploaded_by": "owner-a", "deleting_at": {"$exists": False}},
        {"key": "foreign", "uploaded_by": "owner-a", "deleting_at": {"$exists": False}},
    ]
    assert collection.update_one_calls == []
    rollback_query, rollback_update = collection.update_many_calls[0]
    assert rollback_query == {
        "key": {"$in": ["owned"]},
        "uploaded_by": "owner-a",
        "reference_count": {"$gt": 0},
    }
    assert rollback_update["$inc"] == {"reference_count": -1}
    assert rollback_update["$set"]["cleanup_after"] > rollback_update["$set"][
        "updated_at"
    ] + timedelta(minutes=1)


@pytest.mark.asyncio
async def test_claim_cancellation_rolls_back_prior_owned_keys() -> None:
    collection = _LifecycleCollection()
    collection.claim_results = [{"key": "owned"}, asyncio.CancelledError()]
    storage = FileRecordStorage()
    storage._collection = collection
    storage.ensure_indexes_if_needed = _noop_async

    with pytest.raises(asyncio.CancelledError):
        await storage.claim_owned_references(["owned", "cancelled"], "owner-a")

    assert collection.update_many_calls[0][0] == {
        "key": {"$in": ["owned"]},
        "uploaded_by": "owner-a",
        "reference_count": {"$gt": 0},
    }


@pytest.mark.asyncio
async def test_claim_refreshes_cleanup_deadline_for_reused_zero_reference_record() -> None:
    collection = _LifecycleCollection()
    collection.claim_results = [{"key": "owned"}]
    storage = FileRecordStorage()
    storage._collection = collection
    storage.ensure_indexes_if_needed = _noop_async

    await storage.claim_owned_references(["owned"], "owner-a")

    _query, update, _kwargs = collection.find_one_and_update_calls[0]
    assert update["$set"]["cleanup_after"] > update["$set"]["updated_at"] + timedelta(minutes=1)


@pytest.mark.asyncio
async def test_release_owned_references_is_owner_scoped_positive_and_delays_cleanup() -> None:
    collection = _LifecycleCollection()
    storage = FileRecordStorage()
    storage._collection = collection
    storage.ensure_indexes_if_needed = _noop_async

    released = await storage.release_owned_references(["key-1", "key-1"], "owner-a")

    assert released == 1
    query, update = collection.update_many_calls[0]
    assert query == {
        "key": {"$in": ["key-1"]},
        "uploaded_by": "owner-a",
        "reference_count": {"$gt": 0},
    }
    assert update["$inc"] == {"reference_count": -1}
    assert update["$set"]["cleanup_after"] > update["$set"]["updated_at"] + timedelta(minutes=1)


@pytest.mark.asyncio
async def test_release_reference_counts_clamps_each_key_and_delays_only_zero_records() -> None:
    class _CountedReleaseCollection(_LifecycleCollection):
        def __init__(self) -> None:
            super().__init__()
            self.records = {
                "key-a": {"key": "key-a", "reference_count": 2, "cleanup_after": "old-a"},
                "key-b": {"key": "key-b", "reference_count": 5, "cleanup_after": "old-b"},
                "tombstoned": {
                    "key": "tombstoned",
                    "reference_count": 4,
                    "cleanup_after": "old-t",
                    "deleting_at": "reserved",
                },
            }

        async def find_one_and_update(self, query: dict, update: list[dict], **kwargs):
            self.find_one_and_update_calls.append((query, update, kwargs))
            record = self.records.get(query["key"])
            if record is None or "deleting_at" in record:
                return None

            count_expression = update[0]["$set"]["reference_count"]
            decrement = count_expression["$max"][1]["$subtract"][1]
            record["reference_count"] = max(0, record["reference_count"] - decrement)
            record["updated_at"] = update[0]["$set"]["updated_at"]
            cleanup_expression = update[1]["$set"]["cleanup_after"]
            if record["reference_count"] == 0:
                record["cleanup_after"] = cleanup_expression["$cond"][1]
            return record.copy()

    collection = _CountedReleaseCollection()
    storage = FileRecordStorage()
    storage._collection = collection
    storage.ensure_indexes_if_needed = _noop_async

    released = await storage.release_reference_counts(
        {" key-a ": 3, "key-b": 2, "tombstoned": 1, "missing": 4, "": 1, "skip": 0},
        operation_id="clear-1",
        uploaded_by="owner-a",
    )

    assert released == 2
    assert collection.records["key-a"]["reference_count"] == 0
    assert collection.records["key-a"]["cleanup_after"] > collection.records["key-a"][
        "updated_at"
    ] + timedelta(minutes=1)
    assert collection.records["key-b"]["reference_count"] == 3
    assert collection.records["key-b"]["cleanup_after"] == "old-b"
    assert collection.records["tombstoned"] == {
        "key": "tombstoned",
        "reference_count": 4,
        "cleanup_after": "old-t",
        "deleting_at": "reserved",
    }
    assert [call[0] for call in collection.find_one_and_update_calls] == [
        {
            "key": "key-a",
            "uploaded_by": "owner-a",
            "deleting_at": {"$exists": False},
            "applied_release_operations": {"$ne": "clear-1"},
        },
        {
            "key": "key-b",
            "uploaded_by": "owner-a",
            "deleting_at": {"$exists": False},
            "applied_release_operations": {"$ne": "clear-1"},
        },
        {
            "key": "tombstoned",
            "uploaded_by": "owner-a",
            "deleting_at": {"$exists": False},
            "applied_release_operations": {"$ne": "clear-1"},
        },
        {
            "key": "missing",
            "uploaded_by": "owner-a",
            "deleting_at": {"$exists": False},
            "applied_release_operations": {"$ne": "clear-1"},
        },
    ]
    assert collection.find_one_and_update_calls[0][1][0]["$set"]["reference_count"] == {
        "$max": [0, {"$subtract": [{"$ifNull": ["$reference_count", 0]}, 3]}]
    }


@pytest.mark.asyncio
async def test_release_reference_counts_retries_partial_failure_without_double_decrement() -> None:
    class _RetryCollection(_LifecycleCollection):
        def __init__(self) -> None:
            super().__init__()
            self.records = {
                "key-a": {"reference_count": 2, "applied_release_operations": []},
                "key-b": {"reference_count": 2, "applied_release_operations": []},
            }
            self.fail_key_b_once = True

        async def find_one_and_update(self, query: dict, update: list[dict], **kwargs):
            key = query["key"]
            if key == "key-b" and self.fail_key_b_once:
                self.fail_key_b_once = False
                raise RuntimeError("write interrupted")
            record = self.records[key]
            operation_id = query["applied_release_operations"]["$ne"]
            if operation_id in record["applied_release_operations"]:
                return None
            decrement = update[0]["$set"]["reference_count"]["$max"][1]["$subtract"][1]
            record["reference_count"] = max(0, record["reference_count"] - decrement)
            record["applied_release_operations"].append(operation_id)
            return record.copy()

    collection = _RetryCollection()
    storage = FileRecordStorage()
    storage._collection = collection
    storage.ensure_indexes_if_needed = _noop_async

    with pytest.raises(RuntimeError, match="write interrupted"):
        await storage.release_reference_counts(
            {"key-a": 1, "key-b": 1}, operation_id="clear-1", uploaded_by="owner-a"
        )

    released = await storage.release_reference_counts(
        {"key-a": 1, "key-b": 1}, operation_id="clear-1", uploaded_by="owner-a"
    )

    assert released == 1
    assert collection.records == {
        "key-a": {"reference_count": 1, "applied_release_operations": ["clear-1"]},
        "key-b": {"reference_count": 1, "applied_release_operations": ["clear-1"]},
    }


@pytest.mark.asyncio
async def test_release_reference_counts_is_scoped_to_the_session_owner() -> None:
    collection = _LifecycleCollection()
    storage = FileRecordStorage()
    storage._collection = collection
    storage.ensure_indexes_if_needed = _noop_async

    await storage.release_reference_counts(
        {"key-a": 1}, operation_id="clear-1", uploaded_by="owner-a"
    )

    assert collection.find_one_and_update_calls[0][0]["uploaded_by"] == "owner-a"


@pytest.mark.asyncio
async def test_schedule_owned_zero_reference_cleanup_never_matches_foreign_or_referenced_records() -> (
    None
):
    collection = _LifecycleCollection()
    storage = FileRecordStorage()
    storage._collection = collection
    storage.ensure_indexes_if_needed = _noop_async

    await storage.schedule_owned_cleanup("key-a", "owner-a")

    assert collection.find_one_and_update_calls[0][0] == {
        "key": "key-a",
        "uploaded_by": "owner-a",
        "reference_count": 0,
        "deleting_at": {"$exists": False},
    }


@pytest.mark.asyncio
async def test_tombstone_cleanup_finalizes_only_the_owned_tombstoned_record() -> None:
    tombstone = object()
    record = {"key": "key-a", "uploaded_by": "owner-a", "deleting_at": tombstone}
    collection = _LifecycleCollection()
    collection.claim_results = [record, None]
    storage = FileRecordStorage()
    storage._collection = collection
    storage.ensure_indexes_if_needed = _noop_async

    claimed = await storage.tombstone_cleanup_batch(limit=2)
    finalized = await storage.finalize_tombstone_cleanup(record)

    assert claimed == [record]
    assert collection.find_one_and_update_calls[0][0]["reference_count"] == 0
    assert "$lte" in collection.find_one_and_update_calls[0][0]["cleanup_after"]
    assert collection.find_one_and_update_calls[0][0]["deleting_at"] == {"$exists": False}
    assert finalized is True
    assert collection.delete_one_calls == [
        {"key": "key-a", "uploaded_by": "owner-a", "deleting_at": tombstone}
    ]


@pytest.mark.asyncio
async def test_object_delete_failure_clears_the_exact_tombstone_for_retry() -> None:
    tombstone = object()
    record = {"key": "key-a", "uploaded_by": "owner-a", "deleting_at": tombstone}
    collection = _LifecycleCollection()
    storage = FileRecordStorage()
    storage._collection = collection
    storage.ensure_indexes_if_needed = _noop_async

    async def _tombstone_batch():
        return [record]

    class _FailingObjects:
        async def delete_file(self, key: str) -> None:
            assert key == "key-a"
            raise RuntimeError("object store unavailable")

    storage.tombstone_cleanup_batch = _tombstone_batch

    deleted = await storage.cleanup_scheduled_records(_FailingObjects())

    assert deleted == 0
    assert collection.update_one_calls == [
        (
            {"key": "key-a", "uploaded_by": "owner-a", "deleting_at": tombstone},
            {"$unset": {"deleting_at": ""}, "$set": {"updated_at": ANY}},
        )
    ]


@pytest.mark.asyncio
async def test_startup_registers_and_awaits_strict_file_record_index_migration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    class _Storage:
        async def initialize_indexes(self) -> None:
            calls.append("initialized")

    monkeypatch.setattr(file_record, "FileRecordStorage", _Storage)

    initializers = dict(api_main._startup_index_initializers())
    await initializers["file_record_storage"]()

    assert calls == ["initialized"]
