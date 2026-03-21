"""
Skill files mixin for file management operations

Files are stored in a separate `skill_files` collection (one document per file)
instead of embedded in the skill document. This avoids the 16MB BSON limit,
eliminates read-modify-write races, and allows single-file queries.
"""

from datetime import datetime, timezone
from typing import Any, Optional


class SkillFilesMixin:
    """
    Mixin providing file management functionality for skills.

    Files are stored in a separate `skill_files` collection:
    {
        "skill_name": "ppt-generator",
        "user_id": "user123" | "system",
        "file_path": "references/design_prompt.md",
        "content": "...",
        "created_at": "ISO8601",
        "updated_at": "ISO8601"
    }
    """

    def _get_skill_files_collection(self) -> Any:
        """Get skill_files collection lazily (must be implemented by subclass)"""
        raise NotImplementedError("Subclass must implement _get_skill_files_collection")

    def _resolve_user_id(self, user_id: Optional[str]) -> str:
        """Normalize user_id: None means system skills."""
        return user_id if user_id is not None and user_id != "system" else "system"

    async def get_skill_files(
        self,
        skill_name: str,
        user_id: Optional[str] = None,
    ) -> dict[str, str]:
        """
        Get all files for a skill from the skill_files collection.

        Returns:
            Dictionary of file_path -> content
        """
        collection = self._get_skill_files_collection()
        resolved_uid = self._resolve_user_id(user_id)

        files: dict[str, str] = {}
        async for doc in collection.find({"skill_name": skill_name, "user_id": resolved_uid}):
            files[doc["file_path"]] = doc["content"]
        return files

    async def get_skill_file(
        self,
        skill_name: str,
        file_path: str,
        user_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Get a single file's content from the skill_files collection.

        Returns:
            File content string, or None if not found
        """
        collection = self._get_skill_files_collection()
        resolved_uid = self._resolve_user_id(user_id)

        doc = await collection.find_one(
            {"skill_name": skill_name, "user_id": resolved_uid, "file_path": file_path}
        )
        if doc:
            return doc["content"]
        return None

    async def set_skill_file(
        self,
        skill_name: str,
        file_path: str,
        content: str,
        user_id: Optional[str] = None,
    ) -> None:
        """
        Atomically set a single file using upsert.

        Uses upsert on the compound key (skill_name, user_id, file_path) so
        parallel writes to different files never conflict.
        """
        collection = self._get_skill_files_collection()
        resolved_uid = self._resolve_user_id(user_id)
        now = datetime.now(timezone.utc).isoformat()

        await collection.update_one(
            {"skill_name": skill_name, "user_id": resolved_uid, "file_path": file_path},
            {
                "$set": {
                    "content": content,
                    "updated_at": now,
                },
                "$setOnInsert": {
                    "created_at": now,
                },
            },
            upsert=True,
        )

    async def delete_skill_file(
        self,
        skill_name: str,
        file_path: str,
        user_id: Optional[str] = None,
    ) -> None:
        """Delete a single file from the skill_files collection."""
        collection = self._get_skill_files_collection()
        resolved_uid = self._resolve_user_id(user_id)

        await collection.delete_one(
            {"skill_name": skill_name, "user_id": resolved_uid, "file_path": file_path}
        )

    async def sync_skill_files(
        self,
        skill_name: str,
        files: dict[str, str],
        user_id: Optional[str] = None,
    ) -> None:
        """
        Replace all files for a skill (bulk replace).

        Uses a single ordered bulk write: delete removed files first, then
        upsert all new/updated files. This avoids the race window of a
        separate delete_many + insert_many.
        """
        if not files:
            return

        collection = self._get_skill_files_collection()
        resolved_uid = self._resolve_user_id(user_id)
        now = datetime.now(timezone.utc).isoformat()

        # Fetch existing file paths to determine which ones to remove
        existing_paths = set(await self.list_skill_file_paths(skill_name, user_id))
        new_paths = set(files.keys())
        removed_paths = existing_paths - new_paths

        from pymongo import DeleteOne, UpdateOne

        operations: list = []

        # Delete files that are no longer in the new set
        for path in removed_paths:
            operations.append(
                DeleteOne({"skill_name": skill_name, "user_id": resolved_uid, "file_path": path})
            )

        # Upsert all new files
        for file_path, content in files.items():
            operations.append(
                UpdateOne(
                    {"skill_name": skill_name, "user_id": resolved_uid, "file_path": file_path},
                    {
                        "$set": {
                            "content": content,
                            "updated_at": now,
                        },
                        "$setOnInsert": {
                            "created_at": now,
                        },
                    },
                    upsert=True,
                )
            )

        if operations:
            await collection.bulk_write(operations, ordered=True)

    async def delete_skill_files(
        self,
        skill_name: str,
        user_id: Optional[str] = None,
    ) -> None:
        """Delete all files for a skill from the skill_files collection."""
        collection = self._get_skill_files_collection()
        resolved_uid = self._resolve_user_id(user_id)

        await collection.delete_many({"skill_name": skill_name, "user_id": resolved_uid})

    async def list_skill_file_paths(
        self,
        skill_name: str,
        user_id: Optional[str] = None,
    ) -> list[str]:
        """
        List file paths for a skill without loading content.

        Returns:
            List of file_path strings
        """
        collection = self._get_skill_files_collection()
        resolved_uid = self._resolve_user_id(user_id)

        paths: list[str] = []
        cursor = collection.find(
            {"skill_name": skill_name, "user_id": resolved_uid},
            {"file_path": 1},
        )
        async for doc in cursor:
            paths.append(doc["file_path"])
        return paths

    async def batch_get_skill_files(
        self,
        skill_keys: list[tuple[str, str]],
    ) -> dict[tuple[str, str], dict[str, str]]:
        """
        Batch-fetch files for multiple skills in minimal round-trips.

        Args:
            skill_keys: List of (skill_name, user_id) tuples

        Returns:
            Dict mapping (skill_name, user_id) -> {file_path: content}
        """
        if not skill_keys:
            return {}

        collection = self._get_skill_files_collection()

        # Build $or query with deduplicated resolved user_ids
        seen_clauses: set[tuple[str, str]] = set()
        or_clauses = []
        for skill_name, user_id in skill_keys:
            resolved_uid = self._resolve_user_id(user_id)
            clause_key = (skill_name, resolved_uid)
            if clause_key not in seen_clauses:
                seen_clauses.add(clause_key)
                or_clauses.append({"skill_name": skill_name, "user_id": resolved_uid})

        result: dict[tuple[str, str], dict[str, str]] = {}
        async for doc in collection.find({"$or": or_clauses}):
            key = (doc["skill_name"], doc["user_id"])
            if key not in result:
                result[key] = {}
            result[key][doc["file_path"]] = doc["content"]

        return result
