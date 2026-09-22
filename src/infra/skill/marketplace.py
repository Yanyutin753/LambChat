import re
from typing import TYPE_CHECKING, Any, Optional

from bson import ObjectId
from bson.errors import InvalidId

from src.infra.logging import get_logger
from src.infra.skill.constants import (
    SKILL_MARKETPLACE_COLLECTION,
    SKILL_MARKETPLACE_FILES_COLLECTION,
)
from src.infra.skill.types import (
    MarketplaceSkill,
    MarketplaceSkillCreate,
    MarketplaceSkillResponse,
    MarketplaceSkillUpdate,
)
from src.infra.storage.mongodb import get_mongo_client
from src.infra.utils.datetime import utc_now_iso
from src.kernel.config import settings

logger = get_logger(__name__)

MAX_ZIP_SIZE = 10 * 1024 * 1024  # 10MB
MARKETPLACE_FILE_COPY_BATCH_SIZE = 25
MARKETPLACE_FILES_PER_SKILL_LIMIT = 100
MARKETPLACE_USER_PUBLISHED_LIMIT = 1000
MARKETPLACE_TAG_SCAN_LIMIT = 1000
MARKETPLACE_TAG_LIST_LIMIT = 200


if TYPE_CHECKING:
    from pymongo import AsyncMongoClient
    from pymongo.asynchronous.collection import AsyncCollection


class MarketplaceStorage:
    """商城 Skill 存储"""

    def __init__(self):
        self._client: Optional["AsyncMongoClient"] = None
        self._meta_collection: Optional["AsyncCollection"] = None
        self._files_collection: Optional["AsyncCollection"] = None
        self._users_collection: Optional["AsyncCollection"] = None

    def _get_meta_collection(self) -> "AsyncCollection":
        if self._meta_collection is None:
            self._client = get_mongo_client()
            db = self._client[settings.MONGODB_DB]
            self._meta_collection = db[SKILL_MARKETPLACE_COLLECTION]
        return self._meta_collection

    def _get_files_collection(self) -> "AsyncCollection":
        if self._files_collection is None:
            self._client = get_mongo_client()
            db = self._client[settings.MONGODB_DB]
            self._files_collection = db[SKILL_MARKETPLACE_FILES_COLLECTION]
        return self._files_collection

    def _get_users_collection(self) -> "AsyncCollection":
        if self._users_collection is None:
            self._client = get_mongo_client()
            db = self._client[settings.MONGODB_DB]
            self._users_collection = db["users"]
        return self._users_collection

    async def ensure_indexes(self) -> None:
        """创建索引"""
        meta = self._get_meta_collection()
        await meta.create_index("skill_name", unique=True, background=True)
        await meta.create_index("created_by", background=True)

        files = self._get_files_collection()
        await files.create_index(
            [("skill_name", 1), ("file_path", 1)],
            unique=True,
            background=True,
        )

    async def _batch_get_usernames(self, user_ids: list[str]) -> dict[str, str]:
        """批量查询用户名"""
        if not user_ids:
            return {}
        collection = self._get_users_collection()
        object_ids = []
        for user_id in user_ids:
            try:
                object_ids.append(ObjectId(user_id))
            except (InvalidId, TypeError):
                continue
        if not object_ids:
            return {}
        result: dict[str, str] = {}
        cursor = collection.find({"_id": {"$in": object_ids}}, {"_id": 1, "username": 1})
        async for doc in cursor:
            key = str(doc["_id"])
            result[key] = doc.get("username", key)
        return result

    @staticmethod
    def _normalize_version(version: Optional[str]) -> str:
        """Ensure legacy null versions are exposed as the default string value."""
        return version or "1.0.0"

    def _build_response(
        self,
        doc: dict,
        file_count: int,
        username_map: dict[str, str],
        viewer_id: Optional[str] = None,
    ) -> MarketplaceSkillResponse:
        created_by = doc.get("created_by")
        return MarketplaceSkillResponse(
            skill_name=doc["skill_name"],
            description=doc.get("description", ""),
            tags=doc.get("tags", []),
            version=self._normalize_version(
                doc.get("version") if isinstance(doc.get("version"), str) else None
            ),
            created_at=doc.get("created_at"),
            updated_at=doc.get("updated_at"),
            created_by=created_by,
            created_by_username=username_map.get(created_by) if created_by else None,
            is_active=doc.get("is_active", True),
            is_owner=bool(viewer_id and created_by and created_by == viewer_id),
            file_count=file_count,
        )

    # ==========================================
    # 元数据操作
    # ==========================================

    async def list_marketplace_skills(
        self,
        tags: Optional[list[str]] = None,
        search: Optional[str] = None,
        include_inactive: bool = False,
        viewer_id: Optional[str] = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[MarketplaceSkillResponse]:
        """列出所有商城 Skills（可选按标签筛选/搜索，默认过滤已停用；自己的始终可见）"""
        collection = self._get_meta_collection()

        query: dict[str, Any] = {}
        if not include_inactive:
            # 激活的 skill + 自己发布的 skill（含已停用的）
            if viewer_id:
                query["$or"] = [
                    {"is_active": {"$ne": False}},
                    {"created_by": viewer_id},
                ]
            else:
                query["is_active"] = {"$ne": False}
        if tags:
            query["tags"] = {"$all": tags}
        if search:
            safe_search = re.escape(search)
            search_or = [
                {"skill_name": {"$regex": safe_search, "$options": "i"}},
                {"description": {"$regex": safe_search, "$options": "i"}},
                {"tags": {"$elemMatch": {"$regex": safe_search, "$options": "i"}}},
            ]
            if "$or" in query:
                # 合并 visibility $or 和 search $or
                query["$and"] = [{"$or": query.pop("$or")}, {"$or": search_or}]
            else:
                query["$or"] = search_or

        # Page marketplace metadata first, then count files without materializing
        # every file document into the aggregation result.
        pipeline: list[dict[str, Any]] = [
            {"$match": query},
            {"$sort": {"updated_at": -1}},
            {"$skip": skip},
            {"$limit": limit},
            {
                "$lookup": {
                    "from": SKILL_MARKETPLACE_FILES_COLLECTION,
                    "let": {"skill": "$skill_name"},
                    "pipeline": [
                        {"$match": {"$expr": {"$eq": ["$skill_name", "$$skill"]}}},
                        {"$count": "count"},
                    ],
                    "as": "_file_count_docs",
                }
            },
            {
                "$addFields": {
                    "_file_count": {"$ifNull": [{"$first": "$_file_count_docs.count"}, 0]}
                }
            },
            {"$unset": "_file_count_docs"},
        ]

        docs = []
        async for doc in await collection.aggregate(pipeline):
            docs.append(doc)

        if not docs:
            return []

        # 批量查用户名
        user_ids = [d.get("created_by") for d in docs if d.get("created_by")]
        username_map = await self._batch_get_usernames(user_ids)

        results = []
        for doc in docs:
            file_count = doc.get("_file_count", 0)
            results.append(self._build_response(doc, file_count, username_map, viewer_id=viewer_id))
        return results

    async def get_marketplace_skill(self, skill_name: str) -> Optional[MarketplaceSkill]:
        """获取商城 Skill 元数据"""
        collection = self._get_meta_collection()
        doc = await collection.find_one({"skill_name": skill_name})
        if not doc:
            return None
        return MarketplaceSkill(
            skill_name=doc["skill_name"],
            description=doc.get("description", ""),
            tags=doc.get("tags", []),
            version=self._normalize_version(
                doc.get("version") if isinstance(doc.get("version"), str) else None
            ),
            created_at=doc.get("created_at"),
            updated_at=doc.get("updated_at"),
            created_by=doc.get("created_by"),
            is_active=doc.get("is_active", True),
        )

    async def get_marketplace_skill_response(
        self,
        skill_name: str,
        viewer_id: Optional[str] = None,
    ) -> Optional[MarketplaceSkillResponse]:
        """获取商城 Skill 响应（含文件数量、用户名、是否为创建者）"""
        skill = await self.get_marketplace_skill(skill_name)
        if not skill:
            return None
        files_collection = self._get_files_collection()
        file_count = await files_collection.count_documents({"skill_name": skill_name})

        username_map: dict[str, str] = {}
        if skill.created_by:
            username_map = await self._batch_get_usernames([skill.created_by])

        return MarketplaceSkillResponse(
            skill_name=skill.skill_name,
            description=skill.description,
            tags=skill.tags,
            version=skill.version,
            created_at=skill.created_at,
            updated_at=skill.updated_at,
            created_by=skill.created_by,
            created_by_username=username_map.get(skill.created_by) if skill.created_by else None,
            is_active=skill.is_active,
            is_owner=bool(viewer_id and skill.created_by and skill.created_by == viewer_id),
            file_count=file_count,
        )

    async def create_marketplace_skill(
        self, data: MarketplaceSkillCreate, user_id: str
    ) -> MarketplaceSkill:
        """创建商城 Skill 元数据"""
        collection = self._get_meta_collection()
        now = utc_now_iso()

        existing = await collection.find_one({"skill_name": data.skill_name})
        if existing:
            raise ValueError(f"Marketplace skill '{data.skill_name}' already exists")

        doc = {
            "skill_name": data.skill_name,
            "description": data.description,
            "tags": data.tags,
            "version": data.version,
            "created_at": now,
            "updated_at": now,
            "created_by": user_id,
            "is_active": True,
        }
        await collection.insert_one(doc)
        doc_version: str | None = doc.get("version")  # type: ignore[assignment]
        return MarketplaceSkill(
            **{
                **doc,
                "version": self._normalize_version(doc_version),
            }
        )

    async def update_marketplace_skill(
        self, skill_name: str, data: MarketplaceSkillUpdate
    ) -> Optional[MarketplaceSkill]:
        """更新商城 Skill 元数据"""
        collection = self._get_meta_collection()

        existing = await collection.find_one({"skill_name": skill_name})
        if not existing:
            return None

        update_data: dict[str, Any] = {"updated_at": utc_now_iso()}
        if data.description is not None:
            update_data["description"] = data.description
        if data.tags is not None:
            update_data["tags"] = data.tags
        if data.version is not None:
            update_data["version"] = data.version
        if data.is_active is not None:
            update_data["is_active"] = data.is_active

        await collection.update_one({"skill_name": skill_name}, {"$set": update_data})

        updated = await collection.find_one({"skill_name": skill_name})
        return (
            MarketplaceSkill(
                **{
                    **updated,
                    "version": self._normalize_version(
                        updated.get("version") if isinstance(updated.get("version"), str) else None
                    ),
                }
            )
            if updated
            else None
        )

    async def set_marketplace_active(
        self, skill_name: str, is_active: bool
    ) -> Optional[MarketplaceSkill]:
        """Admin: 激活或停用商城 Skill"""
        collection = self._get_meta_collection()
        now = utc_now_iso()

        result = await collection.find_one_and_update(
            {"skill_name": skill_name},
            {"$set": {"is_active": is_active, "updated_at": now}},
            return_document=True,
        )
        if not result:
            return None
        return MarketplaceSkill(
            **{
                **result,
                "version": self._normalize_version(
                    result.get("version") if isinstance(result.get("version"), str) else None
                ),
            }
        )

    async def delete_marketplace_skill(self, skill_name: str) -> bool:
        """删除商城 Skill 元数据和所有文件"""
        meta = self._get_meta_collection()
        files = self._get_files_collection()

        meta_result = await meta.delete_one({"skill_name": skill_name})
        await files.delete_many({"skill_name": skill_name})

        return meta_result.deleted_count > 0

    # ==========================================
    # 发布状态查询
    # ==========================================

    async def get_user_published_skills(
        self,
        user_id: str,
        *,
        skill_names: list[str] | None = None,
    ) -> dict[str, dict[str, Any]]:
        """获取用户已发布的 Skill 状态 {skill_name: {is_active, ...}}"""
        collection = self._get_meta_collection()
        query: dict[str, Any] = {"created_by": user_id}
        limit = MARKETPLACE_USER_PUBLISHED_LIMIT
        if skill_names is not None:
            names: list[str] = []
            seen: set[str] = set()
            for name in skill_names:
                if not isinstance(name, str) or not name or name in seen:
                    continue
                seen.add(name)
                names.append(name)
                if len(names) >= MARKETPLACE_USER_PUBLISHED_LIMIT:
                    break
            if not names:
                return {}
            query["skill_name"] = {"$in": names}
            limit = len(names)

        result: dict[str, dict[str, Any]] = {}
        cursor = collection.find(query, {"skill_name": 1, "is_active": 1}).limit(limit)
        async for doc in cursor:
            result[doc["skill_name"]] = {
                "is_active": doc.get("is_active", True),
            }
        return result

    # ==========================================
    # 文件操作
    # ==========================================

    async def get_marketplace_files(self, skill_name: str) -> dict[str, str]:
        """获取商城 Skill 所有文件"""
        collection = self._get_files_collection()
        files: dict[str, str] = {}
        cursor = collection.find(
            {"skill_name": skill_name},
            {"_id": 0, "file_path": 1, "content": 1},
        ).limit(MARKETPLACE_FILES_PER_SKILL_LIMIT)
        async for doc in cursor:
            files[doc["file_path"]] = doc["content"]
        return files

    async def iter_marketplace_file_batches(
        self,
        skill_name: str,
        *,
        batch_size: int = MARKETPLACE_FILE_COPY_BATCH_SIZE,
    ):
        """Yield marketplace files in bounded batches without materializing all contents."""
        collection = self._get_files_collection()
        size = max(1, int(batch_size))
        cursor = (
            collection.find(
                {"skill_name": skill_name},
                {"_id": 0, "file_path": 1, "content": 1},
            )
            .sort("file_path", 1)
            .limit(MARKETPLACE_FILES_PER_SKILL_LIMIT)
            .batch_size(size)
        )
        batch: dict[str, str] = {}
        async for doc in cursor:
            batch[doc["file_path"]] = doc.get("content", "")
            if len(batch) >= size:
                yield batch
                batch = {}
        if batch:
            yield batch

    async def get_marketplace_file(self, skill_name: str, file_path: str) -> Optional[str]:
        """获取商城 Skill 单个文件"""
        collection = self._get_files_collection()
        doc = await collection.find_one({"skill_name": skill_name, "file_path": file_path})
        return doc["content"] if doc else None

    async def set_marketplace_file(self, skill_name: str, file_path: str, content: str) -> None:
        """设置商城 Skill 单个文件"""
        collection = self._get_files_collection()
        now = utc_now_iso()
        await collection.update_one(
            {"skill_name": skill_name, "file_path": file_path},
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

    async def sync_marketplace_files(self, skill_name: str, files: dict[str, str]) -> None:
        """批量同步商城 Skill 文件"""
        if not files:
            return
        if len(files) > MARKETPLACE_FILES_PER_SKILL_LIMIT:
            raise ValueError(
                f"Marketplace skill contains too many files "
                f"(max {MARKETPLACE_FILES_PER_SKILL_LIMIT})"
            )
        collection = self._get_files_collection()
        now = utc_now_iso()

        from pymongo import UpdateOne

        await collection.delete_many(
            {
                "skill_name": skill_name,
                "file_path": {"$nin": list(files.keys())},
            }
        )

        operations: list = []
        for file_path, content in files.items():
            operations.append(
                UpdateOne(
                    {"skill_name": skill_name, "file_path": file_path},
                    {
                        "$set": {"content": content, "updated_at": now},
                        "$setOnInsert": {"created_at": now},
                    },
                    upsert=True,
                )
            )

        if operations:
            await collection.bulk_write(operations, ordered=True)

    async def list_marketplace_file_paths(self, skill_name: str) -> list[str]:
        """列出商城 Skill 所有文件路径"""
        collection = self._get_files_collection()
        paths = []
        cursor = collection.find({"skill_name": skill_name}, {"file_path": 1}).limit(
            MARKETPLACE_FILES_PER_SKILL_LIMIT
        )
        async for doc in cursor:
            paths.append(doc["file_path"])
        return paths

    # ==========================================
    # 标签操作
    # ==========================================

    async def list_all_tags(self) -> list[str]:
        """获取所有不重复的标签"""
        collection = self._get_meta_collection()
        tags = set()
        cursor = collection.find({"is_active": {"$ne": False}}, {"tags": 1}).limit(
            MARKETPLACE_TAG_SCAN_LIMIT
        )
        async for doc in cursor:
            for tag in doc.get("tags", []):
                if not isinstance(tag, str) or not tag:
                    continue
                tags.add(tag)
                if len(tags) >= MARKETPLACE_TAG_LIST_LIMIT:
                    return sorted(tags)
        return sorted(list(tags))

    async def close(self):
        """关闭连接（仅清理本地引用，不关闭全局 MongoDB 客户端）"""
        self._client = None
        self._meta_collection = None
        self._files_collection = None
        self._users_collection = None
