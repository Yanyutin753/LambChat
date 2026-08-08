from __future__ import annotations

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
