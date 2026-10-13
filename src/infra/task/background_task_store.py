"""Small durable admission journal for independently owned chat tasks."""

from datetime import timedelta
from uuid import uuid4

from pymongo import ReturnDocument

from src.infra.utils.datetime import utc_now
from src.kernel.config import settings


class BackgroundTaskStore:
    def __init__(self, collection=None):
        self._collection = collection

    @property
    def collection(self):
        if self._collection is None:
            from src.infra.storage.mongodb import get_mongo_client

            self._collection = get_mongo_client()[settings.MONGODB_DB]["background_tasks"]
        return self._collection

    async def reserve(self, record):
        # Mongo's unique _id is the source-call admission identity across workers.
        return await self.collection.find_one_and_update(
            {"_id": record["_id"]},
            {"$setOnInsert": record},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )

    async def claim(self, task_id):
        return await self.collection.find_one_and_update(
            {"_id": task_id, "state": "reserved"},
            {
                "$set": {
                    "state": "submitting",
                    "lease_token": uuid4().hex,
                    "lease_expires_at": utc_now() + timedelta(seconds=120),
                }
            },
            return_document=ReturnDocument.AFTER,
        )

    async def finish(self, task_id, token, state, **fields):
        result = await self.collection.update_one(
            {"_id": task_id, "state": "submitting", "lease_token": token},
            {"$set": {"state": state, "updated_at": utc_now(), **fields}},
        )
        return bool(result.modified_count)

    async def mark_attention_delivered(self, task_id):
        await self.collection.update_one(
            {"_id": task_id, "state": {"$in": ["failed", "uncertain"]}},
            {"$set": {"attention_pending": False}},
        )

    async def recoverable(self):
        return (
            await self.collection.find(
                {
                    "$or": [
                        {"state": "reserved"},
                        {"state": {"$in": ["failed", "uncertain"]}, "attention_pending": True},
                        {"state": "submitting", "lease_expires_at": {"$lte": utc_now()}},
                    ]
                }
            )
            .sort("_id", 1)
            .limit(25)
            .to_list(length=25)
        )
