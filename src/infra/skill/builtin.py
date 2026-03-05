"""
Builtin skills initialization

Load skills from src/skills/ directory into the database on startup.
"""

import logging
from pathlib import Path
from typing import Optional

import yaml

from src.infra.skill.storage import SkillStorage
from src.kernel.schemas.skill import SkillCreate, SkillSource

logger = logging.getLogger(__name__)

# Builtin skills directory
BUILTIN_SKILLS_DIR = Path(__file__).parent.parent.parent / "skills"


def _parse_skill_md(content: str) -> tuple[Optional[str], Optional[str]]:
    """
    Parse SKILL.md frontmatter to extract name and description.

    Args:
        content: SKILL.md file content

    Returns:
        (name, description) tuple
    """
    if not content.startswith("---"):
        return None, None

    # Extract frontmatter
    parts = content.split("---", 2)
    if len(parts) < 3:
        return None, None

    frontmatter_text = parts[1].strip()

    try:
        frontmatter = yaml.safe_load(frontmatter_text)
        if not isinstance(frontmatter, dict):
            return None, None

        name = frontmatter.get("name")
        description = frontmatter.get("description")
        return name, description
    except yaml.YAMLError:
        return None, None


def _read_skill_directory(skill_path: Path) -> Optional[dict[str, str]]:
    """
    Read all files from a skill directory.

    Args:
        skill_path: Path to skill directory

    Returns:
        Dict mapping relative file paths to content, or None if invalid
    """
    if not skill_path.is_dir():
        return None

    files: dict[str, str] = {}

    for file_path in skill_path.rglob("*"):
        if not file_path.is_file():
            continue
        # Skip hidden files and common excludes
        if file_path.name.startswith("."):
            continue
        if file_path.name == "__pycache__":
            continue

        # Get relative path from skill directory
        relative_path = file_path.relative_to(skill_path)

        # Read file content
        try:
            content = file_path.read_text(encoding="utf-8")
            files[str(relative_path)] = content
        except Exception as e:
            logger.warning(f"Failed to read {file_path}: {e}")

    return files if files else None


async def init_builtin_skills() -> int:
    """
    Initialize builtin skills from src/skills/ directory.

    This function:
    1. Scans src/skills/ for skill directories
    2. For each directory with a SKILL.md file, creates/updates a system skill
    3. Skills are created with source=BUILTIN

    Returns:
        Number of skills initialized
    """
    if not BUILTIN_SKILLS_DIR.exists():
        logger.info(f"Builtin skills directory not found: {BUILTIN_SKILLS_DIR}")
        return 0

    storage = SkillStorage()
    initialized_count = 0

    # Scan skill directories
    for skill_dir in BUILTIN_SKILLS_DIR.iterdir():
        if not skill_dir.is_dir():
            continue
        if skill_dir.name.startswith("."):
            continue

        skill_md_path = skill_dir / "SKILL.md"
        if not skill_md_path.exists():
            logger.debug(f"Skipping {skill_dir.name}: no SKILL.md found")
            continue

        # Read all skill files
        files = _read_skill_directory(skill_dir)
        if not files:
            logger.warning(f"Skipping {skill_dir.name}: no files found")
            continue

        # Parse SKILL.md for metadata
        skill_md_content = files.get("SKILL.md", "")
        name, description = _parse_skill_md(skill_md_content)

        if not name:
            name = skill_dir.name
            logger.info(f"Using directory name as skill name: {name}")

        if not description:
            description = f"Builtin skill: {name}"

        # Check if skill already exists
        existing = await storage.get_system_skill(name)

        if existing:
            # Update existing skill
            logger.debug(f"Updating builtin skill: {name}")
            from src.kernel.schemas.skill import SkillUpdate

            await storage.update_system_skill(
                name,
                SkillUpdate(
                    description=description,
                    files=files,
                    content="",  # Use files format
                ),
                admin_user_id="system",
            )
            # Sync files to PostgreSQL
            await storage.sync_skill_files(name, files, user_id="system")
        else:
            # Create new system skill
            logger.info(f"Creating builtin skill: {name}")
            skill_create = SkillCreate(
                name=name,
                description=description,
                content="",  # Use files format
                files=files,
                enabled=True,
                source=SkillSource.BUILTIN,
            )
            await storage.create_system_skill(skill_create, admin_user_id="system")

        initialized_count += 1

    if initialized_count > 0:
        logger.info(f"Initialized {initialized_count} builtin skills")

    return initialized_count
