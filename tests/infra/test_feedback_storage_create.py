"""Tests for FeedbackStorage P2-10 race fix (insert + DuplicateKeyError, no precheck find)."""

from __future__ import annotations

from typing import Any

import pytest
from pymongo.errors import DuplicateKeyError

from src.infra.feedback.storage import FeedbackStorage
from src.kernel.schemas.feedback import FeedbackCreate


class _FakeFeedbackCollection:
    """Records insert_one / create_index; insert_one may raise DuplicateKeyError."""

    def __init__(self, *, insert_raises=None):
        self.insert_raises = insert_raises
        self.insert_calls: list[dict[str, Any]] = []
        self.create_index_calls: list[tuple[list, dict[str, Any]]] = []

    async def insert_one(self, doc: dict[str, Any]):
        self.insert_calls.append(dict(doc))
        if self.insert_raises:
            raise self.insert_raises

        class _Result:
            inserted_id = "fb-1"

        return _Result()

    async def create_index(self, keys, **kwargs):
        self.create_index_calls.append((keys, kwargs))


def _feedback_create() -> FeedbackCreate:
    return FeedbackCreate(session_id="sess-1", run_id="run-1", rating="up", comment="good")


@pytest.mark.asyncio
async def test_create_returns_feedback_on_success() -> None:
    storage = FeedbackStorage()
    collection = _FakeFeedbackCollection()
    storage._collection = collection

    feedback = await storage.create(_feedback_create(), "user-1", "alice")

    assert feedback.id == "fb-1"
    assert feedback.user_id == "user-1"
    assert feedback.username == "alice"
    assert feedback.session_id == "sess-1"
    assert feedback.run_id == "run-1"
    assert feedback.rating == "up"
    assert len(collection.insert_calls) == 1


@pytest.mark.asyncio
async def test_create_raises_value_error_on_duplicate() -> None:
    """重复：insert 抛 DuplicateKeyError → ValueError（保持路由层 except ValueError 契约）。"""
    storage = FeedbackStorage()
    collection = _FakeFeedbackCollection(insert_raises=DuplicateKeyError("duplicate"))
    storage._collection = collection

    with pytest.raises(ValueError, match="您已经对该对话提交过反馈"):
        await storage.create(_feedback_create(), "user-1", "alice")


@pytest.mark.asyncio
async def test_create_indexes_builds_unique_index() -> None:
    """create() 的并发保护依赖 user_run_unique 唯一索引（启动初始化负责创建）。"""
    storage = FeedbackStorage()
    collection = _FakeFeedbackCollection()
    storage._collection = collection

    await storage.create_indexes()

    unique_indexes = [
        (keys, kwargs) for keys, kwargs in collection.create_index_calls if kwargs.get("unique")
    ]
    assert any(
        keys == [("user_id", 1), ("session_id", 1), ("run_id", 1)]
        and kwargs.get("name") == "user_run_unique"
        for keys, kwargs in unique_indexes
    )
