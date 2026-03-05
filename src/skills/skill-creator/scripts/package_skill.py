#!/usr/bin/env python3
"""
Skill Packager - 将技能目录打包为可分发的 .skill 文件

用法:
    python package_skill.py <skill-folder> [output-directory]

示例:
    python package_skill.py skills/my-skill
    python package_skill.py skills/my-skill ./dist

注意: 打包后的 .skill 文件可以通过 LambChat 的 add_skill_from_path 工具导入。
"""

import fnmatch
import sys
import zipfile
from pathlib import Path

# 打包时要排除的模式
EXCLUDE_DIRS = {"__pycache__", "node_modules", ".git", "evals", ".venv", "venv"}
EXCLUDE_GLOBS = {"*.pyc", "*.pyo", "*.egg-info"}
EXCLUDE_FILES = {".DS_Store", "Thumbs.db", ".gitignore", ".env"}


def should_exclude(rel_path: Path) -> bool:
    """检查路径是否应该从打包中排除"""
    parts = rel_path.parts
    if any(part in EXCLUDE_DIRS for part in parts):
        return True
    name = rel_path.name
    if name in EXCLUDE_FILES:
        return True
    return any(fnmatch.fnmatch(name, pat) for pat in EXCLUDE_GLOBS)


def validate_skill(skill_path: Path) -> tuple[bool, str]:
    """
    验证技能目录是否有效。

    返回 (is_valid, message)
    """
    if not skill_path.exists():
        return False, f"Skill folder not found: {skill_path}"

    if not skill_path.is_dir():
        return False, f"Path is not a directory: {skill_path}"

    skill_md = skill_path / "SKILL.md"
    if not skill_md.exists():
        return False, f"SKILL.md not found in {skill_path}"

    # 读取并验证 frontmatter
    try:
        content = skill_md.read_text(encoding="utf-8")
    except Exception as e:
        return False, f"Cannot read SKILL.md: {e}"

    if not content.startswith("---"):
        return False, "SKILL.md must start with YAML frontmatter (---)"

    # 提取 frontmatter
    import re

    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return False, "Invalid frontmatter format in SKILL.md"

    frontmatter_text = match.group(1)

    # 简单验证 name 和 description
    has_name = "name:" in frontmatter_text.lower()
    has_description = "description:" in frontmatter_text.lower()

    if not has_name:
        return False, "Missing 'name' in SKILL.md frontmatter"
    if not has_description:
        return False, "Missing 'description' in SKILL.md frontmatter"

    return True, "Skill is valid!"


def package_skill(skill_path: Path, output_dir: Path | None = None) -> Path | None:
    """
    将技能目录打包为 .skill 文件。

    Args:
        skill_path: 技能目录的路径
        output_dir: 可选的输出目录（默认为当前目录）

    Returns:
        创建的 .skill 文件路径，或 None 如果出错
    """
    skill_path = skill_path.resolve()

    # 验证
    valid, message = validate_skill(skill_path)
    if not valid:
        print(f"❌ {message}")
        return None
    print(f"✅ {message}\n")

    # 确定输出位置
    skill_name = skill_path.name
    if output_dir:
        output_path = Path(output_dir).resolve()
        output_path.mkdir(parents=True, exist_ok=True)
    else:
        output_path = skill_path.parent

    skill_filename = output_path / f"{skill_name}.skill"

    # 创建 .skill 文件（zip 格式）
    try:
        with zipfile.ZipFile(skill_filename, "w", zipfile.ZIP_DEFLATED) as zipf:
            file_count = 0
            for file_path in skill_path.rglob("*"):
                if not file_path.is_file():
                    continue
                arcname = file_path.relative_to(skill_path.parent)
                if should_exclude(arcname):
                    print(f"  Skipped: {arcname}")
                    continue
                zipf.write(file_path, arcname)
                print(f"  Added: {arcname}")
                file_count += 1

        print(f"\n✅ Successfully packaged skill to: {skill_filename}")
        print(f"   Total files: {file_count}")
        return skill_filename

    except Exception as e:
        print(f"❌ Error creating .skill file: {e}")
        return None


def main():
    if len(sys.argv) < 2:
        print("Usage: python package_skill.py <skill-folder> [output-directory]")
        print("\nExample:")
        print("  python package_skill.py skills/my-skill")
        print("  python package_skill.py skills/my-skill ./dist")
        print("\nThe resulting .skill file can be imported via add_skill_from_path.")
        sys.exit(1)

    skill_path = Path(sys.argv[1])
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else None

    print(f"📦 Packaging skill: {skill_path}")
    if output_dir:
        print(f"   Output directory: {output_dir}")
    print()

    result = package_skill(skill_path, output_dir)

    if result:
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
