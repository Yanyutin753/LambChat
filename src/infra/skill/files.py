"""
Skill files mixin for file management operations
"""

from datetime import datetime, timezone
from typing import Any, Optional


class SkillFilesMixin:
    """
    Mixin providing file management functionality for skills.

    This mixin handles:
    - Syncing skill files to MongoDB files field
    - Getting skill files
    - Deleting skill files
    """

    def _get_system_collection(self) -> Any:
        """Get system skills collection lazily (must be implemented by subclass)"""
        raise NotImplementedError("Subclass must implement _get_system_collection")

    def _get_user_collection(self) -> Any:
        """Get user skills collection lazily (must be implemented by subclass)"""
        raise NotImplementedError("Subclass must implement _get_user_collection")

    async def sync_skill_files(
        self,
        skill_name: str,
        files: dict[str, str],
        user_id: Optional[str] = None,
    ) -> None:
        """
        Sync skill files to MongoDB files field.

        Files are stored directly in the skill document's files field.

        Args:
            skill_name: Skill name
            files: Dictionary of file path -> content
            user_id: User ID (None for system skills)
        """
        # Determine which collection to use
        if user_id is None or user_id == "system":
            collection = self._get_system_collection()
            query = {"name": skill_name}
        else:
            collection = self._get_user_collection()
            query = {"name": skill_name, "user_id": user_id}

        # Update files field
        await collection.update_one(
            query,
            {
                "$set": {
                    "files": files,
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            },
        )

    async def get_skill_files(
        self,
        skill_name: str,
        user_id: Optional[str] = None,
    ) -> dict[str, str]:
        """
        Get all files for a skill from MongoDB files field.

        Args:
            skill_name: Skill name
            user_id: User ID (None for system skills)

        Returns:
            Dictionary of file path -> content
        """
        # Determine which collection to use
        if user_id is None or user_id == "system":
            collection = self._get_system_collection()
            doc = await collection.find_one({"name": skill_name})
        else:
            collection = self._get_user_collection()
            doc = await collection.find_one({"name": skill_name, "user_id": user_id})

        if doc:
            return doc.get("files", {})
        return {}

    async def delete_skill_files(
        self,
        skill_name: str,
        user_id: Optional[str] = None,
    ) -> None:
        """
        Delete all files for a skill (clear files field).

        Args:
            skill_name: Skill name
            user_id: User ID (None for system skills)
        """
        # Determine which collection to use
        if user_id is None or user_id == "system":
            collection = self._get_system_collection()
            query = {"name": skill_name}
        else:
            collection = self._get_user_collection()
            query = {"name": skill_name, "user_id": user_id}

        # Clear files field
        await collection.update_one(
            query,
            {
                "$set": {
                    "files": {},
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            },
        )
