"""Revealed file index storage — tracks all files/projects revealed via agent tools."""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from src.infra.logging import get_logger
from src.kernel.config import settings

logger = get_logger(__name__)


class RevealedFileStorage:
    """MongoDB storage for revealed file records."""

    def __init__(self):
        self._collection = None

    @property
    def collection(self):
        if self._collection is None:
            from src.infra.storage.mongodb import get_mongo_client

            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            self._collection = db["revealed_files"]
        return self._collection

    async def ensure_indexes_if_needed(self):
        if not hasattr(self, "_indexes_ensured"):
            self._indexes_ensured = True
            task = asyncio.create_task(self._ensure_indexes())
            task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)

    async def _ensure_indexes(self):
        try:
            c = self.collection
            await c.create_index(
                [("user_id", 1), ("created_at", -1)],
                name="user_created_at_idx",
                background=True,
            )
            await c.create_index(
                [("user_id", 1), ("file_type", 1)],
                name="user_file_type_idx",
                background=True,
            )
            await c.create_index(
                [("user_id", 1), ("file_key", 1), ("trace_id", 1)],
                name="user_key_trace_unique_idx",
                unique=True,
                background=True,
            )
            await c.create_index(
                [("session_id", 1)],
                name="session_id_idx",
                background=True,
            )
            await c.create_index(
                [("user_id", 1), ("project_id", 1)],
                name="user_project_idx",
                background=True,
            )
        except Exception as e:
            logger.warning(f"Failed to create revealed_files indexes: {e}")

    async def upsert_record(
        self,
        user_id: str,
        file_key: str,
        trace_id: str,
        data: Dict[str, Any],
    ) -> None:
        """Insert or update a revealed file record (dedup by user_id + file_key + trace_id)."""
        await self.ensure_indexes_if_needed()
        try:
            await self.collection.update_one(
                {
                    "user_id": user_id,
                    "file_key": file_key,
                    "trace_id": trace_id,
                },
                {
                    "$setOnInsert": {
                        **data,
                        "created_at": data.get("created_at", datetime.now(timezone.utc)),
                    }
                },
                upsert=True,
            )
        except Exception as e:
            logger.warning(f"Failed to upsert revealed file record: {e}")

    async def _search_session_ids(self, search: str) -> list[str]:
        """Find session IDs whose name matches the search term."""
        try:
            from src.infra.storage.mongodb import get_mongo_client

            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            sessions_col = db[settings.MONGODB_SESSIONS_COLLECTION]
            docs = await sessions_col.find(
                {"name": {"$regex": search, "$options": "i"}},
                {"session_id": 1},
            ).to_list(length=50)
            return [d["session_id"] for d in docs if d.get("session_id")]
        except Exception as e:
            logger.warning(f"Failed to search sessions by name: {e}")
            return []

    async def toggle_favorite(self, user_id: str, file_id: str) -> bool:
        """Toggle is_favorite on a revealed file record. Returns new value."""
        await self.ensure_indexes_if_needed()
        from bson import ObjectId

        doc = await self.collection.find_one({"_id": ObjectId(file_id), "user_id": user_id})
        if not doc:
            raise ValueError(f"Revealed file {file_id} not found")
        new_val = not doc.get("is_favorite", False)
        await self.collection.update_one(
            {"_id": ObjectId(file_id)},
            {"$set": {"is_favorite": new_val}},
        )
        return new_val

    async def list_files(
        self,
        user_id: str,
        *,
        file_type: Optional[str] = None,
        session_id: Optional[str] = None,
        project_id: Optional[str] = None,
        search: Optional[str] = None,
        favorites_only: bool = False,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        skip: int = 0,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """List revealed files with pagination, filtering, and sorting."""
        await self.ensure_indexes_if_needed()

        query: Dict[str, Any] = {"user_id": user_id}
        if file_type:
            query["file_type"] = file_type
        if session_id:
            query["session_id"] = session_id
        if project_id == "none":
            query["project_id"] = None
        elif project_id:
            query["project_id"] = project_id
        if favorites_only:
            query["is_favorite"] = True
        if search:
            search_conditions: list[Dict[str, Any]] = [
                {"file_name": {"$regex": search, "$options": "i"}},
                {"description": {"$regex": search, "$options": "i"}},
            ]
            # Also search by session_name (project_name)
            matching_session_ids = await self._search_session_ids(search)
            if matching_session_ids:
                search_conditions.append({"session_id": {"$in": matching_session_ids}})
            query["$or"] = search_conditions

        sort_dir = -1 if sort_order == "desc" else 1
        if sort_by == "file_name":
            sort_key = "file_name"
        elif sort_by == "file_size":
            sort_key = "file_size"
        else:
            sort_key = "created_at"

        total = await self.collection.count_documents(query)
        cursor = (
            self.collection.find(query, {"project_meta": 0})
            .sort(sort_key, sort_dir)
            .skip(skip)
            .limit(limit)
        )
        items = await cursor.to_list(length=limit)

        # Enrich with session_name from sessions collection
        session_ids = list({item["session_id"] for item in items if item.get("session_id")})
        session_names: Dict[str, Optional[str]] = {}
        if session_ids:
            from src.infra.storage.mongodb import get_mongo_client

            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            sessions_col = db[settings.MONGODB_SESSIONS_COLLECTION]
            sessions = await sessions_col.find(
                {"session_id": {"$in": session_ids}},
                {"session_id": 1, "name": 1},
            ).to_list(length=len(session_ids))
            session_names = {s["session_id"]: s.get("name") for s in sessions}

        for item in items:
            item["session_name"] = session_names.get(item.get("session_id"))
            # Convert ObjectId and datetime for JSON serialization
            if "_id" in item:
                item["id"] = str(item.pop("_id"))
            if "created_at" in item and isinstance(item["created_at"], datetime):
                item["created_at"] = item["created_at"].isoformat()

        return {"items": items, "total": total, "skip": skip, "limit": limit}

    async def get_stats(self, user_id: str) -> Dict[str, int]:
        """Get file count per type for a user."""
        await self.ensure_indexes_if_needed()
        pipeline = [
            {"$match": {"user_id": user_id}},
            {"$group": {"_id": "$file_type", "count": {"$sum": 1}}},
        ]
        results = await self.collection.aggregate(pipeline).to_list(length=20)
        stats = {}
        for r in results:
            stats[r["_id"]] = r["count"]
        return stats

    async def list_files_grouped_by_session(
        self,
        user_id: str,
        *,
        file_type: Optional[str] = None,
        project_id: Optional[str] = None,
        search: Optional[str] = None,
        favorites_only: bool = False,
        sort_by: str = "created_at",
        sort_order: str = "desc",
        skip: int = 0,
        limit: int = 20,
    ) -> Dict[str, Any]:
        """List revealed files grouped by session, with session-level pagination."""
        await self.ensure_indexes_if_needed()

        # Build base query (same as list_files minus session_id filter)
        query: Dict[str, Any] = {"user_id": user_id, "session_id": {"$ne": None}}
        if file_type:
            query["file_type"] = file_type
        if project_id == "none":
            query["project_id"] = None
        elif project_id:
            query["project_id"] = project_id
        if favorites_only:
            query["is_favorite"] = True

        if search:
            search_conditions: list[Dict[str, Any]] = [
                {"file_name": {"$regex": search, "$options": "i"}},
                {"description": {"$regex": search, "$options": "i"}},
            ]
            matching_session_ids = await self._search_session_ids(search)
            if matching_session_ids:
                search_conditions.append({"session_id": {"$in": matching_session_ids}})
            query["$or"] = search_conditions

        # Determine sort for the "latest file in session"
        sort_dir = -1 if sort_order == "desc" else 1
        if sort_by in ("file_name", "file_size"):
            file_sort_key = sort_by
        else:
            file_sort_key = "created_at"

        # Aggregate: one doc per session with the latest matching file timestamp
        pipeline: list[Dict[str, Any]] = [
            {"$match": query},
            {
                "$group": {
                    "_id": "$session_id",
                    "latest_file_at": {"$max": "$created_at"},
                    "file_count": {"$sum": 1},
                }
            },
        ]
        if file_sort_key == "created_at":
            pipeline.append({"$sort": {"latest_file_at": sort_dir}})
        elif file_sort_key == "file_name":
            # Sort sessions by the alphabetically first/last file name within the session
            pipeline.append(
                {
                    "$lookup": {
                        "from": self.collection.name,
                        "let": {"sid": "$_id"},
                        "pipeline": [
                            {
                                "$match": {
                                    "$expr": {
                                        "$and": [
                                            {"$eq": ["$session_id", "$$sid"]},
                                            {"$eq": ["$user_id", user_id]},
                                        ]
                                    }
                                }
                            },
                            {"$sort": {"file_name": sort_dir}},
                            {"$limit": 1},
                            {"$project": {"file_name": 1}},
                        ],
                        "as": "_name_sample",
                    }
                }
            )
            pipeline.append(
                {"$unwind": {"path": "$_name_sample", "preserveNullAndEmptyArrays": True}}
            )
            pipeline.append({"$sort": {"_name_sample.file_name": sort_dir}})
        elif file_sort_key == "file_size":
            pipeline.append(
                {
                    "$lookup": {
                        "from": self.collection.name,
                        "let": {"sid": "$_id"},
                        "pipeline": [
                            {
                                "$match": {
                                    "$expr": {
                                        "$and": [
                                            {"$eq": ["$session_id", "$$sid"]},
                                            {"$eq": ["$user_id", user_id]},
                                        ]
                                    }
                                }
                            },
                            {"$sort": {"file_size": sort_dir}},
                            {"$limit": 1},
                            {"$project": {"file_size": 1}},
                        ],
                        "as": "_size_sample",
                    }
                }
            )
            pipeline.append(
                {"$unwind": {"path": "$_size_sample", "preserveNullAndEmptyArrays": True}}
            )
            pipeline.append({"$sort": {"_size_sample.file_size": sort_dir}})

        # Count distinct sessions (before skip/limit)
        count_pipeline = pipeline.copy()
        count_pipeline.append({"$count": "total"})
        count_result = await self.collection.aggregate(count_pipeline).to_list(length=1)
        total_sessions = count_result[0]["total"] if count_result else 0

        # Paginate sessions
        pipeline.append({"$skip": skip})
        pipeline.append({"$limit": limit})

        session_results = await self.collection.aggregate(pipeline).to_list(length=limit)
        session_ids = [r["_id"] for r in session_results]

        if not session_ids:
            return {"sessions": [], "total_sessions": total_sessions, "skip": skip, "limit": limit}

        # Fetch all matching files for these sessions (apply same base query + session_id filter)
        file_query = dict(query)
        file_query["session_id"] = {"$in": session_ids}

        file_sort_dir = -1 if sort_order == "desc" else 1
        if sort_by == "file_name":
            file_sort = [("session_id", 1), ("file_name", file_sort_dir)]
        elif sort_by == "file_size":
            file_sort = [("session_id", 1), ("file_size", file_sort_dir)]
        else:
            file_sort = [("session_id", 1), ("created_at", file_sort_dir)]

        files_cursor = self.collection.find(file_query, {"project_meta": 0}).sort(file_sort)
        raw_files = await files_cursor.to_list(length=500)

        # Enrich with session names
        from src.infra.storage.mongodb import get_mongo_client

        client = get_mongo_client()
        db = client[settings.MONGODB_DB]
        sessions_col = db[settings.MONGODB_SESSIONS_COLLECTION]
        sessions = await sessions_col.find(
            {"session_id": {"$in": session_ids}},
            {"session_id": 1, "name": 1},
        ).to_list(length=len(session_ids))
        name_map: Dict[str, Optional[str]] = {s["session_id"]: s.get("name") for s in sessions}

        # Group files by session
        files_by_session: Dict[str, list] = {sid: [] for sid in session_ids}
        for item in raw_files:
            sid = item.get("session_id")
            item["session_name"] = name_map.get(sid)
            if "_id" in item:
                item["id"] = str(item.pop("_id"))
            if "created_at" in item and isinstance(item["created_at"], datetime):
                item["created_at"] = item["created_at"].isoformat()
            if sid in files_by_session:
                files_by_session[sid].append(item)

        count_map = {r["_id"]: r["file_count"] for r in session_results}
        sessions_list = []
        for sid in session_ids:
            sessions_list.append(
                {
                    "session_id": sid,
                    "session_name": name_map.get(sid),
                    "file_count": count_map[sid],
                    "files": files_by_session[sid],
                }
            )

        return {
            "sessions": sessions_list,
            "total_sessions": total_sessions,
            "skip": skip,
            "limit": limit,
        }

    async def get_user_sessions(self, user_id: str) -> list[Dict[str, Any]]:
        """Get distinct session_id + session_name pairs for a user's revealed files."""
        await self.ensure_indexes_if_needed()
        pipeline = [
            {"$match": {"user_id": user_id, "session_id": {"$ne": None}}},
            {"$group": {"_id": "$session_id", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
        results = await self.collection.aggregate(pipeline).to_list(length=100)
        session_ids = [r["_id"] for r in results]

        if not session_ids:
            return []

        # Enrich with session names
        from src.infra.storage.mongodb import get_mongo_client

        client = get_mongo_client()
        db = client[settings.MONGODB_DB]
        sessions_col = db[settings.MONGODB_SESSIONS_COLLECTION]
        sessions = await sessions_col.find(
            {"session_id": {"$in": session_ids}},
            {"session_id": 1, "name": 1},
        ).to_list(length=len(session_ids))
        name_map: Dict[str, Optional[str]] = {s["session_id"]: s.get("name") for s in sessions}

        count_map = {r["_id"]: r["count"] for r in results}
        items = []
        for sid in session_ids:
            items.append(
                {
                    "session_id": sid,
                    "session_name": name_map.get(sid),
                    "file_count": count_map[sid],
                }
            )
        return items

    async def delete_by_session(self, session_id: str) -> int:
        """Delete all revealed file records for a session."""
        await self.ensure_indexes_if_needed()
        result = await self.collection.delete_many({"session_id": session_id})
        return result.deleted_count

    async def update_project_id_by_session(self, session_id: str, project_id: Optional[str]) -> int:
        """Update project_id on all revealed files belonging to a session."""
        await self.ensure_indexes_if_needed()
        result = await self.collection.update_many(
            {"session_id": session_id},
            {"$set": {"project_id": project_id}},
        )
        return result.modified_count


# Singleton
_revealed_file_storage: Optional[RevealedFileStorage] = None


def get_revealed_file_storage() -> RevealedFileStorage:
    global _revealed_file_storage
    if _revealed_file_storage is None:
        _revealed_file_storage = RevealedFileStorage()
    return _revealed_file_storage
