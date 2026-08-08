"""Dry-run-first migration for obsolete docx skill validation paths."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from datetime import timedelta
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
MIGRATION_ID = "docx-skill-path-v1"
BACKUP_RETENTION_DAYS = 30


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


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _rollout_id(manifest_path: Path) -> str:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    rollout_id = manifest.get("rollout_id") if isinstance(manifest, dict) else None
    if not isinstance(rollout_id, str) or not rollout_id.strip():
        raise ValueError("rollout manifest must contain a non-empty rollout_id")
    return rollout_id


def _verified_rollout_id(manifest_path: Path) -> str:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("apply requires a verified candidate manifest")
    rollout_id = manifest.get("rollout_id")
    build_id = manifest.get("build_id")
    template_name = manifest.get("template_name")
    immutable_ref = manifest.get("immutable_ref")
    if (
        not isinstance(rollout_id, str)
        or not rollout_id.strip()
        or not isinstance(build_id, str)
        or not build_id
        or not isinstance(template_name, str)
        or not template_name
        or immutable_ref != f"{template_name}:{build_id}"
        or manifest.get("verified_build_id") != build_id
        or not manifest.get("verified_at")
    ):
        raise ValueError("apply requires a verified candidate manifest")
    return rollout_id


def _backup_id(rollout_id: str, match: MigrationMatch) -> str:
    identity = f"{MIGRATION_ID}\0{rollout_id}\0{match.collection_name}\0{match.source_id!s}"
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()


async def apply_migration(database: Any, manifest_path: Path) -> MigrationReport:
    """Back up and CAS-update every recognized match for one rollout."""
    from src.infra.utils.datetime import utc_now

    rollout_id = _verified_rollout_id(manifest_path)
    report = await scan_database(database)
    if report.ambiguous:
        raise RuntimeError("ambiguous legacy docx path matches block apply")
    backups = database["skill_migration_backups"]
    await backups.create_index("expire_at", expireAfterSeconds=0)
    for match in report.matches:
        backup = {
            "_id": _backup_id(rollout_id, match),
            "migration_id": MIGRATION_ID,
            "rollout_id": rollout_id,
            "collection_name": match.collection_name,
            "source_id": match.source_id,
            "original_content": match.original_content,
            "original_content_hash": _content_hash(match.original_content),
            "migrated_content_hash": _content_hash(match.migrated_content),
            "created_at": utc_now(),
            "expire_at": utc_now() + timedelta(days=BACKUP_RETENTION_DAYS),
        }
        await backups.update_one(
            {"_id": backup["_id"]},
            {"$setOnInsert": backup},
            upsert=True,
        )
        durable_backup = await backups.find_one({"_id": backup["_id"]})
        if (
            durable_backup is None
            or durable_backup.get("original_content_hash") != backup["original_content_hash"]
            or durable_backup.get("migrated_content_hash") != backup["migrated_content_hash"]
        ):
            report.conflicted += 1
            continue
        result = await database[match.collection_name].update_one(
            {"_id": match.source_id, "content": match.original_content},
            {"$set": {"content": match.migrated_content}},
        )
        if result.matched_count == 1:
            report.migrated += 1
        else:
            report.conflicted += 1
    return report


async def rollback_migration(database: Any, manifest_path: Path) -> MigrationReport:
    """Restore only untouched migrated content belonging to this rollout."""
    rollout_id = _rollout_id(manifest_path)
    report = MigrationReport()
    backups = database["skill_migration_backups"]
    cursor = backups.find(
        {"migration_id": MIGRATION_ID, "rollout_id": rollout_id},
        {
            "collection_name": 1,
            "source_id": 1,
            "original_content": 1,
            "migrated_content_hash": 1,
        },
    ).batch_size(MIGRATION_BATCH_SIZE)
    async for backup in cursor:
        collection = database[backup["collection_name"]]
        source = await collection.find_one(
            {"_id": backup["source_id"]},
            {"content": 1},
        )
        current_content = source.get("content") if source else None
        if (
            not isinstance(current_content, str)
            or _content_hash(current_content) != backup["migrated_content_hash"]
        ):
            report.conflicted += 1
            continue
        result = await collection.update_one(
            {"_id": backup["source_id"], "content": current_content},
            {"$set": {"content": backup["original_content"]}},
        )
        if result.matched_count == 1:
            report.rolled_back += 1
        else:
            report.conflicted += 1
    return report


async def async_main(argv: list[str] | None = None) -> int:
    from src.infra.storage.mongodb import get_mongo_client
    from src.kernel.config import settings

    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--apply", action="store_true")
    actions.add_argument("--rollback", action="store_true")
    parser.add_argument("--manifest", type=Path)
    args = parser.parse_args(argv)
    if (args.apply or args.rollback) and args.manifest is None:
        parser.error("--manifest is required with --apply or --rollback")

    database = get_mongo_client()[settings.MONGODB_DB]
    if args.apply:
        report = await apply_migration(database, args.manifest)
    elif args.rollback:
        report = await rollback_migration(database, args.manifest)
    else:
        report = await scan_database(database)
    print(json.dumps(report.to_safe_dict(), sort_keys=True))
    return 1 if report.ambiguous or report.conflicted else 0


def main() -> None:
    raise SystemExit(asyncio.run(async_main()))


if __name__ == "__main__":
    main()
