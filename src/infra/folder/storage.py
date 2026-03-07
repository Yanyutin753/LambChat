"""Folder storage layer for session organization."""

from datetime import datetime
from typing import Optional

from bson import ObjectId

from src.kernel.config import settings
from src.kernel.schemas.folder import Folder, FolderCreate, FolderUpdate


class FolderStorage:
    """
    Folder storage class using MongoDB.

    Manages folders for organizing user sessions, including the special "favorites" folder.
    """

    FOLDER_COLLECTION = "folders"

    def __init__(self):
        self._collection = None

    @property
    def collection(self):
        """Lazy-load MongoDB collection."""
        if self._collection is None:
            from src.infra.storage.mongodb import get_mongo_client

            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            self._collection = db[self.FOLDER_COLLECTION]
        return self._collection

    async def create(self, folder_data: FolderCreate, user_id: str) -> Folder:
        """Create a new folder."""
        now = datetime.now()

        folder_dict = {
            "name": folder_data.name,
            "type": folder_data.type,
            "sort_order": folder_data.sort_order,
            "user_id": user_id,
            "created_at": now,
            "updated_at": now,
        }

        result = await self.collection.insert_one(folder_dict)
        folder_dict["id"] = str(result.inserted_id)

        return Folder(**folder_dict)

    async def get_by_id(self, folder_id: str, user_id: str) -> Optional[Folder]:
        """Get a folder by ID for a specific user."""
        try:
            folder_dict = await self.collection.find_one(
                {"_id": ObjectId(folder_id), "user_id": user_id}
            )
        except Exception:
            return None

        if not folder_dict:
            return None

        folder_dict["id"] = str(folder_dict.pop("_id"))
        return Folder(**folder_dict)

    async def get_by_type(self, user_id: str, folder_type: str) -> Optional[Folder]:
        """Get a folder by type for a specific user (e.g., 'favorites')."""
        folder_dict = await self.collection.find_one({"user_id": user_id, "type": folder_type})

        if not folder_dict:
            return None

        folder_dict["id"] = str(folder_dict.pop("_id"))
        return Folder(**folder_dict)

    async def list_folders(self, user_id: str) -> list[Folder]:
        """List all folders for a user, sorted by sort_order."""
        cursor = self.collection.find({"user_id": user_id}).sort("sort_order", 1)
        folders = []

        for folder_dict in await cursor.to_list(length=100):
            folder_dict["id"] = str(folder_dict.pop("_id"))
            folders.append(Folder(**folder_dict))

        return folders

    async def update(
        self, folder_id: str, user_id: str, folder_data: FolderUpdate
    ) -> Optional[Folder]:
        """Update a folder."""
        update_dict: dict = {"updated_at": datetime.now()}

        if folder_data.name is not None:
            update_dict["name"] = folder_data.name

        if folder_data.sort_order is not None:
            update_dict["sort_order"] = folder_data.sort_order

        try:
            result = await self.collection.find_one_and_update(
                {"_id": ObjectId(folder_id), "user_id": user_id},
                {"$set": update_dict},
                return_document=True,
            )
        except Exception:
            return None

        if not result:
            return None

        result["id"] = str(result.pop("_id"))
        return Folder(**result)

    async def delete(self, folder_id: str, user_id: str) -> bool:
        """Delete a folder.

        Note: This does not delete the sessions in the folder, only the folder itself.
        """
        try:
            result = await self.collection.delete_one(
                {"_id": ObjectId(folder_id), "user_id": user_id}
            )
            return result.deleted_count > 0
        except Exception:
            return False

    async def ensure_favorites_folder(self, user_id: str) -> Folder:
        """Ensure the favorites folder exists for a user.

        Creates the favorites folder if it doesn't exist.
        Returns the favorites folder.
        """
        # Check if favorites folder already exists
        existing = await self.get_by_type(user_id, "favorites")
        if existing:
            return existing

        # Create the favorites folder
        now = datetime.now()
        folder_dict = {
            "name": "Favorites",
            "type": "favorites",
            "sort_order": 0,  # Favorites always first
            "user_id": user_id,
            "created_at": now,
            "updated_at": now,
        }

        result = await self.collection.insert_one(folder_dict)
        folder_dict["id"] = str(result.inserted_id)

        return Folder(**folder_dict)


# Singleton instance
_folder_storage: Optional[FolderStorage] = None


def get_folder_storage() -> FolderStorage:
    """Get folder storage singleton."""
    global _folder_storage
    if _folder_storage is None:
        _folder_storage = FolderStorage()
    return _folder_storage
