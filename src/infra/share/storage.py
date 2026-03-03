"""
会话分享存储层
"""

import secrets
from datetime import datetime
from typing import Optional

from src.kernel.config import settings
from src.kernel.schemas.share import (
    ShareCreate,
    SharedSession,
    SharedSessionListItem,
    ShareType,
    ShareVisibility,
)


class ShareStorage:
    """
    会话分享存储类

    使用 MongoDB 存储分享数据。
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
            self._collection = db["shared_sessions"]
        return self._collection

    async def ensure_indexes(self):
        """确保索引存在"""
        await self.collection.create_index("share_id", unique=True)
        await self.collection.create_index("session_id")
        await self.collection.create_index("owner_id")

    def _generate_share_id(self) -> str:
        """生成安全的分享 ID（12字符）"""
        return secrets.token_urlsafe(9)  # 9 bytes = 12 chars

    async def create(
        self,
        share_data: ShareCreate,
        owner_id: str,
    ) -> SharedSession:
        """创建分享记录"""
        now = datetime.now()
        share_id = self._generate_share_id()

        share_dict = {
            "share_id": share_id,
            "session_id": share_data.session_id,
            "owner_id": owner_id,
            "share_type": share_data.share_type.value,
            "run_ids": share_data.run_ids,
            "visibility": share_data.visibility.value,
            "created_at": now,
            "updated_at": now,
        }

        result = await self.collection.insert_one(share_dict)
        share_dict["id"] = str(result.inserted_id)

        return SharedSession(
            id=share_dict["id"],
            share_id=share_dict["share_id"],
            session_id=share_dict["session_id"],
            owner_id=share_dict["owner_id"],
            share_type=ShareType(share_dict["share_type"]),
            run_ids=share_dict["run_ids"],
            visibility=ShareVisibility(share_dict["visibility"]),
            created_at=share_dict["created_at"],
            updated_at=share_dict["updated_at"],
        )

    async def get_by_share_id(self, share_id: str) -> Optional[SharedSession]:
        """通过分享 ID 获取分享记录"""
        share_dict = await self.collection.find_one({"share_id": share_id})

        if not share_dict:
            return None

        share_dict["id"] = str(share_dict.pop("_id"))
        return SharedSession(
            id=share_dict["id"],
            share_id=share_dict["share_id"],
            session_id=share_dict["session_id"],
            owner_id=share_dict["owner_id"],
            share_type=ShareType(share_dict["share_type"]),
            run_ids=share_dict.get("run_ids"),
            visibility=ShareVisibility(share_dict["visibility"]),
            created_at=share_dict["created_at"],
            updated_at=share_dict["updated_at"],
        )

    async def get_by_id(self, share_db_id: str) -> Optional[SharedSession]:
        """通过数据库 ID 获取分享记录"""
        from bson import ObjectId

        try:
            share_dict = await self.collection.find_one({"_id": ObjectId(share_db_id)})
        except Exception:
            return None

        if not share_dict:
            return None

        share_dict["id"] = str(share_dict.pop("_id"))
        return SharedSession(
            id=share_dict["id"],
            share_id=share_dict["share_id"],
            session_id=share_dict["session_id"],
            owner_id=share_dict["owner_id"],
            share_type=ShareType(share_dict["share_type"]),
            run_ids=share_dict.get("run_ids"),
            visibility=ShareVisibility(share_dict["visibility"]),
            created_at=share_dict["created_at"],
            updated_at=share_dict["updated_at"],
        )

    async def list_by_owner(
        self,
        owner_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[SharedSessionListItem], int]:
        """列出用户的所有分享"""
        query = {"owner_id": owner_id}
        total = await self.collection.count_documents(query)

        cursor = self.collection.find(query).skip(skip).limit(limit).sort("created_at", -1)

        shares = []
        for share_dict in await cursor.to_list(length=limit):
            shares.append(
                SharedSessionListItem(
                    id=str(share_dict["_id"]),
                    share_id=share_dict["share_id"],
                    session_id=share_dict["session_id"],
                    share_type=ShareType(share_dict["share_type"]),
                    visibility=ShareVisibility(share_dict["visibility"]),
                    run_ids=share_dict.get("run_ids"),
                    created_at=share_dict["created_at"],
                )
            )

        return shares, total

    async def list_by_session(
        self,
        session_id: str,
    ) -> list[SharedSessionListItem]:
        """列出会话的所有分享"""
        cursor = self.collection.find({"session_id": session_id}).sort("created_at", -1)

        shares = []
        for share_dict in await cursor.to_list(length=100):
            shares.append(
                SharedSessionListItem(
                    id=str(share_dict["_id"]),
                    share_id=share_dict["share_id"],
                    session_id=share_dict["session_id"],
                    share_type=ShareType(share_dict["share_type"]),
                    visibility=ShareVisibility(share_dict["visibility"]),
                    run_ids=share_dict.get("run_ids"),
                    created_at=share_dict["created_at"],
                )
            )

        return shares

    async def delete(self, share_db_id: str, owner_id: str) -> bool:
        """删除分享记录（需验证所有权）"""
        from bson import ObjectId

        try:
            result = await self.collection.delete_one(
                {"_id": ObjectId(share_db_id), "owner_id": owner_id}
            )
            return result.deleted_count > 0
        except Exception:
            return False

    async def delete_by_session(self, session_id: str) -> int:
        """删除会话的所有分享（会话删除时调用）"""
        result = await self.collection.delete_many({"session_id": session_id})
        return result.deleted_count
