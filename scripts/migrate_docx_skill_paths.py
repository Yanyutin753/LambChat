"""Dry-run-first migration for obsolete docx skill validation paths."""

from __future__ import annotations

import asyncio
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

LEGACY_PATH = "/home/oai/skills/docx/scripts/office/validate.py"
TRANSFERRED_PATH = "<transferred-docx-skill-dir>/scripts/office/validate.py"
TRANSFER_MARKER = "<!-- lambchat-docx-transfer-v1 -->"
TRANSFER_BLOCK = f"""{TRANSFER_MARKER}
Before running the docx validator:
1. Call `transfer_path` for `/skills/docx/` into the current session workspace.
2. Treat the destination returned by `transfer_path` as the docx skill directory.
3. Run `{TRANSFERRED_PATH}` from that returned destination; never execute a virtual `/skills/` path directly.

"""
COLLECTIONS = ("skill_files", "skill_marketplace_files", "system_skills")
MIGRATION_BATCH_SIZE = 100


@dataclass(frozen=True)
class MigrationMatch:
    collection_name: str
    source_id: Any
    original_content: str
    migrated_content: str


@dataclass
class MigrationReport:
    recognized: int = 0
    ambiguous: int = 0
    migrated: int = 0
    conflicted: int = 0
    rolled_back: int = 0
    matches: list[MigrationMatch] = field(default_factory=list, repr=False)

    def to_safe_dict(self) -> dict[str, int]:
        return {
            "recognized": self.recognized,
            "ambiguous": self.ambiguous,
            "migrated": self.migrated,
            "conflicted": self.conflicted,
            "rolled_back": self.rolled_back,
        }


def rewrite_skill_instructions(content: str) -> str:
    """Replace the obsolete executable path and insert one transfer contract."""
    if LEGACY_PATH not in content:
        return content
    migrated = content.replace(LEGACY_PATH, TRANSFERRED_PATH)
    if TRANSFER_MARKER in migrated:
        return migrated
    first_path_index = content.index(LEGACY_PATH)
    line_start = content.rfind("\n", 0, first_path_index) + 1
    migrated_line_start = len(content[:line_start].replace(LEGACY_PATH, TRANSFERRED_PATH))
    return migrated[:migrated_line_start] + TRANSFER_BLOCK + migrated[migrated_line_start:]


def _normalized_file_path(value: object) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    return normalized.strip("/")


def classify_document(
    collection_name: str,
    document: dict[str, Any],
) -> Literal["recognized", "ambiguous"] | None:
    """Classify only exact-path matches without exposing document identity."""
    content = document.get("content")
    if not isinstance(content, str) or LEGACY_PATH not in content:
        return None
    if collection_name == "system_skills":
        return "recognized"
    file_path = _normalized_file_path(document.get("file_path"))
    if file_path is not None and file_path.casefold() == "skill.md":
        return "recognized"
    return "ambiguous"


async def scan_database(database: Any) -> MigrationReport:
    """Scan only exact legacy-path matches through bounded cursors."""
    report = MigrationReport()
    query = {"content": {"$regex": re.escape(LEGACY_PATH)}}
    projection = {"_id": 1, "file_path": 1, "content": 1}
    for collection_name in COLLECTIONS:
        cursor = database[collection_name].find(query, projection).batch_size(MIGRATION_BATCH_SIZE)
        async for document in cursor:
            classification = classify_document(collection_name, document)
            if classification == "ambiguous":
                report.ambiguous += 1
            elif classification == "recognized":
                report.recognized += 1
                original_content = document["content"]
                report.matches.append(
                    MigrationMatch(
                        collection_name=collection_name,
                        source_id=document["_id"],
                        original_content=original_content,
                        migrated_content=rewrite_skill_instructions(original_content),
                    )
                )
    return report


async def async_main() -> int:
    from src.infra.storage.mongodb import get_mongo_client
    from src.kernel.config import settings

    database = get_mongo_client()[settings.MONGODB_DB]
    report = await scan_database(database)
    print(json.dumps(report.to_safe_dict(), sort_keys=True))
    return 1 if report.ambiguous else 0


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
