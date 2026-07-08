"""
会话存储层
"""

import asyncio
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from bson import ObjectId

from src.infra.async_utils import run_blocking_io
from src.infra.session.favorites import (
    is_session_favorite,
    normalize_session_metadata,
)
from src.infra.session.search_index import (
    SESSION_SEARCH_INDEX_VERSION,
    append_message_to_search_index,
    build_backfilled_search_index,
    build_search_preview,
    build_search_query_terms,
    compose_session_search_index,
    merge_search_state,
)
from src.infra.utils.datetime import utc_now
from src.kernel.config import settings
from src.kernel.schemas.session import Session, SessionCreate, SessionUpdate

SESSION_BATCH_LOOKUP_LIMIT = 100
SESSION_LIST_LOOKUP_LIMIT = 100


def _next_search_index_timestamp(previous: datetime | None) -> datetime:
    current = utc_now()
    if previous is not None and current <= previous:
        return previous + timedelta(microseconds=1)
    return current


class SessionStorage:
    """
    会话存储类

    使用 MongoDB 存储会话数据。
    """

    SEARCH_BACKFILL_SKIP_RECENT_SECONDS = 120
    SEARCH_UPDATE_MAX_RETRIES = 3
    SEARCH_BACKFILL_MAX_USER_MESSAGES = 1000
    SEARCH_BACKFILL_BATCH_MAX = 100
    _indexes_done = False
    _indexes_task: asyncio.Task | None = None
    _indexes_lock: asyncio.Lock | None = None

    def __init__(self):
        self._collection = None

    @property
    def collection(self):
        """延迟加载 MongoDB 集合"""
        if self._collection is None:
            from src.infra.storage.mongodb import get_mongo_client

            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            self._collection = db[settings.MONGODB_SESSIONS_COLLECTION]
        return self._collection

    async def ensure_indexes_if_needed(self):
        """Ensure session indexes exist."""
        cls = type(self)
        if cls._indexes_done:
            return

        if cls._indexes_lock is None:
            cls._indexes_lock = asyncio.Lock()

        async with cls._indexes_lock:
            if cls._indexes_done:
                return
            if cls._indexes_task is None or cls._indexes_task.cancelled():
                cls._indexes_task = asyncio.create_task(self._ensure_indexes())
            task = cls._indexes_task

        succeeded = await task
        if succeeded:
            cls._indexes_done = True
            return

        async with cls._indexes_lock:
            if cls._indexes_task is task:
                cls._indexes_task = None

    async def _ensure_indexes(self) -> bool:
        try:
            collection = self.collection
            await collection.create_index(
                [("user_id", 1), ("is_active", 1), ("updated_at", -1)],
                name="user_status_updated_idx",
                background=True,
            )
            await collection.create_index(
                [("user_id", 1), ("metadata.project_id", 1), ("updated_at", -1)],
                name="user_project_updated_idx",
                background=True,
            )
            await collection.create_index(
                [("session_id", 1)],
                name="session_id_idx",
                background=True,
                sparse=True,
            )
            await collection.create_index(
                [("user_id", 1), ("search_terms", 1), ("updated_at", -1)],
                name="user_search_terms_updated_idx",
                background=True,
            )
            await collection.create_index(
                [("search_index_version", 1), ("updated_at", -1)],
                name="search_index_version_updated_idx",
                background=True,
            )
            await collection.create_index(
                [("search_index_updated_at", 1)],
                name="search_index_updated_at_idx",
                background=True,
                sparse=True,
            )
            await collection.create_index(
                [("metadata.scheduled_task_id", 1), ("updated_at", -1)],
                name="scheduled_task_sessions_idx",
                background=True,
                sparse=True,
            )
            return True
        except Exception:
            # Search index creation is best-effort and should not block the app.
            return False

    @staticmethod
    def _build_session(
        session_dict: dict[str, Any],
        favorites_project_id: str | None = None,
    ) -> Session:
        """Convert a Mongo document into a normalized Session model."""
        normalized = dict(session_dict)
        normalized["metadata"] = normalize_session_metadata(
            normalized.get("metadata"),
            favorites_project_id,
        )
        normalized["id"] = normalized.get("session_id") or str(normalized.pop("_id"))
        if "session_id" in normalized and normalized["id"] == normalized["session_id"]:
            normalized.pop("_id", None)
        return Session(**normalized)

    async def create(
        self,
        session_data: SessionCreate,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Session:
        """创建会话"""
        await self.ensure_indexes_if_needed()
        now = utc_now()

        # 使用自定义 session_id 或生成新的
        actual_session_id = session_id or None
        search_payload = compose_session_search_index(
            session_name=session_data.name,
            message_search_terms=[],
            search_text="",
            latest_user_message="",
        )

        session_dict = {
            "name": session_data.name,
            "metadata": session_data.metadata,
            "user_id": user_id,
            "agent_id": session_data.metadata.get("agent_id", "fast"),
            "created_at": now,
            "updated_at": now,
            "is_active": True,
            "name_search_terms": search_payload.name_search_terms,
            "message_search_terms": search_payload.message_search_terms,
            "search_terms": search_payload.search_terms,
            "search_text": search_payload.search_text,
            "latest_user_message": search_payload.latest_user_message,
            "search_index_version": search_payload.search_index_version,
            "search_index_updated_at": now,
        }

        # 如果提供了自定义 session_id，存储它
        if actual_session_id:
            session_dict["session_id"] = actual_session_id

        result = await self.collection.insert_one(session_dict)

        # 返回时使用自定义 session_id 作为 id 字段
        session_dict["id"] = actual_session_id or str(result.inserted_id)

        return Session(**session_dict)

    async def get_by_session_id(self, session_id: str) -> Optional[Session]:
        """通过自定义 session_id 获取会话"""
        await self.ensure_indexes_if_needed()
        session_dict = await self.collection.find_one({"session_id": session_id})

        if not session_dict:
            return None

        return self._build_session(session_dict)

    async def get_by_session_ids(self, session_ids: list[str]) -> Dict[str, Session]:
        """通过 session_id 列表批量获取会话，返回 {session_id: Session} 映射"""
        if not session_ids:
            return {}
        await self.ensure_indexes_if_needed()
        unique_ids = []
        seen_ids = set()
        for session_id in session_ids:
            if session_id in seen_ids:
                continue
            seen_ids.add(session_id)
            unique_ids.append(session_id)
            if len(unique_ids) >= SESSION_BATCH_LOOKUP_LIMIT:
                break
        cursor = self.collection.find({"session_id": {"$in": unique_ids}})
        result: Dict[str, Session] = {}
        async for doc in cursor:
            session = self._build_session(doc)
            result[session.id] = session
        return result

    async def update_user_id(self, session_id: str, user_id: str) -> bool:
        """通过自定义 session_id 更新 user_id"""
        await self.ensure_indexes_if_needed()
        result = await self.collection.update_one(
            {"session_id": session_id, "user_id": None},
            {"$set": {"user_id": user_id, "updated_at": utc_now()}},
        )
        return result.modified_count > 0

    async def get_by_id(self, session_id: str) -> Optional[Session]:
        """通过 ID 获取会话"""
        await self.ensure_indexes_if_needed()
        try:
            session_dict = await self.collection.find_one({"_id": ObjectId(session_id)})
        except Exception:
            return None

        if not session_dict:
            return None

        return self._build_session(session_dict)

    async def update(self, session_id: str, session_data: SessionUpdate) -> Optional[Session]:
        """更新会话（支持自定义 session_id 或 ObjectId）"""
        await self.ensure_indexes_if_needed()
        update_dict: dict = {"updated_at": utc_now()}

        existing_doc = None
        if session_data.name is not None:
            existing_doc = await self._find_doc(
                session_id,
                {
                    "name": 1,
                    "message_search_terms": 1,
                },
            )

        if session_data.name is not None:
            update_dict["name"] = session_data.name
            search_payload = compose_session_search_index(
                session_name=session_data.name,
                message_search_terms=(existing_doc or {}).get("message_search_terms") or [],
                search_text="",
                latest_user_message="",
            )
            update_dict["name_search_terms"] = search_payload.name_search_terms
            update_dict["search_terms"] = search_payload.search_terms
            update_dict["search_index_version"] = SESSION_SEARCH_INDEX_VERSION
            update_dict["search_index_updated_at"] = utc_now()

        if session_data.metadata is not None:
            # 使用深度合并而非直接覆盖，保留未指定的 metadata 字段
            for key, value in session_data.metadata.items():
                update_dict[f"metadata.{key}"] = value

        # 优先使用自定义 session_id 查询
        result = await self.collection.find_one_and_update(
            {"session_id": session_id},
            {"$set": update_dict},
            return_document=True,
        )

        # 如果没找到，尝试 ObjectId
        if not result:
            try:
                result = await self.collection.find_one_and_update(
                    {"_id": ObjectId(session_id)},
                    {"$set": update_dict},
                    return_document=True,
                )
            except Exception:
                return None

        if not result:
            return None

        return self._build_session(result)

    async def update_metadata_only(self, session_id: str, metadata: dict[str, Any]) -> bool:
        """Update session metadata without fetching and rebuilding the full document."""
        await self.ensure_indexes_if_needed()
        if not metadata:
            return True

        update_dict: dict[str, Any] = {"updated_at": utc_now()}
        for key, value in metadata.items():
            update_dict[f"metadata.{key}"] = value

        result = await self.collection.update_one(
            {"session_id": session_id},
            {"$set": update_dict},
        )
        if result.matched_count > 0:
            return True

        try:
            result = await self.collection.update_one(
                {"_id": ObjectId(session_id)},
                {"$set": update_dict},
            )
            return result.matched_count > 0
        except Exception:
            return False

    async def delete(self, session_id: str) -> bool:
        """删除会话（支持自定义 session_id 或 ObjectId）"""
        await self.ensure_indexes_if_needed()
        # 优先使用自定义 session_id
        result = await self.collection.delete_one({"session_id": session_id})
        if result.deleted_count > 0:
            return True

        try:
            result = await self.collection.delete_one({"_id": ObjectId(session_id)})
            return result.deleted_count > 0
        except Exception:
            return False

    async def list_sessions(
        self,
        user_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 100,
        is_active: Optional[bool] = None,
        project_id: Optional[str] = None,
        search: Optional[str] = None,
        favorites_only: bool = False,
        favorites_project_id: str | None = None,
    ) -> tuple[list[Session], int]:
        """列出会话，返回 (sessions, total_count)

        Args:
            user_id: 用户ID，如果提供则只返回该用户的会话
                     None 表示不过滤（仅管理员使用）
            project_id: 项目ID过滤
                       - None: 不过滤项目
                       - "none": 只返回未分类的会话（没有project_id）
                       - 其他值: 只返回该项目内的会话
            search: 搜索关键词，模糊匹配会话名称
        """
        await self.ensure_indexes_if_needed()
        skip = max(int(skip or 0), 0)
        limit = min(max(int(limit or 1), 1), SESSION_LIST_LOOKUP_LIMIT)
        query: dict[str, Any] = {}
        query["metadata.hidden_from_conversation_list"] = {"$ne": True}
        query["session_id"] = {"$not": {"$regex": "^sch_"}}
        if user_id is not None:
            # 严格匹配用户ID，空字符串也会被当作过滤条件
            query["user_id"] = user_id
        if is_active is not None:
            query["is_active"] = is_active

        if search:
            search_terms = build_search_query_terms(search)
            if search_terms:
                query["search_terms"] = {"$all": search_terms}
            else:
                query["session_id"] = {"$in": []}

        # Project filter
        if project_id == "none":
            # Unclassified conversation list excludes scheduled task sessions;
            # those are shown through the scheduled task drill-down view.
            query["metadata.project_id"] = None
            query["metadata.scheduled_task_id"] = None
        elif project_id is not None:
            query["metadata.project_id"] = project_id

        if favorites_only:
            favorite_query: list[dict[str, Any]] = [{"metadata.is_favorite": True}]
            if favorites_project_id:
                favorite_query.append({"metadata.project_id": favorites_project_id})
            if "$or" in query:
                query = {
                    "$and": [
                        {k: v for k, v in query.items() if k != "$or"},
                        {"$or": query["$or"]},
                        {"$or": favorite_query},
                    ]
                }
            else:
                query["$or"] = favorite_query

        # Get total count
        total = await self.collection.count_documents(query)

        cursor = self.collection.find(query).skip(skip).limit(limit).sort("updated_at", -1)
        sessions = []

        for session_dict in await cursor.to_list(length=limit):
            session = self._build_session(session_dict, favorites_project_id)
            if search:
                match_preview = build_search_preview(session_dict.get("search_text"), search)
                if match_preview:
                    session = session.model_copy(
                        update={
                            "metadata": {
                                **session.metadata,
                                "search_match": match_preview,
                                "search_match_source": "user_message",
                            }
                        }
                    )
            sessions.append(session)

        return sessions, total

    async def list_sessions_for_task(
        self,
        scheduled_task_id: str,
        user_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[Session], int]:
        """List sessions created by a scheduled task.

        Unlike list_sessions(), this does NOT filter out
        hidden_from_conversation_list — scheduled task sessions
        are intentionally hidden from the regular sidebar but
        should be visible in the task drill-down view.
        """
        await self.ensure_indexes_if_needed()
        skip = max(int(skip or 0), 0)
        limit = min(max(int(limit or 1), 1), SESSION_LIST_LOOKUP_LIMIT)
        query: dict[str, Any] = {
            "user_id": user_id,
            "metadata.scheduled_task_id": scheduled_task_id,
        }
        total = await self.collection.count_documents(query)
        cursor = self.collection.find(query).skip(skip).limit(limit).sort("updated_at", -1)
        sessions = []
        for session_dict in await cursor.to_list(length=limit):
            session = self._build_session(session_dict)
            sessions.append(session)
        return sessions, total

    async def get_unread_counts_for_scheduled_tasks(
        self,
        user_id: str,
        scheduled_task_ids: list[str],
    ) -> dict[str, int]:
        """Return unread totals keyed by scheduled task id."""
        await self.ensure_indexes_if_needed()
        if not scheduled_task_ids:
            return {}

        pipeline = [
            {
                "$match": {
                    "user_id": user_id,
                    "metadata.scheduled_task_id": {"$in": scheduled_task_ids},
                    "unread_count": {"$gt": 0},
                }
            },
            {
                "$group": {
                    "_id": "$metadata.scheduled_task_id",
                    "unread_count": {"$sum": "$unread_count"},
                }
            },
        ]

        counts: dict[str, int] = {}
        async for item in self.collection.aggregate(pipeline):
            task_id = item.get("_id")
            if isinstance(task_id, str):
                counts[task_id] = int(item.get("unread_count") or 0)
        return counts

    async def get(self, session_id: str) -> Optional[Session]:
        """获取会话 (兼容旧 API)"""
        return await self.get_by_id(session_id)

    async def clear_project_id(self, project_id: str, user_id: str) -> int:
        """Clear project_id for all sessions in a project (when project is deleted).

        Args:
            project_id: The project ID to clear
            user_id: The user ID to filter sessions

        Returns:
            Number of modified sessions
        """
        await self.ensure_indexes_if_needed()
        result = await self.collection.update_many(
            {"user_id": user_id, "metadata.project_id": project_id},
            {"$set": {"metadata.project_id": None, "updated_at": utc_now()}},
        )
        return result.modified_count

    async def increment_unread_count(self, session_id: str) -> bool:
        """递增会话未读计数"""
        await self.ensure_indexes_if_needed()
        result = await self.collection.update_one(
            {"session_id": session_id},
            {"$inc": {"unread_count": 1}, "$set": {"updated_at": utc_now()}},
        )
        return result.modified_count > 0

    async def mark_read(self, session_id: str) -> bool:
        """将会话标记为已读（清除未读计数）"""
        await self.ensure_indexes_if_needed()
        result = await self.collection.update_one(
            {"session_id": session_id},
            {"$set": {"unread_count": 0}},
        )
        return result.modified_count > 0

    async def mark_all_read(
        self,
        user_id: str,
        project_id: str | None = None,
        scheduled_task_id: str | None = None,
    ) -> int:
        """批量将会话标记为已读（清除未读计数），支持按项目或定时任务过滤。"""
        await self.ensure_indexes_if_needed()
        query: dict[str, Any] = {"user_id": user_id, "unread_count": {"$gt": 0}}
        if project_id:
            query["metadata.project_id"] = project_id
        if scheduled_task_id:
            query["metadata.scheduled_task_id"] = scheduled_task_id
        result = await self.collection.update_many(
            query,
            {"$set": {"unread_count": 0, "updated_at": utc_now()}},
        )
        return result.modified_count

    async def delete_by_project(self, project_id: str, user_id: str) -> int:
        """Delete all sessions in a project.

        Args:
            project_id: The project ID
            user_id: The user ID (for ownership verification)

        Returns:
            Number of deleted sessions
        """
        await self.ensure_indexes_if_needed()
        result = await self.collection.delete_many(
            {"user_id": user_id, "metadata.project_id": project_id},
        )
        return result.deleted_count

    async def list_ids_by_project(self, project_id: str, user_id: str) -> list[str]:
        """List session identifiers for all sessions in a project."""
        await self.ensure_indexes_if_needed()
        cursor = self.collection.find(
            {"user_id": user_id, "metadata.project_id": project_id},
            {"session_id": 1, "_id": 1},
        )
        session_ids: list[str] = []
        async for doc in cursor:
            session_ids.append(doc.get("session_id") or str(doc["_id"]))
        return session_ids

    async def move_to_project(
        self, session_id: str, user_id: str, project_id: Optional[str]
    ) -> Optional[Session]:
        """Move a session to a project.

        Args:
            session_id: The session ID to move
            user_id: The user ID (for ownership verification)
            project_id: The target project ID, or None to uncategorize

        Returns:
            Updated Session if found and updated, None otherwise
        """
        update_dict = {
            "updated_at": utc_now(),
            "metadata.project_id": project_id,
        }

        # Try custom session_id first
        result = await self.collection.find_one_and_update(
            {"session_id": session_id, "user_id": user_id},
            {"$set": update_dict},
            return_document=True,
        )

        # If not found, try ObjectId
        if not result:
            try:
                result = await self.collection.find_one_and_update(
                    {"_id": ObjectId(session_id), "user_id": user_id},
                    {"$set": update_dict},
                    return_document=True,
                )
            except Exception:
                return None

        if not result:
            return None

        return self._build_session(result)

    async def append_user_message_search_content(self, session_id: str, content: str) -> bool:
        """Persist user-message search terms and preview text on the session document."""
        await self.ensure_indexes_if_needed()
        for _ in range(self.SEARCH_UPDATE_MAX_RETRIES):
            existing_doc = await self._find_doc(
                session_id,
                {
                    "name": 1,
                    "message_search_terms": 1,
                    "search_text": 1,
                    "updated_at": 1,
                    "search_index_updated_at": 1,
                },
            )
            if not existing_doc:
                return False

            payload = append_message_to_search_index(
                session_name=existing_doc.get("name"),
                existing_message_search_terms=existing_doc.get("message_search_terms") or [],
                existing_search_text=existing_doc.get("search_text"),
                latest_user_message=content,
            )
            update_dict = {
                "name_search_terms": payload.name_search_terms,
                "message_search_terms": payload.message_search_terms,
                "search_terms": payload.search_terms,
                "search_text": payload.search_text,
                "latest_user_message": payload.latest_user_message,
                "search_index_version": payload.search_index_version,
                "search_index_updated_at": _next_search_index_timestamp(
                    existing_doc.get("search_index_updated_at")
                ),
            }
            cas_field, cas_value = self._get_search_index_cas(existing_doc)
            result = await self._update_doc(
                session_id,
                {"$set": update_dict},
                expected_cas_field=cas_field,
                expected_cas_value=cas_value,
            )
            if result.modified_count > 0:
                return True
        return False

    async def rebuild_search_index(self, session_id: str) -> bool:
        """Rebuild session search data from persisted user:message events."""
        await self.ensure_indexes_if_needed()
        existing_doc = await self._find_doc(
            session_id,
            {
                "name": 1,
            },
        )
        if not existing_doc:
            return False

        from src.infra.session.trace_storage import get_trace_storage

        trace_storage = get_trace_storage()
        events = await trace_storage.get_session_events(
            session_id,
            event_types=["user:message"],
            completed_only=False,
            max_events=self.SEARCH_BACKFILL_MAX_USER_MESSAGES,
        )
        user_messages = [
            data.get("content", "").strip()
            for event in events
            if isinstance((data := event.get("data")), dict)
            and isinstance(data.get("content"), str)
            and data.get("content", "").strip()
        ]

        payload = await run_blocking_io(
            build_backfilled_search_index,
            session_name=existing_doc.get("name"),
            user_messages=user_messages,
        )
        for _ in range(self.SEARCH_UPDATE_MAX_RETRIES):
            current_doc = await self._find_doc(
                session_id,
                {
                    "name": 1,
                    "message_search_terms": 1,
                    "search_text": 1,
                    "latest_user_message": 1,
                    "updated_at": 1,
                    "search_index_updated_at": 1,
                },
            )
            if not current_doc:
                return False

            merged = merge_search_state(
                session_name=current_doc.get("name") or existing_doc.get("name"),
                base_message_terms=payload.message_search_terms,
                base_search_text=payload.search_text,
                base_latest_user_message=payload.latest_user_message,
                extra_message_terms=current_doc.get("message_search_terms") or [],
                extra_search_text=current_doc.get("search_text"),
                extra_latest_user_message=current_doc.get("latest_user_message"),
            )
            update_dict = {
                "name_search_terms": merged.name_search_terms,
                "message_search_terms": merged.message_search_terms,
                "search_terms": merged.search_terms,
                "search_text": merged.search_text,
                "latest_user_message": merged.latest_user_message,
                "search_index_version": merged.search_index_version,
                "search_index_updated_at": _next_search_index_timestamp(
                    current_doc.get("search_index_updated_at")
                ),
            }
            cas_field, cas_value = self._get_search_index_cas(current_doc)
            result = await self._update_doc(
                session_id,
                {"$set": update_dict},
                expected_cas_field=cas_field,
                expected_cas_value=cas_value,
            )
            if result.modified_count > 0:
                return True
        return False

    async def backfill_search_indexes(self, batch_size: int = 100) -> int:
        """Backfill stale session search indexes in small batches."""
        await self.ensure_indexes_if_needed()
        batch_size = min(max(int(batch_size), 1), self.SEARCH_BACKFILL_BATCH_MAX)
        cutoff = utc_now().timestamp() - self.SEARCH_BACKFILL_SKIP_RECENT_SECONDS
        cutoff_dt = datetime.fromtimestamp(cutoff)
        stale_query = {
            "$and": [
                {
                    "$or": [
                        {"search_index_version": {"$ne": SESSION_SEARCH_INDEX_VERSION}},
                        {"search_index_version": None},
                    ]
                },
                {"updated_at": {"$lt": cutoff_dt}},
            ]
        }
        cursor = (
            self.collection.find(stale_query, {"session_id": 1, "_id": 1})
            .sort("updated_at", -1)
            .limit(batch_size)
        )
        docs = await cursor.to_list(length=batch_size)
        rebuilt = 0
        for doc in docs:
            lookup_id = doc.get("session_id") or str(doc.get("_id"))
            if lookup_id and await self.rebuild_search_index(lookup_id):
                rebuilt += 1
        return rebuilt

    async def _find_doc(
        self,
        session_id: str,
        projection: dict[str, Any] | None = None,
    ) -> Optional[dict[str, Any]]:
        doc = await self.collection.find_one({"session_id": session_id}, projection)
        if doc:
            return doc
        try:
            return await self.collection.find_one({"_id": ObjectId(session_id)}, projection)
        except Exception:
            return None

    async def _update_doc(
        self,
        session_id: str,
        update: dict[str, Any],
        expected_cas_field: str | None = None,
        expected_cas_value: Any = None,
    ):
        result = await self._update_doc_with_query(
            {"session_id": session_id},
            update,
            expected_cas_field=expected_cas_field,
            expected_cas_value=expected_cas_value,
        )
        if result.modified_count > 0:
            return result
        try:
            return await self._update_doc_with_query(
                {"_id": ObjectId(session_id)},
                update,
                expected_cas_field=expected_cas_field,
                expected_cas_value=expected_cas_value,
            )
        except Exception:
            return result

    async def _update_doc_with_query(
        self,
        query: dict[str, Any],
        update: dict[str, Any],
        expected_cas_field: str | None = None,
        expected_cas_value: Any = None,
    ):
        actual_query = dict(query)
        if expected_cas_field is not None:
            actual_query[expected_cas_field] = expected_cas_value
        return await self.collection.update_one(actual_query, update)

    @staticmethod
    def _get_search_index_cas(doc: dict[str, Any]) -> tuple[str | None, Any]:
        if "search_index_updated_at" in doc:
            return "search_index_updated_at", doc.get("search_index_updated_at")
        if "updated_at" in doc:
            return "updated_at", doc.get("updated_at")
        return None, None

    async def toggle_favorite(
        self,
        session_id: str,
        user_id: str,
        favorites_project_id: str | None = None,
    ) -> Optional[Session]:
        """Toggle a session's independent favorite state."""

        session = await self.get_by_session_id(session_id)
        if not session:
            try:
                session = await self.get_by_id(session_id)
            except Exception:
                session = None

        if not session or session.user_id != user_id:
            return None

        current_favorite = is_session_favorite(
            session.metadata,
            favorites_project_id,
        )
        next_favorite = not current_favorite
        update_dict: dict[str, Any] = {
            "updated_at": utc_now(),
            "metadata.is_favorite": next_favorite,
        }
        if (
            not next_favorite
            and favorites_project_id
            and session.metadata.get("project_id") == favorites_project_id
        ):
            update_dict["metadata.project_id"] = None

        result = await self.collection.find_one_and_update(
            {"session_id": session_id, "user_id": user_id},
            {"$set": update_dict},
            return_document=True,
        )

        if not result:
            try:
                result = await self.collection.find_one_and_update(
                    {"_id": ObjectId(session_id), "user_id": user_id},
                    {"$set": update_dict},
                    return_document=True,
                )
            except Exception:
                return None

        if not result:
            return None

        return self._build_session(result, favorites_project_id)
