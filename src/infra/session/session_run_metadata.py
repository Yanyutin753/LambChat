"""Session metadata updates, including atomic ownership fencing for resumed runs."""

from typing import TYPE_CHECKING, Any

from bson import ObjectId

from src.infra.utils.datetime import utc_now


class SessionRunMetadataMixin:
    if TYPE_CHECKING:
        collection: Any

        async def ensure_indexes_if_needed(self) -> None: ...

        async def _find_doc(
            self, session_id: str, projection: dict[str, Any] | None = None
        ) -> dict[str, Any] | None: ...

    async def update_metadata_only(self, session_id: str, metadata: dict[str, Any]) -> bool:
        """Update session metadata without fetching and rebuilding the full document."""
        await self.ensure_indexes_if_needed()
        if not metadata:
            return True

        update_dict: dict[str, Any] = {"updated_at": utc_now()}
        for key, value in metadata.items():
            update_dict[f"metadata.{key}"] = value

        if "persistent_goal_revision" in metadata:
            document = await self._find_doc(session_id, {"_id": 1})
            if document is None:
                return False
            result = await self.collection.update_one(
                {
                    "_id": document["_id"],
                    "$or": [
                        {"metadata.persistent_goal_revision": {"$exists": False}},
                        {
                            "metadata.persistent_goal_revision": {
                                "$lte": metadata["persistent_goal_revision"]
                            }
                        },
                    ],
                },
                {"$set": update_dict},
            )
            return result.matched_count > 0

        result = await self.collection.update_one(
            {"session_id": session_id},
            {"$set": update_dict},
        )
        if result.matched_count > 0:
            return True

        try:
            result = await self.collection.update_one(
                {"_id": ObjectId(session_id)},
                {"$set": update_dict},
            )
            return result.matched_count > 0
        except Exception:
            return False

    async def update_metadata_for_run(
        self,
        session_id: str,
        run_id: str,
        metadata: dict[str, Any],
        *,
        expected_statuses: list[str] | None = None,
        expected_recovery_token: str | None = None,
    ) -> bool:
        """Apply run metadata only while this exact run still owns the session."""
        await self.ensure_indexes_if_needed()
        document = await self._find_doc(session_id, {"_id": 1})
        if document is None:
            return False
        update = {
            "updated_at": utc_now(),
            **{f"metadata.{key}": value for key, value in metadata.items()},
        }
        predicate = {"_id": document["_id"], "metadata.current_run_id": run_id}
        if expected_statuses is not None:
            predicate["metadata.task_status"] = {"$in": expected_statuses}
        if expected_recovery_token is not None:
            predicate["metadata.recovery_token"] = expected_recovery_token
        result = await self.collection.update_one(
            predicate,
            {"$set": update},
        )
        return result.matched_count > 0

    async def claim_run_recovery(
        self,
        session_id: str,
        run_id: str,
        metadata: dict[str, Any],
        *,
        expected_recovery_token: str | None = None,
    ) -> bool:
        """Claim recovery before touching traces; completion and cancellation win atomically."""
        await self.ensure_indexes_if_needed()
        document = await self._find_doc(session_id, {"_id": 1})
        if document is None:
            return False
        predicate = {
            "_id": document["_id"],
            "metadata.current_run_id": run_id,
            "metadata.verification_required": {"$ne": True},
            "metadata.task_error_code": {"$nin": ["cancelled", "task_recovery_uncertain_effect"]},
            "$or": [
                {
                    "metadata.task_status": {
                        "$in": ["running", "starting", "recovering", "pending", "queued"]
                    }
                },
                {"metadata.task_status": "failed", "metadata.task_recoverable": True},
            ],
        }
        if expected_recovery_token is not None:
            predicate["metadata.recovery_token"] = expected_recovery_token
        result = await self.collection.update_one(
            predicate,
            {
                "$set": {
                    "updated_at": utc_now(),
                    **{f"metadata.{key}": value for key, value in metadata.items()},
                }
            },
        )
        return result.matched_count > 0

    async def mark_all_read(
        self,
        user_id: str,
        project_id: str | None = None,
        scheduled_task_id: str | None = None,
    ) -> int:
        """批量将会话标记为已读（清除未读计数），支持按项目或定时任务过滤。"""
        await self.ensure_indexes_if_needed()
        query: dict[str, Any] = {
            "user_id": user_id,
            "$or": [{"unread_count": {"$gt": 0}}, {"metadata.task_status": "waiting_human"}],
        }
        if project_id:
            query["metadata.project_id"] = project_id
        if scheduled_task_id:
            query["metadata.scheduled_task_id"] = scheduled_task_id
        from src.infra.scheduler.storage import get_scheduled_task_storage

        conversation_modified = await get_scheduled_task_storage().mark_conversation_read(
            scheduled_task_id, user_id
        )
        result = await self.collection.update_many(
            query,
            {"$set": {"unread_count": 0, "last_read_at": utc_now()}},
        )
        return result.modified_count + conversation_modified
