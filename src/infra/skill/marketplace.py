# src/infra/skill/marketplace.py
import io
import zipfile
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

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
from src.kernel.config import settings

logger = get_logger(__name__)

MAX_ZIP_SIZE = 10 * 1024 * 1024  # 10MB


if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection


class MarketplaceStorage:
    """商城 Skill 存储"""

    def __init__(self):
        self._client: Optional["AsyncIOMotorClient"] = None
        self._meta_collection: Optional["AsyncIOMotorCollection"] = None
        self._files_collection: Optional["AsyncIOMotorCollection"] = None

    def _get_meta_collection(self) -> "AsyncIOMotorCollection":
        if self._meta_collection is None:
            self._client = get_mongo_client()
            db = self._client[settings.MONGODB_DB]
            self._meta_collection = db[SKILL_MARKETPLACE_COLLECTION]
        return self._meta_collection

    def _get_files_collection(self) -> "AsyncIOMotorCollection":
        if self._files_collection is None:
            self._client = get_mongo_client()
            db = self._client[settings.MONGODB_DB]
            self._files_collection = db[SKILL_MARKETPLACE_FILES_COLLECTION]
        return self._files_collection

    async def ensure_indexes(self) -> None:
        """创建索引"""
        meta = self._get_meta_collection()
        await meta.create_index("skill_name", unique=True, background=True)

        files = self._get_files_collection()
        await files.create_index(
            [("skill_name", 1), ("file_path", 1)],
            unique=True,
            background=True,
        )

    # ==========================================
    # 元数据操作
    # ==========================================

    async def list_marketplace_skills(
        self, tags: Optional[list[str]] = None, search: Optional[str] = None
    ) -> list[MarketplaceSkillResponse]:
        """列出所有商城 Skills（可选按标签筛选/搜索）"""
        collection = self._get_meta_collection()

        query: dict[str, Any] = {}
        if tags:
            query["tags"] = {"$in": tags}
        if search:
            query["$or"] = [
                {"skill_name": {"$regex": search, "$options": "i"}},
                {"description": {"$regex": search, "$options": "i"}},
            ]

        files_collection = self._get_files_collection()
        results = []
        async for doc in collection.find(query):
            # 统计文件数量
            file_count = await files_collection.count_documents({"skill_name": doc["skill_name"]})
            results.append(
                MarketplaceSkillResponse(
                    skill_name=doc["skill_name"],
                    description=doc.get("description", ""),
                    tags=doc.get("tags", []),
                    version=doc.get("version", "1.0.0"),
                    created_at=doc.get("created_at"),
                    updated_at=doc.get("updated_at"),
                    created_by=doc.get("created_by"),
                    file_count=file_count,
                )
            )
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
            version=doc.get("version", "1.0.0"),
            created_at=doc.get("created_at"),
            updated_at=doc.get("updated_at"),
            created_by=doc.get("created_by"),
        )

    async def get_marketplace_skill_response(
        self, skill_name: str
    ) -> Optional[MarketplaceSkillResponse]:
        """获取商城 Skill 响应（含文件数量）"""
        skill = await self.get_marketplace_skill(skill_name)
        if not skill:
            return None
        files_collection = self._get_files_collection()
        file_count = await files_collection.count_documents({"skill_name": skill_name})
        return MarketplaceSkillResponse(
            skill_name=skill.skill_name,
            description=skill.description,
            tags=skill.tags,
            version=skill.version,
            created_at=skill.created_at,
            updated_at=skill.updated_at,
            created_by=skill.created_by,
            file_count=file_count,
        )

    async def create_marketplace_skill(
        self, data: MarketplaceSkillCreate, admin_user_id: str
    ) -> MarketplaceSkill:
        """创建商城 Skill 元数据"""
        collection = self._get_meta_collection()
        now = datetime.now(timezone.utc).isoformat()

        # 检查是否已存在
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
            "created_by": admin_user_id,
        }
        await collection.insert_one(doc)
        return MarketplaceSkill(**doc)

    async def update_marketplace_skill(
        self, skill_name: str, data: MarketplaceSkillUpdate
    ) -> Optional[MarketplaceSkill]:
        """更新商城 Skill 元数据"""
        collection = self._get_meta_collection()

        existing = await collection.find_one({"skill_name": skill_name})
        if not existing:
            return None

        update_data: dict[str, Any] = {"updated_at": datetime.now(timezone.utc).isoformat()}
        if data.description is not None:
            update_data["description"] = data.description
        if data.tags is not None:
            update_data["tags"] = data.tags
        if data.version is not None:
            update_data["version"] = data.version

        await collection.update_one({"skill_name": skill_name}, {"$set": update_data})

        updated = await collection.find_one({"skill_name": skill_name})
        return MarketplaceSkill(**updated) if updated else None

    async def delete_marketplace_skill(self, skill_name: str) -> bool:
        """删除商城 Skill 元数据和所有文件"""
        meta = self._get_meta_collection()
        files = self._get_files_collection()

        # 删除元数据
        meta_result = await meta.delete_one({"skill_name": skill_name})

        # 删除所有文件
        await files.delete_many({"skill_name": skill_name})

        return meta_result.deleted_count > 0

    # ==========================================
    # 文件操作
    # ==========================================

    async def get_marketplace_files(self, skill_name: str) -> dict[str, str]:
        """获取商城 Skill 所有文件"""
        collection = self._get_files_collection()
        files: dict[str, str] = {}
        async for doc in collection.find({"skill_name": skill_name}):
            files[doc["file_path"]] = doc["content"]
        return files

    async def get_marketplace_file(self, skill_name: str, file_path: str) -> Optional[str]:
        """获取商城 Skill 单个文件"""
        collection = self._get_files_collection()
        doc = await collection.find_one({"skill_name": skill_name, "file_path": file_path})
        return doc["content"] if doc else None

    async def set_marketplace_file(self, skill_name: str, file_path: str, content: str) -> None:
        """设置商城 Skill 单个文件"""
        collection = self._get_files_collection()
        now = datetime.now(timezone.utc).isoformat()
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
        collection = self._get_files_collection()
        now = datetime.now(timezone.utc).isoformat()

        from pymongo import DeleteOne, UpdateOne

        # 获取现有文件路径
        existing_paths = set()
        async for doc in collection.find({"skill_name": skill_name}, {"file_path": 1}):
            existing_paths.add(doc["file_path"])

        new_paths = set(files.keys())
        removed_paths = existing_paths - new_paths

        operations = []
        for path in removed_paths:
            operations.append(DeleteOne({"skill_name": skill_name, "file_path": path}))
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
        async for doc in collection.find({"skill_name": skill_name}, {"file_path": 1}):
            paths.append(doc["file_path"])
        return paths

    # ==========================================
    # ZIP 上传
    # ==========================================

    async def upload_from_zip(
        self,
        skill_name: str,
        zip_content: bytes,
        admin_user_id: str,
    ) -> MarketplaceSkill:
        """从 ZIP 上传商城 Skill 文件"""
        if len(zip_content) > MAX_ZIP_SIZE:
            raise ValueError("ZIP file too large (max 10MB)")

        try:
            zf = zipfile.ZipFile(io.BytesIO(zip_content))
        except zipfile.BadZipFile:
            raise ValueError("Invalid ZIP file")

        try:
            files = self._parse_zip(zf)

            # 确保 Skill 存在
            skill = await self.get_marketplace_skill(skill_name)
            if not skill:
                skill = await self.create_marketplace_skill(
                    MarketplaceSkillCreate(skill_name=skill_name),
                    admin_user_id,
                )

            # 同步文件
            await self.sync_marketplace_files(skill_name, files)

            return skill
        finally:
            zf.close()

    def _parse_zip(self, zf: zipfile.ZipFile) -> dict[str, str]:
        """解析 ZIP 文件"""
        all_files: dict[str, str] = {}

        names = zf.namelist()
        top_level = set()
        for n in names:
            parts = n.split("/")
            if parts[0]:
                top_level.add(parts[0])

        prefix = ""
        if len(top_level) == 1:
            top = list(top_level)[0]
            is_dir = any(n.startswith(top + "/") for n in names)
            if is_dir:
                prefix = top + "/"

        for name in names:
            if (
                name.endswith("/")
                or "__MACOSX" in name
                or name.endswith(".DS_Store")
                or name.endswith("Thumbs.db")
                or ".git/" in name
            ):
                continue
            if name.startswith(prefix):
                rel_path = name[len(prefix) :]
            else:
                rel_path = name
            if not rel_path:
                continue

            try:
                raw = zf.read(name)
            except Exception:
                continue

            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                continue

            all_files[rel_path] = text

        return all_files

    # ==========================================
    # 标签操作
    # ==========================================

    async def list_all_tags(self) -> list[str]:
        """获取所有不重复的标签"""
        collection = self._get_meta_collection()
        tags = set()
        async for doc in collection.find({}, {"tags": 1}):
            for tag in doc.get("tags", []):
                tags.add(tag)
        return sorted(list(tags))

    async def close(self):
        """关闭连接"""
        if self._client:
            self._client.close()
            self._client = None
            self._meta_collection = None
            self._files_collection = None
