"""
Skills 加载模块

从数据库加载用户技能文件，供 DeepAgent 使用。
"""

import re
from typing import Any, Dict, List, Optional, TypedDict

from src.infra.logging import get_logger
from src.infra.skill.binary import parse_binary_ref_async
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
                        if await parse_binary_ref_async(file_content):
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


def normalize_skill_keywords(value: Any) -> tuple[str, ...]:
    if isinstance(value, str):
        return tuple(item.strip() for item in value.replace(";", ",").split(",") if item.strip())
    if isinstance(value, (list, tuple, set)):
        return tuple(sorted({str(item).strip() for item in value if str(item).strip()}))
    return ()


def skill_discovery_keywords(skill: dict) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            keyword
            for field in ("category", "classification", "tags", "capabilities")
            for keyword in normalize_skill_keywords(skill.get(field))
        )
    )


def ordered_skill_metadata(skills: list[dict]) -> list[tuple[str, dict]]:
    """The directory and search must use the same enabled, deduplicated inventory."""
    unique: dict[str, dict] = {}
    for skill in skills:
        name = str(skill.get("name") or "").strip()
        if name and skill.get("enabled", True) and name not in unique:
            unique[name] = skill
    return [(name, unique[name]) for name in sorted(unique, key=lambda item: (item.lower(), item))]


_SKILL_CAPABILITY_GROUPS = (
    (
        "data",
        "SQL, databases, spreadsheets and analysis",
        r"sql|databases?|spreadsheets?|analytics|数据|表格",
    ),
    ("documents", "Documents, PDFs and presentations", r"documents?|pdf|presentations?|文档|演示"),
    (
        "development",
        "Code, repositories and software testing",
        r"code|coding|git|software|编程|代码",
    ),
    ("media", "Images, video and audio", r"images?|videos?|audio|图片|视频|音频"),
    ("research", "Search, research and web sources", r"research|search|web|搜索|研究"),
    (
        "communication",
        "Mail, messaging and social content",
        r"email|mail|social|messaging|邮件|社交",
    ),
    ("automation", "Tasks, schedules and automation", r"automation|schedule|workflow|自动化|定时"),
)


def _skill_group(skill: dict) -> tuple[str, str]:
    classification = normalize_skill_keywords(skill.get("category") or skill.get("classification"))
    if classification:
        return classification[0], "Search this classification for available capabilities"
    text = " ".join((*skill_discovery_keywords(skill), str(skill.get("description") or "")))
    for name, description, keywords in _SKILL_CAPABILITY_GROUPS:
        if re.search(rf"(?<![a-z])(?:{keywords})(?![a-z])", text, re.IGNORECASE):
            return name, description
    return "uncategorized", "Search by name or capability; all these Skills remain available"


def format_skills_prompt(skills: list[dict]) -> str:
    """Format enabled Skills, grouping large directories without hiding search candidates."""
    ordered = ordered_skill_metadata(skills)
    if not ordered:
        return ""

    threshold = max(int(settings.SKILL_PROMPT_DESCRIPTION_THRESHOLD), 0)
    if len(ordered) <= threshold:
        inventory = "\n".join(
            f"- {name}: {skill.get('description') or 'No description'}" for name, skill in ordered
        )
    else:
        groups: dict[tuple[str, str], int] = {}
        for _name, skill in ordered:
            group = _skill_group(skill)
            groups[group] = groups.get(group, 0) + 1
        inventory = "\n".join(
            f"- {group} ({count} skills): {description}"
            for (group, description), count in sorted(groups.items())
        )
        inventory += "\nAll available Skills remain searchable; groups are discovery hints."

    return f"""## Skills System

Available Skills ({len(ordered)}):
{inventory}

Use `search_skills`, then read `/skills/<name>/SKILL.md` before applying a Skill. `/skills/` is virtual; use file tools, not shell. Transfer executables once into `/workspace/.shared/` (persists across sessions; `ls` first to reuse) with `transfer_file` or `transfer_path` before running them.
"""


async def build_skills_prompt(skills: list[dict]) -> str:
    """Async-compatible wrapper around the shared Skill inventory formatter."""
    return format_skills_prompt(skills)
