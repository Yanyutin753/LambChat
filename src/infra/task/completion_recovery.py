"""Bounded recovery of completion delivery without re-running any agent work."""

from __future__ import annotations

import logging

from src.infra.task.completion_events import sanitize_completion
from src.infra.task.status import TaskStatus

logger = logging.getLogger(__name__)


class TaskCompletionOutbox:
    def __init__(self, storage=None):
        if storage is None:
            from src.infra.session.storage import SessionStorage

            storage = SessionStorage()
        self.storage = storage

    async def _identity(self, session_id, user_id):
        document = await self.storage._find_doc(session_id, {"_id": 1})
        return {"_id": document["_id"], "user_id": user_id} if document else None

    async def stage(self, session_id, user_id, data):
        identity = await self._identity(session_id, user_id)
        if identity:
            await self.storage.collection.update_one(
                identity,
                {
                    "$addToSet": {"metadata.pending_task_completions": sanitize_completion(data)},
                },
            )

    async def clear(self, session_id, user_id, key):
        identity = await self._identity(session_id, user_id)
        if identity:
            await self.storage.collection.update_one(
                identity,
                {
                    "$pull": {"metadata.pending_task_completions": {"dedupe_key": key}},
                },
            )

    async def pending(self, limit=25):
        limit = min(25, max(1, limit))
        documents = (
            await self.storage.collection.find(
                {"metadata.pending_task_completions.0": {"$exists": True}},
                {"session_id": 1, "user_id": 1, "metadata.pending_task_completions": 1},
            )
            .sort("_id", 1)
            .limit(limit)
            .to_list(length=limit)
        )
        result = []
        for document in documents:
            for data in document["metadata"]["pending_task_completions"]:
                result.append(
                    {
                        "session_id": document.get("session_id") or str(document["_id"]),
                        "user_id": document["user_id"],
                        "data": data,
                    }
                )
                if len(result) == limit:
                    return result
        return result


async def reconcile_pending_completions(*, outbox=None, executor=None, limit=25):
    outbox = outbox or TaskCompletionOutbox()
    try:
        pending = await outbox.pending(min(25, max(1, limit)))
        if not pending:
            return
        if executor is None:
            from src.infra.task.manager import get_task_manager

            executor = get_task_manager()._ensure_executor()
        for item in pending:
            try:
                data = item["data"]
                await executor._send_task_notification(
                    item["session_id"],
                    data["run_id"],
                    TaskStatus(data["status"]),
                    item["user_id"],
                    prepared_completion=data,
                )
            except Exception:
                logger.warning("Completion retry deferred: session=%s", item["session_id"])
    except Exception:
        logger.warning("Completion outbox scan unavailable", exc_info=True)
