"""File record storage for content-hash based deduplication."""

import asyncio
from collections import Counter
from datetime import timedelta
from typing import Any, Mapping, Optional
from uuid import UUID

from pymongo import ReturnDocument

from src.infra.upload.file_record_cleanup_operations import FileRecordCleanupOperationsMixin
from src.infra.utils.datetime import utc_now
from src.kernel.config import settings

REFERENCE_KEYS_MAX = 100
CLEANUP_GRACE_PERIOD = timedelta(minutes=15)
CLEANUP_BATCH_SIZE = 100
CLEANUP_TOMBSTONE_LEASE_PERIOD = timedelta(minutes=15)
SCHEDULED_TASK_REFERENCES_PER_FILE_MAX = 1000


class AttachmentClaimError(Exception):
    """Raised when an attachment cannot be safely claimed by its owner."""

    def __init__(self) -> None:
        super().__init__("Attachment is unavailable")


def _bounded_unique_keys(keys: list[str], *, limit: int = REFERENCE_KEYS_MAX) -> list[str]:
    unique_keys: list[str] = []
    seen = set()
    for key in keys:
        clean = str(key).strip() if key else ""
        if not clean or clean in seen:
            continue
        seen.add(clean)
        unique_keys.append(clean)
        if len(unique_keys) >= limit:
            break
    return unique_keys


def _positive_reference_counts(counts: Mapping[str, int]) -> Counter[str]:
    """Normalize positive release counts without applying a per-call key cap."""
    normalized: Counter[str] = Counter()
    for key, count in counts.items():
        clean = str(key).strip() if key else ""
        if not clean or count <= 0:
            continue
        normalized[clean] += count
    return normalized


def _scheduled_task_reference_id(task_id: str) -> str:
    clean = str(task_id).strip()
    try:
        return str(UUID(clean))
    except (ValueError, AttributeError) as exc:
        raise ValueError("task_id must be a UUID") from exc


def _scheduled_task_reference_state(task_id: str) -> tuple[dict, dict, dict, dict]:
    """Build aggregation expressions for compact live leases and their global fence."""
    existing_ids = {"$ifNull": ["$scheduled_task_reference_ids", []]}
    existing_generations = {"$ifNull": ["$scheduled_task_reference_generations", []]}
    live_generations = {
        "$filter": {
            "input": existing_generations,
            "as": "lease",
            "cond": {"$in": ["$$lease.task_id", existing_ids]},
        }
    }
    other_live_generations = {
        "$filter": {
            "input": live_generations,
            "as": "lease",
            "cond": {"$ne": ["$$lease.task_id", task_id]},
        }
    }
    legacy_generation_high_water = {
        "$ifNull": [
            {
                "$max": {
                    "$map": {
                        "input": existing_generations,
                        "as": "lease",
                        "in": "$$lease.generation",
                    }
                }
            },
            0,
        ]
    }
    high_water = {
        "$max": [
            {"$ifNull": ["$scheduled_task_generation_high_water", 0]},
            legacy_generation_high_water,
        ]
    }
    return existing_ids, other_live_generations, high_water, live_generations


class FileRecordStorage(FileRecordCleanupOperationsMixin):
    """Storage layer for file records, keyed by content hash."""

    REFERENCE_KEYS_MAX = REFERENCE_KEYS_MAX

    def __init__(self):
        self._collection: Any = None
        self._indexes_task: asyncio.Task[None] | None = None

    @property
    def collection(self):
        """Lazy-load MongoDB collection."""
        if self._collection is None:
            from src.infra.storage.mongodb import get_mongo_client

            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            self._collection = db["file_records"]
        return self._collection

    async def ensure_indexes_if_needed(self):
        """Ensure indexes exist (called lazily on first use)."""
        if not hasattr(self, "_indexes_ensured"):
            self._indexes_ensured = True
            task = asyncio.create_task(self._ensure_indexes())
            task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
            self._indexes_task = task

    async def initialize_indexes(self) -> None:
        """Strictly initialize indexes before this storage becomes ready.

        Unlike the lazy path, errors are deliberately propagated so application
        startup cannot serve requests without owner-scoped deduplication.
        """
        await self._ensure_indexes()
        self._indexes_ensured = True

    async def _ensure_indexes(self):
        """Create required indexes on the file_records collection."""
        collection = self.collection
        await collection.create_index(
            [("uploaded_by", 1), ("hash", 1)],
            name="uploaded_by_hash_unique_idx",
            unique=True,
            background=True,
        )

        indexes = [index async for index in collection.list_indexes()]
        for index in indexes:
            key_pattern = list(index.get("key", {}).items())
            if key_pattern == [("hash", 1)] and index.get("unique") is True:
                await collection.drop_index(index["name"])

        await collection.create_index("key", unique=True, background=True)
        await collection.create_index("uploaded_by", background=True)

    async def find_by_hash(self, file_hash: str, uploaded_by: str) -> Optional[dict]:
        """Look up a file record by content hash.

        Args:
            file_hash: SHA-256 hex digest.
            uploaded_by: User ID that owns the content hash.

        Returns:
            Document dict with ``id`` (instead of ``_id``), or None.
        """
        await self.ensure_indexes_if_needed()
        doc = await self.collection.find_one(
            {
                "hash": file_hash,
                "uploaded_by": uploaded_by,
                "deleting_at": {"$exists": False},
            }
        )
        if doc:
            doc["id"] = str(doc.pop("_id"))
        return doc

    async def find_by_key(self, key: str, uploaded_by: str | None = None) -> Optional[dict]:
        """Look up a file record by storage key.

        Args:
            key: Storage object key (e.g. "category/user_id/uuid.ext").
            uploaded_by: Optional owner scope for private callers.

        Returns:
            Document dict with ``id`` (instead of ``_id``), or None.
        """
        await self.ensure_indexes_if_needed()
        query = {"key": key}
        if uploaded_by is not None:
            query["uploaded_by"] = uploaded_by
        doc = await self.collection.find_one(query)
        if doc:
            doc["id"] = str(doc.pop("_id"))
        return doc

    async def create(
        self,
        file_hash: str,
        key: str,
        name: str,
        mime_type: str,
        size: int,
        category: str,
        uploaded_by: str,
    ) -> dict:
        """Insert a new file record.

        Args:
            file_hash: SHA-256 hex digest.
            key: Storage object key (e.g. "user_id/abc123hash").
            name: Original filename.
            mime_type: MIME type of the file.
            size: File size in bytes.
            category: One of "image", "video", "audio", "document".
            uploaded_by: User ID of the uploader.

        Returns:
            Document dict with ``id`` field.
        """
        await self.ensure_indexes_if_needed()
        now = utc_now()
        doc = {
            "hash": file_hash,
            "key": key,
            "name": name,
            "mime_type": mime_type,
            "size": size,
            "category": category,
            "uploaded_by": uploaded_by,
            "reference_count": 0,
            "cleanup_after": now + CLEANUP_GRACE_PERIOD,
            "created_at": now,
            "updated_at": now,
        }
        result = await self.collection.insert_one(doc)
        doc["id"] = str(result.inserted_id)
        return doc

    async def add_references(self, keys: list[str]) -> int:
        """Increment persisted message references for the given storage keys."""
        unique_keys = _bounded_unique_keys(keys)
        if not unique_keys:
            return 0

        await self.ensure_indexes_if_needed()
        result = await self.collection.update_many(
            {"key": {"$in": unique_keys}},
            {"$inc": {"reference_count": 1}, "$set": {"updated_at": utc_now()}},
        )
        return result.modified_count

    async def claim_owned_references(self, keys: list[str], uploaded_by: str) -> list[str]:
        """Atomically claim each owned, non-tombstoned key or roll back this call."""
        unique_keys = _bounded_unique_keys(keys)
        if not unique_keys:
            return []
        if len(unique_keys) != len({str(key).strip() for key in keys if key and str(key).strip()}):
            raise AttachmentClaimError()

        await self.ensure_indexes_if_needed()
        claimed: list[str] = []
        now = utc_now()
        try:
            for key in unique_keys:
                record = await self.collection.find_one_and_update(
                    {
                        "key": key,
                        "uploaded_by": uploaded_by,
                        "deleting_at": {"$exists": False},
                    },
                    {
                        "$inc": {"reference_count": 1},
                        "$set": {
                            "updated_at": now,
                            "cleanup_after": now + CLEANUP_GRACE_PERIOD,
                        },
                    },
                    return_document=ReturnDocument.AFTER,
                )
                if record is None:
                    raise AttachmentClaimError()
                claimed.append(key)
        except (Exception, asyncio.CancelledError):
            await self.release_owned_references(claimed, uploaded_by)
            raise
        return claimed

    async def claim_scheduled_task_references(
        self,
        keys: list[str],
        uploaded_by: str,
        task_id: str,
        *,
        mutation_generation: int,
    ) -> list[str]:
        """Claim a live task reference only at or above its durable generation fence."""
        task_id = _scheduled_task_reference_id(task_id)
        if mutation_generation < 1:
            raise ValueError("mutation_generation must be positive")
        unique_keys = _bounded_unique_keys(keys)
        if not unique_keys:
            return []
        if len(unique_keys) != len({str(key).strip() for key in keys if key and str(key).strip()}):
            raise AttachmentClaimError()

        await self.ensure_indexes_if_needed()
        newly_claimed: list[str] = []
        now = utc_now()
        existing_ids, other_generations, high_water, _live_generations = (
            _scheduled_task_reference_state(task_id)
        )
        already_claimed = {"$in": [task_id, existing_ids]}
        try:
            for key in unique_keys:
                previous = await self.collection.find_one_and_update(
                    {
                        "key": key,
                        "uploaded_by": uploaded_by,
                        "deleting_at": {"$exists": False},
                        "$and": [
                            {
                                "$or": [
                                    {"scheduled_task_reference_ids": task_id},
                                    {
                                        "$expr": {
                                            "$lt": [
                                                {"$size": existing_ids},
                                                SCHEDULED_TASK_REFERENCES_PER_FILE_MAX,
                                            ]
                                        }
                                    },
                                ]
                            },
                            {
                                "$or": [
                                    {"$expr": {"$gt": [mutation_generation, high_water]}},
                                    {
                                        "scheduled_task_reference_ids": task_id,
                                        "scheduled_task_reference_generations": {
                                            "$elemMatch": {
                                                "task_id": task_id,
                                                "generation": mutation_generation,
                                            }
                                        },
                                    },
                                ]
                            },
                        ],
                    },
                    [
                        {
                            "$set": {
                                "reference_count": {
                                    "$cond": [
                                        already_claimed,
                                        {"$ifNull": ["$reference_count", 0]},
                                        {
                                            "$add": [
                                                {"$ifNull": ["$reference_count", 0]},
                                                1,
                                            ]
                                        },
                                    ]
                                },
                                "scheduled_task_reference_ids": {
                                    "$setUnion": [existing_ids, [task_id]]
                                },
                                "scheduled_task_reference_generations": {
                                    "$concatArrays": [
                                        other_generations,
                                        [
                                            {
                                                "task_id": task_id,
                                                "generation": mutation_generation,
                                            }
                                        ],
                                    ]
                                },
                                "scheduled_task_generation_high_water": {
                                    "$max": [high_water, mutation_generation]
                                },
                                "cleanup_after": now + CLEANUP_GRACE_PERIOD,
                                "updated_at": now,
                            }
                        }
                    ],
                    return_document=ReturnDocument.BEFORE,
                )
                if previous is None:
                    raise AttachmentClaimError()
                if task_id not in previous.get("scheduled_task_reference_ids", []):
                    newly_claimed.append(key)
        except (Exception, asyncio.CancelledError):
            await self.release_scheduled_task_references(
                newly_claimed,
                uploaded_by,
                task_id,
                mutation_generation=mutation_generation,
            )
            raise
        return newly_claimed

    async def adopt_scheduled_task_reference_generation(
        self,
        keys: list[str],
        uploaded_by: str,
        task_id: str,
        *,
        mutation_generation: int,
    ) -> int:
        """Advance the task high-water mark without creating a live reference."""
        task_id = _scheduled_task_reference_id(task_id)
        if mutation_generation < 1:
            raise ValueError("mutation_generation must be positive")
        unique_keys = _bounded_unique_keys(keys)
        if not unique_keys:
            return 0
        if len(unique_keys) != len({str(key).strip() for key in keys if key and str(key).strip()}):
            raise AttachmentClaimError()
        await self.ensure_indexes_if_needed()
        existing_ids, other_generations, high_water, _live_generations = (
            _scheduled_task_reference_state(task_id)
        )
        adopted = 0
        for key in unique_keys:
            previous = await self.collection.find_one_and_update(
                {
                    "key": key,
                    "uploaded_by": uploaded_by,
                    "deleting_at": {"$exists": False},
                    "$or": [
                        {"$expr": {"$gt": [mutation_generation, high_water]}},
                        {
                            "scheduled_task_reference_ids": task_id,
                            "scheduled_task_reference_generations": {
                                "$elemMatch": {
                                    "task_id": task_id,
                                    "generation": mutation_generation,
                                }
                            },
                        },
                    ],
                },
                [
                    {
                        "$set": {
                            "scheduled_task_reference_generations": {
                                "$cond": [
                                    {"$in": [task_id, existing_ids]},
                                    {
                                        "$concatArrays": [
                                            other_generations,
                                            [
                                                {
                                                    "task_id": task_id,
                                                    "generation": mutation_generation,
                                                }
                                            ],
                                        ]
                                    },
                                    other_generations,
                                ]
                            },
                            "scheduled_task_generation_high_water": {
                                "$max": [high_water, mutation_generation]
                            },
                            "updated_at": utc_now(),
                        }
                    }
                ],
                return_document=ReturnDocument.BEFORE,
            )
            if previous is not None:
                adopted += 1
        return adopted

    async def release_references(self, keys: list[str]) -> int:
        """Decrement persisted message references for the given storage keys."""
        unique_keys = _bounded_unique_keys(keys)
        if not unique_keys:
            return 0

        await self.ensure_indexes_if_needed()
        result = await self.collection.update_many(
            {
                "key": {"$in": unique_keys},
                "reference_count": {"$gt": 0},
            },
            {"$inc": {"reference_count": -1}, "$set": {"updated_at": utc_now()}},
        )
        return result.modified_count

    async def release_scheduled_task_references(
        self,
        keys: list[str],
        uploaded_by: str,
        task_id: str,
        *,
        mutation_generation: int,
    ) -> int:
        """Release live references while retaining their generation tombstones."""
        task_id = _scheduled_task_reference_id(task_id)
        if mutation_generation < 1:
            raise ValueError("mutation_generation must be positive")
        unique_keys = _bounded_unique_keys(keys)
        if not unique_keys:
            return 0
        if len(unique_keys) != len({str(key).strip() for key in keys if key and str(key).strip()}):
            raise AttachmentClaimError()

        await self.ensure_indexes_if_needed()
        now = utc_now()
        cleanup_after = now + CLEANUP_GRACE_PERIOD
        released = 0
        _existing_ids, other_generations, high_water, _live_generations = (
            _scheduled_task_reference_state(task_id)
        )
        for key in unique_keys:
            previous = await self.collection.find_one_and_update(
                {
                    "key": key,
                    "uploaded_by": uploaded_by,
                    "deleting_at": {"$exists": False},
                    "scheduled_task_reference_ids": task_id,
                    "scheduled_task_reference_generations": {
                        "$elemMatch": {
                            "task_id": task_id,
                            "generation": mutation_generation,
                        }
                    },
                },
                [
                    {
                        "$set": {
                            "reference_count": {
                                "$max": [
                                    0,
                                    {
                                        "$subtract": [
                                            {"$ifNull": ["$reference_count", 0]},
                                            1,
                                        ]
                                    },
                                ]
                            },
                            "scheduled_task_reference_ids": {
                                "$setDifference": [
                                    {"$ifNull": ["$scheduled_task_reference_ids", []]},
                                    [task_id],
                                ]
                            },
                            "scheduled_task_reference_generations": other_generations,
                            "scheduled_task_generation_high_water": {
                                "$max": [high_water, mutation_generation]
                            },
                            "updated_at": now,
                        }
                    },
                    {
                        "$set": {
                            "cleanup_after": {
                                "$cond": [
                                    {"$eq": ["$reference_count", 0]},
                                    cleanup_after,
                                    "$cleanup_after",
                                ]
                            }
                        }
                    },
                ],
                return_document=ReturnDocument.BEFORE,
            )
            if previous is not None:
                released += 1
        return released

    async def release_reference_counts(
        self,
        counts: Mapping[str, int],
        *,
        operation_id: str,
        uploaded_by: str,
        owner_epoch: int,
    ) -> int:
        """Release counts only through the exact live operation epoch."""
        normalized_counts = _positive_reference_counts(counts)
        if not normalized_counts:
            return 0
        operation_id = operation_id.strip()
        if not operation_id:
            raise ValueError("operation_id is required for counted reference release")
        if owner_epoch < 1:
            raise ValueError("owner_epoch must be positive")

        await self.ensure_indexes_if_needed()
        now = utc_now()
        cleanup_after = now + CLEANUP_GRACE_PERIOD
        released = 0
        for key, count in normalized_counts.items():
            record = await self.collection.find_one_and_update(
                {
                    "key": key,
                    "uploaded_by": uploaded_by,
                    "deleting_at": {"$exists": False},
                    "session_release_operations": {
                        "$elemMatch": {
                            "operation_id": operation_id,
                            "epoch": owner_epoch,
                        }
                    },
                },
                [
                    {
                        "$set": {
                            "reference_count": {
                                "$cond": [
                                    {
                                        "$anyElementTrue": {
                                            "$map": {
                                                "input": {
                                                    "$ifNull": [
                                                        "$session_release_operations",
                                                        [],
                                                    ]
                                                },
                                                "as": "operation",
                                                "in": {
                                                    "$and": [
                                                        {
                                                            "$eq": [
                                                                "$$operation.operation_id",
                                                                operation_id,
                                                            ]
                                                        },
                                                        {
                                                            "$eq": [
                                                                "$$operation.epoch",
                                                                owner_epoch,
                                                            ]
                                                        },
                                                        {
                                                            "$eq": [
                                                                "$$operation.applied",
                                                                True,
                                                            ]
                                                        },
                                                    ]
                                                },
                                            }
                                        }
                                    },
                                    {"$ifNull": ["$reference_count", 0]},
                                    {
                                        "$max": [
                                            0,
                                            {
                                                "$subtract": [
                                                    {"$ifNull": ["$reference_count", 0]},
                                                    count,
                                                ]
                                            },
                                        ]
                                    },
                                ]
                            },
                            "session_release_operations": {
                                "$map": {
                                    "input": {"$ifNull": ["$session_release_operations", []]},
                                    "as": "operation",
                                    "in": {
                                        "$cond": [
                                            {
                                                "$and": [
                                                    {
                                                        "$eq": [
                                                            "$$operation.operation_id",
                                                            operation_id,
                                                        ]
                                                    },
                                                    {
                                                        "$eq": [
                                                            "$$operation.epoch",
                                                            owner_epoch,
                                                        ]
                                                    },
                                                ]
                                            },
                                            {
                                                "$mergeObjects": [
                                                    "$$operation",
                                                    {"applied": True},
                                                ]
                                            },
                                            "$$operation",
                                        ]
                                    },
                                }
                            },
                            "updated_at": now,
                        }
                    },
                    {
                        "$set": {
                            "cleanup_after": {
                                "$cond": [
                                    {"$eq": ["$reference_count", 0]},
                                    cleanup_after,
                                    "$cleanup_after",
                                ]
                            }
                        }
                    },
                ],
                return_document=ReturnDocument.BEFORE,
            )
            if record is not None:
                was_applied = any(
                    operation.get("operation_id") == operation_id
                    and operation.get("epoch") == owner_epoch
                    and operation.get("applied") is True
                    for operation in record.get("session_release_operations", [])
                    if isinstance(operation, dict)
                )
                if not was_applied:
                    released += 1
        return released

    async def adopt_release_operation_epoch(
        self,
        keys: list[str],
        *,
        operation_id: str,
        owner_epoch: int,
        uploaded_by: str,
    ) -> bool:
        """Create or advance the bounded live marker for a clear-group owner."""
        unique_keys = list(
            dict.fromkeys(str(key).strip() for key in keys if key and str(key).strip())
        )
        operation_id = operation_id.strip()
        if not operation_id or owner_epoch < 1:
            raise ValueError("operation_id and positive owner_epoch are required")
        if not unique_keys:
            return True
        await self.ensure_indexes_if_needed()
        existing_operations = {"$ifNull": ["$session_release_operations", []]}
        matching_operations = {
            "$filter": {
                "input": existing_operations,
                "as": "operation",
                "cond": {"$eq": ["$$operation.operation_id", operation_id]},
            }
        }
        other_operations = {
            "$filter": {
                "input": existing_operations,
                "as": "operation",
                "cond": {"$ne": ["$$operation.operation_id", operation_id]},
            }
        }
        for key in unique_keys:
            previous = await self.collection.find_one_and_update(
                {
                    "key": key,
                    "uploaded_by": uploaded_by,
                    "deleting_at": {"$exists": False},
                    "$expr": {
                        "$or": [
                            {
                                "$and": [
                                    {"$gt": [{"$size": matching_operations}, 0]},
                                    {
                                        "$lte": [
                                            {
                                                "$max": {
                                                    "$map": {
                                                        "input": matching_operations,
                                                        "as": "operation",
                                                        "in": "$$operation.epoch",
                                                    }
                                                }
                                            },
                                            owner_epoch,
                                        ]
                                    },
                                ]
                            },
                            {
                                "$and": [
                                    {"$eq": [{"$size": matching_operations}, 0]},
                                    {
                                        "$gt": [
                                            owner_epoch,
                                            {
                                                "$ifNull": [
                                                    "$session_release_epoch_high_water",
                                                    0,
                                                ]
                                            },
                                        ]
                                    },
                                ]
                            },
                        ]
                    },
                },
                [
                    {
                        "$set": {
                            "session_release_operations": {
                                "$concatArrays": [
                                    other_operations,
                                    [
                                        {
                                            "operation_id": operation_id,
                                            "epoch": owner_epoch,
                                            "applied": {
                                                "$or": [
                                                    {
                                                        "$anyElementTrue": {
                                                            "$map": {
                                                                "input": matching_operations,
                                                                "as": "operation",
                                                                "in": "$$operation.applied",
                                                            }
                                                        }
                                                    },
                                                    {
                                                        "$in": [
                                                            operation_id,
                                                            {
                                                                "$ifNull": [
                                                                    "$applied_release_operations",
                                                                    [],
                                                                ]
                                                            },
                                                        ]
                                                    },
                                                ]
                                            },
                                        }
                                    ],
                                ]
                            },
                            "updated_at": utc_now(),
                        }
                    }
                ],
                return_document=ReturnDocument.BEFORE,
            )
            if previous is None:
                return False
        return True

    async def forget_release_operation(
        self,
        keys: list[str],
        *,
        operation_id: str,
        owner_epoch: int,
        uploaded_by: str,
    ) -> bool:
        """Remove a completed session-release marker and verify no marker remains."""
        unique_keys = list(
            dict.fromkeys(str(key).strip() for key in keys if key and str(key).strip())
        )
        operation_id = operation_id.strip()
        if not operation_id:
            raise ValueError("operation_id is required for release marker cleanup")
        if owner_epoch < 1:
            raise ValueError("owner_epoch must be positive")
        if not unique_keys:
            return True

        await self.ensure_indexes_if_needed()
        for offset in range(0, len(unique_keys), REFERENCE_KEYS_MAX):
            chunk = unique_keys[offset : offset + REFERENCE_KEYS_MAX]
            marker_query: dict[str, Any] = {
                "key": {"$in": chunk},
                "uploaded_by": uploaded_by,
                "session_release_operations": {
                    "$elemMatch": {
                        "operation_id": operation_id,
                        "epoch": owner_epoch,
                        "applied": True,
                    }
                },
            }
            await self.collection.update_many(
                marker_query,
                [
                    {
                        "$set": {
                            "session_release_operations": {
                                "$filter": {
                                    "input": {"$ifNull": ["$session_release_operations", []]},
                                    "as": "operation",
                                    "cond": {
                                        "$not": [
                                            {
                                                "$and": [
                                                    {
                                                        "$eq": [
                                                            "$$operation.operation_id",
                                                            operation_id,
                                                        ]
                                                    },
                                                    {
                                                        "$eq": [
                                                            "$$operation.epoch",
                                                            owner_epoch,
                                                        ]
                                                    },
                                                ]
                                            }
                                        ]
                                    },
                                }
                            },
                            "session_release_epoch_high_water": {
                                "$max": [
                                    {
                                        "$ifNull": [
                                            "$session_release_epoch_high_water",
                                            0,
                                        ]
                                    },
                                    owner_epoch,
                                ]
                            },
                            "applied_release_operations": {
                                "$setDifference": [
                                    {"$ifNull": ["$applied_release_operations", []]},
                                    [operation_id],
                                ]
                            },
                        }
                    }
                ],
            )
            if await self.collection.count_documents(marker_query, limit=1):
                return False
        return True

    async def release_owned_references(self, keys: list[str], uploaded_by: str) -> int:
        """Roll back owned positive references and retain a conservative cleanup grace."""
        unique_keys = _bounded_unique_keys(keys)
        if not unique_keys:
            return 0

        await self.ensure_indexes_if_needed()
        now = utc_now()
        result = await self.collection.update_many(
            {
                "key": {"$in": unique_keys},
                "uploaded_by": uploaded_by,
                "reference_count": {"$gt": 0},
            },
            {
                "$inc": {"reference_count": -1},
                "$set": {
                    "updated_at": now,
                    "cleanup_after": now + CLEANUP_GRACE_PERIOD,
                },
            },
        )
        return result.modified_count
