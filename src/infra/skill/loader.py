"""
Skills 加载模块

从数据库加载用户技能文件，供 DeepAgent 使用。
"""

from typing import Any, Dict, List, Optional, TypedDict

from src.infra.logging import get_logger
from src.infra.skill.binary import parse_binary_ref
from src.kernel.config import settings

logger = get_logger(__name__)


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
            # 确保 name 字段存在
            skill_dict["name"] = skill_dict.get("name", skill_name)
            skill_dict["is_system"] = skill_dict.get("is_system", True)
            is_enabled = skill_dict.get("enabled", True)
            if is_enabled:
                skills_list.append(skill_dict)

                # 如果有多个文件（新格式）
                if skill_files:
                    for file_name, file_content in skill_files.items():
                        # 跳过二进制文件引用（它们存储在 S3，不适合作为文本加载）
                        if parse_binary_ref(file_content):
                            continue
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
    Build skills prompt text with progressive disclosure pattern.

    Matches the format used by deepagents.middleware.skills.SkillsMiddleware
    to ensure consistent behavior when SkillsMiddleware is disabled.
    """
    if not skills:
        return ""

    # Format skills list with progressive disclosure pattern
    skills_lines = []
    for skill in skills:
        name = skill.get("name", "unnamed skill")
        description = skill.get("description", "no description")
        skill_path = f"/skills/{name}/SKILL.md"

        # Format skill entry matching SkillsMiddleware._format_skills_list
        desc_line = f"- **{name}**: {description}"
        skills_lines.append(desc_line)
        skills_lines.append(f"  -> Read `{skill_path}` for full instructions")

    skills_list_str = "\n".join(skills_lines)

    # Build full prompt matching SkillsMiddleware.SKILLS_SYSTEM_PROMPT format
    prompt = f"""## Skills System

**Skills Location**: `/skills/`

**Available Skills:**

{skills_list_str}

**Usage:** When a task matches a skill's description, read its `SKILL.md` for step-by-step workflows. Skills may include executable scripts — use absolute paths.
**Commands:** Use `ls("/skills/")`, `read_file`, `write_file`, `edit_file(path, old, new)` to access skills. Do NOT create directories manually.

**IMPORTANT:** `/skills/` is a virtual path backed by a database, NOT a real filesystem directory. NEVER use shell commands (e.g., `ls -la /skills/`, `cat /skills/x.md`, `python /skills/x.py`, `cp /skills/* .`) to access skills — they will fail. Always use the `ls`, `read_file`, `write_file`, `edit_file` tools instead.
"""
    return prompt
