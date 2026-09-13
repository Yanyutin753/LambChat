"""Tests for ProjectStorage P2-10 race fix (unique partial indexes + DuplicateKeyError)."""

from __future__ import annotations

from typing import Any

import pytest
from pymongo.errors import DuplicateKeyError

from src.infra.folder.storage import ProjectStorage
from src.infra.utils.datetime import utc_now


class _FakeProjectCollection:
    """Records find_one / insert_one / create_index; insert_one may raise DuplicateKeyError."""

    def __init__(self, *, find_one_seq=None, insert_raises=None):
        self._find_one_seq = list(find_one_seq or [])
        self._find_one_idx = 0
        self.insert_raises = insert_raises
        self.insert_calls: list[dict[str, Any]] = []
        self.create_index_calls: list[tuple[list, dict[str, Any]]] = []

    async def find_one(self, query: dict[str, Any]) -> dict[str, Any] | None:
        if self._find_one_idx < len(self._find_one_seq):
            doc = self._find_one_seq[self._find_one_idx]
            self._find_one_idx += 1
            return dict(doc) if doc else None
        return None

    async def insert_one(self, doc: dict[str, Any]):
        self.insert_calls.append(dict(doc))
        if self.insert_raises:
            raise self.insert_raises

        class _Result:
            inserted_id = "new-id"

        return _Result()

    async def create_index(self, keys, **kwargs):
        self.create_index_calls.append((keys, kwargs))


def _fav_doc() -> dict[str, Any]:
    return {
        "_id": "fav-1",
        "name": "Favorites",
        "type": "favorites",
        "icon": "Star",
        "sort_order": 0,
        "user_id": "user-1",
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }


def _channel_doc(doc_id: str = "ch-1", name: str = "feishu-channel") -> dict[str, Any]:
    return {
        "_id": doc_id,
        "name": name,
        "type": "channel",
        "icon": "💬",
        "sort_order": 100,
        "user_id": "user-1",
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }


@pytest.mark.asyncio
async def test_ensure_indexes_creates_partial_unique_indexes() -> None:
    storage = ProjectStorage()
    collection = _FakeProjectCollection()
    storage._collection = collection

    await storage.ensure_indexes()

    by_name = {kwargs["name"]: kwargs for _keys, kwargs in collection.create_index_calls}
    assert "project_user_type_idx" in by_name  # 通用查询索引保留
    # P2-10 ①：favorites partial 唯一
    fav = by_name["project_user_favorites_uniq"]
    assert fav["unique"] is True
    assert fav["partialFilterExpression"] == {"type": "favorites"}
    # P2-10 ②：channel partial 唯一
    ch = by_name["project_user_name_type_channel_uniq"]
    assert ch["unique"] is True
    assert ch["partialFilterExpression"] == {"type": "channel"}


@pytest.mark.asyncio
async def test_ensure_favorites_returns_existing_on_duplicate() -> None:
    """并发：首次无 → insert 抛 DuplicateKeyError → 回查返回已存在（幂等）。"""
    storage = ProjectStorage()
    collection = _FakeProjectCollection(
        find_one_seq=[None, _fav_doc()],
        insert_raises=DuplicateKeyError("duplicate"),
    )
    storage._collection = collection

    project = await storage.ensure_favorites_project("user-1")

    assert project.id == "fav-1"
    assert len(collection.insert_calls) == 1  # 未重试裸 insert


@pytest.mark.asyncio
async def test_get_or_create_by_name_returns_existing_on_duplicate() -> None:
    """并发：首次无 → insert 抛 DuplicateKeyError → 回查返回已存在（幂等）。"""
    storage = ProjectStorage()
    collection = _FakeProjectCollection(
        find_one_seq=[None, _channel_doc()],
        insert_raises=DuplicateKeyError("duplicate"),
    )
    storage._collection = collection

    project = await storage.get_or_create_by_name("user-1", "feishu-channel")

    assert project.id == "ch-1"
    assert project.name == "feishu-channel"
    assert len(collection.insert_calls) == 1


@pytest.mark.asyncio
async def test_get_or_create_by_name_inserts_when_absent() -> None:
    storage = ProjectStorage()
    collection = _FakeProjectCollection(find_one_seq=[None])  # 无 → insert 成功
    storage._collection = collection

    project = await storage.get_or_create_by_name("user-1", "new-channel")

    assert project.name == "new-channel"
    assert len(collection.insert_calls) == 1


@pytest.mark.asyncio
async def test_get_or_create_by_name_returns_existing_without_insert() -> None:
    storage = ProjectStorage()
    collection = _FakeProjectCollection(find_one_seq=[_channel_doc(name="existing")])
    storage._collection = collection

    project = await storage.get_or_create_by_name("user-1", "existing")

    assert project.id == "ch-1"
    assert collection.insert_calls == []  # 命中已有，未 insert
