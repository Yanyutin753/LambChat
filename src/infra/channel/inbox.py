"""Durable channel inputs and fenced processing checkpoints.

Pending records never expire. Only completed records receive a retention TTL;
transport acknowledgements may therefore precede execution without losing work
when the receiving process exits. MongoDB, rather than the evictable Redis cache,
owns both the record and its processing lease.
"""

from __future__ import annotations

import hashlib
import json
from datetime import timedelta
from typing import Any

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError
from pymongo.write_concern import WriteConcern

from src.infra.storage.mongodb import get_mongo_client
from src.infra.utils.datetime import utc_now
from src.kernel.config import settings

LEASE_SECONDS = 90


def conversation_key(scope: list[str], message: dict[str, Any]) -> str:
    """Match the provider's session identity for ordering and conversation leases."""
    metadata = message.get("metadata") or {}
    identity = [*scope, message.get("chat_id", "")]
    if scope[0] not in {"weixin", "feishu"}:
        identity.extend(
            [
                message.get("sender_id", ""),
                metadata.get("thread_ts", ""),
                metadata.get("message_thread_id", ""),
            ]
        )
    return hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()


class ChannelInbox:
    def __init__(self, channel_type: str, user_id: str, instance_id: str, *, collection=None):
        self.scope = [channel_type, user_id, instance_id]
        self.scope_key = hashlib.sha256(json.dumps(self.scope).encode()).hexdigest()
        self._collection = collection
        self._indexed = False

    @property
    def collection(self):
        if self._collection is None:
            self._collection = get_mongo_client()[settings.MONGODB_DB][
                "channel_inbox"
            ].with_options(write_concern=WriteConcern(w="majority", j=True))
        return self._collection

    async def ensure_indexes(self) -> None:
        if self._indexed:
            return
        await self.collection.create_index([("scope", 1), ("state", 1), ("created_at", 1)])
        await self.collection.create_index(
            [
                ("scope", 1),
                ("state", 1),
                ("conversation", 1),
                ("created_at", 1),
                ("order_id", 1),
                ("_id", 1),
            ]
        )
        await self.collection.create_index("expires_at", expireAfterSeconds=0)
        self._indexed = True

    async def accept(self, message: dict[str, Any]) -> str:
        await self.ensure_indexes()
        identity = [*self.scope, message["message_id"]]
        key = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()
        try:
            await self.collection.update_one(
                {"_id": key},
                {
                    "$setOnInsert": {
                        "scope": self.scope_key,
                        "state": "pending",
                        "conversation": conversation_key(self.scope, message),
                        "message": message,
                        "created_at": utc_now(),
                        # BSON dates truncate to milliseconds; ObjectId preserves
                        # sequential acceptance order within the receiving process.
                        "order_id": ObjectId(),
                        "checkpoint": {},
                    }
                },
                upsert=True,
            )
        except DuplicateKeyError:
            # Simultaneous first acceptance races on the immutable _id index.
            pass
        return key

    async def pending(self, limit: int = 32) -> list[dict[str, Any]]:
        # Group BEFORE excluding leased rows: a leased/retrying head must block
        # later inputs in its conversation, without hiding unrelated chats.
        cursor = await self.collection.aggregate(
            [
                {"$match": {"scope": self.scope_key, "state": "pending"}},
                {"$sort": {"created_at": 1, "order_id": 1, "_id": 1}},
                {"$group": {"_id": "$conversation", "head": {"$first": "$$ROOT"}}},
                {"$replaceRoot": {"newRoot": "$head"}},
                {
                    "$match": {
                        "$or": [
                            {"lease_until": {"$exists": False}},
                            {"lease_until": {"$lte": utc_now()}},
                        ]
                    }
                },
                {"$sort": {"created_at": 1, "order_id": 1, "_id": 1}},
                {"$limit": limit},
            ],
            allowDiskUse=True,
        )
        return await cursor.to_list(length=limit)

    async def is_head(self, key: str) -> bool:
        row = await self.collection.find_one(
            {"_id": key, "scope": self.scope_key, "state": "pending"},
            {"conversation": 1},
        )
        if row is None:
            return False
        head = await self.collection.find_one(
            {"scope": self.scope_key, "state": "pending", "conversation": row["conversation"]},
            {"_id": 1},
            sort=[("created_at", 1), ("order_id", 1), ("_id", 1)],
        )
        return head is not None and head["_id"] == key

    async def claim(self, key: str, owner: str) -> dict[str, Any] | None:
        if not await self.is_head(key):
            return None
        now = utc_now()
        return await self.collection.find_one_and_update(
            {
                "_id": key,
                "scope": self.scope_key,
                "state": "pending",
                "$or": [
                    {"lease_until": {"$exists": False}},
                    {"lease_until": {"$lte": now}},
                ],
            },
            {"$set": {"owner": owner, "lease_until": now + timedelta(seconds=LEASE_SECONDS)}},
            return_document=ReturnDocument.AFTER,
        )

    def _owned(self, key: str, owner: str) -> dict[str, Any]:
        return {
            "_id": key,
            "scope": self.scope_key,
            "state": "pending",
            "owner": owner,
            "lease_until": {"$gt": utc_now()},
        }

    async def renew(self, key: str, owner: str) -> bool:
        result = await self.collection.update_one(
            self._owned(key, owner),
            {"$set": {"lease_until": utc_now() + timedelta(seconds=LEASE_SECONDS)}},
        )
        return bool(result.matched_count)

    async def checkpoint(self, key: str, owner: str, values: dict[str, Any]) -> None:
        result = await self.collection.update_one(
            self._owned(key, owner), {"$set": {f"checkpoint.{k}": v for k, v in values.items()}}
        )
        if not result.matched_count:
            raise RuntimeError("Channel inbox lease lost")

    async def release(self, key: str, owner: str) -> None:
        await self.collection.update_one(
            {"_id": key, "scope": self.scope_key, "owner": owner, "state": "pending"},
            {"$unset": {"owner": "", "lease_until": ""}},
        )

    async def complete(self, key: str, owner: str) -> bool:
        result = await self.collection.update_one(
            self._owned(key, owner),
            {
                "$set": {"state": "done", "expires_at": utc_now() + timedelta(days=7)},
                "$unset": {"owner": "", "lease_until": "", "message": "", "checkpoint": ""},
            },
        )
        return bool(result.matched_count)
