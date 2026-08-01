"""Tests for RoleStorage.ensure_indexes (P0-2)."""

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
async def test_role_storage_ensures_unique_name_index(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collection = _FakeCollection()
    client = _FakeClient(collection)
    monkeypatch.setattr("src.infra.storage.mongodb.get_mongo_client", lambda: client)

    from src.infra.role.storage import RoleStorage

    storage = RoleStorage()
    await storage.ensure_indexes()

    assert any(
        keys == [("name", 1)]
        and kwargs.get("name") == "role_name_unique_idx"
        and kwargs.get("unique") is True
        and kwargs.get("background") is True
        for keys, kwargs in collection.created_indexes
    )


@pytest.mark.asyncio
async def test_role_storage_ensure_indexes_swallows_create_index_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failing create_index (e.g. duplicate name on dirty data) must not crash startup."""

    class _ExplodingCollection:
        async def create_index(self, keys, **kwargs):
            raise RuntimeError("index build failed")

    class _ExplodingDb:
        def __getitem__(self, name: str) -> _ExplodingCollection:
            return _ExplodingCollection()

    class _ExplodingClient:
        def __getitem__(self, name: str) -> _ExplodingDb:
            return _ExplodingDb()

    monkeypatch.setattr("src.infra.storage.mongodb.get_mongo_client", lambda: _ExplodingClient())

    from src.infra.role.storage import RoleStorage

    storage = RoleStorage()
    # Must not raise — ensure_indexes swallows so startup can continue.
    await storage.ensure_indexes()
