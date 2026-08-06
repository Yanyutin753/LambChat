"""
会话分享存储层
"""

import asyncio
import secrets
from typing import Any, Optional

from src.infra.utils.datetime import utc_now
from src.kernel.config import settings
from src.kernel.schemas.share import (
    ProjectSnapshot,
    ShareCreate,
    SharedSession,
    SharedSessionListItem,
    ShareScope,
    ShareType,
    ShareVisibility,
)

SHARE_LIST_LIMIT_MAX = 100


class ShareStorage:
    """
    会话分享存储类

    使用 MongoDB 存储分享数据。同时支持会话维度（scope=session）与
    项目维度（scope=project）的分享。
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
        # 项目分享按 project_id 检索；稀疏索引避免对老数据/会话分享建空值索引
        await self.collection.create_index("project_id", sparse=True)

    def _generate_share_id(self) -> str:
        """生成安全的分享 ID（12字符）"""
        return secrets.token_urlsafe(9)  # 9 bytes = 12 chars

    @staticmethod
    def _resolve_project_snapshot(raw: Any) -> Optional[ProjectSnapshot]:
        if raw is None:
            return None
        if isinstance(raw, ProjectSnapshot):
            return raw
        if isinstance(raw, dict):
            try:
                return ProjectSnapshot(**raw)
            except Exception:
                return None
        return None

    def _build_shared_session(self, share_dict: dict) -> SharedSession:
        """Convert a Mongo document into a SharedSession with legacy defaults."""
        normalized = dict(share_dict)
        normalized["id"] = str(normalized.pop("_id"))
        created_at = normalized.get("created_at") or utc_now()
        return SharedSession(
            id=normalized["id"],
            share_id=normalized["share_id"],
            session_id=normalized.get("session_id"),
            owner_id=normalized["owner_id"],
            share_scope=ShareScope(normalized.get("share_scope") or ShareScope.SESSION.value),
            share_type=ShareType(normalized.get("share_type") or ShareType.FULL.value),
            run_ids=normalized.get("run_ids"),
            session_ids=normalized.get("session_ids"),
            project_id=normalized.get("project_id"),
            project_snapshot=self._resolve_project_snapshot(normalized.get("project_snapshot")),
            visibility=ShareVisibility(
                normalized.get("visibility") or ShareVisibility.PUBLIC.value
            ),
            created_at=created_at,
            updated_at=normalized.get("updated_at") or created_at,
        )

    def _build_list_item(self, share_dict: dict) -> SharedSessionListItem:
        """Build a list item from a Mongo document (shared by all list methods)."""
        snapshot = self._resolve_project_snapshot(share_dict.get("project_snapshot"))
        return SharedSessionListItem(
            id=str(share_dict["_id"]),
            share_id=share_dict["share_id"],
            session_id=share_dict.get("session_id"),
            share_scope=ShareScope(share_dict.get("share_scope") or ShareScope.SESSION.value),
            project_id=share_dict.get("project_id"),
            project_name=snapshot.name if snapshot else None,
            share_type=ShareType(share_dict["share_type"]),
            visibility=ShareVisibility(share_dict["visibility"]),
            run_ids=share_dict.get("run_ids"),
            session_ids=share_dict.get("session_ids"),
            created_at=share_dict["created_at"],
        )

    async def create(
        self,
        share_data: ShareCreate,
        owner_id: str,
        project_snapshot: Optional[ProjectSnapshot] = None,
    ) -> SharedSession:
        """创建分享记录"""
        now = utc_now()
        share_id = self._generate_share_id()

        share_dict = {
            "share_id": share_id,
            "session_id": share_data.session_id,
            "owner_id": owner_id,
            "share_scope": share_data.share_scope.value,
            "share_type": share_data.share_type.value,
            "run_ids": share_data.run_ids,
            "session_ids": share_data.session_ids,
            "project_id": share_data.project_id,
            "project_snapshot": (project_snapshot.model_dump() if project_snapshot else None),
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
            share_scope=ShareScope(share_dict["share_scope"]),
            share_type=ShareType(share_dict["share_type"]),
            run_ids=share_dict["run_ids"],
            session_ids=share_dict["session_ids"],
            project_id=share_dict["project_id"],
            project_snapshot=self._resolve_project_snapshot(share_dict["project_snapshot"]),
            visibility=ShareVisibility(share_dict["visibility"]),
            created_at=share_dict["created_at"],
            updated_at=share_dict["updated_at"],
        )

    async def get_by_share_id(self, share_id: str) -> Optional[SharedSession]:
        """通过分享 ID 获取分享记录"""
        share_dict = await self.collection.find_one({"share_id": share_id})

        if not share_dict:
            return None

        return self._build_shared_session(share_dict)

    async def get_by_id(self, share_db_id: str) -> Optional[SharedSession]:
        """通过数据库 ID 获取分享记录"""
        from bson import ObjectId

        try:
            share_dict = await self.collection.find_one({"_id": ObjectId(share_db_id)})
        except Exception:
            return None

        if not share_dict:
            return None

        return self._build_shared_session(share_dict)

    async def list_by_owner(
        self,
        owner_id: str,
        skip: int = 0,
        limit: int = 100,
    ) -> tuple[list[SharedSessionListItem], int]:
        """列出用户的所有分享"""
        limit = min(max(int(limit), 1), SHARE_LIST_LIMIT_MAX)
        query = {"owner_id": owner_id}

        cursor = self.collection.find(query).skip(skip).limit(limit).sort("created_at", -1)
        total, share_dicts = await asyncio.gather(
            self.collection.count_documents(query),
            cursor.to_list(length=limit),
        )

        shares = [self._build_list_item(share_dict) for share_dict in share_dicts]

        return shares, total

    async def list_by_session(
        self,
        session_id: str,
    ) -> list[SharedSessionListItem]:
        """列出会话的所有分享"""
        cursor = (
            self.collection.find({"session_id": session_id})
            .sort("created_at", -1)
            .limit(SHARE_LIST_LIMIT_MAX)
        )

        share_dicts = await cursor.to_list(length=SHARE_LIST_LIMIT_MAX)
        return [self._build_list_item(share_dict) for share_dict in share_dicts]

    async def list_by_project(
        self,
        project_id: str,
        owner_id: str,
    ) -> list[SharedSessionListItem]:
        """列出项目的所有分享"""
        cursor = (
            self.collection.find({"project_id": project_id, "owner_id": owner_id})
            .sort("created_at", -1)
            .limit(SHARE_LIST_LIMIT_MAX)
        )

        share_dicts = await cursor.to_list(length=SHARE_LIST_LIMIT_MAX)
        return [self._build_list_item(share_dict) for share_dict in share_dicts]

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

    async def update(
        self,
        share_db_id: str,
        owner_id: str,
        share_type: ShareType,
        run_ids: Optional[list[str]],
        visibility: ShareVisibility,
        session_ids: Optional[list[str]] = None,
    ) -> Optional[SharedSession]:
        """更新分享设置（保持公开 share_id 不变）。

        ``run_ids`` 用于 session partial 分享；``session_ids`` 用于 project
        partial 分享刷新快照。
        """
        from bson import ObjectId

        try:
            object_id = ObjectId(share_db_id)
        except Exception:
            return None

        now = utc_now()
        set_fields: dict = {
            "share_type": share_type.value,
            "run_ids": run_ids,
            "session_ids": session_ids,
            "visibility": visibility.value,
            "updated_at": now,
        }
        result = await self.collection.update_one(
            {"_id": object_id, "owner_id": owner_id},
            {"$set": set_fields},
        )
        if getattr(result, "matched_count", result.modified_count) <= 0:
            return None

        share_dict = await self.collection.find_one({"_id": object_id})
        if not share_dict:
            return None
        return self._build_shared_session(share_dict)

    async def delete_by_session(self, session_id: str) -> int:
        """删除会话的所有分享（会话删除时调用）"""
        result = await self.collection.delete_many({"session_id": session_id})
        return result.deleted_count

    async def delete_project_live_shares(self, project_id: str) -> int:
        """删除项目的实时（share_type=full）分享。

        项目删除后，full 分享内容会失效，因此删除其记录；
        partial（快照）分享内容已冻结且自包含，予以保留。
        """
        result = await self.collection.delete_many(
            {"project_id": project_id, "share_type": ShareType.FULL.value}
        )
        return result.deleted_count
