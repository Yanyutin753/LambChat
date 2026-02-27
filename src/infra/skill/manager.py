"""
技能管理器

支持用户级别的技能访问。
"""

from typing import Optional

from src.infra.skill.storage import SkillStorage
from src.kernel.config import settings
from src.kernel.schemas.skill import SystemSkill, UserSkill


class SkillManager:
    """
    技能管理器

    管理技能的加载和执行。
    支持从 MongoDB 加载技能。
    支持用户级别的技能访问（系统技能 + 用户技能）。
    """

    def __init__(self, user_id: Optional[str] = None):
        """
        初始化技能管理器

        Args:
            user_id: 用户 ID，用于获取用户级别的技能
        """
        self.user_id = user_id
        self.storage = SkillStorage() if settings.ENABLE_SKILLS else None
        self._loaded_skills: dict = {}

    def list_skills(self) -> list[dict]:
        """列出所有可用技能（同步版本，仅 MongoDB）"""
        return []

    async def list_skills_async(self) -> list[dict]:
        """
        列出所有可用技能（异步版本）

        如果提供了 user_id，返回用户可见的技能（系统技能 + 用户技能）。
        否则返回所有技能。
        """
        # 如果有 user_id 且有 MongoDB，使用新的存储方法
        if self.user_id and self.storage:
            try:
                visible_skills = await self.storage.get_visible_skills(self.user_id, is_admin=False)
                # 转换为 dict 格式以保持兼容性
                return [
                    {
                        "name": s.name,
                        "description": s.description,
                        "content": s.content,
                        "enabled": s.enabled,
                        "source": (s.source.value if hasattr(s.source, "value") else s.source),
                        "github_url": s.github_url,
                        "version": s.version,
                        "is_system": s.is_system,
                        "can_edit": s.can_edit,
                        "created_at": s.created_at,
                        "updated_at": s.updated_at,
                    }
                    for s in visible_skills
                ]
            except Exception:
                pass

        # 回退到旧的逻辑（兼容模式）
        fallback_skills: list[dict] = []

        # 从 MongoDB 加载
        if self.storage:
            try:
                if self.user_id:
                    mongo_skills: list[UserSkill] = await self.storage.list_user_skills(
                        self.user_id
                    )
                else:
                    mongo_skills = await self.storage.list_system_skills()
                for s in mongo_skills:
                    fallback_skills.append(
                        {
                            "name": s.name,
                            "description": s.description,
                            "content": s.content,
                            "enabled": s.enabled,
                            "source": s.source,
                            "github_url": s.github_url,
                            "version": s.version,
                            "created_at": s.created_at,
                            "updated_at": s.updated_at,
                        }
                    )
            except Exception:
                pass

        return fallback_skills

    def get_skill(self, skill_name: str) -> Optional[dict]:
        """获取指定技能（同步版本，仅 MongoDB）"""
        if skill_name in self._loaded_skills:
            return self._loaded_skills[skill_name]
        return None

    async def get_skill_async(self, skill_name: str) -> Optional[dict]:
        """
        获取指定技能（异步版本）

        如果提供了 user_id，会先检查用户技能，然后检查系统技能。
        """
        if skill_name in self._loaded_skills:
            return self._loaded_skills[skill_name]

        # 如果有 user_id 且有 MongoDB，使用新的存储方法
        if self.user_id and self.storage:
            try:
                # 先检查用户技能
                user_skill: Optional[UserSkill] = await self.storage.get_user_skill(
                    skill_name, self.user_id
                )
                if user_skill:
                    return {
                        "name": user_skill.name,
                        "description": user_skill.description,
                        "content": user_skill.content,
                        "enabled": user_skill.enabled,
                        "source": (
                            user_skill.source.value
                            if hasattr(user_skill.source, "value")
                            else user_skill.source
                        ),
                        "github_url": user_skill.github_url,
                        "version": user_skill.version,
                        "is_system": False,
                        "can_edit": True,
                        "created_at": user_skill.created_at,
                        "updated_at": user_skill.updated_at,
                    }

                # 再检查系统技能
                system_skill: Optional[SystemSkill] = await self.storage.get_system_skill(
                    skill_name
                )
                if system_skill:
                    return {
                        "name": system_skill.name,
                        "description": system_skill.description,
                        "content": system_skill.content,
                        "enabled": system_skill.enabled,
                        "source": (
                            system_skill.source.value
                            if hasattr(system_skill.source, "value")
                            else system_skill.source
                        ),
                        "github_url": system_skill.github_url,
                        "version": system_skill.version,
                        "is_system": True,
                        "can_edit": False,
                        "created_at": system_skill.created_at,
                        "updated_at": system_skill.updated_at,
                    }
            except Exception:
                pass

        # 回退到旧的逻辑（兼容模式）
        if self.storage:
            try:
                if self.user_id:
                    skill: Optional[UserSkill] = await self.storage.get_user_skill(
                        skill_name, self.user_id
                    )
                else:
                    skill: Optional[SystemSkill] = await self.storage.get_system_skill(skill_name)
                if skill:
                    return {
                        "name": skill.name,
                        "description": skill.description,
                        "content": skill.content,
                        "enabled": skill.enabled,
                        "source": skill.source,
                        "github_url": skill.github_url,
                        "version": skill.version,
                        "created_at": skill.created_at,
                        "updated_at": skill.updated_at,
                    }
            except Exception:
                pass

        return None

    def load_skill(self, skill_name: str) -> Optional[dict]:
        """加载技能到内存"""
        skill = self.get_skill(skill_name)
        if skill:
            self._loaded_skills[skill_name] = skill
        return skill

    async def load_skill_async(self, skill_name: str) -> Optional[dict]:
        """加载技能到内存（异步版本）"""
        skill = await self.get_skill_async(skill_name)
        if skill:
            self._loaded_skills[skill_name] = skill
        return skill

    def unload_skill(self, skill_name: str) -> bool:
        """卸载技能"""
        if skill_name in self._loaded_skills:
            del self._loaded_skills[skill_name]
            return True
        return False

    def is_loaded(self, skill_name: str) -> bool:
        """检查技能是否已加载"""
        return skill_name in self._loaded_skills

    async def get_effective_skills(self) -> dict:
        """
        获取用户的有效技能配置

        返回用户启用的所有技能（系统技能 + 用户技能），包含完整内容。
        """
        if not self.user_id or not self.storage:
            return {}

        try:
            result = await self.storage.get_effective_skills(self.user_id)
            return result.get("skills", {})
        except Exception:
            return {}
