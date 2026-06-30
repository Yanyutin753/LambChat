"""Shared helpers and limits for skill storage."""

from typing import Any, Optional

from src.infra.async_utils import run_blocking_io

SKILL_METADATA_LIST_LIMIT = 100
SKILL_EFFECTIVE_LOAD_LIMIT = 100
SKILL_BATCH_FILE_LOOKUP_LIMIT = 100
SKILL_MD_SCAN_LIMIT = 500
SKILL_FILES_PER_SKILL_LIMIT = 100


def normalize_skill_name_list(
    values: Any,
    limit: int = SKILL_METADATA_LIST_LIMIT,
) -> list[str]:
    """Bound user-controlled skill name lists from metadata or request bodies."""
    if not isinstance(values, (list, tuple, set)):
        return []
    bounded: list[str] = []
    seen: set[str] = set()
    for value in values:
        if not isinstance(value, str) or not value or value in seen:
            continue
        seen.add(value)
        bounded.append(value)
        if len(bounded) >= limit:
            break
    return bounded


def normalize_skill_file_path(file_path: str) -> str:
    """Canonicalize the primary skill instruction filename."""
    parts = file_path.replace("\\", "/").split("/")
    if parts and parts[-1].lower() == "skill.md":
        parts[-1] = "SKILL.md"
    return "/".join(parts)


def normalize_skill_files(files: dict[str, str]) -> dict[str, str]:
    """Normalize skill file keys while letting explicit canonical paths win."""
    normalized: dict[str, str] = {}
    for file_path, content in files.items():
        canonical_path = normalize_skill_file_path(file_path)
        if canonical_path in normalized and file_path != canonical_path:
            continue
        normalized[canonical_path] = content
    return normalized


async def _parse_skill_md_offload(content: str) -> tuple[Optional[str], str, list[str]]:
    from src.infra.skill.parser import parse_skill_md

    return await run_blocking_io(parse_skill_md, content)
