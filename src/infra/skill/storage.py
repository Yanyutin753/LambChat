"""
Skill 存储层 - 简化架构

2 张核心表：
- skill_files: 用户文件存储（包括 __meta__ 元数据文档）
- skill_marketplace / skill_marketplace_files: 商城（见 marketplace.py）
"""

import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

from src.infra.logging import get_logger
from src.infra.skill.binary import (
    SkillBinaryRef,
    build_binary_ref_content,
    build_storage_key,
    guess_mime_type,
    parse_binary_ref,
)
from src.infra.skill.constants import SKILL_FILES_COLLECTION
from src.infra.skill.types import InstalledFrom, SkillMeta
from src.infra.storage.mongodb import get_mongo_client
from src.kernel.config import settings

logger = get_logger(__name__)

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection


class SkillStorage:
    """
    用户 Skill 文件存储

    提供文件级别的 CRUD 操作。
    元数据（installed_from, published_marketplace_name）存储在 skill_files 的 __meta__ 文档中。
    enabled/disabled 状态存储在用户 metadata.disabled_skills 中。
    """

    def __init__(self):
        self._client: Optional["AsyncIOMotorClient"] = None
        self._files_collection: Optional["AsyncIOMotorCollection"] = None

    def _get_files_collection(self) -> "AsyncIOMotorCollection":
        if self._files_collection is None:
            self._client = get_mongo_client()
            db = self._client[settings.MONGODB_DB]
            self._files_collection = db[SKILL_FILES_COLLECTION]
        return self._files_collection

    async def ensure_indexes(self) -> None:
        """创建索引"""
        files = self._get_files_collection()
        await files.create_index(
            [("skill_name", 1), ("user_id", 1), ("file_path", 1)],
            unique=True,
            background=True,
        )

    # ==========================================
    # 文件操作
    # ==========================================

    async def get_skill_files(self, skill_name: str, user_id: str) -> dict[str, str]:
        """获取用户某个 Skill 的所有文件（排除 __meta__）"""
        collection = self._get_files_collection()
        files: dict[str, str] = {}
        async for doc in collection.find({"skill_name": skill_name, "user_id": user_id}):
            if doc["file_path"] != "__meta__":
                files[doc["file_path"]] = doc["content"]
        return files

    async def get_skill_file(self, skill_name: str, file_path: str, user_id: str) -> Optional[str]:
        """获取用户某个 Skill 的单个文件"""
        collection = self._get_files_collection()
        doc = await collection.find_one(
            {
                "skill_name": skill_name,
                "user_id": user_id,
                "file_path": file_path,
            }
        )
        return doc["content"] if doc else None

    async def set_skill_file(
        self, skill_name: str, file_path: str, content: str, user_id: str
    ) -> None:
        """原子 upsert 单个文件（文本内容）"""
        collection = self._get_files_collection()
        now = datetime.now(timezone.utc).isoformat()
        await collection.update_one(
            {"skill_name": skill_name, "user_id": user_id, "file_path": file_path},
            {
                "$set": {"content": content, "updated_at": now},
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )

    async def set_skill_binary_file(
        self,
        skill_name: str,
        file_path: str,
        data: bytes,
        user_id: str,
        mime_type: Optional[str] = None,
    ) -> SkillBinaryRef:
        """上传二进制文件到 S3/本地存储，并在 MongoDB 存储引用。"""
        from src.infra.storage.s3.service import get_or_init_storage

        if not mime_type:
            mime_type = guess_mime_type(file_path)

        storage_key = build_storage_key(user_id, skill_name, file_path)
        storage_service = await get_or_init_storage()

        # 上传到 S3/本地存储
        await storage_service.upload_to_key(
            data=data,
            key=storage_key,
            content_type=mime_type,
            skip_size_limit=True,  # size already validated at API layer
        )

        # 构建引用并存入 MongoDB
        ref_content = build_binary_ref_content(storage_key, mime_type, len(data))
        await self.set_skill_file(skill_name, file_path, ref_content, user_id)

        return SkillBinaryRef(
            storage_key=storage_key,
            mime_type=mime_type,
            size=len(data),
        )

    async def update_skill_file_cas(
        self,
        skill_name: str,
        file_path: str,
        expected_content: str,
        new_content: str,
        user_id: str,
    ) -> bool:
        """
        Compare-and-swap: 仅当当前内容匹配 expected_content 时才更新。
        用于防止并发编辑丢失更新。

        Returns:
            True 如果更新成功，False 如果内容已被其他人修改
        """
        collection = self._get_files_collection()
        now = datetime.now(timezone.utc).isoformat()
        result = await collection.update_one(
            {
                "skill_name": skill_name,
                "user_id": user_id,
                "file_path": file_path,
                "content": expected_content,
            },
            {
                "$set": {"content": new_content, "updated_at": now},
            },
        )
        return result.modified_count > 0

    async def delete_skill_file(self, skill_name: str, file_path: str, user_id: str) -> None:
        """删除单个文件（如果是二进制引用，同时删除 S3 对象）"""
        collection = self._get_files_collection()
        doc = await collection.find_one(
            {"skill_name": skill_name, "user_id": user_id, "file_path": file_path},
        )
        if doc:
            # 检查是否为二进制引用，如果是则删除 S3 对象
            binary_ref = parse_binary_ref(doc.get("content", ""))
            if binary_ref:
                await self._delete_s3_object(binary_ref.storage_key)
            await collection.delete_one(
                {"skill_name": skill_name, "user_id": user_id, "file_path": file_path},
            )

    async def _delete_s3_object(self, storage_key: str) -> None:
        """删除 S3/本地存储中的文件"""
        try:
            from src.infra.storage.s3.service import get_or_init_storage

            storage_service = await get_or_init_storage()
            await storage_service.delete_file(storage_key)
        except Exception as e:
            logger.warning(f"Failed to delete S3 object {storage_key}: {e}")

    async def sync_skill_files(self, skill_name: str, files: dict[str, str], user_id: str) -> None:
        """批量同步文件（替换所有，但保留 __meta__）。支持文本和二进制引用。"""
        if not files:
            return
        collection = self._get_files_collection()
        now = datetime.now(timezone.utc).isoformat()

        # 获取现有文件路径和内容（排除 __meta__），用于检测二进制引用
        existing_docs: dict[str, str] = {}
        async for doc in collection.find(
            {"skill_name": skill_name, "user_id": user_id, "file_path": {"$ne": "__meta__"}},
            {"file_path": 1, "content": 1},
        ):
            existing_docs[doc["file_path"]] = doc.get("content", "")

        existing_paths = set(existing_docs.keys())
        new_paths = set(files.keys())
        removed_paths = existing_paths - new_paths

        from pymongo import DeleteOne, UpdateOne

        operations: list = []

        # 删除不再存在的文件（包括 S3 清理）
        s3_keys_to_delete: list[str] = []
        for path in removed_paths:
            binary_ref = parse_binary_ref(existing_docs.get(path, ""))
            if binary_ref:
                s3_keys_to_delete.append(binary_ref.storage_key)
            operations.append(
                DeleteOne(
                    {
                        "skill_name": skill_name,
                        "user_id": user_id,
                        "file_path": path,
                    }
                )
            )

        for file_path, content in files.items():
            operations.append(
                UpdateOne(
                    {"skill_name": skill_name, "user_id": user_id, "file_path": file_path},
                    {
                        "$set": {"content": content, "updated_at": now},
                        "$setOnInsert": {"created_at": now},
                    },
                    upsert=True,
                )
            )

        if operations:
            await collection.bulk_write(operations, ordered=True)

        # 批量删除 S3 对象
        for s3_key in s3_keys_to_delete:
            await self._delete_s3_object(s3_key)

    async def delete_skill_files(self, skill_name: str, user_id: str) -> None:
        """删除用户某个 Skill 的所有文件（包括 S3 二进制清理）"""
        collection = self._get_files_collection()

        # 先收集所有二进制引用，清理 S3
        async for doc in collection.find(
            {"skill_name": skill_name, "user_id": user_id, "file_path": {"$ne": "__meta__"}},
            {"content": 1},
        ):
            binary_ref = parse_binary_ref(doc.get("content", ""))
            if binary_ref:
                await self._delete_s3_object(binary_ref.storage_key)

        await collection.delete_many(
            {
                "skill_name": skill_name,
                "user_id": user_id,
            }
        )

    async def list_skill_file_paths(self, skill_name: str, user_id: str) -> list[str]:
        """列出用户某个 Skill 的所有文件路径（排除 __meta__）"""
        collection = self._get_files_collection()
        paths = []
        async for doc in collection.find(
            {"skill_name": skill_name, "user_id": user_id, "file_path": {"$ne": "__meta__"}},
            {"file_path": 1},
        ):
            paths.append(doc["file_path"])
        return paths

    async def get_skill_file_stats(self, skill_name: str, user_id: str) -> dict[str, Any]:
        """获取单个 Skill 的文件统计信息（created_at/updated_at 来自文件聚合，排除 __meta__）"""
        collection = self._get_files_collection()
        pipeline: list[dict[str, Any]] = [
            {
                "$match": {
                    "skill_name": skill_name,
                    "user_id": user_id,
                    "file_path": {"$ne": "__meta__"},
                }
            },
            {
                "$group": {
                    "_id": "$skill_name",
                    "file_count": {"$sum": 1},
                    "created_at": {"$min": "$created_at"},
                    "updated_at": {"$max": "$updated_at"},
                }
            },
        ]
        async for doc in collection.aggregate(pipeline):  # type: ignore[arg-type]
            return {
                "file_count": doc["file_count"],
                "created_at": doc.get("created_at"),
                "updated_at": doc.get("updated_at"),
            }
        return {"file_count": 0, "created_at": None, "updated_at": None}

    async def list_user_skills(
        self,
        user_id: str,
        skip: int = 0,
        limit: int = 100,
        disabled_skills: Optional[list[str]] = None,
    ) -> list[dict[str, Any]]:
        """列出用户所有 Skill（带文件信息）

        Args:
            user_id: 用户 ID
            skip: 分页跳过数量
            limit: 分页限制
            disabled_skills: 从用户 metadata 中获取的 disabled_skills 列表
        """
        if disabled_skills is None:
            disabled_skills = []
        disabled_set = set(disabled_skills)

        collection = self._get_files_collection()

        # 使用 aggregation 一次获取所有 skill 的统计信息 + 文件路径（排除 __meta__）
        pipeline: list[dict[str, Any]] = [
            {"$match": {"user_id": user_id, "file_path": {"$ne": "__meta__"}}},
            {
                "$group": {
                    "_id": "$skill_name",
                    "file_count": {"$sum": 1},
                    "file_paths": {"$push": "$file_path"},
                    "created_at": {"$min": "$created_at"},
                    "updated_at": {"$max": "$updated_at"},
                }
            },
            {"$sort": {"_id": 1}},
            {"$skip": skip},
            {"$limit": limit},
        ]
        skill_stats: dict[str, dict] = {}
        async for doc in collection.aggregate(pipeline):  # type: ignore[arg-type]
            skill_stats[doc["_id"]] = {
                "file_count": doc["file_count"],
                "file_paths": doc.get("file_paths", []),
                "created_at": doc.get("created_at"),
                "updated_at": doc.get("updated_at"),
            }

        # 批量获取所有 __meta__ 文档
        skill_names = list(skill_stats.keys())
        meta_map: dict[str, SkillMeta] = {}
        if skill_names:
            async for doc in collection.find(
                {"skill_name": {"$in": skill_names}, "user_id": user_id, "file_path": "__meta__"},
                {"skill_name": 1, "content": 1},
            ):
                try:
                    data = json.loads(doc["content"])
                    meta_map[doc["skill_name"]] = SkillMeta(**data)
                except Exception:
                    pass

        # 组装结果
        result = []
        for skill_name in sorted(skill_stats.keys()):
            stats = skill_stats[skill_name]
            meta = meta_map.get(skill_name)
            enabled = skill_name not in disabled_set

            result.append(
                {
                    "skill_name": skill_name,
                    "enabled": enabled,
                    "file_count": stats["file_count"],
                    "file_paths": stats.get("file_paths", []),
                    "installed_from": meta.installed_from.value if meta else None,
                    "published_marketplace_name": meta.published_marketplace_name if meta else None,
                    "created_at": stats.get("created_at"),
                    "updated_at": stats.get("updated_at"),
                }
            )

        return result

    async def batch_get_skill_md_contents(
        self, skill_names: list[str], user_id: str
    ) -> dict[str, str]:
        """批量获取多个 skill 的 SKILL.md 内容"""
        if not skill_names:
            return {}
        collection = self._get_files_collection()
        docs = {}
        async for doc in collection.find(
            {"skill_name": {"$in": skill_names}, "user_id": user_id, "file_path": "SKILL.md"},
            {"skill_name": 1, "content": 1},
        ):
            docs[doc["skill_name"]] = doc.get("content", "")
        return docs

    async def batch_get_skill_files(
        self, skill_keys: list[tuple[str, str]]
    ) -> dict[tuple[str, str], dict[str, str]]:
        """批量获取多个 Skill 的文件"""
        if not skill_keys:
            return {}

        collection = self._get_files_collection()

        # 去重
        seen: set[tuple[str, str]] = set()
        or_clauses = []
        for skill_name, user_id in skill_keys:
            key = (skill_name, user_id)
            if key not in seen:
                seen.add(key)
                or_clauses.append({"skill_name": skill_name, "user_id": user_id})

        result: dict[tuple[str, str], dict[str, str]] = {}
        async for doc in collection.find({"$or": or_clauses}):
            key = (doc["skill_name"], doc["user_id"])
            if key not in result:
                result[key] = {}
            if doc["file_path"] != "__meta__":
                result[key][doc["file_path"]] = doc["content"]

        return result

    # ==========================================
    # Skill 元数据操作（存储在 __meta__ 文档中）
    # ==========================================

    async def get_skill_meta(self, skill_name: str, user_id: str) -> Optional[SkillMeta]:
        """获取 skill 元数据（从 __meta__ 文档）"""
        collection = self._get_files_collection()
        doc = await collection.find_one(
            {"skill_name": skill_name, "user_id": user_id, "file_path": "__meta__"}
        )
        if not doc:
            return None
        try:
            data = json.loads(doc["content"])
            return SkillMeta(**data)
        except Exception:
            return None

    async def set_skill_meta(
        self,
        skill_name: str,
        user_id: str,
        installed_from: InstalledFrom = InstalledFrom.MANUAL,
        published_marketplace_name: Optional[str] = None,
    ) -> None:
        """设置 skill 元数据（存储为 __meta__ 文档）"""
        collection = self._get_files_collection()
        now = datetime.now(timezone.utc).isoformat()
        meta = SkillMeta(
            installed_from=installed_from,
            published_marketplace_name=published_marketplace_name,
            created_at=now,
            updated_at=now,
        )
        await collection.update_one(
            {"skill_name": skill_name, "user_id": user_id, "file_path": "__meta__"},
            {
                "$set": {"content": json.dumps(meta.model_dump()), "updated_at": now},
                "$setOnInsert": {"created_at": now},
            },
            upsert=True,
        )

    async def delete_skill_meta(self, skill_name: str, user_id: str) -> None:
        """删除 skill __meta__ 文档"""
        collection = self._get_files_collection()
        await collection.delete_one(
            {"skill_name": skill_name, "user_id": user_id, "file_path": "__meta__"}
        )

    async def delete_skill_and_meta(self, skill_name: str, user_id: str) -> None:
        """删除 Skill 所有文件（包括 __meta__ 和 S3 二进制文件）"""
        collection = self._get_files_collection()

        # 先收集所有二进制引用，清理 S3
        async for doc in collection.find(
            {"skill_name": skill_name, "user_id": user_id, "file_path": {"$ne": "__meta__"}},
            {"content": 1},
        ):
            binary_ref = parse_binary_ref(doc.get("content", ""))
            if binary_ref:
                await self._delete_s3_object(binary_ref.storage_key)

        await collection.delete_many({"skill_name": skill_name, "user_id": user_id})

    # ==========================================
    # 生效 Skills（供 DeepAgent 使用）
    # ==========================================

    async def get_effective_skills(
        self, user_id: str, disabled_skills: Optional[list[str]] = None
    ) -> dict[str, dict[str, Any]]:
        """
        获取用户生效的 Skills（已启用 + 有文件）

        Args:
            user_id: 用户 ID
            disabled_skills: 从用户 metadata 中获取的 disabled_skills 列表

        Returns:
            {
                "skills": {
                    "skill_name": {
                        "files": {file_path: content},
                        "enabled": True,
                    }
                }
            }
        """
        from src.infra.skill.constants import SKILLS_CACHE_KEY_PREFIX, SKILLS_CACHE_TTL

        cache_key = f"{SKILLS_CACHE_KEY_PREFIX}{user_id}"

        # 尝试从 Redis 缓存获取
        try:
            from src.infra.storage.redis import get_redis_client

            redis_client = get_redis_client()
            cached = await redis_client.get(cache_key)
            if cached:
                return json.loads(cached)
        except Exception as e:
            logger.warning(f"[Skills Cache] Redis get failed: {e}")

        if disabled_skills is None:
            disabled_skills = await self._get_user_disabled_skills(user_id)
        disabled_set = set(disabled_skills)

        # 获取所有用户 skill 名称（排除 __meta__）
        all_skill_names = await self.get_all_user_skill_names(user_id)
        # 过滤掉 disabled 的
        enabled_names = [name for name in all_skill_names if name not in disabled_set]

        if not enabled_names:
            return {"skills": {}}

        # 批量获取文件
        skill_keys = [(name, user_id) for name in enabled_names]
        files_map = await self.batch_get_skill_files(skill_keys)

        result: dict[str, Any] = {"skills": {}}
        for name in enabled_names:
            files = files_map.get((name, user_id), {})
            if files:  # 只包含有文件的 skill
                # 从 SKILL.md frontmatter 解析 description
                description = ""
                if "SKILL.md" in files:
                    try:
                        from src.infra.skill.parser import parse_skill_md

                        _, parsed_desc, _ = parse_skill_md(files["SKILL.md"])
                        if parsed_desc:
                            description = parsed_desc
                    except Exception:
                        pass

                result["skills"][name] = {
                    "name": name,
                    "description": description or f"Skill: {name}",
                    "files": files,
                    "enabled": True,
                }

        # 缓存
        try:
            from src.infra.storage.redis import get_redis_client

            redis_client = get_redis_client()

            await redis_client.set(cache_key, json.dumps(result), ex=SKILLS_CACHE_TTL)
        except Exception as e:
            logger.warning(f"[Skills Cache] Redis set failed: {e}")

        return result

    async def _get_user_disabled_skills(self, user_id: str) -> list[str]:
        """Load disabled skills from user metadata for cache-safe default behavior."""
        try:
            from src.infra.user.storage import UserStorage

            user_storage = UserStorage()
            user_doc = await user_storage.get_by_id(user_id)
            if user_doc and user_doc.metadata:
                return user_doc.metadata.get("disabled_skills", [])
        except Exception as e:
            logger.warning(f"Failed to load disabled_skills for user {user_id}: {e}")
        return []

    async def get_all_user_skill_names(self, user_id: str) -> list[str]:
        """获取用户所有 skill 名称（无论 enabled/disabled，排除 __meta__）"""
        collection = self._get_files_collection()
        pipeline: list[dict[str, Any]] = [
            {"$match": {"user_id": user_id, "file_path": {"$ne": "__meta__"}}},
            {"$group": {"_id": "$skill_name"}},
        ]
        return [doc["_id"] async for doc in collection.aggregate(pipeline)]

    async def invalidate_user_cache(self, user_id: str) -> None:
        """失效用户缓存"""
        from src.infra.skill.constants import SKILLS_CACHE_KEY_PREFIX

        cache_key = f"{SKILLS_CACHE_KEY_PREFIX}{user_id}"
        try:
            from src.infra.storage.redis import get_redis_client

            redis_client = get_redis_client()
            await redis_client.delete(cache_key)
        except Exception as e:
            logger.warning(f"[Skills Cache] Redis delete failed: {e}")

    async def create_user_skill(
        self,
        skill_name: str,
        files: dict[str, str],
        user_id: str,
        installed_from: InstalledFrom = InstalledFrom.MANUAL,
        enabled: bool = True,
        binary_files: Optional[dict[str, bytes]] = None,
    ) -> None:
        """
        Create a complete user skill: sync files + upload binaries + create __meta__ + invalidate cache.

        This is the single entry point for all skill creation paths:
        - MarketplacePanel direct create (installed_from=MARKETPLACE)
        - SkillsPanel manual create (installed_from=MANUAL)
        - GitHub import (installed_from=MANUAL)
        - ZIP upload (installed_from=MANUAL)

        Args:
            files: 文本文件 {file_path: text_content}
            binary_files: 二进制文件 {file_path: binary_data}，上传到 S3/local
            user_id: 用户 ID
            skill_name: Skill 名称
            installed_from: 安装来源
            enabled: 是否启用

        Note: The `enabled` parameter is kept for API compatibility but the actual
        enabled/disabled state is managed in user.metadata.disabled_skills.
        """
        if not files and not binary_files:
            raise ValueError("Skill must have at least one file")

        await self.sync_skill_files(skill_name, files, user_id)

        # 上传二进制文件
        if binary_files:
            for file_path, data in binary_files.items():
                await self.set_skill_binary_file(skill_name, file_path, data, user_id)

        await self.set_skill_meta(skill_name, user_id, installed_from=installed_from)
        await self.invalidate_user_cache(user_id)

    async def close(self):
        """关闭连接（仅清理本地引用，不关闭全局 MongoDB 客户端）"""
        self._files_collection = None
