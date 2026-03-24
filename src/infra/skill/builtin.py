"""
Builtin skills initialization

Load skills from src/skills/ directory into the marketplace on startup.
Simplified architecture: builtin skills are pre-loaded into the marketplace.
"""

import hashlib
from pathlib import Path
from typing import Optional

from src.infra.logging import get_logger
from src.infra.skill.marketplace import MarketplaceStorage
from src.infra.skill.parser import parse_skill_md
from src.infra.skill.types import MarketplaceSkillCreate, MarketplaceSkillUpdate

logger = get_logger(__name__)

# Builtin skills directory
BUILTIN_SKILLS_DIR = Path(__file__).parent.parent.parent / "skills"


def _compute_version(files: dict[str, str]) -> str:
    """根据文件内容 hash 生成版本号"""
    hasher = hashlib.md5()
    for path in sorted(files.keys()):
        hasher.update(path.encode("utf-8"))
        hasher.update(files[path].encode("utf-8"))
    digest = hasher.hexdigest()[:8]
    return f"1.0.{int(digest, 16) % 10000}"


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
            name, description, tags = parse_skill_md(skill_md_content)

            if not name:
                name = skill_dir.name
                logger.info(f"Using directory name as skill name: {name}")

            if not description:
                description = f"Builtin skill: {name}"

            # 根据文件内容生成版本号
            version = _compute_version(files)

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
                            version=version,
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
                            version=version,
                        ),
                        user_id="system",
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
