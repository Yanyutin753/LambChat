from __future__ import annotations

import asyncio
from copy import deepcopy
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import ANY
from uuid import UUID

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


class _DelayedScheduledTaskReferenceCollection:
    def __init__(self, task_id: str) -> None:
        self.task_id = task_id
        self.record: dict = {
            "key": "key-a",
            "uploaded_by": "owner-a",
            "reference_count": 1,
            "scheduled_task_reference_ids": [task_id],
            "scheduled_task_reference_generations": [{"task_id": task_id, "generation": 1}],
        }
        self.stale_release_started = asyncio.Event()
        self.release_stale_write = asyncio.Event()
        self.delayed_commands: list[asyncio.Task[dict | None]] = []

    def _generation(self) -> int | None:
        for lease in self.record["scheduled_task_reference_generations"]:
            if lease["task_id"] == self.task_id:
                return int(lease["generation"])
        return None

    async def find_one_and_update(self, query: dict, update: list[dict], **_kwargs):
        generation_match = query.get("scheduled_task_reference_generations")
        is_release = isinstance(generation_match, dict) and "$elemMatch" in generation_match
        requested_generation = (
            int(generation_match["$elemMatch"]["generation"])
            if is_release
            else int(
                update[0]["$set"]["scheduled_task_reference_generations"]["$concatArrays"][1][0][
                    "generation"
                ]
            )
        )

        async def _apply() -> dict | None:
            if is_release and requested_generation == 1:
                self.stale_release_started.set()
                await self.release_stale_write.wait()
            current_generation = self._generation()
            if is_release:
                if current_generation != requested_generation:
                    return None
                previous = dict(self.record)
                self.record["scheduled_task_reference_ids"] = []
                self.record["scheduled_task_reference_generations"] = []
                self.record["reference_count"] = 0
                return previous
            if current_generation is not None and current_generation > requested_generation:
                return None
            previous = dict(self.record)
            self.record["scheduled_task_reference_generations"] = [
                {"task_id": self.task_id, "generation": requested_generation}
            ]
            return previous

        if is_release and requested_generation == 1:
            command = asyncio.create_task(_apply())
            self.delayed_commands.append(command)
            return await asyncio.shield(command)
        return await _apply()


class _DelayedScheduledTaskClaimCollection:
    def __init__(
        self,
        task_id: str,
        *,
        live_generation: int | None = None,
        tombstone_generation: int | None = None,
        delay_generation: int | None = None,
    ) -> None:
        generation = live_generation or tombstone_generation
        self.task_id = task_id
        self.record: dict = {
            "key": "key-a",
            "uploaded_by": "owner-a",
            "reference_count": int(live_generation is not None),
            "scheduled_task_reference_ids": [task_id] if live_generation else [],
            "scheduled_task_reference_generations": (
                [{"task_id": task_id, "generation": generation}] if generation is not None else []
            ),
        }
        self.delay_generation = delay_generation
        self.deleted = False
        self.stale_claim_started = asyncio.Event()
        self.release_stale_claim = asyncio.Event()
        self.delayed_commands: list[asyncio.Task[dict | None]] = []
        self.find_one_and_update_options: list[dict] = []

    def _generation(self) -> int | None:
        for lease in self.record["scheduled_task_reference_generations"]:
            if lease["task_id"] == self.task_id:
                return int(lease["generation"])
        return None

    def _is_live(self) -> bool:
        return self.task_id in self.record["scheduled_task_reference_ids"]

    @staticmethod
    def _requested_generation(
        query: dict,
        state: dict,
        *,
        is_release: bool,
    ) -> int:
        if is_release:
            return int(query["scheduled_task_reference_generations"]["$elemMatch"]["generation"])
        generation = _ManyScheduledTaskFenceCollection._find_generation(state)
        assert generation is not None
        return generation

    async def find_one_and_update(self, query: dict, update: list[dict], **_kwargs):
        self.find_one_and_update_options.append(dict(_kwargs))
        state = update[0]["$set"]
        reference_ids = state.get("scheduled_task_reference_ids", {})
        is_claim = isinstance(reference_ids, dict) and "$setUnion" in reference_ids
        is_release = isinstance(reference_ids, dict) and "$setDifference" in reference_ids
        requested_generation = self._requested_generation(
            query,
            state,
            is_release=is_release,
        )

        async def _apply() -> dict | None:
            if is_claim and requested_generation == self.delay_generation:
                self.stale_claim_started.set()
                await self.release_stale_claim.wait()
            if self.deleted:
                return None

            current_generation = self._generation()
            high_water = max(
                int(self.record.get("scheduled_task_generation_high_water", 0)),
                max(
                    (
                        int(lease["generation"])
                        for lease in self.record["scheduled_task_reference_generations"]
                    ),
                    default=0,
                ),
            )
            compact = "scheduled_task_generation_high_water" in state
            if compact:
                if requested_generation < high_water:
                    return None
                if (
                    is_claim
                    and requested_generation == high_water
                    and not (self._is_live() and current_generation == requested_generation)
                ):
                    return None
            elif current_generation is not None and current_generation > requested_generation:
                return None

            previous = deepcopy(self.record)
            if is_claim:
                # The high-water claim query adds an explicit equal-generation
                # live-reference branch. Without it, an equal tombstone matches.
                if (
                    current_generation == requested_generation
                    and not self._is_live()
                    and "$and" in query
                ):
                    return None
                if not self._is_live():
                    self.record["reference_count"] += 1
                    self.record["scheduled_task_reference_ids"] = [self.task_id]
                self.record["scheduled_task_reference_generations"] = [
                    {"task_id": self.task_id, "generation": requested_generation}
                ]
                if compact:
                    self.record["scheduled_task_generation_high_water"] = max(
                        high_water, requested_generation
                    )
                return previous

            if is_release:
                if not self._is_live() or current_generation != requested_generation:
                    return None
                self.record["reference_count"] -= 1
                self.record["scheduled_task_reference_ids"] = []
                if "scheduled_task_reference_generations" in state:
                    self.record["scheduled_task_reference_generations"] = []
                if compact:
                    self.record["scheduled_task_generation_high_water"] = max(
                        high_water, requested_generation
                    )
                return previous

            if query.get("scheduled_task_reference_ids") == self.task_id and not self._is_live():
                return None
            self.record["scheduled_task_reference_generations"] = (
                [{"task_id": self.task_id, "generation": requested_generation}]
                if self._is_live() or not compact
                else []
            )
            if compact:
                self.record["scheduled_task_generation_high_water"] = max(
                    high_water, requested_generation
                )
            return previous

        if is_claim and requested_generation == self.delay_generation:
            command = asyncio.create_task(_apply())
            self.delayed_commands.append(command)
            return await asyncio.shield(command)
        return await _apply()


class _ManyScheduledTaskFenceCollection:
    """Small state model that distinguishes legacy tombstones from compact fences."""

    def __init__(self) -> None:
        self.record: dict = {
            "key": "key-a",
            "uploaded_by": "owner-a",
            "reference_count": 0,
            "scheduled_task_reference_ids": [],
            "scheduled_task_reference_generations": [],
        }

    @staticmethod
    def _find_generation(value: object) -> int | None:
        if isinstance(value, dict):
            generation = value.get("generation")
            if isinstance(generation, int):
                return generation
            for nested in value.values():
                found = _ManyScheduledTaskFenceCollection._find_generation(nested)
                if found is not None:
                    return found
        if isinstance(value, list):
            for nested in value:
                found = _ManyScheduledTaskFenceCollection._find_generation(nested)
                if found is not None:
                    return found
        return None

    async def find_one_and_update(self, query: dict, update: list[dict], **_kwargs):
        state = update[0]["$set"]
        task_id = query.get("scheduled_task_reference_ids")
        is_release = isinstance(task_id, str)
        if not is_release:
            task_id = self._find_task_id(state)
        generation = self._find_generation(query if is_release else state)
        assert isinstance(task_id, str) and isinstance(generation, int)

        live_ids = self.record["scheduled_task_reference_ids"]
        leases = self.record["scheduled_task_reference_generations"]
        live_generation = next(
            (lease["generation"] for lease in leases if lease["task_id"] == task_id),
            None,
        )
        compact = "scheduled_task_generation_high_water" in state
        high_water = int(self.record.get("scheduled_task_generation_high_water", 0))
        previous = deepcopy(self.record)

        if is_release:
            if task_id not in live_ids or live_generation != generation:
                return None
            live_ids.remove(task_id)
            self.record["reference_count"] -= 1
            if compact:
                self.record["scheduled_task_reference_generations"] = [
                    lease for lease in leases if lease["task_id"] != task_id
                ]
                self.record["scheduled_task_generation_high_water"] = max(high_water, generation)
            return previous

        is_claim = "$setUnion" in state.get("scheduled_task_reference_ids", {})
        if compact:
            if generation < high_water:
                return None
            if generation == high_water and not (
                task_id in live_ids and live_generation == generation
            ):
                return None
        elif live_generation is not None and live_generation > generation:
            return None

        if is_claim and task_id not in live_ids:
            live_ids.append(task_id)
            self.record["reference_count"] += 1
        self.record["scheduled_task_reference_generations"] = [
            lease for lease in leases if lease["task_id"] != task_id
        ]
        if is_claim or not compact:
            self.record["scheduled_task_reference_generations"].append(
                {"task_id": task_id, "generation": generation}
            )
        if compact:
            self.record["scheduled_task_generation_high_water"] = max(high_water, generation)
        return previous

    @classmethod
    def _find_task_id(cls, value: object) -> str | None:
        if isinstance(value, dict):
            task_id = value.get("task_id")
            if isinstance(task_id, str):
                return task_id
            for nested in value.values():
                found = cls._find_task_id(nested)
                if found is not None:
                    return found
        if isinstance(value, list):
            for nested in value:
                found = cls._find_task_id(nested)
                if found is not None:
                    return found
        return None


class _ReleaseMarkerCleanupCollection:
    def __init__(self, *, lose_reply: bool = False) -> None:
        self.records: dict[str, dict] = {
            "key-a": {
                "key": "key-a",
                "uploaded_by": "owner-a",
                "reference_count": 1,
                "session_release_operations": [],
                "session_release_epoch_high_water": 0,
            }
        }
        self.lose_reply = lose_reply

    @staticmethod
    def _operation(value: object) -> dict | None:
        if isinstance(value, dict):
            if isinstance(value.get("operation_id"), str) and isinstance(value.get("epoch"), int):
                return value
            for nested in value.values():
                found = _ReleaseMarkerCleanupCollection._operation(nested)
                if found is not None:
                    return found
        elif isinstance(value, list):
            for nested in value:
                found = _ReleaseMarkerCleanupCollection._operation(nested)
                if found is not None:
                    return found
        return None

    @staticmethod
    def _decrement(value: object) -> int | None:
        if isinstance(value, dict):
            subtract = value.get("$subtract")
            if isinstance(subtract, list) and len(subtract) == 2 and isinstance(subtract[1], int):
                return subtract[1]
            for nested in value.values():
                found = _ReleaseMarkerCleanupCollection._decrement(nested)
                if found is not None:
                    return found
        elif isinstance(value, list):
            for nested in value:
                found = _ReleaseMarkerCleanupCollection._decrement(nested)
                if found is not None:
                    return found
        return None

    async def find_one_and_update(self, query: dict, update: list[dict], **_kwargs):
        record = self.records.get(query["key"])
        if record is None or "deleting_at" in record:
            return None
        previous = deepcopy(record)
        exact = query.get("session_release_operations", {}).get("$elemMatch")
        if exact is not None:
            operation = next(
                (
                    item
                    for item in record["session_release_operations"]
                    if item["operation_id"] == exact["operation_id"]
                    and item["epoch"] == exact["epoch"]
                ),
                None,
            )
            if operation is None:
                return None
            if not operation["applied"]:
                decrement = self._decrement(update)
                assert decrement is not None
                record["reference_count"] = max(0, record["reference_count"] - decrement)
                operation["applied"] = True
            return previous

        incoming = self._operation(update)
        assert incoming is not None
        current = next(
            (
                item
                for item in record["session_release_operations"]
                if item["operation_id"] == incoming["operation_id"]
            ),
            None,
        )
        if current is None:
            if incoming["epoch"] <= record.get("session_release_epoch_high_water", 0):
                return None
            record["session_release_operations"].append({**incoming, "applied": False})
        elif current["epoch"] <= incoming["epoch"]:
            current["epoch"] = incoming["epoch"]
        else:
            return None
        return previous

    async def update_many(self, query: dict, _update: object):
        exact = query["session_release_operations"]["$elemMatch"]
        for key in query["key"]["$in"]:
            record = self.records.get(key)
            if record is None:
                continue
            record["session_release_operations"] = [
                operation
                for operation in record["session_release_operations"]
                if not (
                    operation["operation_id"] == exact["operation_id"]
                    and operation["epoch"] == exact["epoch"]
                    and operation["applied"] is True
                )
            ]
            record["session_release_epoch_high_water"] = max(
                record.get("session_release_epoch_high_water", 0), exact["epoch"]
            )
        if self.lose_reply:
            self.lose_reply = False
            raise ConnectionError("marker cleanup reply lost")
        return SimpleNamespace(modified_count=1)

    async def count_documents(self, query: dict, **_kwargs) -> int:
        exact = query["session_release_operations"]["$elemMatch"]
        return int(
            any(
                any(
                    operation["operation_id"] == exact["operation_id"]
                    and operation["epoch"] == exact["epoch"]
                    and operation["applied"] is True
                    for operation in self.records.get(key, {}).get("session_release_operations", [])
                )
                for key in query["key"]["$in"]
            )
        )


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
    collection = _ReleaseMarkerCleanupCollection()
    collection.records["key-a"]["reference_count"] = 2
    collection.records["key-b"] = deepcopy(collection.records["key-a"])
    collection.records["key-b"].update({"key": "key-b", "reference_count": 5})
    storage = FileRecordStorage()
    storage._collection = collection
    storage.ensure_indexes_if_needed = _noop_async

    assert await storage.adopt_release_operation_epoch(
        ["key-a", "key-b"],
        operation_id="clear-1",
        owner_epoch=7,
        uploaded_by="owner-a",
    )
    released = await storage.release_reference_counts(
        {" key-a ": 3, "key-b": 2, "": 1, "skip": 0},
        operation_id="clear-1",
        uploaded_by="owner-a",
        owner_epoch=7,
    )

    assert released == 2
    assert collection.records["key-a"]["reference_count"] == 0
    assert collection.records["key-b"]["reference_count"] == 3


@pytest.mark.asyncio
async def test_release_reference_counts_retries_partial_failure_without_double_decrement() -> None:
    class _RetryCollection(_ReleaseMarkerCleanupCollection):
        def __init__(self) -> None:
            super().__init__()
            self.records["key-a"]["reference_count"] = 2
            self.records["key-b"] = deepcopy(self.records["key-a"])
            self.records["key-b"]["key"] = "key-b"
            self.fail_key_b_once = True

        async def find_one_and_update(self, query: dict, update: list[dict], **kwargs):
            if (
                query["key"] == "key-b"
                and "session_release_operations" in query
                and self.fail_key_b_once
            ):
                self.fail_key_b_once = False
                raise RuntimeError("write interrupted")
            return await super().find_one_and_update(query, update, **kwargs)

    collection = _RetryCollection()
    storage = FileRecordStorage()
    storage._collection = collection
    storage.ensure_indexes_if_needed = _noop_async

    assert await storage.adopt_release_operation_epoch(
        ["key-a", "key-b"], operation_id="clear-1", owner_epoch=7, uploaded_by="owner-a"
    )
    with pytest.raises(RuntimeError, match="write interrupted"):
        await storage.release_reference_counts(
            {"key-a": 1, "key-b": 1},
            operation_id="clear-1",
            uploaded_by="owner-a",
            owner_epoch=7,
        )

    released = await storage.release_reference_counts(
        {"key-a": 1, "key-b": 1},
        operation_id="clear-1",
        uploaded_by="owner-a",
        owner_epoch=7,
    )

    assert released == 1
    assert collection.records["key-a"]["reference_count"] == 1
    assert collection.records["key-b"]["reference_count"] == 1


@pytest.mark.asyncio
async def test_release_reference_counts_is_scoped_to_the_session_owner() -> None:
    collection = _LifecycleCollection()
    storage = FileRecordStorage()
    storage._collection = collection
    storage.ensure_indexes_if_needed = _noop_async

    collection.claim_results = [{"key": "key-a"}]
    await storage.release_reference_counts(
        {"key-a": 1},
        operation_id="clear-1",
        uploaded_by="owner-a",
        owner_epoch=7,
    )

    assert collection.find_one_and_update_calls[0][0]["uploaded_by"] == "owner-a"


@pytest.mark.asyncio
async def test_scheduled_task_reference_claim_increments_once_for_retry() -> None:
    task_id = "2f191ddb-b029-4a2e-a66e-8b292fa2401f"
    collection = _LifecycleCollection()
    collection.claim_results = [
        {
            "key": "key-a",
            "uploaded_by": "owner-a",
            "reference_count": 0,
            "scheduled_task_reference_ids": [],
        },
        {
            "key": "key-a",
            "uploaded_by": "owner-a",
            "reference_count": 1,
            "scheduled_task_reference_ids": [task_id],
        },
    ]
    storage = FileRecordStorage()
    storage._collection = collection
    storage.ensure_indexes_if_needed = _noop_async

    first_claim = await storage.claim_scheduled_task_references(
        ["key-a"], "owner-a", task_id, mutation_generation=3
    )
    retry_claim = await storage.claim_scheduled_task_references(
        ["key-a"], "owner-a", task_id, mutation_generation=3
    )

    assert first_claim == ["key-a"]
    assert retry_claim == []
    for query, update, _kwargs in collection.find_one_and_update_calls:
        assert query["key"] == "key-a"
        assert query["uploaded_by"] == "owner-a"
        assert query["deleting_at"] == {"$exists": False}
        assert query["$and"][0]["$or"] == [
            {"scheduled_task_reference_ids": task_id},
            {
                "$expr": {
                    "$lt": [
                        {"$size": {"$ifNull": ["$scheduled_task_reference_ids", []]}},
                        1000,
                    ]
                }
            },
        ]
        generation_gate = query["$and"][1]["$or"]
        assert generation_gate[0]["$expr"]["$gt"][0] == 3
        assert generation_gate[1] == {
            "scheduled_task_reference_ids": task_id,
            "scheduled_task_reference_generations": {
                "$elemMatch": {"task_id": task_id, "generation": 3}
            },
        }
        assert update[0]["$set"]["reference_count"] == {
            "$cond": [
                {
                    "$in": [
                        task_id,
                        {"$ifNull": ["$scheduled_task_reference_ids", []]},
                    ]
                },
                {"$ifNull": ["$reference_count", 0]},
                {"$add": [{"$ifNull": ["$reference_count", 0]}, 1]},
            ]
        }
        assert update[0]["$set"]["scheduled_task_reference_generations"] == {
            "$concatArrays": [
                {
                    "$filter": {
                        "input": ANY,
                        "as": "lease",
                        "cond": {"$ne": ["$$lease.task_id", task_id]},
                    }
                },
                [{"task_id": task_id, "generation": 3}],
            ]
        }
        assert update[0]["$set"]["scheduled_task_generation_high_water"]["$max"][1] == 3


@pytest.mark.asyncio
async def test_scheduled_task_reference_release_is_idempotent_and_clamped() -> None:
    task_id = "2f191ddb-b029-4a2e-a66e-8b292fa2401f"
    collection = _LifecycleCollection()
    collection.claim_results = [
        {
            "key": "key-a",
            "uploaded_by": "owner-a",
            "reference_count": 0,
            "scheduled_task_reference_ids": [task_id],
        },
        None,
    ]
    storage = FileRecordStorage()
    storage._collection = collection
    storage.ensure_indexes_if_needed = _noop_async

    first_release = await storage.release_scheduled_task_references(
        ["key-a"], "owner-a", task_id, mutation_generation=3
    )
    retry_release = await storage.release_scheduled_task_references(
        ["key-a"], "owner-a", task_id, mutation_generation=3
    )

    assert first_release == 1
    assert retry_release == 0
    query, update, _kwargs = collection.find_one_and_update_calls[0]
    assert query == {
        "key": "key-a",
        "uploaded_by": "owner-a",
        "deleting_at": {"$exists": False},
        "scheduled_task_reference_ids": task_id,
        "scheduled_task_reference_generations": {
            "$elemMatch": {"task_id": task_id, "generation": 3}
        },
    }
    assert update[0]["$set"]["reference_count"] == {
        "$max": [
            0,
            {"$subtract": [{"$ifNull": ["$reference_count", 0]}, 1]},
        ]
    }
    assert update[0]["$set"]["scheduled_task_reference_ids"] == {
        "$setDifference": [
            {"$ifNull": ["$scheduled_task_reference_ids", []]},
            [task_id],
        ]
    }
    assert update[0]["$set"]["scheduled_task_reference_generations"]["$filter"]["cond"] == {
        "$ne": ["$$lease.task_id", task_id]
    }
    assert update[0]["$set"]["scheduled_task_generation_high_water"]["$max"][1] == 3
    assert update[1]["$set"]["cleanup_after"]["$cond"][0] == {"$eq": ["$reference_count", 0]}


@pytest.mark.asyncio
async def test_successor_generation_fences_stale_scheduled_task_release() -> None:
    task_id = "2f191ddb-b029-4a2e-a66e-8b292fa2401f"
    collection = _DelayedScheduledTaskReferenceCollection(task_id)
    storage = FileRecordStorage()
    storage._collection = collection
    storage.ensure_indexes_if_needed = _noop_async

    stale_release = asyncio.create_task(
        storage.release_scheduled_task_references(
            ["key-a"],
            "owner-a",
            task_id,
            mutation_generation=1,
        )
    )
    await asyncio.sleep(0)
    if stale_release.done():
        await stale_release
    await asyncio.wait_for(collection.stale_release_started.wait(), timeout=1)
    stale_release.cancel()
    with pytest.raises(asyncio.CancelledError):
        await stale_release

    adopted = await storage.claim_scheduled_task_references(
        ["key-a"],
        "owner-a",
        task_id,
        mutation_generation=2,
    )
    assert adopted == []

    collection.release_stale_write.set()
    await asyncio.gather(*collection.delayed_commands)

    assert collection.record["scheduled_task_reference_ids"] == [task_id]
    assert collection.record["scheduled_task_reference_generations"] == [
        {"task_id": task_id, "generation": 2}
    ]
    assert collection.record["reference_count"] == 1


@pytest.mark.asyncio
async def test_successor_tombstone_fences_claim_that_finishes_after_marker_clear() -> None:
    task_id = "2f191ddb-b029-4a2e-a66e-8b292fa2401f"
    collection = _DelayedScheduledTaskClaimCollection(
        task_id,
        delay_generation=1,
    )
    storage = FileRecordStorage()
    storage._collection = collection
    storage.ensure_indexes_if_needed = _noop_async

    stale_claim = asyncio.create_task(
        storage.claim_scheduled_task_references(
            ["key-a"],
            "owner-a",
            task_id,
            mutation_generation=1,
        )
    )
    await asyncio.wait_for(collection.stale_claim_started.wait(), timeout=1)
    stale_claim.cancel()
    with pytest.raises(asyncio.CancelledError):
        await stale_claim

    adopted = await storage.adopt_scheduled_task_reference_generation(
        ["key-a"],
        "owner-a",
        task_id,
        mutation_generation=2,
    )
    released = await storage.release_scheduled_task_references(
        ["key-a"],
        "owner-a",
        task_id,
        mutation_generation=2,
    )
    task_marker_cleared = True

    collection.release_stale_claim.set()
    await asyncio.gather(*collection.delayed_commands)

    assert adopted == 1
    assert released == 0
    assert task_marker_cleared is True
    assert collection.record["scheduled_task_reference_ids"] == []
    assert collection.record["scheduled_task_reference_generations"] == []
    assert collection.record["scheduled_task_generation_high_water"] == 2
    assert collection.record["reference_count"] == 0


@pytest.mark.asyncio
async def test_deleted_file_record_is_not_recreated_by_delayed_claim() -> None:
    task_id = "2f191ddb-b029-4a2e-a66e-8b292fa2401f"
    collection = _DelayedScheduledTaskClaimCollection(
        task_id,
        delay_generation=1,
    )
    storage = FileRecordStorage()
    storage._collection = collection
    storage.ensure_indexes_if_needed = _noop_async

    stale_claim = asyncio.create_task(
        storage.claim_scheduled_task_references(
            ["key-a"],
            "owner-a",
            task_id,
            mutation_generation=1,
        )
    )
    await asyncio.wait_for(collection.stale_claim_started.wait(), timeout=1)
    stale_claim.cancel()
    with pytest.raises(asyncio.CancelledError):
        await stale_claim

    collection.deleted = True
    collection.record.clear()
    collection.release_stale_claim.set()
    await asyncio.gather(*collection.delayed_commands)

    assert collection.record == {}
    assert all(
        options.get("upsert") is not True for options in collection.find_one_and_update_options
    )


@pytest.mark.asyncio
async def test_scheduled_task_release_retains_generation_high_water() -> None:
    task_id = "2f191ddb-b029-4a2e-a66e-8b292fa2401f"
    collection = _DelayedScheduledTaskClaimCollection(
        task_id,
        live_generation=2,
    )
    storage = FileRecordStorage()
    storage._collection = collection
    storage.ensure_indexes_if_needed = _noop_async

    released = await storage.release_scheduled_task_references(
        ["key-a"],
        "owner-a",
        task_id,
        mutation_generation=2,
    )

    assert released == 1
    assert collection.record["scheduled_task_reference_ids"] == []
    assert collection.record["scheduled_task_reference_generations"] == []
    assert collection.record["scheduled_task_generation_high_water"] == 2
    assert collection.record["reference_count"] == 0


@pytest.mark.asyncio
async def test_many_released_task_fences_compact_to_one_global_high_water() -> None:
    collection = _ManyScheduledTaskFenceCollection()
    storage = FileRecordStorage()
    storage._collection = collection
    storage.ensure_indexes_if_needed = _noop_async

    task_ids = [str(UUID(int=index + 1)) for index in range(1100)]
    for epoch, task_id in enumerate(task_ids, start=1):
        assert await storage.claim_scheduled_task_references(
            ["key-a"], "owner-a", task_id, mutation_generation=epoch
        ) == ["key-a"]
        assert (
            await storage.release_scheduled_task_references(
                ["key-a"], "owner-a", task_id, mutation_generation=epoch
            )
            == 1
        )

    assert collection.record["scheduled_task_reference_ids"] == []
    assert collection.record["scheduled_task_reference_generations"] == []
    assert collection.record["scheduled_task_generation_high_water"] == 1100
    with pytest.raises(AttachmentClaimError):
        await storage.claim_scheduled_task_references(
            ["key-a"], "owner-a", task_ids[0], mutation_generation=1
        )
    assert await storage.claim_scheduled_task_references(
        ["key-a"],
        "owner-a",
        str(UUID(int=2000)),
        mutation_generation=1101,
    ) == ["key-a"]


@pytest.mark.asyncio
async def test_completed_release_operation_markers_remain_bounded_and_retry_reply_loss() -> None:
    collection = _ReleaseMarkerCleanupCollection()
    storage = FileRecordStorage()
    storage._collection = collection
    storage.ensure_indexes_if_needed = _noop_async
    collection.records["key-a"]["reference_count"] = 1200

    for index in range(1100):
        operation_id = f"clear-{index}"
        owner_epoch = index + 1
        assert await storage.adopt_release_operation_epoch(
            ["key-a"],
            operation_id=operation_id,
            owner_epoch=owner_epoch,
            uploaded_by="owner-a",
        )
        await storage.release_reference_counts(
            {"key-a": 1},
            operation_id=operation_id,
            owner_epoch=owner_epoch,
            uploaded_by="owner-a",
        )
        assert await storage.forget_release_operation(
            ["key-a"],
            operation_id=operation_id,
            owner_epoch=owner_epoch,
            uploaded_by="owner-a",
        )
    assert collection.records["key-a"]["session_release_operations"] == []
    assert collection.records["key-a"]["session_release_epoch_high_water"] == 1100
    assert not await storage.adopt_release_operation_epoch(
        ["key-a"], operation_id="clear-0", owner_epoch=1, uploaded_by="owner-a"
    )
    assert (
        await storage.release_reference_counts(
            {"key-a": 1},
            operation_id="clear-0",
            owner_epoch=1,
            uploaded_by="owner-a",
        )
        == 0
    )

    assert await storage.adopt_release_operation_epoch(
        ["key-a"], operation_id="reply-lost", owner_epoch=1101, uploaded_by="owner-a"
    )
    await storage.release_reference_counts(
        {"key-a": 1},
        operation_id="reply-lost",
        owner_epoch=1101,
        uploaded_by="owner-a",
    )
    collection.lose_reply = True
    with pytest.raises(ConnectionError, match="marker cleanup reply lost"):
        await storage.forget_release_operation(
            ["key-a"],
            operation_id="reply-lost",
            owner_epoch=1101,
            uploaded_by="owner-a",
        )
    assert await storage.forget_release_operation(
        ["key-a"],
        operation_id="reply-lost",
        owner_epoch=1101,
        uploaded_by="owner-a",
    )
    assert collection.records["key-a"]["session_release_operations"] == []


@pytest.mark.asyncio
async def test_release_epoch_takeover_preserves_already_applied_decrement() -> None:
    collection = _ReleaseMarkerCleanupCollection()
    collection.records["key-a"]["reference_count"] = 2
    storage = FileRecordStorage()
    storage._collection = collection
    storage.ensure_indexes_if_needed = _noop_async

    assert await storage.adopt_release_operation_epoch(
        ["key-a"], operation_id="clear-1", owner_epoch=1, uploaded_by="owner-a"
    )
    assert (
        await storage.release_reference_counts(
            {"key-a": 1},
            operation_id="clear-1",
            owner_epoch=1,
            uploaded_by="owner-a",
        )
        == 1
    )
    assert await storage.adopt_release_operation_epoch(
        ["key-a"], operation_id="clear-1", owner_epoch=2, uploaded_by="owner-a"
    )
    assert (
        await storage.release_reference_counts(
            {"key-a": 1},
            operation_id="clear-1",
            owner_epoch=2,
            uploaded_by="owner-a",
        )
        == 0
    )
    assert collection.records["key-a"]["reference_count"] == 1


@pytest.mark.asyncio
async def test_generation_tombstone_requires_newer_claim_but_live_retry_is_idempotent() -> None:
    task_id = "2f191ddb-b029-4a2e-a66e-8b292fa2401f"
    collection = _DelayedScheduledTaskClaimCollection(
        task_id,
        tombstone_generation=2,
    )
    storage = FileRecordStorage()
    storage._collection = collection
    storage.ensure_indexes_if_needed = _noop_async

    with pytest.raises(AttachmentClaimError):
        await storage.claim_scheduled_task_references(
            ["key-a"],
            "owner-a",
            task_id,
            mutation_generation=1,
        )
    with pytest.raises(AttachmentClaimError):
        await storage.claim_scheduled_task_references(
            ["key-a"],
            "owner-a",
            task_id,
            mutation_generation=2,
        )

    claimed = await storage.claim_scheduled_task_references(
        ["key-a"],
        "owner-a",
        task_id,
        mutation_generation=3,
    )
    retried = await storage.claim_scheduled_task_references(
        ["key-a"],
        "owner-a",
        task_id,
        mutation_generation=3,
    )

    assert claimed == ["key-a"]
    assert retried == []
    assert collection.record["scheduled_task_reference_ids"] == [task_id]
    assert collection.record["scheduled_task_reference_generations"] == [
        {"task_id": task_id, "generation": 3}
    ]
    assert collection.record["reference_count"] == 1


@pytest.mark.asyncio
async def test_scheduled_task_generation_adopt_rejects_unbounded_keys() -> None:
    task_id = "2f191ddb-b029-4a2e-a66e-8b292fa2401f"
    collection = _LifecycleCollection()
    storage = FileRecordStorage()
    storage._collection = collection
    storage.ensure_indexes_if_needed = _noop_async

    with pytest.raises(AttachmentClaimError):
        await storage.adopt_scheduled_task_reference_generation(
            [f"key-{index}" for index in range(101)],
            "owner-a",
            task_id,
            mutation_generation=2,
        )

    assert collection.find_one_and_update_calls == []


@pytest.mark.asyncio
async def test_scheduled_task_claim_rolls_back_only_tokens_added_by_this_call() -> None:
    task_id = "2f191ddb-b029-4a2e-a66e-8b292fa2401f"
    collection = _LifecycleCollection()
    collection.claim_results = [
        {
            "key": "existing",
            "scheduled_task_reference_ids": [task_id],
        },
        {
            "key": "new",
            "scheduled_task_reference_ids": [],
        },
        None,
        {
            "key": "new",
            "scheduled_task_reference_ids": [task_id],
        },
    ]
    storage = FileRecordStorage()
    storage._collection = collection
    storage.ensure_indexes_if_needed = _noop_async

    with pytest.raises(AttachmentClaimError):
        await storage.claim_scheduled_task_references(
            ["existing", "new", "foreign"],
            "owner-a",
            task_id,
            mutation_generation=3,
        )

    rollback_query = collection.find_one_and_update_calls[-1][0]
    assert rollback_query == {
        "key": "new",
        "uploaded_by": "owner-a",
        "deleting_at": {"$exists": False},
        "scheduled_task_reference_ids": task_id,
        "scheduled_task_reference_generations": {
            "$elemMatch": {"task_id": task_id, "generation": 3}
        },
    }


@pytest.mark.asyncio
async def test_scheduled_task_claim_rejects_unbounded_keys_and_invalid_task_id() -> None:
    collection = _LifecycleCollection()
    storage = FileRecordStorage()
    storage._collection = collection
    storage.ensure_indexes_if_needed = _noop_async

    with pytest.raises(AttachmentClaimError):
        await storage.claim_scheduled_task_references(
            [f"key-{index}" for index in range(101)],
            "owner-a",
            "2f191ddb-b029-4a2e-a66e-8b292fa2401f",
            mutation_generation=1,
        )
    with pytest.raises(ValueError, match="task_id must be a UUID"):
        await storage.claim_scheduled_task_references(
            ["key-a"],
            "owner-a",
            "not-a-task-uuid",
            mutation_generation=1,
        )
    with pytest.raises(ValueError, match="task_id must be a UUID"):
        await storage.release_scheduled_task_references(
            ["key-a"],
            "owner-a",
            "not-a-task-uuid",
            mutation_generation=1,
        )
    with pytest.raises(AttachmentClaimError):
        await storage.release_scheduled_task_references(
            [f"key-{index}" for index in range(101)],
            "owner-a",
            "2f191ddb-b029-4a2e-a66e-8b292fa2401f",
            mutation_generation=1,
        )

    assert collection.find_one_and_update_calls == []


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
    eligibility = collection.find_one_and_update_calls[0][0]["$or"]
    assert eligibility[0] == {"deleting_at": {"$exists": False}}
    assert "$lte" in eligibility[1]["deleting_at"]
    assert finalized is True
    assert collection.delete_one_calls == [
        {"key": "key-a", "uploaded_by": "owner-a", "deleting_at": tombstone}
    ]


@pytest.mark.asyncio
async def test_tombstone_cleanup_batch_is_bounded_even_when_caller_requests_more() -> None:
    collection = _LifecycleCollection()
    collection.claim_results = [
        {"key": f"key-{index}", "uploaded_by": "owner-a", "deleting_at": object()}
        for index in range(101)
    ]
    storage = FileRecordStorage()
    storage._collection = collection
    storage.ensure_indexes_if_needed = _noop_async

    claimed = await storage.tombstone_cleanup_batch(limit=1000)

    assert len(claimed) == file_record.CLEANUP_BATCH_SIZE
    assert len(collection.find_one_and_update_calls) == file_record.CLEANUP_BATCH_SIZE


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
async def test_cleanup_cancellation_clears_current_tombstone_before_propagating() -> None:
    tombstone = object()
    record = {"key": "key-a", "uploaded_by": "owner-a", "deleting_at": tombstone}
    collection = _LifecycleCollection()
    storage = FileRecordStorage()
    storage._collection = collection
    storage.ensure_indexes_if_needed = _noop_async

    async def _tombstone_batch():
        return [record]

    class _CancelledObjects:
        async def delete_file(self, key: str) -> None:
            raise asyncio.CancelledError

    storage.tombstone_cleanup_batch = _tombstone_batch

    with pytest.raises(asyncio.CancelledError):
        await storage.cleanup_scheduled_records(_CancelledObjects())

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
