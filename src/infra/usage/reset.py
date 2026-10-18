"""Account-local reset cards and audited, atomic quota-window rotation."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from pymongo.errors import DuplicateKeyError

from src.infra.usage.quota import WINDOW_NAMES, UsageQuota, quota_storage, usd_units
from src.kernel.errors import AppError, ErrorCode

CARD_LIFETIME = timedelta(days=30)
HISTORY_GRACE = timedelta(days=7)
MAX_AVAILABLE_CARDS = 100
MAX_OPERATIONS = 1000


class QuotaReset:
    def __init__(self, collection=None):
        self.collection = collection if collection is not None else UsageQuota().collection

    @staticmethod
    def _available(cards, now):
        return sorted(
            (
                card
                for card in cards.values()
                if card["status"] == "available" and card["expires_at"] > now
            ),
            key=lambda card: (card["expires_at"], card["id"]),
        )

    async def credits(self, user_id: str, *, now=None) -> dict:
        current = now or datetime.now(UTC)
        async with quota_storage():
            doc = await self.collection.find_one({"_id": user_id}, {"reset_cards": 1}) or {}
        stored = doc.get("reset_cards", {})
        cards = self._available(stored, current)
        return {
            "available_count": len(cards),
            "history": [
                {
                    "id": card["id"],
                    "redeemed_at": card["redeemed_at"],
                    **({"window": card["window"]} if card.get("window") else {}),
                }
                for card in sorted(
                    (
                        card
                        for card in stored.values()
                        if card["status"] == "redeemed"
                        and card["expires_at"] + HISTORY_GRACE > current
                    ),
                    key=lambda card: (card["redeemed_at"], card["id"]),
                    reverse=True,
                )
            ],
            "credits": [
                {
                    **{key: card[key] for key in ("id", "status", "granted_at", "expires_at")},
                    **({"window": card["window"]} if card.get("window") else {}),
                }
                for card in cards
            ],
        }

    async def reset(self, user_id, actor_id, window, operation_id, budgets, *, now=None):
        if window not in WINDOW_NAMES:
            raise AppError(ErrorCode.BAD_REQUEST)
        return await self._mutate(
            user_id, actor_id, "reset", operation_id, budgets, window=window, now=now
        )

    async def issue_card(self, user_id, actor_id, operation_id, *, window=None, now=None):
        if window is not None and window not in WINDOW_NAMES:
            raise AppError(ErrorCode.BAD_REQUEST)
        return await self._mutate(user_id, actor_id, "issue", operation_id, window=window, now=now)

    async def consume(self, user_id, operation_id, budgets, *, credit_id=None, now=None):
        return await self._mutate(
            user_id, user_id, "consume", operation_id, budgets, credit_id=credit_id, now=now
        )

    async def _mutate(
        self,
        user_id,
        actor_id,
        kind,
        operation_id,
        budgets=None,
        *,
        window=None,
        credit_id=None,
        now=None,
    ):
        try:
            operation_id = str(uuid.UUID(str(operation_id)))
        except (ValueError, TypeError, AttributeError) as exc:
            raise AppError(ErrorCode.BAD_REQUEST) from exc
        request = {"kind": kind, "actor_id": actor_id, "window": window, "credit_id": credit_id}
        async with quota_storage():
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
                doc = await self.collection.find_one(
                    {"_id": user_id},
                    {
                        **dict.fromkeys(WINDOW_NAMES, 1),
                        "reset_cards": 1,
                        "reset_operations": 1,
                        "reset_revision": 1,
                    },
                )
                operations = doc.get("reset_operations", {})
                if previous := operations.get(operation_id):
                    if previous["request"] != request:
                        raise AppError(ErrorCode.CONFLICT)
                    result = dict(previous["result"])
                    result["outcome"] = {"reset": "alreadyRedeemed", "issued": "alreadyIssued"}.get(
                        result["outcome"], result["outcome"]
                    )
                    return result
                cards = doc.get("reset_cards", {})
                stale = {
                    **{
                        f"reset_cards.{key}": ""
                        for key, card in cards.items()
                        if card["expires_at"] + HISTORY_GRACE <= current
                    },
                    **{
                        f"reset_operations.{key}": ""
                        for key, operation in operations.items()
                        if operation["expires_at"] <= current
                    },
                }
                if (
                    len(operations) - sum(key.startswith("reset_operations.") for key in stale)
                    >= MAX_OPERATIONS
                ):
                    raise AppError(ErrorCode.CONFLICT)
                available = self._available(cards, current)
                updates = {}
                scope = []
                periods = {}
                active = {}
                if kind == "issue":
                    if len(available) >= MAX_AVAILABLE_CARDS:
                        raise AppError(ErrorCode.CONFLICT)
                    issued_id = uuid.uuid4().hex
                    updates[f"reset_cards.{issued_id}"] = {
                        "id": issued_id,
                        "status": "available",
                        "granted_at": current,
                        "expires_at": current + CARD_LIFETIME,
                        "granted_by": actor_id,
                        **({"window": window} if window else {}),
                    }
                    result = {"outcome": "issued", "credit_id": issued_id}
                else:
                    selected = (
                        cards.get(credit_id) if credit_id else (available[0] if available else None)
                    )
                    card_window = selected.get("window") if selected else None
                    active = {
                        name: anchor
                        for name in WINDOW_NAMES
                        if (anchor := doc.get(name))
                        and anchor.get("reset_at") is not None
                        and anchor["reset_at"] > current
                    }
                    if active:
                        observed = await self.collection.find_one(
                            {"_id": user_id},
                            {f"periods.{anchor['key']}": 1 for anchor in active.values()},
                        )
                        periods = observed.get("periods", {})
                    for name, limit in zip(WINDOW_NAMES, budgets):
                        if limit is None or limit <= 0 or name not in active:
                            continue
                        period = periods.get(active[name]["key"], {})
                        used, unknown = period.get("used", 0), period.get("unknown", 0)
                        if (
                            kind == "reset"
                            and name == window
                            and (used > 0 or unknown)
                            or kind == "consume"
                            and (card_window is None or name == card_window)
                            and (used > 0 if card_window else used >= usd_units(limit))
                        ):
                            scope.append(name)
                    if kind == "consume" and (
                        selected is None or selected["expires_at"] <= current
                    ):
                        result, scope = {"outcome": "noCredit"}, []
                    elif (
                        kind == "consume"
                        and selected is not None
                        and selected["status"] != "available"
                    ):
                        result, scope = (
                            {"outcome": "alreadyRedeemed", "credit_id": selected["id"]},
                            [],
                        )
                    elif not scope:
                        result = {"outcome": "nothingToReset"}
                    else:
                        # A weekly reset restores both pools, preserving old in-flight receipts.
                        if "weekly" in scope:
                            scope = list(WINDOW_NAMES)
                        result = {"outcome": "reset", "windows": scope}
                        for name in scope:
                            prefix = "f" if name == "five_hour" else "w"
                            updates[name] = {
                                "key": f"{prefix}{current.strftime('%Y%m%d%H%M%S%f')}_{uuid.uuid4().hex}",
                                "reset_at": current
                                + (
                                    timedelta(hours=5) if name == "five_hour" else timedelta(days=7)
                                ),
                            }
                        if kind == "consume":
                            assert selected is not None
                            result["credit_id"] = selected["id"]
                            updates[f"reset_cards.{selected['id']}"] = {
                                **selected,
                                "status": "redeemed",
                                "redeemed_at": current,
                                "operation_id": operation_id,
                            }
                updates[f"reset_operations.{operation_id}"] = {
                    "actor_id": actor_id,
                    "user_id": user_id,
                    "scope": scope,
                    "created_at": current,
                    "expires_at": current + CARD_LIFETIME + HISTORY_GRACE,
                    "request": request,
                    "result": result,
                }
                query = {
                    "_id": user_id,
                    "reset_revision": doc.get("reset_revision", {"$exists": False}),
                    **{name: doc.get(name) for name in WINDOW_NAMES},
                    **{
                        f"periods.{anchor['key']}": periods.get(anchor["key"], {"$exists": False})
                        for anchor in active.values()
                    },
                }
                if scope and now is None:
                    deadlines = [active[name]["reset_at"] for name in scope if name in active]
                    if kind == "consume":
                        assert selected is not None
                        deadlines.append(selected["expires_at"])
                    if deadlines and min(deadlines) <= datetime.now(UTC):
                        continue
                mutation = {"$set": updates, "$inc": {"reset_revision": 1}}
                if stale:
                    mutation["$unset"] = stale
                changed = await self.collection.update_one(query, mutation)
                if changed.matched_count:
                    return result
