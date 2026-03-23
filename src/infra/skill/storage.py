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

    async def list_user_skills(self, user_id: str) -> list[dict[str, Any]]:
        """列出用户所有 Skill（带文件信息）"""
        collection = self._get_files_collection()

        # 获取用户所有 skill_name（去重）
        skill_names: set[str] = set()
        async for doc in collection.find({"user_id": user_id}, {"skill_name": 1}):
            skill_names.add(doc["skill_name"])

        # 获取开关状态
        toggles_collection = self._get_toggles_collection()
        toggles: dict[str, dict] = {}
        async for doc in toggles_collection.find({"user_id": user_id}):
            toggles[doc["skill_name"]] = doc

        # 组装结果
        result = []
        for skill_name in sorted(skill_names):
            file_count = await collection.count_documents(
                {
                    "skill_name": skill_name,
                    "user_id": user_id,
                }
            )

            # 获取最早创建时间和最新更新时间
            created_at = None
            updated_at = None
            async for doc in collection.find({"skill_name": skill_name, "user_id": user_id}):
                if not created_at or doc.get("created_at", "") < created_at:
                    created_at = doc.get("created_at")
                if not updated_at or doc.get("updated_at", "") > updated_at:
                    updated_at = doc.get("updated_at")

            toggle = toggles.get(skill_name, {})

            result.append(
                {
                    "skill_name": skill_name,
                    "enabled": toggle.get("enabled", True),
                    "file_count": file_count,
                    "installed_from": toggle.get("installed_from"),
                    "created_at": created_at,
                    "updated_at": updated_at,
                }
            )

        return result

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
            created_at=doc.get("created_at"),
            updated_at=doc.get("updated_at"),
        )

    async def upsert_toggle(
        self,
        skill_name: str,
        user_id: str,
        enabled: bool = True,
        installed_from: Optional[InstalledFrom] = None,
    ) -> SkillToggle:
        """Upsert 开关记录（原子操作，避免竞态）"""
        collection = self._get_toggles_collection()
        now = datetime.now(timezone.utc).isoformat()

        # 使用 find_one_and_update 进行原子 upsert
        result = await collection.find_one_and_update(
            {"skill_name": skill_name, "user_id": user_id},
            {
                "$set": {
                    "enabled": enabled,
                    "updated_at": now,
                    **({"installed_from": installed_from.value} if installed_from else {}),
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
        """原子删除 Skill 文件和开关"""
        from pymongo import DeleteOne

        files_coll = self._get_files_collection()
        toggles_coll = self._get_toggles_collection()

        operations = [
            DeleteOne({"skill_name": skill_name, "user_id": user_id}),
            DeleteOne({"skill_name": skill_name, "user_id": user_id}),
        ]
        try:
            await toggles_coll.bulk_write([operations[1]])
            await files_coll.bulk_write([operations[0]])
        except Exception:
            # 回退：分开删除
            await files_coll.delete_many({"skill_name": skill_name, "user_id": user_id})
            await toggles_coll.delete_one({"skill_name": skill_name, "user_id": user_id})

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
                        from src.infra.skill.builtin import _parse_skill_md

                        _, parsed_desc, _ = _parse_skill_md(files["SKILL.md"])
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

    async def close(self):
        """关闭连接（仅清理本地引用，不关闭全局 MongoDB 客户端）"""
        self._files_collection = None
        self._toggles_collection = None
