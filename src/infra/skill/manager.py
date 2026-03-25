"""
Skill 管理器

门面类，封装 SkillStorage 操作。
"""

from typing import Optional

from src.infra.skill.storage import SkillStorage
from src.infra.user.storage import UserStorage
from src.kernel.config import settings


class SkillManager:
    """Skill 管理器"""

    def __init__(self, user_id: Optional[str] = None):
        self.user_id = user_id
        self.storage = SkillStorage() if settings.ENABLE_SKILLS else None

    async def _get_disabled_skills(self) -> list[str]:
        """Get disabled_skills from user metadata"""
        if not self.user_id:
            return []
        try:
            user_storage = UserStorage()
            user_doc = await user_storage.get_by_id(self.user_id)
            if user_doc and user_doc.metadata:
                return user_doc.metadata.get("disabled_skills", [])
            return []
        except Exception:
            return []

    async def list_skills_async(self) -> list[dict]:
        """列出用户所有 Skills"""
        if not self.user_id or not self.storage:
            return []
        try:
            disabled_skills = await self._get_disabled_skills()
            skills = await self.storage.list_user_skills(
                self.user_id, disabled_skills=disabled_skills
            )
            return [
                {
                    "name": s["skill_name"],
                    "enabled": s["enabled"],
                    "file_count": s["file_count"],
                    "installed_from": s.get("installed_from"),
                }
                for s in skills
            ]
        except Exception:
            return []

    async def get_skill_async(self, skill_name: str) -> Optional[dict]:
        """获取指定 Skill"""
        if not self.user_id or not self.storage:
            return None
        try:
            files = await self.storage.get_skill_files(skill_name, self.user_id)
            if not files:
                return None
            # Get metadata from __meta__ doc
            meta = await self.storage.get_skill_meta(skill_name, self.user_id)
            # Compute enabled from disabled_skills
            disabled_skills = await self._get_disabled_skills()
            enabled = skill_name not in set(disabled_skills)
            return {
                "name": skill_name,
                "files": files,
                "enabled": enabled,
                "installed_from": meta.installed_from.value if meta else None,
            }
        except Exception:
            return None

    async def get_effective_skills(self) -> dict:
        """获取生效的 Skills"""
        if not self.user_id or not self.storage:
            return {}
        try:
            disabled_skills = await self._get_disabled_skills()
            result = await self.storage.get_effective_skills(
                self.user_id, disabled_skills=disabled_skills
            )
            return result.get("skills", {})
        except Exception:
            return {}
