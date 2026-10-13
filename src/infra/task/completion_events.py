"""User-scoped completion journal for reconnect and foreground catch-up."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import NAMESPACE_URL, uuid5

from bson import Timestamp
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError

from src.infra.utils.datetime import utc_now
from src.kernel.errors import AppError, ErrorCode

RETENTION = timedelta(days=30)
_FIELDS = {
    "session_id",
    "run_id",
    "status",
    "notification_kind",
    "parent_session_id",
    "goal_id",
    "goal_version",
    "goal_status",
    "message",
    "unread_count",
    "project_id",
    "scheduled_task_id",
    "is_favorite",
    "dedupe_key",
}


def _aware(value: datetime) -> datetime:
    return (
        value.replace(tzinfo=timezone.utc)
        if value.tzinfo is None
        else value.astimezone(timezone.utc)
    )


def _cursor(document: dict) -> str:
    order = document["commit_order"]
    raw = json.dumps([2, order.time, order.inc]).encode()
    return base64.urlsafe_b64encode(raw).decode()


def _decode_cursor(cursor: str) -> Timestamp:
    try:
        if len(cursor) > 512:
            raise ValueError("Cursor too long")
        version, seconds, increment = json.loads(
            base64.b64decode(cursor, altchars=b"-_", validate=True)
        )
        if version != 2 or type(seconds) is not int or type(increment) is not int:
            raise ValueError("Invalid completion cursor")
        return Timestamp(seconds, increment)
    except (ValueError, TypeError, KeyError) as error:
        raise AppError(ErrorCode.VALIDATION_ERROR) from error


def _public(document: dict) -> dict:
    return {
        **document["data"],
        "id": document["id"],
        "created_at": _aware(document["created_at"]).isoformat(),
    }


def prepare_completion(data: dict, metadata: dict) -> dict | None:
    """Classify the exact run; a historical Goal pointer never captures later chat."""
    result = dict(data)
    goal_run = metadata.get("persistent_goal_run_id") == data["run_id"]
    goal_status = metadata.get("persistent_goal_status") if goal_run else None
    if goal_status in {"paused", "cleared"}:
        return None
    parent = metadata.get("background_parent_session_id")
    if parent:
        result["parent_session_id"] = parent
    if data["status"] == "waiting_human":
        result["notification_kind"] = "waiting_human"
    elif goal_status in {"completed", "blocked", "budget_limited"}:
        result.update(
            status="completed" if goal_status == "completed" else "failed",
            notification_kind="goal_terminal",
            goal_id=metadata["persistent_goal_id"],
            goal_version=metadata.get("persistent_goal_version", 1),
            goal_status=goal_status,
        )
        result["message"] = f"Goal {goal_status.replace('_', ' ')}"
    elif goal_status in {"active", "waiting_human"}:
        return None
    else:
        result["notification_kind"] = "background_task_complete" if parent else "run_complete"
    result["dedupe_key"] = (
        f"goal:{result['goal_id']}:{result['goal_version']}:{goal_status}"
        if result["notification_kind"] == "goal_terminal"
        else f"task:{data['run_id']}:{result['status']}"
    )
    return result


def sanitize_completion(data: dict) -> dict:
    # Arbitrary task errors can contain provider URLs, request text or credentials.
    # Catch-up uses structured status/kind fields instead of persisting those errors.
    return {
        key: value[:1000] if isinstance(value, str) else value
        for key, value in data.items()
        if key in _FIELDS and key != "message" and isinstance(value, (str, int, bool, type(None)))
    }


class TaskCompletionStore:
    def __init__(self, collection: Any = None):
        self._collection = collection
        self._indexed = False

    @property
    def collection(self):
        if self._collection is None:
            from src.infra.storage.mongodb import get_mongo_client
            from src.kernel.config import settings

            self._collection = get_mongo_client()[settings.MONGODB_DB]["task_completions"]
        return self._collection

    async def _ensure_indexes(self) -> None:
        if self._indexed:
            return
        await self.collection.create_index([("user_id", 1), ("id", 1)], unique=True)
        await self.collection.create_index([("user_id", 1), ("commit_order", 1)])
        await self.collection.create_index([("expires_at", 1)], expireAfterSeconds=0)
        self._indexed = True

    async def record(self, user_id: str, data: dict) -> dict:
        event, _ = await self.record_once(user_id, data)
        return event

    async def record_once(self, user_id: str, data: dict) -> tuple[dict, bool]:
        """Insert once; only the insertion owner attempts best-effort live delivery."""
        await self._ensure_indexes()
        clean = sanitize_completion(data)
        identity = str(uuid5(NAMESPACE_URL, f"{user_id}:{clean['dedupe_key']}"))
        query = {"user_id": user_id, "id": identity}
        now = utc_now()
        try:
            document = await self.collection.find_one_and_update(
                {**query, "commit_order": {"$exists": False}},
                {
                    "$setOnInsert": {**query, "data": clean, "expires_at": now + RETENTION},
                    "$currentDate": {"created_at": True, "commit_order": {"$type": "timestamp"}},
                },
                upsert=True,
                return_document=ReturnDocument.AFTER,
            )
            fresh = True
        except DuplicateKeyError:
            document = await self.collection.find_one(query)
            fresh = False
        if document is None:
            raise RuntimeError("Completion event was not persisted")
        return _public(document), fresh

    async def list_for_user(
        self,
        user_id: str,
        *,
        cursor: str | None = None,
        since: datetime | None = None,
        limit: int = 50,
    ) -> dict:
        position = _decode_cursor(cursor) if cursor else None
        await self._ensure_indexes()
        cutoff = utc_now() - RETENTION
        if since is not None:
            cutoff = max(cutoff, _aware(since))
        query: dict[str, Any] = {"user_id": user_id, "created_at": {"$gte": cutoff}}
        if position:
            query["commit_order"] = {"$gt": position}
        limit = min(50, max(1, limit))
        documents = (
            await self.collection.find(query)
            .sort([("commit_order", 1)])
            .limit(limit + 1)
            .to_list(length=limit + 1)
        )
        page = documents[:limit]
        checkpoint = _cursor(page[-1]) if page else cursor
        return {
            "items": [_public(document) for document in page],
            "cursor": checkpoint,
            "next_cursor": checkpoint if len(documents) > limit else None,
        }
