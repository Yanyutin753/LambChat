from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

LEGACY_COMMAND = "python /home/oai/skills/docx/scripts/office/validate.py /tmp/document.docx"


def test_rewrite_inserts_transfer_instructions_once() -> None:
    from scripts.migrate_docx_skill_paths import rewrite_skill_instructions

    migrated = rewrite_skill_instructions(LEGACY_COMMAND)

    assert "transfer_path" in migrated
    assert "/skills/docx/" in migrated
    assert "<transferred-docx-skill-dir>/scripts/office/validate.py" in migrated
    assert "/home/oai/skills/docx/scripts/office/validate.py" not in migrated
    assert rewrite_skill_instructions(migrated) == migrated


@pytest.mark.parametrize("collection_name", ["skill_files", "skill_marketplace_files"])
def test_main_skill_documents_are_recognized(collection_name: str) -> None:
    from scripts.migrate_docx_skill_paths import classify_document

    assert (
        classify_document(
            collection_name,
            {"_id": "doc-1", "file_path": "./SKILL.md", "content": LEGACY_COMMAND},
        )
        == "recognized"
    )


def test_legacy_system_skill_content_is_recognized() -> None:
    from scripts.migrate_docx_skill_paths import classify_document

    assert (
        classify_document(
            "system_skills",
            {"_id": "doc-1", "content": LEGACY_COMMAND},
        )
        == "recognized"
    )


@pytest.mark.parametrize(
    "document",
    [
        {"_id": "doc-1", "file_path": "scripts/run.py", "content": LEGACY_COMMAND},
        {"_id": "doc-1", "content": LEGACY_COMMAND},
        {"_id": "doc-1", "file_path": "notes.md", "content": LEGACY_COMMAND},
    ],
)
def test_auxiliary_or_unidentified_matches_are_ambiguous(document: dict[str, str]) -> None:
    from scripts.migrate_docx_skill_paths import classify_document

    assert classify_document("skill_files", document) == "ambiguous"


def test_unrelated_content_is_not_a_match() -> None:
    from scripts.migrate_docx_skill_paths import classify_document

    assert (
        classify_document(
            "skill_files",
            {"_id": "doc-1", "file_path": "SKILL.md", "content": "python validate.py"},
        )
        is None
    )


class _AsyncCursor:
    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self.documents = documents
        self.index = 0
        self.batch_size_value: int | None = None

    def batch_size(self, value: int) -> _AsyncCursor:
        self.batch_size_value = value
        return self

    def __aiter__(self) -> _AsyncCursor:
        return self

    async def __anext__(self) -> dict[str, Any]:
        if self.index >= len(self.documents):
            raise StopAsyncIteration
        document = self.documents[self.index]
        self.index += 1
        return document


class _ScanCollection:
    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self.documents = documents
        self.find_calls: list[tuple[dict[str, Any], dict[str, int]]] = []
        self.cursor: _AsyncCursor | None = None

    def find(
        self,
        query: dict[str, Any],
        projection: dict[str, int],
    ) -> _AsyncCursor:
        self.find_calls.append((query, projection))
        self.cursor = _AsyncCursor(self.documents)
        return self.cursor


class _FakeDatabase:
    def __init__(self, collections: dict[str, _ScanCollection]) -> None:
        self.collections = collections

    def __getitem__(self, name: str) -> _ScanCollection:
        return self.collections[name]


@pytest.mark.asyncio
async def test_scan_is_bounded_and_reports_only_aggregate_counts() -> None:
    from scripts.migrate_docx_skill_paths import scan_database

    collections = {
        "skill_files": _ScanCollection(
            [
                {"_id": "recognized", "file_path": "SKILL.md", "content": LEGACY_COMMAND},
                {"_id": "ambiguous", "file_path": "run.py", "content": LEGACY_COMMAND},
            ]
        ),
        "skill_marketplace_files": _ScanCollection([]),
        "system_skills": _ScanCollection([{"_id": "legacy", "content": LEGACY_COMMAND}]),
    }

    report = await scan_database(_FakeDatabase(collections))

    assert report.to_safe_dict() == {
        "recognized": 2,
        "ambiguous": 1,
        "migrated": 0,
        "conflicted": 0,
        "rolled_back": 0,
    }
    for collection in collections.values():
        assert collection.cursor is not None
        assert collection.cursor.batch_size_value == 100
        query, projection = collection.find_calls[0]
        assert query == {
            "content": {"$regex": "/home/oai/skills/docx/scripts/office/validate\\.py"}
        }
        assert projection == {"_id": 1, "file_path": 1, "content": 1}


def _migration_matches(document: dict[str, Any], query: dict[str, Any]) -> bool:
    for key, expected in query.items():
        current = document.get(key)
        if isinstance(expected, dict) and "$regex" in expected:
            if not isinstance(current, str) or re.search(expected["$regex"], current) is None:
                return False
        elif current != expected:
            return False
    return True


class _MigrationCollection:
    def __init__(
        self,
        documents: list[dict[str, Any]] | None = None,
        *,
        events: list[str] | None = None,
        name: str = "collection",
        raise_after_source_update: bool = False,
        fail_next_update: bool = False,
    ) -> None:
        self.documents = [dict(document) for document in (documents or [])]
        self.events = events if events is not None else []
        self.name = name
        self.raise_after_source_update = raise_after_source_update
        self.fail_next_update = fail_next_update
        self.index_calls: list[tuple[str, int]] = []

    def find(
        self,
        query: dict[str, Any],
        projection: dict[str, int] | None = None,
    ) -> _AsyncCursor:
        del projection
        return _AsyncCursor(
            [document for document in self.documents if _migration_matches(document, query)]
        )

    async def find_one(
        self,
        query: dict[str, Any],
        projection: dict[str, int] | None = None,
    ) -> dict[str, Any] | None:
        del projection
        return next(
            (dict(document) for document in self.documents if _migration_matches(document, query)),
            None,
        )

    async def create_index(self, field: str, **kwargs: int) -> str:
        self.index_calls.append((field, kwargs["expireAfterSeconds"]))
        return field

    async def update_one(
        self,
        query: dict[str, Any],
        update: dict[str, Any],
        *,
        upsert: bool = False,
    ) -> object:
        self.events.append(self.name)
        if self.fail_next_update and "$set" in update:
            self.fail_next_update = False
            return type("Result", (), {"matched_count": 0, "upserted_id": None})()
        existing = next(
            (document for document in self.documents if _migration_matches(document, query)),
            None,
        )
        if existing is None and upsert and "$setOnInsert" in update:
            self.documents.append(dict(update["$setOnInsert"]))
            return type("Result", (), {"matched_count": 0, "upserted_id": query.get("_id")})()
        if existing is None:
            return type("Result", (), {"matched_count": 0, "upserted_id": None})()
        existing.update(update.get("$set", {}))
        if self.raise_after_source_update and "$set" in update:
            raise RuntimeError("crash after source CAS")
        return type("Result", (), {"matched_count": 1, "upserted_id": None})()


class _MigrationDatabase:
    def __init__(self, collections: dict[str, _MigrationCollection]) -> None:
        self.collections = collections

    def __getitem__(self, name: str) -> _MigrationCollection:
        return self.collections.setdefault(name, _MigrationCollection(name=name))


def _write_rollout_manifest(path: Path, rollout_id: str = "rollout-current") -> None:
    path.write_text(
        json.dumps(
            {
                "rollout_id": rollout_id,
                "template_name": "lambchat-prod",
                "build_id": "build-1",
                "immutable_ref": "lambchat-prod:build-1",
                "verified_build_id": "build-1",
                "verified_at": "verified",
            }
        ),
        encoding="utf-8",
    )


@pytest.mark.asyncio
async def test_apply_writes_rollout_backup_before_source_cas(tmp_path: Path) -> None:
    from scripts.migrate_docx_skill_paths import apply_migration

    events: list[str] = []
    source = _MigrationCollection(
        [{"_id": "source-1", "file_path": "SKILL.md", "content": LEGACY_COMMAND}],
        events=events,
        name="source",
    )
    backups = _MigrationCollection(events=events, name="backup")
    database = _MigrationDatabase(
        {
            "skill_files": source,
            "skill_marketplace_files": _MigrationCollection(),
            "system_skills": _MigrationCollection(),
            "skill_migration_backups": backups,
        }
    )
    manifest_path = tmp_path / "rollout.json"
    _write_rollout_manifest(manifest_path)

    report = await apply_migration(database, manifest_path)

    assert report.migrated == 1
    assert events[:2] == ["backup", "source"]
    assert backups.index_calls == [("expire_at", 0)]
    assert backups.documents[0]["rollout_id"] == "rollout-current"
    assert backups.documents[0]["original_content"] == LEGACY_COMMAND
    assert "/home/oai/skills" not in source.documents[0]["content"]

    second_report = await apply_migration(database, manifest_path)
    assert second_report.recognized == 0
    assert second_report.migrated == 0
    assert len(backups.documents) == 1


@pytest.mark.asyncio
async def test_rollback_survives_crash_after_source_cas_and_is_rollout_scoped(
    tmp_path: Path,
) -> None:
    from scripts.migrate_docx_skill_paths import apply_migration, rollback_migration

    source = _MigrationCollection(
        [{"_id": "source-1", "file_path": "SKILL.md", "content": LEGACY_COMMAND}],
        name="source",
        raise_after_source_update=True,
    )
    backups = _MigrationCollection(name="backup")
    database = _MigrationDatabase(
        {
            "skill_files": source,
            "skill_marketplace_files": _MigrationCollection(),
            "system_skills": _MigrationCollection(),
            "skill_migration_backups": backups,
        }
    )
    manifest_path = tmp_path / "rollout.json"
    _write_rollout_manifest(manifest_path)

    with pytest.raises(RuntimeError, match="crash after source CAS"):
        await apply_migration(database, manifest_path)
    source.raise_after_source_update = False
    backups.documents.append(
        {
            "_id": "older-backup",
            "migration_id": "docx-skill-path-v1",
            "rollout_id": "rollout-older",
            "collection_name": "skill_files",
            "source_id": "source-1",
            "original_content": "must-not-be-used",
            "migrated_content_hash": "irrelevant",
        }
    )

    report = await rollback_migration(database, manifest_path)

    assert report.rolled_back == 1
    assert source.documents[0]["content"] == LEGACY_COMMAND
    assert backups.documents[-1]["rollout_id"] == "rollout-older"


@pytest.mark.asyncio
async def test_rollback_preserves_later_user_edits(tmp_path: Path) -> None:
    from scripts.migrate_docx_skill_paths import apply_migration, rollback_migration

    source = _MigrationCollection(
        [{"_id": "source-1", "file_path": "SKILL.md", "content": LEGACY_COMMAND}]
    )
    backups = _MigrationCollection()
    database = _MigrationDatabase(
        {
            "skill_files": source,
            "skill_marketplace_files": _MigrationCollection(),
            "system_skills": _MigrationCollection(),
            "skill_migration_backups": backups,
        }
    )
    manifest_path = tmp_path / "rollout.json"
    _write_rollout_manifest(manifest_path)
    await apply_migration(database, manifest_path)
    source.documents[0]["content"] = "later administrator edit"

    report = await rollback_migration(database, manifest_path)

    assert report.rolled_back == 0
    assert report.conflicted == 1
    assert source.documents[0]["content"] == "later administrator edit"


@pytest.mark.asyncio
async def test_apply_rejects_unverified_rollout_manifest_before_writes(
    tmp_path: Path,
) -> None:
    from scripts.migrate_docx_skill_paths import apply_migration

    source = _MigrationCollection(
        [{"_id": "source-1", "file_path": "SKILL.md", "content": LEGACY_COMMAND}]
    )
    backups = _MigrationCollection()
    database = _MigrationDatabase(
        {
            "skill_files": source,
            "skill_marketplace_files": _MigrationCollection(),
            "system_skills": _MigrationCollection(),
            "skill_migration_backups": backups,
        }
    )
    manifest_path = tmp_path / "rollout.json"
    manifest_path.write_text(json.dumps({"rollout_id": "rollout-current"}), encoding="utf-8")

    with pytest.raises(ValueError, match="verified candidate"):
        await apply_migration(database, manifest_path)

    assert backups.documents == []
    assert source.documents[0]["content"] == LEGACY_COMMAND


@pytest.mark.asyncio
async def test_apply_rejects_stale_backup_after_source_revision_changes(
    tmp_path: Path,
) -> None:
    from scripts.migrate_docx_skill_paths import apply_migration, rollback_migration

    first_content = f"first\n{LEGACY_COMMAND}"
    second_content = f"second administrator revision\n{LEGACY_COMMAND}"
    source = _MigrationCollection(
        [{"_id": "source-1", "file_path": "SKILL.md", "content": first_content}],
        fail_next_update=True,
    )
    backups = _MigrationCollection()
    database = _MigrationDatabase(
        {
            "skill_files": source,
            "skill_marketplace_files": _MigrationCollection(),
            "system_skills": _MigrationCollection(),
            "skill_migration_backups": backups,
        }
    )
    manifest_path = tmp_path / "rollout.json"
    _write_rollout_manifest(manifest_path)
    first_report = await apply_migration(database, manifest_path)
    assert first_report.conflicted == 1
    rollback_report = await rollback_migration(database, manifest_path)
    assert rollback_report.rolled_back == 0
    assert rollback_report.conflicted == 1
    assert source.documents[0]["content"] == first_content
    source.documents[0]["content"] = second_content

    second_report = await apply_migration(database, manifest_path)

    assert second_report.migrated == 0
    assert second_report.conflicted == 1
    assert source.documents[0]["content"] == second_content
    assert backups.documents[0]["original_content"] == first_content
