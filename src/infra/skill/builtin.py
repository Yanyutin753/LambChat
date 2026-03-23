"""
Builtin skills initialization

Load skills from src/skills/ directory into the marketplace on startup.
Simplified architecture: builtin skills are pre-loaded into the marketplace.
"""

from pathlib import Path
from typing import Optional

import yaml

from src.infra.logging import get_logger
from src.infra.skill.marketplace import MarketplaceStorage
from src.infra.skill.types import MarketplaceSkillCreate, MarketplaceSkillUpdate

logger = get_logger(__name__)

# Builtin skills directory
BUILTIN_SKILLS_DIR = Path(__file__).parent.parent.parent / "skills"


def _parse_skill_md(content: str) -> tuple[Optional[str], Optional[str], Optional[list[str]]]:
    """
    Parse SKILL.md frontmatter to extract name, description, and tags.

    Args:
        content: SKILL.md file content

    Returns:
        (name, description, tags) tuple
    """
    if not content.startswith("---"):
        return None, None, None

    # Extract frontmatter
    parts = content.split("---", 2)
    if len(parts) < 3:
        return None, None, None

    frontmatter_text = parts[1].strip()

    try:
        frontmatter = yaml.safe_load(frontmatter_text)
        if not isinstance(frontmatter, dict):
            return None, None, None

        name = frontmatter.get("name")
        description = frontmatter.get("description", "")
        tags = frontmatter.get("tags", [])
        return name, description, tags
    except yaml.YAMLError:
        return None, None, None


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
    2. For each directory with a SKILL.md file, upserts a marketplace skill
    3. Syncs skill files to the marketplace files collection

    Returns:
        Number of skills initialized
    """
    if not BUILTIN_SKILLS_DIR.exists():
        logger.info(f"Builtin skills directory not found: {BUILTIN_SKILLS_DIR}")
        return 0

    marketplace = MarketplaceStorage()
    initialized_count = 0
    try:
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
            name, description, tags = _parse_skill_md(skill_md_content)

            if not name:
                name = skill_dir.name
                logger.info(f"Using directory name as skill name: {name}")

            if not description:
                description = f"Builtin skill: {name}"

            # Upsert marketplace skill metadata
            try:
                existing = await marketplace.get_marketplace_skill(name)
                if existing:
                    # Update existing
                    logger.debug(f"Updating builtin skill in marketplace: {name}")
                    await marketplace.update_marketplace_skill(
                        name,
                        MarketplaceSkillUpdate(
                            description=description,
                            tags=tags or [],
                        ),
                    )
                else:
                    # Create new
                    logger.info(f"Creating builtin skill in marketplace: {name}")
                    await marketplace.create_marketplace_skill(
                        MarketplaceSkillCreate(
                            skill_name=name,
                            description=description,
                            tags=tags or [],
                        ),
                        admin_user_id="system",
                    )
            except ValueError as e:
                logger.warning(f"Failed to upsert marketplace skill {name}: {e}")
                continue

            # Sync files to marketplace
            await marketplace.sync_marketplace_files(name, files)

            initialized_count += 1
    finally:
        await marketplace.close()

    if initialized_count > 0:
        logger.info(f"Initialized {initialized_count} builtin skills in marketplace")

    return initialized_count
