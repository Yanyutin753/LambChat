"""Durable, bounded bulk grants; recipient records are the authoritative ledger."""

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4, uuid5

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from src.infra.usage.notifications import broadcast_quota_changed
from src.infra.usage.quota import WINDOW_NAMES, quota_storage
from src.infra.usage.reset import CARD_LIFETIME, HISTORY_GRACE, QuotaReset
from src.kernel.errors import AppError, ErrorCode

CHUNK_SIZE = 25
LEASE_DURATION = timedelta(seconds=60)
ERROR_SAMPLE_SIZE = 20


class ResetCardBatches:
    def __init__(self, database=None):
        if database is None:
            from src.infra.storage.mongodb import get_mongo_client
            from src.kernel.config import settings

            database = get_mongo_client()[settings.MONGODB_DB]
        self.batches = database["quota_reset_card_batches"]
        self.recipients = database["quota_reset_card_batch_recipients"]
        self.users = database["users"]
        self.resets = QuotaReset(database["user_usage_quotas"])

    @staticmethod
    def _id(value):
        try:
            return str(UUID(str(value)))
        except (ValueError, TypeError, AttributeError) as exc:
            raise AppError(ErrorCode.BAD_REQUEST) from exc

    @staticmethod
    def _response(doc):
        return {
            "id": doc["_id"],
            **{
                key: doc[key]
                for key in ("window", "status", "total", "processed", "issued", "failed", "errors")
            },
        }

    async def _owned(self, batch_id, actor_id):
        doc = await self.batches.find_one({"_id": self._id(batch_id), "actor_id": actor_id})
        if doc is None:
            raise AppError(ErrorCode.NOT_FOUND)
        return doc

    async def create(self, actor_id, idempotency_key, window):
        batch_id = self._id(idempotency_key)
        if window not in WINDOW_NAMES:
            raise AppError(ErrorCode.BAD_REQUEST)
        async with quota_storage():
            await self.batches.create_index([("actor_id", 1), ("created_at", -1), ("_id", -1)])
            await self.recipients.create_index([("batch_id", 1), ("status", 1), ("_id", 1)])
            previous = await self.batches.find_one({"_id": batch_id})
            if previous is None:
                now = datetime.now(UTC)
                eligible = {"$or": [{"created_at": {"$lte": now}}, {"created_at": None}]}
                last = await self.users.find_one(eligible, {"_id": 1}, sort=[("_id", -1)])
                upper_id = last["_id"] if last else None
                total = (
                    await self.users.count_documents({**eligible, "_id": {"$lte": upper_id}})
                    if last
                    else 0
                )
                doc = {
                    "_id": batch_id,
                    "actor_id": actor_id,
                    "window": window,
                    "status": "preparing",
                    "cutoff": now,
                    "upper_id": upper_id,
                    "cursor": None,
                    "total": total,
                    "processed": 0,
                    "issued": 0,
                    "failed": 0,
                    "errors": [],
                    "created_at": now,
                    "updated_at": now,
                }
                try:
                    await self.batches.insert_one(doc)
                    previous = doc
                except DuplicateKeyError:
                    previous = await self.batches.find_one({"_id": batch_id})
            if previous["actor_id"] != actor_id or previous["window"] != window:
                raise AppError(ErrorCode.CONFLICT)
            return self._response(previous)

    async def get(self, batch_id, actor_id):
        async with quota_storage():
            return self._response(await self._owned(batch_id, actor_id))

    async def latest(self, actor_id, limit=1):
        async with quota_storage():
            cursor = (
                self.batches.find({"actor_id": actor_id})
                .sort([("created_at", -1), ("_id", -1)])
                .limit(max(1, min(limit, 20)))
            )
            return {"items": [self._response(doc) async for doc in cursor]}

    async def _renew(self, batch_id, token):
        now = datetime.now(UTC)
        result = await self.batches.update_one(
            {"_id": batch_id, "lease_token": token, "lease_until": {"$gt": now}},
            {"$set": {"lease_until": now + LEASE_DURATION, "updated_at": now}},
        )
        return bool(result.matched_count)

    async def _prepare(self, doc, token):
        if doc["upper_id"] is None:
            targets = []
        else:
            bounds = {"$lte": doc["upper_id"]}
            if doc["cursor"] is not None:
                bounds["$gt"] = doc["cursor"]
            targets = [
                user
                async for user in self.users.find(
                    {
                        "_id": bounds,
                        "$or": [{"created_at": {"$lte": doc["cutoff"]}}, {"created_at": None}],
                    },
                    {"_id": 1},
                )
                .sort("_id", 1)
                .limit(CHUNK_SIZE)
            ]
        for target in targets:
            if not await self._renew(doc["_id"], token):
                return
            user_id = str(target["_id"])
            now = datetime.now(UTC)
            recipient_id = str(uuid5(UUID(doc["_id"]), user_id))
            await self.recipients.update_one(
                {"_id": recipient_id},
                {
                    "$setOnInsert": {
                        "batch_id": doc["_id"],
                        "user_id": user_id,
                        "source_id": target["_id"],
                        "status": "pending",
                        "operation_id": recipient_id,
                        "created_at": now,
                        "updated_at": now,
                    }
                },
                upsert=True,
            )
        changes: dict = {"updated_at": datetime.now(UTC)}
        if targets:
            changes["cursor"] = targets[-1]["_id"]
        if len(targets) < CHUNK_SIZE:
            changes["status"] = "running"
            changes["total"] = await self.recipients.count_documents({"batch_id": doc["_id"]})
        await self.batches.update_one(
            {"_id": doc["_id"], "lease_token": token, "lease_until": {"$gt": datetime.now(UTC)}},
            {"$set": changes},
        )

    async def _issue(self, doc, token, notified_users):
        cursor = (
            self.recipients.find(
                {"batch_id": doc["_id"], "status": {"$in": ["pending", "issuing"]}}
            )
            .sort("_id", 1)
            .limit(CHUNK_SIZE)
        )
        async for recipient in cursor:
            if not await self._renew(doc["_id"], token):
                return
            now = datetime.now(UTC)
            if recipient["status"] == "pending":
                await self.recipients.update_one(
                    {"_id": recipient["_id"], "status": "pending"},
                    {"$set": {"status": "issuing", "issuing_at": now, "updated_at": now}},
                )
                recipient = await self.recipients.find_one({"_id": recipient["_id"]})
            if recipient["status"] != "issuing":
                continue
            try:
                # An uncertain old grant must not outlive the account's idempotency fence.
                if recipient["issuing_at"] + CARD_LIFETIME + HISTORY_GRACE - LEASE_DURATION <= now:
                    raise AppError(ErrorCode.CONFLICT, message="Issuance retry window expired")
                if not await self.users.find_one({"_id": recipient["source_id"]}, {"_id": 1}):
                    raise AppError(ErrorCode.USER_NOT_FOUND)
                result = await self.resets.issue_card(
                    recipient["user_id"],
                    doc["actor_id"],
                    recipient["operation_id"],
                    window=doc["window"],
                )
                changes = {"status": "issued", "credit_id": result["credit_id"]}
            except AppError as exc:
                if exc.http_status >= 500:
                    raise
                changes = {
                    "status": "failed",
                    "error": {
                        "user_id": recipient["user_id"],
                        "code": exc.error_code.code,
                        "message": exc.message,
                    },
                }
            if not await self._renew(doc["_id"], token):
                return
            updated = await self.recipients.update_one(
                {"_id": recipient["_id"], "status": "issuing"},
                {"$set": {**changes, "updated_at": datetime.now(UTC)}},
            )
            if updated.matched_count and changes["status"] == "issued":
                notified_users.append(recipient["user_id"])

    async def _summarize(self, doc, token):
        counts = {
            item["_id"]: item["count"]
            async for item in await self.recipients.aggregate(
                [
                    {"$match": {"batch_id": doc["_id"]}},
                    {"$group": {"_id": "$status", "count": {"$sum": 1}}},
                ]
            )
        }
        issued, failed = counts.get("issued", 0), counts.get("failed", 0)
        errors = [
            item["error"]
            async for item in self.recipients.find(
                {"batch_id": doc["_id"], "status": "failed"}, {"error": 1}
            )
            .sort([("updated_at", -1), ("_id", -1)])
            .limit(ERROR_SAMPLE_SIZE)
        ]
        changes = {
            "processed": issued + failed,
            "issued": issued,
            "failed": failed,
            "errors": errors,
        }
        current = await self.batches.find_one({"_id": doc["_id"]})
        if current["status"] == "running" and issued + failed == current["total"]:
            changes["status"] = "completed"
        changes["updated_at"] = datetime.now(UTC)
        await self.batches.update_one(
            {"_id": doc["_id"], "lease_token": token, "lease_until": {"$gt": datetime.now(UTC)}},
            {"$set": changes},
        )

    async def advance(self, batch_id, actor_id):
        notified_users: list[str] = []
        try:
            async with quota_storage():
                doc = await self._owned(batch_id, actor_id)
                if doc["status"] == "completed":
                    return self._response(doc)
                token, now = str(uuid4()), datetime.now(UTC)
                claimed = await self.batches.find_one_and_update(
                    {
                        "_id": doc["_id"],
                        "actor_id": actor_id,
                        "status": {"$ne": "completed"},
                        "$or": [
                            {"lease_until": {"$lte": now}},
                            {"lease_until": {"$exists": False}},
                        ],
                    },
                    {"$set": {"lease_token": token, "lease_until": now + LEASE_DURATION}},
                    return_document=ReturnDocument.AFTER,
                )
                if claimed is None:
                    return self._response(await self._owned(batch_id, actor_id))
                try:
                    if claimed["status"] == "preparing":
                        await self._prepare(claimed, token)
                    else:
                        await self._issue(claimed, token, notified_users)
                    await self._summarize(claimed, token)
                finally:
                    await self.batches.update_one(
                        {"_id": doc["_id"], "lease_token": token},
                        {"$unset": {"lease_token": "", "lease_until": ""}},
                    )
                return self._response(await self._owned(batch_id, actor_id))
        finally:
            # Delivery failures must not occupy the issuance lease or its storage deadline.
            try:
                async with asyncio.timeout(2):
                    for user_id in notified_users:
                        await broadcast_quota_changed(user_id)
            except TimeoutError:
                pass
