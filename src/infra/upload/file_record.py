"""File record storage for content-hash based deduplication."""

from datetime import datetime
from typing import Optional

from src.infra.logging import get_logger
from src.kernel.config import settings


class FileRecordStorage:
    """Storage layer for file records, keyed by content hash."""

    def __init__(self):
        self._collection = None

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
            import asyncio

            task = asyncio.create_task(self._ensure_indexes())
            task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)

    async def _ensure_indexes(self):
        """Create required indexes on the file_records collection."""
        try:
            collection = self.collection
            await collection.create_index("hash", unique=True, background=True)
            await collection.create_index("key", unique=True, background=True)
            await collection.create_index("uploaded_by", background=True)
        except Exception as e:
            get_logger(__name__).warning(f"Failed to create file_records indexes: {e}")

    async def find_by_hash(self, file_hash: str) -> Optional[dict]:
        """Look up a file record by content hash.

        Args:
            file_hash: SHA-256 hex digest.

        Returns:
            Document dict with ``id`` (instead of ``_id``), or None.
        """
        await self.ensure_indexes_if_needed()
        doc = await self.collection.find_one({"hash": file_hash})
        if doc:
            doc["id"] = str(doc.pop("_id"))
        return doc

    async def find_by_key(self, key: str) -> Optional[dict]:
        """Look up a file record by storage key.

        Args:
            key: Storage object key (e.g. "category/user_id/uuid.ext").

        Returns:
            Document dict with ``id`` (instead of ``_id``), or None.
        """
        await self.ensure_indexes_if_needed()
        doc = await self.collection.find_one({"key": key})
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
        now = datetime.now()
        doc = {
            "hash": file_hash,
            "key": key,
            "name": name,
            "mime_type": mime_type,
            "size": size,
            "category": category,
            "uploaded_by": uploaded_by,
            "reference_count": 0,
            "created_at": now,
            "updated_at": now,
        }
        result = await self.collection.insert_one(doc)
        doc["id"] = str(result.inserted_id)
        return doc

    async def add_references(self, keys: list[str]) -> int:
        """Increment persisted message references for the given storage keys."""
        unique_keys = sorted({key for key in keys if key})
        if not unique_keys:
            return 0

        await self.ensure_indexes_if_needed()
        result = await self.collection.update_many(
            {"key": {"$in": unique_keys}},
            {"$inc": {"reference_count": 1}, "$set": {"updated_at": datetime.now()}},
        )
        return result.modified_count

    async def release_references(self, keys: list[str]) -> int:
        """Decrement persisted message references for the given storage keys."""
        unique_keys = sorted({key for key in keys if key})
        if not unique_keys:
            return 0

        await self.ensure_indexes_if_needed()
        result = await self.collection.update_many(
            {
                "key": {"$in": unique_keys},
                "reference_count": {"$gt": 0},
            },
            {"$inc": {"reference_count": -1}, "$set": {"updated_at": datetime.now()}},
        )
        return result.modified_count

    async def delete_by_key(self, key: str) -> bool:
        """Delete a file record by storage key.

        Args:
            key: Storage object key.

        Returns:
            True if a document was deleted, False otherwise.
        """
        await self.ensure_indexes_if_needed()
        result = await self.collection.delete_one({"key": key})
        return result.deleted_count > 0

    async def delete_by_hash(self, file_hash: str) -> bool:
        """Delete a file record by content hash.

        Args:
            file_hash: SHA-256 hex digest.

        Returns:
            True if a document was deleted, False otherwise.
        """
        await self.ensure_indexes_if_needed()
        result = await self.collection.delete_one({"hash": file_hash})
        return result.deleted_count > 0
