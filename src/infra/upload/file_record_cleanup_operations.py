"""Delayed cleanup and terminal deletion operations for file records."""

import asyncio
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from pymongo import ReturnDocument

from src.infra.utils.datetime import utc_now

_CLEANUP_GRACE_PERIOD = timedelta(minutes=15)
_CLEANUP_BATCH_SIZE = 100
_CLEANUP_TOMBSTONE_LEASE_PERIOD = timedelta(minutes=15)


class FileRecordCleanupOperationsMixin:
    """Cleanup operations composed into ``FileRecordStorage``."""

    if TYPE_CHECKING:
        collection: Any
        _indexes_task: asyncio.Task[None] | None

        async def ensure_indexes_if_needed(self) -> None: ...

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
            {"$set": {"cleanup_after": now + _CLEANUP_GRACE_PERIOD, "updated_at": now}},
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
            {"$set": {"cleanup_after": now + _CLEANUP_GRACE_PERIOD, "updated_at": now}},
        )
        return result.modified_count > 0

    async def tombstone_cleanup_batch(self, *, limit: int = _CLEANUP_BATCH_SIZE) -> list[dict]:
        """Atomically reserve overdue, unused records for object deletion."""
        await self.ensure_indexes_if_needed()
        claimed: list[dict] = []
        now = utc_now()
        bounded_limit = max(0, min(int(limit), _CLEANUP_BATCH_SIZE))
        for _ in range(bounded_limit):
            record = await self.collection.find_one_and_update(
                {
                    "reference_count": 0,
                    "cleanup_after": {"$lte": now},
                    "$or": [
                        {"deleting_at": {"$exists": False}},
                        {"deleting_at": {"$lte": now - _CLEANUP_TOMBSTONE_LEASE_PERIOD}},
                    ],
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
            except asyncio.CancelledError:
                await asyncio.shield(self.clear_tombstone(record))
                raise
            except Exception:
                await self.clear_tombstone(record)
                continue
            if await self.finalize_tombstone_cleanup(record):
                deleted += 1
        return deleted

    async def delete_by_key(self, key: str, uploaded_by: str | None = None) -> bool:
        """Delete an owner-scoped record by storage key."""
        await self.ensure_indexes_if_needed()
        if uploaded_by is None:
            return False
        result = await self.collection.delete_one({"key": key, "uploaded_by": uploaded_by})
        return result.deleted_count > 0

    async def delete_by_hash(self, file_hash: str, uploaded_by: str) -> bool:
        """Delete an owner-scoped record by content hash."""
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
