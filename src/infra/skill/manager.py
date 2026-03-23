"""
Skill 管理器

门面类，封装 SkillStorage 操作。
"""

from typing import Optional

from src.infra.skill.storage import SkillStorage
from src.kernel.config import settings


class SkillManager:
    """Skill 管理器"""

    def __init__(self, user_id: Optional[str] = None):
        self.user_id = user_id
        self.storage = SkillStorage() if settings.ENABLE_SKILLS else None

    async def list_skills_async(self) -> list[dict]:
        """列出用户所有 Skills"""
        if not self.user_id or not self.storage:
            return []
        try:
            skills = await self.storage.list_user_skills(self.user_id)
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
            toggle = await self.storage.get_toggle(skill_name, self.user_id)
            return {
                "name": skill_name,
                "files": files,
                "enabled": toggle.enabled if toggle else True,
            }
        except Exception:
            return None

    async def get_effective_skills(self) -> dict:
        """获取生效的 Skills"""
        if not self.user_id or not self.storage:
            return {}
        try:
            result = await self.storage.get_effective_skills(self.user_id)
            return result.get("skills", {})
        except Exception:
            return {}
