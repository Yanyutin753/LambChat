"""
消息书签存储层

按 (user_id, session_id, message_id) 唯一收藏会话内的消息；
toggle 语义与 session 的 pin/favorite 一致：存在则删除，不存在则创建。
"""

from __future__ import annotations

from typing import Any

from bson import ObjectId
from bson.errors import InvalidId

from src.infra.logging import get_logger
from src.infra.storage.mongodb import get_mongo_client
from src.infra.utils.datetime import utc_now
from src.kernel.config import settings
from src.kernel.schemas.bookmark import Bookmark, BookmarkWithSession

logger = get_logger(__name__)

BOOKMARK_LIST_LIMIT = 500


class BookmarkStorage:
    """消息书签存储"""

    def __init__(self):
        self._collection = None
        self._sessions_collection = None

    @property
    def collection(self):
        """延迟加载书签集合"""
        if self._collection is None:
            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            self._collection = db["bookmarks"]
        return self._collection

    @property
    def sessions_collection(self):
        """延迟加载会话集合（列表联查会话名）"""
        if self._sessions_collection is None:
            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            self._sessions_collection = db[settings.MONGODB_SESSIONS_COLLECTION]
        return self._sessions_collection

    async def create_indexes(self) -> None:
        """创建索引"""
        await self.collection.create_index(
            [("user_id", 1), ("session_id", 1), ("message_id", 1)],
            unique=True,
            name="user_session_message_unique",
        )
        await self.collection.create_index([("user_id", 1), ("created_at", -1)])
        logger.info("Bookmark indexes created")

    @staticmethod
    def _unique_key(user_id: str, session_id: str, message_id: str) -> dict[str, Any]:
        return {"user_id": user_id, "session_id": session_id, "message_id": message_id}

    @staticmethod
    def _to_bookmark(doc: dict[str, Any]) -> Bookmark:
        doc = dict(doc)
        doc["id"] = str(doc.pop("_id"))
        return Bookmark.model_validate(doc)

    async def get(
        self,
        user_id: str,
        session_id: str,
        message_id: str,
    ) -> Bookmark | None:
        """查询单条书签"""
        doc = await self.collection.find_one(self._unique_key(user_id, session_id, message_id))
        return self._to_bookmark(doc) if doc else None

    async def toggle(
        self,
        *,
        user_id: str,
        session_id: str,
        message_id: str,
        run_id: str | None = None,
        label: str | None = None,
    ) -> tuple[bool, Bookmark | None]:
        """切换书签状态：存在则删除返回 (False, None)，不存在则创建返回 (True, bookmark)"""
        key = self._unique_key(user_id, session_id, message_id)
        existing = await self.collection.find_one(key)
        if existing:
            await self.collection.delete_one(key)
            logger.info(
                "Bookmark removed: user=%s session=%s message=%s",
                user_id,
                session_id,
                message_id,
            )
            return False, None

        doc: dict[str, Any] = {
            **key,
            "run_id": run_id,
            "label": label,
            "created_at": utc_now(),
        }
        result = await self.collection.insert_one(doc)
        doc["id"] = str(result.inserted_id)
        logger.info(
            "Bookmark added: user=%s session=%s message=%s",
            user_id,
            session_id,
            message_id,
        )
        return True, Bookmark.model_validate(doc)

    async def list_for_user(self, user_id: str) -> list[BookmarkWithSession]:
        """列出用户全部书签，联查会话名；会话已删除的书签过滤掉"""
        cursor = (
            self.collection.find({"user_id": user_id})
            .sort("created_at", -1)
            .limit(BOOKMARK_LIST_LIMIT)
        )
        bookmarks: list[Bookmark] = []
        async for doc in cursor:
            bookmarks.append(self._to_bookmark(doc))

        if not bookmarks:
            return []

        session_ids = sorted({b.session_id for b in bookmarks})
        object_ids = []
        for session_id in session_ids:
            try:
                object_ids.append(ObjectId(session_id))
            except InvalidId:
                continue

        session_query: dict[str, Any] = {"session_id": {"$in": session_ids}}
        if object_ids:
            session_query = {"$or": [session_query, {"_id": {"$in": object_ids}}]}

        session_infos: dict[str, dict[str, Any]] = {}
        async for doc in self.sessions_collection.find(session_query):
            session_id = doc.get("session_id") or str(doc.get("_id"))
            session_infos[session_id] = doc

        items: list[BookmarkWithSession] = []
        for bookmark in bookmarks:
            session_doc = session_infos.get(bookmark.session_id)
            if session_doc is None:
                continue
            items.append(
                BookmarkWithSession(
                    **bookmark.model_dump(),
                    session_name=session_doc.get("name") or bookmark.session_id,
                    session_is_active=bool(session_doc.get("is_active", True)),
                )
            )
        return items
