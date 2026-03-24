"""
Skill 存储层 - 简化架构

3 张核心表：
- skill_files: 用户文件存储
- skill_toggles: 用户开关
- skill_marketplace / skill_marketplace_files: 商城（见 marketplace.py）
"""

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

from src.infra.logging import get_logger
from src.infra.skill.constants import (
    SKILL_FILES_COLLECTION,
    SKILL_TOGGLES_COLLECTION,
)
from src.infra.skill.types import InstalledFrom, SkillToggle
from src.infra.storage.mongodb import get_mongo_client
from src.kernel.config import settings

logger = get_logger(__name__)

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection


class SkillStorage:
    """
    用户 Skill 文件存储

    提供文件级别的 CRUD 操作和开关管理。
    """

    def __init__(self):
        self._client: Optional["AsyncIOMotorClient"] = None
        self._files_collection: Optional["AsyncIOMotorCollection"] = None
        self._toggles_collection: Optional["AsyncIOMotorCollection"] = None

    def _get_files_collection(self) -> "AsyncIOMotorCollection":
        if self._files_collection is None:
            self._client = get_mongo_client()
            db = self._client[settings.MONGODB_DB]
            self._files_collection = db[SKILL_FILES_COLLECTION]
        return self._files_collection

    def _get_toggles_collection(self) -> "AsyncIOMotorCollection":
        if self._toggles_collection is None:
            self._client = get_mongo_client()
            db = self._client[settings.MONGODB_DB]
            self._toggles_collection = db[SKILL_TOGGLES_COLLECTION]
        return self._toggles_collection

    async def ensure_indexes(self) -> None:
        """创建索引"""
        files = self._get_files_collection()
        await files.create_index(
            [("skill_name", 1), ("user_id", 1), ("file_path", 1)],
            unique=True,
            background=True,
        )

        toggles = self._get_toggles_collection()
        await toggles.create_index(
            [("skill_name", 1), ("user_id", 1)],
            unique=True,
            background=True,
        )

    # ==========================================
    # 文件操作
    # ==========================================

    async def get_skill_files(self, skill_name: str, user_id: str) -> dict[str, str]:
        """获取用户某个 Skill 的所有文件"""
        collection = self._get_files_collection()
        files: dict[str, str] = {}
        async for doc in collection.find({"skill_name": skill_name, "user_id": user_id}):
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
        """原子 upsert 单个文件"""
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
        """删除单个文件"""
        collection = self._get_files_collection()
        await collection.delete_one(
            {
                "skill_name": skill_name,
                "user_id": user_id,
                "file_path": file_path,
            }
        )

    async def sync_skill_files(self, skill_name: str, files: dict[str, str], user_id: str) -> None:
        """批量同步文件（替换所有）"""
        if not files:
            return
        collection = self._get_files_collection()
        now = datetime.now(timezone.utc).isoformat()

        # 获取现有文件路径
        existing_paths = set()
        async for doc in collection.find(
            {"skill_name": skill_name, "user_id": user_id}, {"file_path": 1}
        ):
            existing_paths.add(doc["file_path"])

        new_paths = set(files.keys())
        removed_paths = existing_paths - new_paths

        from pymongo import DeleteOne, UpdateOne

        operations = []
        for path in removed_paths:
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

    async def delete_skill_files(self, skill_name: str, user_id: str) -> None:
        """删除用户某个 Skill 的所有文件"""
        collection = self._get_files_collection()
        await collection.delete_many(
            {
                "skill_name": skill_name,
                "user_id": user_id,
            }
        )

    async def list_skill_file_paths(self, skill_name: str, user_id: str) -> list[str]:
        """列出用户某个 Skill 的所有文件路径"""
        collection = self._get_files_collection()
        paths = []
        async for doc in collection.find(
            {"skill_name": skill_name, "user_id": user_id}, {"file_path": 1}
        ):
            paths.append(doc["file_path"])
        return paths

    async def get_skill_file_stats(self, skill_name: str, user_id: str) -> dict[str, Any]:
        """获取单个 Skill 的文件统计信息（created_at/updated_at 来自文件聚合）"""
        collection = self._get_files_collection()
        pipeline = [
            {"$match": {"skill_name": skill_name, "user_id": user_id}},
            {
                "$group": {
                    "_id": "$skill_name",
                    "file_count": {"$sum": 1},
                    "created_at": {"$min": "$created_at"},
                    "updated_at": {"$max": "$updated_at"},
                }
            },
        ]
        async for doc in collection.aggregate(pipeline):
            return {
                "file_count": doc["file_count"],
                "created_at": doc.get("created_at"),
                "updated_at": doc.get("updated_at"),
            }
        return {"file_count": 0, "created_at": None, "updated_at": None}

    async def list_user_skills(self, user_id: str) -> list[dict[str, Any]]:
        """列出用户所有 Skill（带文件信息）"""
        collection = self._get_files_collection()

        # 使用 aggregation 一次获取所有 skill 的统计信息 + 文件路径
        pipeline = [
            {"$match": {"user_id": user_id}},
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
        ]
        skill_stats: dict[str, dict] = {}
        async for doc in collection.aggregate(pipeline):
            skill_stats[doc["_id"]] = {
                "file_count": doc["file_count"],
                "file_paths": doc.get("file_paths", []),
                "created_at": doc.get("created_at"),
                "updated_at": doc.get("updated_at"),
            }

        # 获取开关状态
        toggles_collection = self._get_toggles_collection()
        toggles: dict[str, dict] = {}
        async for doc in toggles_collection.find({"user_id": user_id}):
            toggles[doc["skill_name"]] = doc

        # 组装结果
        result = []
        for skill_name in sorted(skill_stats.keys()):
            stats = skill_stats[skill_name]
            toggle = toggles.get(skill_name, {})

            result.append(
                {
                    "skill_name": skill_name,
                    "enabled": toggle.get("enabled", True),
                    "file_count": stats["file_count"],
                    "file_paths": stats.get("file_paths", []),
                    "installed_from": toggle.get("installed_from"),
                    "published_marketplace_name": toggle.get("published_marketplace_name"),
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
            result[key][doc["file_path"]] = doc["content"]

        return result

    # ==========================================
    # 开关操作
    # ==========================================

    async def get_toggle(self, skill_name: str, user_id: str) -> Optional[SkillToggle]:
        """获取用户某个 Skill 的开关状态"""
        collection = self._get_toggles_collection()
        doc = await collection.find_one(
            {
                "skill_name": skill_name,
                "user_id": user_id,
            }
        )
        if not doc:
            return None
        return SkillToggle(
            skill_name=doc["skill_name"],
            user_id=doc["user_id"],
            enabled=doc.get("enabled", True),
            installed_from=InstalledFrom(doc.get("installed_from", "manual")),
            published_marketplace_name=doc.get("published_marketplace_name"),
            created_at=doc.get("created_at"),
            updated_at=doc.get("updated_at"),
        )

    async def upsert_toggle(
        self,
        skill_name: str,
        user_id: str,
        enabled: bool = True,
        installed_from: Optional[InstalledFrom] = None,
        published_marketplace_name: Optional[str] = None,
    ) -> SkillToggle:
        """Upsert 开关记录（原子操作，避免竞态）"""
        collection = self._get_toggles_collection()
        now = datetime.now(timezone.utc).isoformat()

        # 使用 find_one_and_update 进行原子 upsert
        # 注意：installed_from 只在首次创建时设置，更新时不覆盖
        result = await collection.find_one_and_update(
            {"skill_name": skill_name, "user_id": user_id},
            {
                "$set": {
                    "enabled": enabled,
                    "updated_at": now,
                    **(
                        {"published_marketplace_name": published_marketplace_name}
                        if published_marketplace_name is not None
                        else {}
                    ),
                },
                "$setOnInsert": {
                    "skill_name": skill_name,
                    "user_id": user_id,
                    "installed_from": (installed_from or InstalledFrom.MANUAL).value,
                    "created_at": now,
                },
            },
            upsert=True,
            return_document=True,
        )

        return SkillToggle(
            skill_name=result["skill_name"],
            user_id=result["user_id"],
            enabled=result.get("enabled", True),
            installed_from=InstalledFrom(result.get("installed_from", "manual")),
            published_marketplace_name=result.get("published_marketplace_name"),
            created_at=result.get("created_at"),
            updated_at=result.get("updated_at"),
        )

    async def toggle_skill(self, skill_name: str, user_id: str) -> Optional[SkillToggle]:
        """切换开关状态"""
        toggle = await self.get_toggle(skill_name, user_id)
        if not toggle:
            return None
        return await self.upsert_toggle(skill_name, user_id, enabled=not toggle.enabled)

    async def delete_toggle(self, skill_name: str, user_id: str) -> bool:
        """删除开关记录"""
        collection = self._get_toggles_collection()
        result = await collection.delete_one(
            {
                "skill_name": skill_name,
                "user_id": user_id,
            }
        )
        return result.deleted_count > 0

    async def delete_skill_and_toggle(self, skill_name: str, user_id: str) -> None:
        """删除 Skill 文件和开关（使用事务保证原子性）"""
        client = get_mongo_client()
        session = None
        try:
            session = await client.start_session()
            async with session.start_transaction():
                files_col = self._get_files_collection()
                await files_col.delete_many(
                    {"skill_name": skill_name, "user_id": user_id}, session=session,
                )
                toggles_col = self._get_toggles_collection()
                await toggles_col.delete_one(
                    {"skill_name": skill_name, "user_id": user_id}, session=session,
                )
        except Exception as e:
            logger.warning(f"Failed to delete skill '{skill_name}' atomically: {e}")
            # Fallback: try non-transactional delete
            try:
                await self.delete_skill_files(skill_name, user_id)
            except Exception as e2:
                logger.warning(f"Failed to delete skill files for '{skill_name}': {e2}")
            try:
                await self.delete_toggle(skill_name, user_id)
            except Exception as e2:
                logger.warning(f"Failed to delete toggle for '{skill_name}': {e2}")

    # ==========================================
    # 生效 Skills（供 DeepAgent 使用）
    # ==========================================

    async def get_effective_skills(self, user_id: str) -> dict[str, dict[str, Any]]:
        """
        获取用户生效的 Skills（已启用 + 有文件）

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
                import json

                return json.loads(cached)
        except Exception as e:
            logger.warning(f"[Skills Cache] Redis get failed: {e}")

        # 从 MongoDB 加载
        enabled_names = await self._get_enabled_skill_names(user_id)
        if not enabled_names:
            return {"skills": {}}

        # 批量获取文件
        skill_keys = [(name, user_id) for name in enabled_names]
        files_map = await self.batch_get_skill_files(skill_keys)

        result = {"skills": {}}
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
            import json

            await redis_client.set(cache_key, json.dumps(result), ex=SKILLS_CACHE_TTL)
        except Exception as e:
            logger.warning(f"[Skills Cache] Redis set failed: {e}")

        return result

    async def _get_enabled_skill_names(self, user_id: str) -> list[str]:
        """获取用户已启用的 skill_names"""
        collection = self._get_toggles_collection()
        names = []
        async for doc in collection.find({"user_id": user_id, "enabled": True}):
            names.append(doc["skill_name"])
        return names

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
    ) -> None:
        """
        Create a complete user skill: sync files + create toggle + invalidate cache.

        This is the single entry point for all skill creation paths:
        - MarketplacePanel direct create (installed_from=MARKETPLACE)
        - SkillsPanel manual create (installed_from=MANUAL)
        - GitHub import (installed_from=MANUAL)
        - ZIP upload (installed_from=MANUAL)
        """
        if not files:
            raise ValueError("Skill must have at least one file")

        await self.sync_skill_files(skill_name, files, user_id)
        await self.upsert_toggle(skill_name, user_id, enabled=enabled, installed_from=installed_from)
        await self.invalidate_user_cache(user_id)

    async def close(self):
        """关闭连接（仅清理本地引用，不关闭全局 MongoDB 客户端）"""
        self._files_collection = None
        self._toggles_collection = None
