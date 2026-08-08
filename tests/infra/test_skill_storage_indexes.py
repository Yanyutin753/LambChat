"""Tests for SkillStorage.ensure_indexes (P1-6).

Verifies the new non-unique (user_id, file_path) index is added alongside the
existing unique (skill_name, user_id, file_path) index, so {user_id, file_path}
queries (list_user_skills / count / get_all_user_skill_names) stop full-collection scanning.
"""

from __future__ import annotations

import pytest


class _FakeCollection:
    def __init__(self) -> None:
        self.created_indexes: list[tuple[object, dict[str, object]]] = []

    async def create_index(self, keys, **kwargs):
        self.created_indexes.append((keys, dict(kwargs)))


class _FakeDb:
    def __init__(self, collection: _FakeCollection) -> None:
        self._collection = collection

    def __getitem__(self, name: str) -> _FakeCollection:
        return self._collection


class _FakeClient:
    def __init__(self, collection: _FakeCollection) -> None:
        self._db = _FakeDb(collection)

    def __getitem__(self, name: str) -> _FakeDb:
        return self._db


@pytest.mark.asyncio
async def test_skill_storage_ensures_non_unique_user_file_path_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collection = _FakeCollection()
    client = _FakeClient(collection)
    monkeypatch.setattr("src.infra.skill.storage.get_mongo_client", lambda: client)

    from src.infra.skill.storage import SkillStorage

    storage = SkillStorage()
    await storage.ensure_indexes()

    # Existing unique index preserved.
    assert any(
        keys == [("skill_name", 1), ("user_id", 1), ("file_path", 1)]
        and kwargs.get("unique") is True
        for keys, kwargs in collection.created_indexes
    )
    # New non-unique index for {user_id, file_path} queries (P1-6).
    assert any(
        keys == [("user_id", 1), ("file_path", 1)]
        and kwargs.get("name") == "user_file_path_idx"
        and kwargs.get("background") is True
        and not kwargs.get("unique")
        for keys, kwargs in collection.created_indexes
    )
