"""Tests for TeamStorage.ensure_indexes (P0-2)."""

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
async def test_team_storage_ensures_owner_updated_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collection = _FakeCollection()
    client = _FakeClient(collection)
    monkeypatch.setattr("src.infra.storage.mongodb.get_mongo_client", lambda: client)

    from src.infra.team.storage import TeamStorage

    storage = TeamStorage()
    await storage.ensure_indexes()

    assert any(
        keys == [("owner_user_id", 1), ("updated_at", -1)]
        and kwargs.get("name") == "team_owner_updated_idx"
        and kwargs.get("background") is True
        and not kwargs.get("unique")
        for keys, kwargs in collection.created_indexes
    )
