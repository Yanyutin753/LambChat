from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import pytest
from bson import ObjectId

from src.infra.notification.storage import NotificationStorage
from src.infra.utils.datetime import utc_now

NOTIFICATION_LIST_LIMIT_MAX = 100


def _notification_doc(
    notification_id: ObjectId,
    *,
    title: str = "title",
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> dict[str, Any]:
    now = utc_now()
    return {
        "_id": notification_id,
        "title_i18n": {"en": title, "zh": title, "ja": title, "ko": title, "ru": title},
        "content_i18n": {"en": "body", "zh": "body", "ja": "body", "ko": "body", "ru": "body"},
        "type": "info",
        "start_time": start_time,
        "end_time": end_time,
        "is_active": True,
        "created_at": now,
        "updated_at": now,
        "created_by": "admin",
    }


class _AggregateCursor:
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


class _NotificationCollection:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.docs = docs
        self.pipeline: list[dict[str, Any]] | None = None

    async def aggregate(self, pipeline: list[dict[str, Any]]):
        self.pipeline = pipeline
        return _AggregateCursor([dict(doc) for doc in self.docs])


class _FindCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = docs
        self.skip_value: int | None = None
        self.limit_value: int | None = None

    def sort(self, *_args):
        return self

    def skip(self, value: int):
        self.skip_value = value
        return self

    def limit(self, value: int):
        self.limit_value = value
        return self

    def __aiter__(self):
        cap = self.limit_value
        self._iter = iter(self._docs[: cap or None])
        return self

    async def __anext__(self):
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _ListNotificationCollection:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.cursor = _FindCursor([dict(doc) for doc in docs])

    async def count_documents(self, _query: dict[str, Any]) -> int:
        return 1_000

    def find(self):
        return self.cursor


class _DismissalCollection:
    async def distinct(self, *_args, **_kwargs):
        raise AssertionError("get_active_notifications should not materialize all dismissals")


@pytest.mark.asyncio
async def test_active_notifications_filters_in_mongo_without_distinct() -> None:
    storage = NotificationStorage()
    notification_id = ObjectId()
    storage._collection = _NotificationCollection([_notification_doc(notification_id)])
    storage._dismissal_collection = _DismissalCollection()

    items = await storage.get_active_notifications("user-1", limit=3)

    assert [item.id for item in items] == [str(notification_id)]
    pipeline = storage._collection.pipeline
    assert pipeline is not None
    assert pipeline[0]["$match"]["is_active"] is True
    now = utc_now()
    start_conditions = pipeline[0]["$match"]["$and"][0]["$or"]
    end_conditions = pipeline[0]["$match"]["$and"][1]["$or"]
    assert {"start_time": {"$exists": False}} in start_conditions
    assert {"start_time": None} in start_conditions
    assert any(
        "start_time" in condition
        and isinstance(condition["start_time"], dict)
        and "$lte" in condition["start_time"]
        and isinstance(condition["start_time"]["$lte"], datetime)
        and abs(condition["start_time"]["$lte"] - now) <= timedelta(seconds=5)
        for condition in start_conditions
    )
    assert {"end_time": {"$exists": False}} in end_conditions
    assert {"end_time": None} in end_conditions
    assert any(
        "end_time" in condition
        and isinstance(condition["end_time"], dict)
        and "$gte" in condition["end_time"]
        and isinstance(condition["end_time"]["$gte"], datetime)
        and abs(condition["end_time"]["$gte"] - now) <= timedelta(seconds=5)
        for condition in end_conditions
    )
    assert pipeline[-1] == {"$limit": 3}
    assert any("$lookup" in stage for stage in pipeline)
    assert any(stage == {"$match": {"dismissals": {"$eq": []}}} for stage in pipeline)


@pytest.mark.asyncio
async def test_list_notifications_clamps_storage_limit() -> None:
    storage = NotificationStorage()
    storage._collection = _ListNotificationCollection(
        [_notification_doc(ObjectId()) for _ in range(150)]
    )

    items, total = await storage.list_notifications(limit=10_000)

    assert total == 1_000
    assert len(items) == NOTIFICATION_LIST_LIMIT_MAX
    assert storage.collection.cursor.limit_value == NOTIFICATION_LIST_LIMIT_MAX


@pytest.mark.asyncio
async def test_active_notifications_clamps_storage_limit() -> None:
    storage = NotificationStorage()
    storage._collection = _NotificationCollection([_notification_doc(ObjectId())])

    await storage.get_active_notifications("user-1", limit=10_000)

    assert storage.collection.pipeline is not None
    assert storage.collection.pipeline[-1] == {"$limit": NOTIFICATION_LIST_LIMIT_MAX}


@pytest.mark.asyncio
async def test_notification_storage_close_clears_collection_refs() -> None:
    storage = NotificationStorage()
    storage._collection = object()
    storage._dismissal_collection = object()

    await storage.close()

    assert storage._collection is None
    assert storage._dismissal_collection is None
