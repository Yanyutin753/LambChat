"""
技能注入模块

从数据库读取技能并注入到系统提示中。
支持用户级别的技能访问。

与 CompositeBackend 配合工作：
- CompositeBackend 自动处理 /skills/ 路径的读写
- LLM 可以直接通过 /skills/{skill_name}/ 读取技能文件
- LLM 写入 /skills/ 路径会自动更新 MongoDB
"""

from typing import Optional

from src.infra.logging import get_logger
from src.infra.skill.loader import format_skills_prompt
from src.infra.skill.manager import SkillManager

logger = get_logger(__name__)


class SkillsMiddleware:
    """
    技能注入中间件

    从数据库读取技能内容，注入到 Agent 的系统提示中。
    支持用户级别的技能访问（系统技能 + 用户技能）。

    如果提供了 user_id，将使用用户级别的技能访问。
    """

    def __init__(self, user_id: Optional[str] = None):
        """
        初始化技能中间件

        Args:
            user_id: 用户 ID，用于获取用户级别的技能
        """
        self._user_id = user_id
        self._manager = SkillManager(user_id=user_id)

    async def inject_skills_async(self, system_prompt: str) -> str:
        """
        将技能内容注入到系统提示中（异步版本，包含 MongoDB）

        Args:
            system_prompt: 原始系统提示

        Returns:
            注入技能后的系统提示
        """
        skills_content = await self.load_all_skills_async()

        if not skills_content:
            return system_prompt

        # 构建技能提示
        skills_prompt = await self._build_skills_prompt(skills_content)

        # 将技能插入到系统提示中
        if "{skills}" in system_prompt:
            return system_prompt.replace("{skills}", skills_prompt)
        else:
            # 追加到系统提示末尾
            return f"{system_prompt}\n\n{skills_prompt}"

    async def load_all_skills_async(self) -> list[dict]:
        """加载所有技能"""
        if not self._user_id:
            logger.warning("No user_id provided, cannot load skills")
            return []

        try:
            effective = await self._manager.get_effective_skills()
            skills = []
            for skill_name, skill in effective.items():
                if hasattr(skill, "model_dump"):
                    skill_dict = skill.model_dump()
                else:
                    skill_dict = dict(skill) if not isinstance(skill, dict) else skill
                # 确保 name 字段存在
                skill_dict["name"] = skill_dict.get("name", skill_name)
                skill_dict["is_system"] = skill_dict.get("is_system", True)
                skills.append(skill_dict)
            return [s for s in skills if s.get("enabled", True)]
        except Exception as e:
            logger.warning(f"Failed to load skills for user {self._user_id}: {e}")
            return []

    async def _build_skills_prompt(self, skills: list[dict]) -> str:
        """Build the same Skill prompt used by direct agent contexts."""
        return format_skills_prompt(skills)


def get_skills_middleware(
    user_id: Optional[str] = None,
) -> SkillsMiddleware:
    """
    获取技能中间件实例

    Args:
        user_id: 用户 ID，用于获取用户级别的技能
    """
    return SkillsMiddleware(user_id=user_id)
