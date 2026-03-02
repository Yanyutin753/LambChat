"""
Skills 加载模块

从数据库加载用户技能文件，供 DeepAgent 使用。
"""

import logging
from typing import Any, Dict, List, Optional, TypedDict

from src.kernel.config import settings

logger = logging.getLogger(__name__)


class SkillLoadResult(TypedDict):
    """技能加载结果"""

    files: Dict[str, Any]  # 文件路径 -> file_data
    skills: List[dict]  # 技能列表，用于构建 prompt


async def load_skill_files(user_id: Optional[str]) -> SkillLoadResult:
    """
    从数据库加载用户的技能文件和技能列表

    Args:
        user_id: 用户 ID

    Returns:
        SkillLoadResult 包含:
        - files: 技能文件字典，格式为 {file_path: file_data}
        - skills: 技能列表，用于构建 skills prompt
    """
    result: SkillLoadResult = {
        "files": {},
        "skills": [],
    }

    if not settings.ENABLE_SKILLS:
        return result

    try:
        from deepagents.backends.utils import create_file_data

        from src.infra.skill.manager import SkillManager

        skill_manager = SkillManager(user_id=user_id)
        effective_skills = await skill_manager.get_effective_skills()

        if not effective_skills:
            return result

        tenant_id = user_id or "default"
        logger.info(f"Loading {len(effective_skills)} skills for user: {tenant_id}")

        skills_list: List[dict] = []
        for skill_name, skill_data in effective_skills.items():
            skill_files = skill_data.get("files", {})
            skill_content = skill_data.get("content", "")

            # 构建技能列表用于 prompt
            skill_dict = (
                skill_data.model_dump()
                if hasattr(skill_data, "model_dump")
                else (dict(skill_data) if not isinstance(skill_data, dict) else skill_data)
            )
            skill_dict["is_system"] = skill_dict.get("is_system", True)
            if skill_dict.get("enabled", True):
                skills_list.append(skill_dict)

            # 如果有多个文件（新格式）
            if skill_files:
                for file_name, file_content in skill_files.items():
                    file_path = f"/{skill_name}/{file_name}"
                    result["files"][file_path] = create_file_data(file_content)
            # 否则只有主内容（旧格式兼容）
            elif skill_content:
                file_path = f"/{skill_name}/SKILL.md"
                result["files"][file_path] = create_file_data(skill_content)

        result["skills"] = skills_list
        logger.info(
            f"Prepared {len(result['files'])} skill files and {len(skills_list)} skills for prompt"
        )

    except Exception as e:
        logger.warning(f"Failed to load skills: {e}")

    return result


async def build_skills_prompt(skills: list[dict]) -> str:
    """
    Build skills prompt text with enhanced matching hints.

    Includes skill descriptions, usage triggers, and matching guidance
    to help the LLM select the most relevant skill for user queries.
    """
    if not skills:
        return ""

    lines = ["## Available Skills", ""]
    # Categorize skills by their domain/type for better organization
    for skill in skills:
        name = skill.get("name", "unnamed skill")
        description = skill.get("description", "no description")

        # Build skill entry with matching hints
        lines.append(f"### {name}")
        lines.append(f"**Description**: {description}")
        lines.append("")

    lines.append("### Skill Selection Strategy")
    lines.append("")
    lines.append(
        "To learn more about a skill's details, access the corresponding file at `/skills/{skill_name}/SKILL.md`."
    )
    lines.append("")

    return "\n".join(lines)
