"""Session-anchor operations for attachment cleanup and trace writer fencing."""

import uuid
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from bson import ObjectId

from src.infra.utils.datetime import utc_now

# A delete fence held longer than this TTL belongs to a delete that died
# mid-flight (process killed before its cancel path ran) and is safe to reclaim.
SESSION_DELETE_FENCE_TTL = timedelta(minutes=10)


class SessionAttachmentOperationsMixin:
    """Attachment lifecycle state composed into the public SessionStorage class."""

    if TYPE_CHECKING:
        collection: Any

        async def ensure_indexes_if_needed(self) -> None: ...

        async def get_by_session_id(self, session_id: str) -> Any: ...

        async def get_by_id(self, session_id: str) -> Any: ...

    async def begin_attachment_clear_operation(
        self,
        session_id: str,
        operation: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Persist one clear operation, or return the operation already in progress."""
        await self.ensure_indexes_if_needed()
        operation_field = "metadata.attachment_clear_operation"
        query = {
            "session_id": session_id,
            "$or": [{operation_field: {"$exists": False}}, {operation_field: None}],
        }
        result = await self.collection.find_one_and_update(
            query,
            {"$set": {operation_field: operation, "updated_at": utc_now()}},
            return_document=True,
        )
        if result:
            return (result.get("metadata") or {}).get("attachment_clear_operation")

        existing = await self.get_by_session_id(session_id)
        if existing is not None:
            return (existing.metadata or {}).get("attachment_clear_operation")

        try:
            object_id = ObjectId(session_id)
        except Exception:
            return None
        result = await self.collection.find_one_and_update(
            {
                "_id": object_id,
                "$or": [{operation_field: {"$exists": False}}, {operation_field: None}],
            },
            {"$set": {operation_field: operation, "updated_at": utc_now()}},
            return_document=True,
        )
        if result:
            return (result.get("metadata") or {}).get("attachment_clear_operation")
        existing = await self.get_by_id(session_id)
        return (existing.metadata or {}).get("attachment_clear_operation") if existing else None

    async def complete_attachment_clear_operation(self, session_id: str, operation_id: str) -> bool:
        """Clear the exact completed operation without overwriting a newer one."""
        await self.ensure_indexes_if_needed()
        field = "attachment_clear_operation"
        query = {
            "session_id": session_id,
            f"{field}.id": operation_id,
        }
        result = await self.collection.update_one(
            query,
            {
                "$unset": {field: ""},
                "$set": {"updated_at": utc_now()},
            },
        )
        if result.modified_count > 0:
            return True
        try:
            result = await self.collection.update_one(
                {
                    "_id": ObjectId(session_id),
                    f"{field}.id": operation_id,
                },
                {
                    "$unset": {field: ""},
                    "$set": {"updated_at": utc_now()},
                },
            )
            return result.modified_count > 0
        except Exception:
            return False

    async def claim_attachment_clear_operation(self, session_id: str) -> dict[str, Any] | None:
        """Atomically create or return server-only attachment clear state."""
        await self.ensure_indexes_if_needed()
        operation = {"id": uuid.uuid4().hex, "cutoff": utc_now()}
        field = "attachment_clear_operation"
        result = await self.collection.find_one_and_update(
            {"session_id": session_id, "$or": [{field: {"$exists": False}}, {field: None}]},
            [
                {
                    "$set": {
                        field: {**operation, "uploaded_by": "$user_id"},
                        "updated_at": utc_now(),
                    }
                }
            ],
            return_document=True,
        )
        if result:
            return result.get(field)
        result = await self.collection.find_one({"session_id": session_id}, {field: 1})
        if result:
            return result.get(field)
        try:
            object_id = ObjectId(session_id)
        except Exception:
            return None
        result = await self.collection.find_one_and_update(
            {"_id": object_id, "$or": [{field: {"$exists": False}}, {field: None}]},
            [{"$set": {field: {**operation, "uploaded_by": "$user_id"}, "updated_at": utc_now()}}],
            return_document=True,
        )
        if result:
            return result.get(field)
        result = await self.collection.find_one({"_id": object_id}, {field: 1})
        return result.get(field) if result else None

    async def persist_attachment_clear_snapshot(
        self,
        session_id: str,
        operation_id: str,
        counts: dict[str, int],
        trace_ids: list[str],
        *,
        parent_ids: list[Any],
        chunk_ids: list[Any],
        groups: dict[str, dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Persist the exact cutoff snapshot before a release can begin."""
        field = "attachment_clear_operation"
        result = await self.collection.find_one_and_update(
            {
                "session_id": session_id,
                f"{field}.id": operation_id,
                f"{field}.counts": {"$exists": False},
            },
            {
                "$set": {
                    f"{field}.counts": counts,
                    f"{field}.trace_ids": trace_ids,
                    f"{field}.parent_ids": parent_ids,
                    f"{field}.chunk_ids": chunk_ids,
                    f"{field}.groups": groups,
                    "updated_at": utc_now(),
                }
            },
            return_document=True,
        )
        if result:
            return result.get(field)
        result = await self.collection.find_one({"session_id": session_id}, {field: 1})
        if result:
            return result.get(field)
        try:
            object_id = ObjectId(session_id)
        except Exception:
            return None
        result = await self.collection.find_one_and_update(
            {
                "_id": object_id,
                f"{field}.id": operation_id,
                f"{field}.counts": {"$exists": False},
            },
            {
                "$set": {
                    f"{field}.counts": counts,
                    f"{field}.trace_ids": trace_ids,
                    f"{field}.parent_ids": parent_ids,
                    f"{field}.chunk_ids": chunk_ids,
                    f"{field}.groups": groups,
                    "updated_at": utc_now(),
                }
            },
            return_document=True,
        )
        if result:
            return result.get(field)
        result = await self.collection.find_one({"_id": object_id}, {field: 1})
        return result.get(field) if result else None

    async def set_attachment_clear_group_status(
        self,
        session_id: str,
        operation_id: str,
        group_id: str,
        *,
        expected_status: str,
        status: str,
    ) -> bool:
        """Persist one group's monotonic clear state transition."""
        field = "attachment_clear_operation"
        group_status = f"{field}.groups.{group_id}.status"

        async def _update(identity: dict[str, Any]) -> bool:
            result = await self.collection.update_one(
                {
                    **identity,
                    f"{field}.id": operation_id,
                    group_status: expected_status,
                },
                {
                    "$set": {
                        group_status: status,
                        "updated_at": utc_now(),
                    }
                },
            )
            return result.modified_count > 0

        if await _update({"session_id": session_id}):
            return True
        try:
            return await _update({"_id": ObjectId(session_id)})
        except Exception:
            return False

    async def acquire_trace_write(self, session_id: str) -> bool:
        """Acquire a session-scoped writer lease unless deletion is fenced."""
        await self.ensure_indexes_if_needed()
        delete_field = "attachment_delete_operation"

        async def _acquire(identity: dict[str, Any]) -> bool:
            result = await self.collection.update_one(
                {**identity, delete_field: {"$exists": False}},
                {
                    "$inc": {"active_trace_writers": 1},
                    "$set": {"updated_at": utc_now()},
                },
            )
            return result.matched_count > 0

        if await _acquire({"session_id": session_id}):
            return True
        try:
            return await _acquire({"_id": ObjectId(session_id)})
        except Exception:
            return False

    async def release_trace_write(self, session_id: str) -> None:
        """Release a writer lease acquired with :meth:`acquire_trace_write`."""

        async def _release(identity: dict[str, Any]) -> bool:
            result = await self.collection.update_one(
                {**identity, "active_trace_writers": {"$gt": 0}},
                {
                    "$inc": {"active_trace_writers": -1},
                    "$set": {"updated_at": utc_now()},
                },
            )
            return result.matched_count > 0

        if await _release({"session_id": session_id}):
            return
        try:
            await _release({"_id": ObjectId(session_id)})
        except Exception:
            return

    async def claim_attachment_delete_operation(self, session_id: str) -> dict[str, Any] | None:
        """Fence new trace writers only when no writer lease is active."""
        await self.ensure_indexes_if_needed()
        field = "attachment_delete_operation"
        operation = {"id": uuid.uuid4().hex, "claimed_at": utc_now()}

        async def _reclaim_stale(
            identity: dict[str, Any], existing_operation: dict[str, Any]
        ) -> dict[str, Any] | None:
            # A fence whose claimant died mid-delete (no cancel ran) would block
            # deletion forever; reclaim it once it is older than the TTL.
            claimed_at = existing_operation.get("claimed_at")
            if claimed_at is None:
                return None
            try:
                from src.infra.utils.datetime import ensure_utc

                claimed_at = ensure_utc(claimed_at)
            except (TypeError, ValueError):
                return None
            if (
                not isinstance(claimed_at, datetime)
                or claimed_at > utc_now() - SESSION_DELETE_FENCE_TTL
            ):
                return None
            result = await self.collection.find_one_and_update(
                {
                    **identity,
                    f"{field}.id": existing_operation.get("id"),
                    f"{field}.claimed_at": claimed_at,
                },
                [
                    {
                        "$set": {
                            field: {**operation, "uploaded_by": "$user_id"},
                            "updated_at": utc_now(),
                        }
                    }
                ],
                return_document=True,
            )
            if result:
                claimed_operation = result.get(field)
                if isinstance(claimed_operation, dict):
                    return {**claimed_operation, "acquired": True}
            return None

        async def _claim(identity: dict[str, Any]) -> dict[str, Any] | None:
            for writer_predicate in (0, {"$exists": False}):
                result = await self.collection.find_one_and_update(
                    {
                        **identity,
                        field: {"$exists": False},
                        "active_trace_writers": writer_predicate,
                    },
                    {"$set": {field: operation, "updated_at": utc_now()}},
                    return_document=True,
                )
                if result:
                    claimed_operation = result.get(field)
                    if isinstance(claimed_operation, dict):
                        return {**claimed_operation, "acquired": True}
                    return None
            result = await self.collection.find_one(identity, {field: 1})
            existing_operation = result.get(field) if result else None
            if isinstance(existing_operation, dict):
                reclaimed = await _reclaim_stale(identity, existing_operation)
                if reclaimed is not None:
                    return reclaimed
                return {**existing_operation, "acquired": False}
            return None

        claimed = await _claim({"session_id": session_id})
        if claimed is not None:
            return claimed
        try:
            return await _claim({"_id": ObjectId(session_id)})
        except Exception:
            return None

    async def cancel_attachment_delete_operation(self, session_id: str, operation_id: str) -> bool:
        """Remove the exact delete fence after a fail-closed refusal."""
        field = "attachment_delete_operation"

        async def _cancel(identity: dict[str, Any]) -> bool:
            result = await self.collection.update_one(
                {**identity, f"{field}.id": operation_id},
                {"$unset": {field: ""}, "$set": {"updated_at": utc_now()}},
            )
            return result.modified_count > 0

        if await _cancel({"session_id": session_id}):
            return True
        try:
            return await _cancel({"_id": ObjectId(session_id)})
        except Exception:
            return False

    async def delete_claimed_session(self, session_id: str, operation_id: str) -> bool:
        """Atomically delete the exact fenced session when all writers are gone."""
        await self.ensure_indexes_if_needed()
        field = "attachment_delete_operation"
        writer_predicate = {
            "$or": [
                {"active_trace_writers": 0},
                {"active_trace_writers": {"$exists": False}},
            ]
        }

        async def _delete(identity: dict[str, Any]) -> bool:
            result = await self.collection.delete_one(
                {
                    **identity,
                    f"{field}.id": operation_id,
                    **writer_predicate,
                }
            )
            return result.deleted_count > 0

        if await _delete({"session_id": session_id}):
            return True
        try:
            return await _delete({"_id": ObjectId(session_id)})
        except Exception:
            return False
