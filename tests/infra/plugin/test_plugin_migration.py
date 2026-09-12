from __future__ import annotations

from typing import Any

import pytest

from src.infra.plugin.migration import migrate_skill_marketplace_to_plugins


class _MigrationCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = docs

    def __aiter__(self):
        self._iter = iter(self._docs)
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc

    def limit(self, *_args, **_kwargs):
        return self

    def batch_size(self, *_args, **_kwargs):
        return self


class _MigrationCollection:
    def __init__(self, docs: list[dict[str, Any]] | None = None) -> None:
        self.docs = list(docs or [])

    def find(self, query: dict[str, Any], *_args, **_kwargs):
        matched = [
            doc
            for doc in self.docs
            if all(doc.get(k) == v for k, v in query.items() if k != "file_path")
        ]
        if "file_path" in query:
            expected = query["file_path"]
            matched = [
                doc
                for doc in matched
                if isinstance(expected, dict)
                and doc.get("file_path") in expected.get("$nin", [])
                or (not isinstance(expected, dict) and doc.get("file_path") == expected)
            ]
        return _MigrationCursor(matched)

    async def find_one(self, query: dict[str, Any], *_args, **_kwargs):
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items()):
                return doc
        return None

    async def insert_one(self, doc: dict[str, Any]):
        self.docs.append(dict(doc))

    async def update_one(self, query: dict[str, Any], update: dict[str, Any], upsert=False):
        target = None
        for doc in self.docs:
            if all(doc.get(k) == v for k, v in query.items()):
                target = doc
                break
        if target is None:
            if upsert:
                self.docs.append({**query, **update.get("$setOnInsert", {})})
            return
        for key, value in update.get("$setOnInsert", {}).items():
            target.setdefault(key, value)


@pytest.mark.asyncio
async def test_migration_creates_single_skill_plugins_and_copies_files() -> None:
    marketplace = _MigrationCollection(
        [
            {
                "skill_name": "planner",
                "description": "Plan work",
                "tags": ["planning"],
                "is_active": True,
                "created_by": "user-1",
            },
            {
                "skill_name": "legacy-off",
                "description": "Deactivated",
                "tags": [],
                "is_active": False,
                "created_by": "user-2",
            },
        ]
    )
    marketplace_files = _MigrationCollection(
        [
            {"skill_name": "planner", "file_path": "SKILL.md", "content": "# Plan"},
            {"skill_name": "planner", "file_path": "notes.md", "content": "n"},
        ]
    )
    plugins = _MigrationCollection()
    plugin_files = _MigrationCollection()

    migrated = await migrate_skill_marketplace_to_plugins(
        plugins_collection=plugins,
        marketplace_collection=marketplace,
        marketplace_files_collection=marketplace_files,
        plugin_files_collection=plugin_files,
    )
    assert migrated == 2

    by_name = {doc["name"]: doc for doc in plugins.docs}
    assert by_name["planner"]["status"] == "active"
    assert by_name["planner"]["migrated_from"] == "skill_marketplace"
    assert by_name["planner"]["created_by"] == "user-1"
    assert by_name["planner"]["skills"] == [
        {"skill_name": "planner", "description": "Plan work", "tags": ["planning"]}
    ]
    assert by_name["legacy-off"]["status"] == "deactivated"

    copied = {(doc["plugin_name"], doc["file_path"]) for doc in plugin_files.docs}
    assert copied == {("planner", "SKILL.md"), ("planner", "notes.md")}


@pytest.mark.asyncio
async def test_migration_is_idempotent() -> None:
    marketplace = _MigrationCollection(
        [{"skill_name": "planner", "description": "", "tags": [], "is_active": True}]
    )
    marketplace_files = _MigrationCollection(
        [{"skill_name": "planner", "file_path": "SKILL.md", "content": "# Plan"}]
    )
    plugins = _MigrationCollection()
    plugin_files = _MigrationCollection()

    first = await migrate_skill_marketplace_to_plugins(
        plugins_collection=plugins,
        marketplace_collection=marketplace,
        marketplace_files_collection=marketplace_files,
        plugin_files_collection=plugin_files,
    )
    second = await migrate_skill_marketplace_to_plugins(
        plugins_collection=plugins,
        marketplace_collection=marketplace,
        marketplace_files_collection=marketplace_files,
        plugin_files_collection=plugin_files,
    )
    assert first == 1
    assert second == 0
    assert len(plugins.docs) == 1
    assert len(plugin_files.docs) == 1
