"""Tests for PersonaPresetStorage.ensure_indexes (P0-2)."""

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
async def test_persona_preset_storage_ensures_visibility_indexes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collection = _FakeCollection()
    client = _FakeClient(collection)
    monkeypatch.setattr("src.infra.storage.mongodb.get_mongo_client", lambda: client)

    from src.infra.persona_preset.storage import PersonaPresetStorage

    storage = PersonaPresetStorage()
    await storage.ensure_indexes()

    by_name = {kwargs.get("name"): (keys, kwargs) for keys, kwargs in collection.created_indexes}

    # user-scope branch of _build_visible_query $or.
    scope_owner = by_name["persona_scope_owner_idx"]
    assert scope_owner[0] == [("scope", 1), ("owner_user_id", 1)]
    assert scope_owner[1].get("background") is True
    assert not scope_owner[1].get("unique")

    # global published branch.
    scope_status_vis = by_name["persona_scope_status_visibility_idx"]
    assert scope_status_vis[0] == [("scope", 1), ("status", 1), ("visibility", 1)]
    assert scope_status_vis[1].get("background") is True
    assert not scope_status_vis[1].get("unique")


@pytest.mark.asyncio
async def test_persona_preset_storage_attempts_second_index_when_first_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FailsFirstCollection(_FakeCollection):
        async def create_index(self, keys, **kwargs):
            self.created_indexes.append((keys, dict(kwargs)))
            if len(self.created_indexes) == 1:
                raise RuntimeError("first index failed")

    collection = _FailsFirstCollection()
    client = _FakeClient(collection)
    monkeypatch.setattr("src.infra.storage.mongodb.get_mongo_client", lambda: client)

    from src.infra.persona_preset.storage import PersonaPresetStorage

    await PersonaPresetStorage().ensure_indexes()

    assert [kwargs["name"] for _, kwargs in collection.created_indexes] == [
        "persona_scope_owner_idx",
        "persona_scope_status_visibility_idx",
    ]
