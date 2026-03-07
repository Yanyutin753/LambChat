"""
会话存储层
"""

from datetime import datetime
from typing import Any, Optional

from bson import ObjectId

from src.kernel.config import settings
from src.kernel.schemas.session import Session, SessionCreate, SessionUpdate


class SessionStorage:
    """
    会话存储类

    使用 MongoDB 存储会话数据。
    """

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

    async def create(
        self,
        session_data: SessionCreate,
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Session:
        """创建会话"""
        now = datetime.now()

        # 使用自定义 session_id 或生成新的
        actual_session_id = session_id or None

        session_dict = {
            "name": session_data.name,
            "metadata": session_data.metadata,
            "user_id": user_id,
            "agent_id": session_data.metadata.get("agent_id", "default"),
            "created_at": now,
            "updated_at": now,
            "is_active": True,
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
        session_dict = await self.collection.find_one({"session_id": session_id})

        if not session_dict:
            return None

        # 优先使用自定义 session_id 作为 id
        session_dict["id"] = session_dict.get("session_id") or str(session_dict.pop("_id"))
        if "session_id" in session_dict and session_dict["id"] == session_dict["session_id"]:
            session_dict.pop("_id", None)
        return Session(**session_dict)

    async def update_user_id(self, session_id: str, user_id: str) -> bool:
        """通过自定义 session_id 更新 user_id"""
        result = await self.collection.update_one(
            {"session_id": session_id, "user_id": None},
            {"$set": {"user_id": user_id, "updated_at": datetime.now()}},
        )
        return result.modified_count > 0

    async def get_by_id(self, session_id: str) -> Optional[Session]:
        """通过 ID 获取会话"""
        try:
            session_dict = await self.collection.find_one({"_id": ObjectId(session_id)})
        except Exception:
            return None

        if not session_dict:
            return None

        session_dict["id"] = str(session_dict.pop("_id"))
        return Session(**session_dict)

    async def update(self, session_id: str, session_data: SessionUpdate) -> Optional[Session]:
        """更新会话（支持自定义 session_id 或 ObjectId）"""
        update_dict: dict = {"updated_at": datetime.now()}

        if session_data.name is not None:
            update_dict["name"] = session_data.name

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

        result["id"] = result.get("session_id") or str(result.pop("_id"))
        return Session(**result)

    async def delete(self, session_id: str) -> bool:
        """删除会话（支持自定义 session_id 或 ObjectId）"""
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
        folder_id: Optional[str] = None,
    ) -> tuple[list[Session], int]:
        """列出会话，返回 (sessions, total_count)

        Args:
            user_id: 用户ID，如果提供则只返回该用户的会话
                     None 表示不过滤（仅管理员使用）
            folder_id: 文件夹ID过滤
                       - None: 不过滤文件夹
                       - "none": 只返回未分类的会话（没有folder_id）
                       - 其他值: 只返回该文件夹内的会话
        """
        query: dict[str, Any] = {}
        if user_id is not None:
            # 严格匹配用户ID，空字符串也会被当作过滤条件
            query["user_id"] = user_id
        if is_active is not None:
            query["is_active"] = is_active

        # Folder filter
        if folder_id == "none":
            # 未分类：folder_id 为 None 或不存在
            query["metadata.folder_id"] = None
        elif folder_id is not None:
            query["metadata.folder_id"] = folder_id

        # Get total count
        total = await self.collection.count_documents(query)

        cursor = self.collection.find(query).skip(skip).limit(limit).sort("updated_at", -1)
        sessions = []

        for session_dict in await cursor.to_list(length=limit):
            # 优先使用自定义 session_id 作为 id
            session_dict["id"] = session_dict.get("session_id") or str(session_dict.pop("_id"))
            sessions.append(Session(**session_dict))

        return sessions, total

    async def get(self, session_id: str) -> Optional[Session]:
        """获取会话 (兼容旧 API)"""
        return await self.get_by_id(session_id)

    async def clear_folder_id(self, folder_id: str, user_id: str) -> int:
        """Clear folder_id for all sessions in a folder (when folder is deleted).

        Args:
            folder_id: The folder ID to clear
            user_id: The user ID to filter sessions

        Returns:
            Number of modified sessions
        """
        result = await self.collection.update_many(
            {"user_id": user_id, "metadata.folder_id": folder_id},
            {"$set": {"metadata.folder_id": None, "updated_at": datetime.now()}},
        )
        return result.modified_count

    async def move_to_folder(
        self, session_id: str, user_id: str, folder_id: Optional[str]
    ) -> Optional[Session]:
        """Move a session to a folder.

        Args:
            session_id: The session ID to move
            user_id: The user ID (for ownership verification)
            folder_id: The target folder ID, or None to uncategorize

        Returns:
            Updated Session if found and updated, None otherwise
        """
        update_dict = {
            "updated_at": datetime.now(),
            "metadata.folder_id": folder_id,
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

        result["id"] = result.get("session_id") or str(result.pop("_id"))
        return Session(**result)
