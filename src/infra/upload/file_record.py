"""File record storage for content-hash based deduplication."""

import asyncio
from collections import Counter
from datetime import timedelta
from typing import Any, Mapping, Optional

from pymongo import ReturnDocument

from src.infra.utils.datetime import utc_now
from src.kernel.config import settings

REFERENCE_KEYS_MAX = 100
CLEANUP_GRACE_PERIOD = timedelta(minutes=15)
CLEANUP_BATCH_SIZE = 100


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


class FileRecordStorage:
    """Storage layer for file records, keyed by content hash."""

    REFERENCE_KEYS_MAX = REFERENCE_KEYS_MAX

    def __init__(self):
        self._collection = None
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

    async def release_reference_counts(self, counts: Mapping[str, int]) -> int:
        """Atomically release each requested count while preserving cleanup grace."""
        normalized_counts = _positive_reference_counts(counts)
        if not normalized_counts:
            return 0

        await self.ensure_indexes_if_needed()
        now = utc_now()
        cleanup_after = now + CLEANUP_GRACE_PERIOD
        released = 0
        for key, count in normalized_counts.items():
            record = await self.collection.find_one_and_update(
                {"key": key, "deleting_at": {"$exists": False}},
                [
                    {
                        "$set": {
                            "reference_count": {
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
                return_document=ReturnDocument.AFTER,
            )
            if record is not None:
                released += 1
        return released

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

    async def schedule_owned_cleanup(self, key: str, uploaded_by: str) -> bool:
        """Give an owned, unused record a conservative cleanup deadline."""
        await self.ensure_indexes_if_needed()
        now = utc_now()
        record = await self.collection.find_one_and_update(
            {
                "key": key,
                "uploaded_by": uploaded_by,
                "reference_count": 0,
                "deleting_at": {"$exists": False},
            },
            {"$set": {"cleanup_after": now + CLEANUP_GRACE_PERIOD, "updated_at": now}},
            return_document=ReturnDocument.AFTER,
        )
        return record is not None

    async def refresh_owned_cleanup(self, key: str, uploaded_by: str) -> bool:
        """Refresh an owner's cleanup grace period when its draft record is reused."""
        await self.ensure_indexes_if_needed()
        now = utc_now()
        result = await self.collection.update_one(
            {
                "key": key,
                "uploaded_by": uploaded_by,
                "deleting_at": {"$exists": False},
            },
            {"$set": {"cleanup_after": now + CLEANUP_GRACE_PERIOD, "updated_at": now}},
        )
        return result.modified_count > 0

    async def tombstone_cleanup_batch(self, *, limit: int = CLEANUP_BATCH_SIZE) -> list[dict]:
        """Atomically reserve overdue, unused records for object deletion."""
        await self.ensure_indexes_if_needed()
        claimed: list[dict] = []
        now = utc_now()
        for _ in range(limit):
            record = await self.collection.find_one_and_update(
                {
                    "reference_count": 0,
                    "cleanup_after": {"$lte": now},
                    "deleting_at": {"$exists": False},
                },
                {"$set": {"deleting_at": now, "updated_at": now}},
                return_document=ReturnDocument.AFTER,
            )
            if record is None:
                break
            claimed.append(record)
        return claimed

    async def finalize_tombstone_cleanup(self, record: dict) -> bool:
        """Remove a successfully deleted object record while preserving ownership scope."""
        await self.ensure_indexes_if_needed()
        result = await self.collection.delete_one(
            {
                "key": record["key"],
                "uploaded_by": record["uploaded_by"],
                "deleting_at": record["deleting_at"],
            }
        )
        return result.deleted_count > 0

    async def clear_tombstone(self, record: dict) -> bool:
        """Make an object-delete failure eligible for a later cleanup retry."""
        await self.ensure_indexes_if_needed()
        result = await self.collection.update_one(
            {
                "key": record["key"],
                "uploaded_by": record["uploaded_by"],
                "deleting_at": record["deleting_at"],
            },
            {"$unset": {"deleting_at": ""}, "$set": {"updated_at": utc_now()}},
        )
        return result.modified_count > 0

    async def cleanup_scheduled_records(self, object_storage: Any) -> int:
        """Delete tombstoned objects, clearing the tombstone when deletion fails."""
        deleted = 0
        for record in await self.tombstone_cleanup_batch():
            try:
                await object_storage.delete_file(record["key"])
            except Exception:
                await self.clear_tombstone(record)
                continue
            if await self.finalize_tombstone_cleanup(record):
                deleted += 1
        return deleted

    async def delete_by_key(self, key: str, uploaded_by: str | None = None) -> bool:
        """Delete a file record by storage key.

        Args:
            key: Storage object key.
            uploaded_by: Required owner scope; an omitted owner never deletes.

        Returns:
            True if a document was deleted, False otherwise.
        """
        await self.ensure_indexes_if_needed()
        if uploaded_by is None:
            return False
        result = await self.collection.delete_one({"key": key, "uploaded_by": uploaded_by})
        return result.deleted_count > 0

    async def delete_by_hash(self, file_hash: str, uploaded_by: str) -> bool:
        """Delete a file record by content hash.

        Args:
            file_hash: SHA-256 hex digest.
            uploaded_by: User ID that owns the content hash.

        Returns:
            True if a document was deleted, False otherwise.
        """
        await self.ensure_indexes_if_needed()
        result = await self.collection.delete_one({"hash": file_hash, "uploaded_by": uploaded_by})
        return result.deleted_count > 0

    async def close(self) -> None:
        task = self._indexes_task
        self._indexes_task = None
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if hasattr(self, "_indexes_ensured"):
            delattr(self, "_indexes_ensured")
        self._collection = None
