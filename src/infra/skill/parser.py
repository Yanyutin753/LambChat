"""
Unified SKILL.md parser

Single source of truth for extracting metadata from SKILL.md files.
Supports YAML frontmatter with fallback to markdown-style extraction.
"""

import re
from typing import Optional

# 允许的 skill name 字符：字母、数字、下划线、中文、连字符、点
_SKILL_NAME_ALLOWED = re.compile(r"^[\w\u4e00-\u9fff\-.]+$")


def sanitize_skill_name(name: str) -> str:
    """将 name 转为路径安全的 skill_name。

    - 去掉首尾空白
    - 空格和非法字符替换为连字符
    - 合并连续连字符
    - 去掉首尾连字符
    """
    name = name.strip()
    name = re.sub(r"[^\w\u4e00-\u9fff\-.]", "-", name)
    name = re.sub(r"-{2,}", "-", name)
    name = name.strip("-")
    return name or "unnamed-skill"


def parse_skill_md(content: str) -> tuple[Optional[str], str, list[str]]:
    """
    Parse SKILL.md content to extract name, description, and tags.

    Parsing priority:
    1. YAML frontmatter (--- ... ---) with name, description, tags fields
    2. Fallback: first `# Title` line as description
    3. Fallback: `description:` line as description

    Args:
        content: SKILL.md file content

    Returns:
        (name, description, tags) tuple.
        name may be None if not found.
        description defaults to "".
        tags defaults to [].
    """
    name: Optional[str] = None
    description = ""
    tags: list[str] = []

    lines = content.splitlines()

    # Try YAML frontmatter
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            frontmatter_text = parts[1].strip()
            try:
                import yaml

                frontmatter = yaml.safe_load(frontmatter_text)
                if isinstance(frontmatter, dict):
                    name = frontmatter.get("name")
                    desc = frontmatter.get("description")
                    if isinstance(desc, str):
                        description = desc.strip()
                    t = frontmatter.get("tags")
                    if isinstance(t, list):
                        tags = [str(tag) for tag in t]
            except Exception:
                pass

    # Fallback: scan first 20 lines for name/description
    for line in lines[:20]:
        stripped = line.strip()

        # name: (only if not already set from frontmatter)
        if name is None and stripped.startswith("name:"):
            name = stripped.split("name:", 1)[1].strip().strip('"').strip("'")

        # description: (only if not already set from frontmatter)
        if not description and stripped.startswith("description:"):
            val = stripped.split("description:", 1)[1].strip()
            if val not in ("|", ">"):
                description = val.strip('"').strip("'")

        # # Title as description (only if not already set)
        if not description and stripped.startswith("# "):
            description = stripped[2:].strip()

    return name, description, tags
