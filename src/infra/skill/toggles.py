# src/infra/skill/toggles.py
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection

from src.infra.logging import get_logger
from src.infra.skill.constants import SKILL_TOGGLES_COLLECTION
from src.infra.skill.types import InstalledFrom, SkillToggle
from src.infra.storage.mongodb import get_mongo_client
from src.kernel.config import settings

logger = get_logger(__name__)


class TogglesStorage:
    """用户 Skill 开关存储"""

    def __init__(self):
        self._client: Optional["AsyncIOMotorClient"] = None
        self._collection: Optional["AsyncIOMotorCollection"] = None

    def _get_collection(self) -> "AsyncIOMotorCollection":
        if self._collection is None:
            self._client = get_mongo_client()
            db = self._client[settings.MONGODB_DB]
            self._collection = db[SKILL_TOGGLES_COLLECTION]
        return self._collection

    async def ensure_indexes(self) -> None:
        """创建索引"""
        collection = self._get_collection()
        await collection.create_index(
            [("skill_name", 1), ("user_id", 1)],
            unique=True,
            background=True,
        )

    async def get_toggle(self, skill_name: str, user_id: str) -> Optional[SkillToggle]:
        """获取用户的某个 Skill 开关状态"""
        collection = self._get_collection()
        doc = await collection.find_one({"skill_name": skill_name, "user_id": user_id})
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

    async def list_user_toggles(self, user_id: str) -> list[SkillToggle]:
        """列出用户的所有开关"""
        collection = self._get_collection()
        toggles = []
        async for doc in collection.find({"user_id": user_id}):
            toggles.append(
                SkillToggle(
                    skill_name=doc["skill_name"],
                    user_id=doc["user_id"],
                    enabled=doc.get("enabled", True),
                    installed_from=InstalledFrom(doc.get("installed_from", "manual")),
                    created_at=doc.get("created_at"),
                    updated_at=doc.get("updated_at"),
                )
            )
        return toggles

    async def list_enabled_skills(self, user_id: str) -> list[str]:
        """列出用户所有 enabled=True 的 skill_names"""
        collection = self._get_collection()
        names = []
        async for doc in collection.find({"user_id": user_id, "enabled": True}):
            names.append(doc["skill_name"])
        return names

    async def create_toggle(
        self,
        skill_name: str,
        user_id: str,
        enabled: bool = True,
        installed_from: InstalledFrom = InstalledFrom.MANUAL,
    ) -> SkillToggle:
        """创建开关记录"""
        collection = self._get_collection()
        now = datetime.now(timezone.utc).isoformat()
        doc = {
            "skill_name": skill_name,
            "user_id": user_id,
            "enabled": enabled,
            "installed_from": installed_from.value,
            "created_at": now,
            "updated_at": now,
        }
        await collection.insert_one(doc)
        return SkillToggle(
            skill_name=skill_name,
            user_id=user_id,
            enabled=enabled,
            installed_from=installed_from,
            created_at=now,
            updated_at=now,
        )

    async def upsert_toggle(
        self,
        skill_name: str,
        user_id: str,
        enabled: bool = True,
        installed_from: Optional[InstalledFrom] = None,
    ) -> SkillToggle:
        """Upsert 开关记录（使用 find_one_and_update 原子操作避免竞态）"""
        collection = self._get_collection()
        now = datetime.now(timezone.utc).isoformat()

        update_data = {
            "enabled": enabled,
            "updated_at": now,
        }
        if installed_from:
            update_data["installed_from"] = installed_from.value

        # 使用 find_one_and_update 进行原子 upsert
        result = await collection.find_one_and_update(
            {"skill_name": skill_name, "user_id": user_id},
            {
                "$set": update_data,
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
        existing = await self.get_toggle(skill_name, user_id)
        if not existing:
            return None
        new_enabled = not existing.enabled
        return await self.upsert_toggle(skill_name, user_id, enabled=new_enabled)

    async def delete_toggle(self, skill_name: str, user_id: str) -> bool:
        """删除开关记录"""
        collection = self._get_collection()
        result = await collection.delete_one({"skill_name": skill_name, "user_id": user_id})
        return result.deleted_count > 0

    async def delete_user_toggles(self, user_id: str, skill_name: str) -> int:
        """删除用户某个 Skill 的开关记录"""
        collection = self._get_collection()
        result = await collection.delete_many({"user_id": user_id, "skill_name": skill_name})
        return result.deleted_count

    async def close(self):
        """关闭连接"""
        if self._client:
            self._client.close()
            self._client = None
            self._collection = None
