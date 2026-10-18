"""Durable per-user USD quotas, independent of trace aggregation and Redis caches."""

from __future__ import annotations

import asyncio
import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from decimal import ROUND_CEILING, Decimal
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from src.kernel.errors import AppError, ErrorCode

UNITS = 1_000_000_000
QUOTA_TIMEZONE = ZoneInfo("Asia/Shanghai")
WINDOW_NAMES = ("five_hour", "weekly")


def usd_units(value: float) -> int:
    return int((Decimal(str(value)) * UNITS).to_integral_value(rounding=ROUND_CEILING))


def quota_windows(now: datetime | None = None) -> list[tuple[str, datetime]]:
    current = (now or datetime.now(UTC)).astimezone(QUOTA_TIMEZONE)
    anchor = current.astimezone(UTC).strftime("%Y%m%d%H%M%S%f")
    return [
        (f"f{anchor}", current + timedelta(hours=5)),
        (f"w{anchor}", current + timedelta(days=7)),
    ]


def resolve_budgets(roles) -> tuple[float | None, float | None]:
    # An unconfigured role must not erase a configured role's quota.
    def maximum(field):
        values = [
            getattr(role.limits, field)
            for role in roles
            if role.limits and getattr(role.limits, field) is not None
        ]
        return max(values) if values else None

    return maximum("five_hour_budget_usd"), maximum("weekly_budget_usd")


@asynccontextmanager
async def quota_storage():
    try:
        async with asyncio.timeout(10):
            yield
    except AppError:
        raise
    except Exception as exc:
        raise AppError(ErrorCode.USAGE_QUOTA_UNAVAILABLE) from exc


async def user_budgets(user_id: str) -> tuple[float | None, float | None]:
    from src.infra.role.storage import RoleStorage
    from src.infra.user.storage import UserStorage
    from src.kernel.schemas.role import RoleLimits

    async with quota_storage():
        user = await UserStorage().get_by_id(user_id)
        if user is None or not user.is_active:
            raise AppError(ErrorCode.UNAUTHORIZED)
        roles = []
        # Optional role caches must not keep a successfully reduced budget unlimited.
        async for doc in RoleStorage().collection.find(
            {"name": {"$in": user.roles}},
            {"name": 1, "limits.five_hour_budget_usd": 1, "limits.weekly_budget_usd": 1},
        ):
            roles.append(
                SimpleNamespace(name=doc["name"], limits=RoleLimits(**(doc.get("limits") or {})))
            )
        if set(user.roles) - {role.name for role in roles}:
            raise AppError(ErrorCode.USAGE_QUOTA_UNAVAILABLE)
        return resolve_budgets(roles)


class UsageQuota:
    def __init__(self, collection: Any = None):
        if collection is None:
            from src.infra.storage.mongodb import get_mongo_client
            from src.kernel.config import settings

            collection = get_mongo_client()[settings.MONGODB_DB]["user_usage_quotas"]
        self.collection = collection

    async def _active_windows(self, user_id: str, now: datetime) -> list[tuple[str, datetime]]:
        updates = {}
        for name, (key, reset) in zip(WINDOW_NAMES, quota_windows(now)):
            previous_reset = {"$ifNull": [f"${name}.reset_at", None]}
            updates[name] = {
                "$cond": [
                    {"$or": [{"$eq": [previous_reset, None]}, {"$lte": [previous_reset, now]}]},
                    {"key": f"{key}_{uuid.uuid4().hex}", "reset_at": reset},
                    f"${name}",
                ]
            }
        async with quota_storage():
            for attempt in range(2):
                try:
                    doc = await self.collection.find_one_and_update(
                        {"_id": user_id},
                        [{"$set": updates}],
                        upsert=True,
                        return_document=ReturnDocument.AFTER,
                        projection={name: 1 for name in WINDOW_NAMES},
                    )
                    return [
                        (doc[name]["key"], doc[name]["reset_at"].astimezone(QUOTA_TIMEZONE))
                        for name in WINDOW_NAMES
                    ]
                except DuplicateKeyError:
                    if attempt:
                        raise
        raise AppError(ErrorCode.USAGE_QUOTA_UNAVAILABLE)

    async def _prune(self, user_id: str, now: datetime) -> None:
        """Bound expired uncertainty without depending on a user opening the quota UI."""
        retained_calls = {
            "$arrayToObject": {
                "$filter": {
                    "input": {"$objectToArray": {"$ifNull": ["$calls", {}]}},
                    "as": "call",
                    "cond": {
                        "$or": [
                            # Legacy tickets have no trustworthy expiry; retain for reconciliation.
                            {"$eq": [{"$ifNull": ["$$call.v.expires_at", None]}, None]},
                            {
                                "$gt": [
                                    "$$call.v.expires_at",
                                    {
                                        "$cond": [
                                            {"$ifNull": ["$$call.v.pending", True]},
                                            now - timedelta(days=7),
                                            now,
                                        ]
                                    },
                                ]
                            },
                        ]
                    },
                }
            }
        }
        held_periods = {
            "$reduce": {
                "input": {"$objectToArray": "$calls"},
                "initialValue": [],
                "in": {"$concatArrays": ["$$value", "$$this.v.periods"]},
            }
        }
        await self.collection.update_one(
            {
                "_id": user_id,
                "$or": [
                    {"cleanup_after": {"$exists": False}},
                    {"cleanup_after": {"$lte": now}},
                ],
            },
            [
                {"$set": {"calls": retained_calls, "cleanup_after": now + timedelta(hours=5)}},
                {
                    "$set": {
                        "periods": {
                            "$arrayToObject": {
                                "$filter": {
                                    "input": {"$objectToArray": {"$ifNull": ["$periods", {}]}},
                                    "as": "period",
                                    "cond": {
                                        "$or": [
                                            {
                                                "$in": [
                                                    "$$period.k",
                                                    ["$five_hour.key", "$weekly.key"],
                                                ]
                                            },
                                            {"$in": ["$$period.k", held_periods]},
                                        ]
                                    },
                                }
                            }
                        }
                    }
                },
            ],
        )

    async def reserve(
        self,
        user_id: str,
        budgets,
        amount_usd: float | None,
        *,
        windows=None,
        now=None,
        context: dict | None = None,
        call_id: str | None = None,
    ) -> dict:
        """Check settled spending in both windows, retrying if a window rotates."""
        current = now or datetime.now(UTC)
        explicit_windows = windows is not None
        amount = usd_units(amount_usd) if amount_usd is not None else 0
        call_id = uuid.UUID(call_id).hex if call_id is not None else uuid.uuid4().hex
        async with quota_storage():
            if explicit_windows:
                try:
                    await self.collection.update_one(
                        {"_id": user_id},
                        {"$setOnInsert": {"periods": {}, "calls": {}}},
                        upsert=True,
                    )
                except DuplicateKeyError:
                    pass
            while True:
                current = now or datetime.now(UTC)
                windows = (
                    windows if explicit_windows else await self._active_windows(user_id, current)
                )
                await self._prune(user_id, current)
                conditions = []
                increments = {}
                for (key, _), budget in zip(windows, budgets):
                    increments[f"periods.{key}.reserved"] = amount
                    if amount_usd is None:
                        increments[f"periods.{key}.unknown"] = 1
                    if budget is None:
                        continue
                    path = f"$periods.{key}"
                    used = {"$ifNull": [f"{path}.used", 0]}
                    # shortcut: in-flight calls may overshoot; use holds again for a hard cap.
                    conditions.append({"$lt": [used, usd_units(budget)]})
                reservation = {
                    "id": call_id,
                    "user_id": user_id,
                    "amount": amount,
                    "periods": [key for key, _ in windows],
                    "created_at": current,
                    "expires_at": max(reset for _, reset in windows),
                    "pending": True,
                    "unknown": amount_usd is None,
                    "context": context or {},
                }
                query: dict = {"_id": user_id, f"calls.{call_id}": {"$exists": False}}
                admission_time = now or datetime.now(UTC)
                if not explicit_windows:
                    for name, (key, _) in zip(WINDOW_NAMES, windows):
                        query[f"{name}.key"] = key
                        query[f"{name}.reset_at"] = {"$gt": admission_time}
                if conditions:
                    query["$expr"] = {"$and": conditions}
                doc = await self.collection.find_one_and_update(
                    query,
                    {"$inc": increments, "$set": {f"calls.{call_id}": reservation}},
                    return_document=ReturnDocument.AFTER,
                    projection={"_id": 1},
                )
                if doc is not None:
                    return reservation
                projection = {name: 1 for name in WINDOW_NAMES}
                projection.update({f"periods.{key}": 1 for key, _ in windows})
                projection[f"calls.{call_id}"] = 1
                latest = await self.collection.find_one({"_id": user_id}, projection) or {}
                if call_id in latest.get("calls", {}):
                    raise AppError(ErrorCode.USAGE_QUOTA_UNAVAILABLE)
                if not explicit_windows and any(
                    latest.get(name, {}).get("key") != key
                    or latest.get(name, {}).get("reset_at") is None
                    or latest[name]["reset_at"] <= admission_time
                    for name, (key, _) in zip(WINDOW_NAMES, windows)
                ):
                    continue
                exhausted = []
                failed_names = []
                for name, (key, reset), budget in zip(WINDOW_NAMES, windows, budgets):
                    if budget is None:
                        continue
                    period = latest.get("periods", {}).get(key, {})
                    if period.get("used", 0) >= usd_units(budget):
                        exhausted.append(reset)
                        failed_names.append(name)
                if not failed_names:
                    continue
                raise AppError(
                    ErrorCode.USAGE_QUOTA_EXCEEDED,
                    args={
                        "reset_at": max(exhausted or [reset for _, reset in windows]).isoformat(),
                        "windows": failed_names,
                        "reason": "exhausted",
                    },
                )

    async def cancel_unstarted(self, user_id: str, call_id: str) -> None:
        """Release a lost acknowledgement only after the caller proves no provider work began."""
        call_id = uuid.UUID(call_id).hex
        async with quota_storage():
            doc = await self.collection.find_one({"_id": user_id}, {f"calls.{call_id}": 1}) or {}
            ticket = doc.get("calls", {}).get(call_id)
            if ticket is not None:
                await self.settle(ticket, 0)

    async def settle(
        self, reservation: dict, cost_usd: float | None, *, partial: bool = False
    ) -> dict | None:
        """Charge reported usage now; a later final receipt only adjusts the difference."""
        call_id, user_id = reservation["id"], reservation["user_id"]
        unknown = partial or cost_usd is None
        previous = reservation
        async with quota_storage():
            while True:
                if previous is None:
                    return
                charged = previous.get("settled_units", 0)
                total = charged if cost_usd is None else usd_units(cost_usd)
                if partial:
                    total = max(charged, total)
                updates: dict = {}
                for key in previous["periods"]:
                    updates[f"periods.{key}.used"] = total - charged
                    updates[f"periods.{key}.unknown"] = int(unknown) - int(
                        previous.get("unknown", False)
                    )
                    if not unknown:
                        updates[f"periods.{key}.reserved"] = -previous["amount"]
                mutation: dict = {"$inc": updates}
                if unknown:
                    mutation["$set"] = {
                        f"calls.{call_id}.unknown": True,
                        f"calls.{call_id}.pending": False,
                        f"calls.{call_id}.settled_units": total,
                    }
                else:
                    mutation["$unset"] = {f"calls.{call_id}": ""}
                result = await self.collection.update_one(
                    {"_id": user_id, f"calls.{call_id}": previous}, mutation
                )
                if result.matched_count:
                    break
                doc = (
                    await self.collection.find_one({"_id": user_id}, {f"calls.{call_id}": 1}) or {}
                )
                previous = doc.get("calls", {}).get(call_id)

        if result.modified_count:
            from src.infra.usage.notifications import broadcast_quota_changed

            await broadcast_quota_changed(user_id)
        return {"charged_units": total, "unknown": unknown}

    async def snapshot(self, user_id: str, budgets, *, now=None) -> dict:
        current = now or datetime.now(UTC)
        async with quota_storage():
            doc = (
                await self.collection.find_one(
                    {"_id": user_id},
                    {
                        "five_hour": 1,
                        "weekly": 1,
                        "periods": {
                            "$arrayToObject": {
                                "$filter": {
                                    "input": {"$objectToArray": {"$ifNull": ["$periods", {}]}},
                                    "as": "period",
                                    "cond": {
                                        "$in": ["$$period.k", ["$five_hour.key", "$weekly.key"]]
                                    },
                                }
                            }
                        },
                    },
                )
                or {}
            )
            windows = []
            for name in WINDOW_NAMES:
                active = doc.get(name, {})
                windows.append(
                    (active["key"], active["reset_at"].astimezone(QUOTA_TIMEZONE))
                    if active.get("reset_at") is not None and active["reset_at"] > current
                    else (None, None)
                )
            periods = doc.get("periods", {})
        result: dict = {"currency": "USD", "timezone": "Asia/Shanghai"}
        for name, (key, reset), limit in zip(WINDOW_NAMES, windows, budgets):
            period = periods.get(key, {})
            used = period.get("used", 0) / UNITS
            reserved = period.get("reserved", 0) / UNITS
            unknown = bool(period.get("unknown", 0))
            result[name] = {
                "limit_usd": limit,
                "used_usd": used,
                "reserved_usd": reserved,
                "remaining_usd": None if limit is None else max(0, limit - used),
                "unknown": unknown,
                "blocked": limit is not None and used >= limit,
                "reset_at": reset.isoformat() if reset is not None else None,
            }
        return result
