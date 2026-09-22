"""通知存储层"""

from __future__ import annotations

from enum import Enum
from typing import Optional

from bson import ObjectId

from src.infra.logging import get_logger
from src.infra.storage.mongodb import get_mongo_client
from src.infra.utils.datetime import utc_now
from src.kernel.config import settings
from src.kernel.schemas.notification import (
    Notification,
    NotificationCreate,
    NotificationUpdate,
)

logger = get_logger(__name__)

NOTIFICATION_LIST_LIMIT_MAX = 100


def _bounded_limit(limit: int) -> int:
    return min(max(int(limit), 1), NOTIFICATION_LIST_LIMIT_MAX)


class NotificationStorage:
    """通知存储"""

    def __init__(self):
        self._collection = None
        self._dismissal_collection = None

    @property
    def collection(self):
        if self._collection is None:
            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            self._collection = db["notifications"]
        return self._collection

    @property
    def dismissal_collection(self):
        if self._dismissal_collection is None:
            client = get_mongo_client()
            db = client[settings.MONGODB_DB]
            self._dismissal_collection = db["notification_dismissals"]
        return self._dismissal_collection

    async def create_indexes(self) -> None:
        await self.collection.create_index([("created_at", -1)])
        await self.collection.create_index([("is_active", 1), ("created_at", -1)])
        await self.dismissal_collection.create_index(
            [("notification_id", 1), ("user_id", 1)], unique=True
        )
        logger.info("Notification indexes created")

    async def create(self, data: NotificationCreate, user_id: str) -> Notification:
        now = utc_now()
        doc = {
            "title_i18n": data.title_i18n.model_dump(),
            "content_i18n": data.content_i18n.model_dump(),
            "type": data.type.value if isinstance(data.type, Enum) else data.type,
            "start_time": data.start_time,
            "end_time": data.end_time,
            "is_active": data.is_active,
            "created_at": now,
            "updated_at": now,
            "created_by": user_id,
        }
        result = await self.collection.insert_one(doc)
        doc["id"] = str(result.inserted_id)
        return Notification.model_validate(doc)

    async def get_by_id(self, notification_id: str) -> Optional[Notification]:
        try:
            doc = await self.collection.find_one({"_id": ObjectId(notification_id)})
            if doc:
                doc["id"] = str(doc.pop("_id"))
                return Notification.model_validate(doc)
            return None
        except Exception as e:
            logger.error(f"Error getting notification {notification_id}: {e}")
            return None

    async def list_notifications(
        self, skip: int = 0, limit: int = 50
    ) -> tuple[list[Notification], int]:
        limit = _bounded_limit(limit)
        total = await self.collection.count_documents({})
        cursor = self.collection.find().sort("created_at", -1).skip(skip).limit(limit)
        items = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            items.append(Notification.model_validate(doc))
        return items, total

    async def update(
        self, notification_id: str, data: NotificationUpdate
    ) -> Optional[Notification]:
        try:
            update_fields: dict = {"updated_at": utc_now()}
            provided = data.model_fields_set
            if "title_i18n" in provided and data.title_i18n is not None:
                update_fields["title_i18n"] = data.title_i18n.model_dump()
            if "content_i18n" in provided and data.content_i18n is not None:
                update_fields["content_i18n"] = data.content_i18n.model_dump()
            if "start_time" in provided:
                update_fields["start_time"] = data.start_time
            if "end_time" in provided:
                update_fields["end_time"] = data.end_time
            if "is_active" in provided:
                update_fields["is_active"] = data.is_active

            result = await self.collection.find_one_and_update(
                {"_id": ObjectId(notification_id)},
                {"$set": update_fields},
                return_document=True,
            )
            if result:
                result["id"] = str(result.pop("_id"))
                return Notification.model_validate(result)
            return None
        except Exception as e:
            logger.error(f"Error updating notification {notification_id}: {e}")
            return None

    async def delete(self, notification_id: str) -> bool:
        try:
            result = await self.collection.delete_one({"_id": ObjectId(notification_id)})
            if result.deleted_count > 0:
                await self.dismissal_collection.delete_many({"notification_id": notification_id})
                return True
            return False
        except Exception as e:
            logger.error(f"Error deleting notification {notification_id}: {e}")
            return False

    async def get_active_notifications(self, user_id: str, limit: int = 5) -> list[Notification]:
        """Get active notifications that the user hasn't dismissed, sorted by created_at desc."""
        now = utc_now()
        limit = _bounded_limit(limit)

        pipeline = [
            {
                "$match": {
                    "is_active": True,
                    "$and": [
                        {
                            "$or": [
                                {"start_time": {"$exists": False}},
                                {"start_time": None},
                                {"start_time": {"$lte": now}},
                            ]
                        },
                        {
                            "$or": [
                                {"end_time": {"$exists": False}},
                                {"end_time": None},
                                {"end_time": {"$gte": now}},
                            ]
                        },
                    ],
                }
            },
            {"$sort": {"created_at": -1}},
            {
                "$lookup": {
                    "from": "notification_dismissals",
                    "let": {"notification_id": {"$toString": "$_id"}},
                    "pipeline": [
                        {
                            "$match": {
                                "$expr": {
                                    "$and": [
                                        {"$eq": ["$notification_id", "$$notification_id"]},
                                        {"$eq": ["$user_id", user_id]},
                                    ]
                                }
                            }
                        },
                        {"$limit": 1},
                    ],
                    "as": "dismissals",
                }
            },
            {"$match": {"dismissals": {"$eq": []}}},
            {"$limit": limit},
        ]

        cursor = await self.collection.aggregate(pipeline)
        results = []
        async for doc in cursor:
            doc["id"] = str(doc.pop("_id"))
            doc.pop("dismissals", None)
            results.append(Notification.model_validate(doc))
        return results

    async def dismiss(self, notification_id: str, user_id: str) -> bool:
        try:
            await self.dismissal_collection.update_one(
                {"notification_id": notification_id, "user_id": user_id},
                {"$set": {"dismissed_at": utc_now()}},
                upsert=True,
            )
            return True
        except Exception as e:
            logger.error(f"Error dismissing notification: {e}")
            return False

    async def close(self) -> None:
        self._collection = None
        self._dismissal_collection = None
