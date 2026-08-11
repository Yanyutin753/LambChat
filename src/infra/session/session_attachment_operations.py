"""Session-anchor operations for attachment cleanup and trace writer fencing."""

import asyncio
import uuid
from datetime import timedelta
from typing import TYPE_CHECKING, Any

from bson import ObjectId

from src.infra.logging import get_logger
from src.infra.utils.datetime import utc_now

logger = get_logger(__name__)
TRACE_WRITER_LEASES_FIELD = "trace_writer_leases"
TRACE_WRITER_LEASE_TTL = timedelta(minutes=5)
TRACE_WRITER_HEARTBEAT_INTERVAL_SECONDS = 60.0


def _without_live_trace_writers(now: Any) -> dict[str, Any]:
    """Match sessions whose identity-bearing writer leases are all expired."""
    return {
        "$nor": [
            {
                TRACE_WRITER_LEASES_FIELD: {
                    "$elemMatch": {"expires_at": {"$gt": now}},
                }
            },
            {
                TRACE_WRITER_LEASES_FIELD: {
                    "$elemMatch": {"id": {"$exists": False}},
                }
            },
            {
                TRACE_WRITER_LEASES_FIELD: {
                    "$elemMatch": {"expires_at": {"$exists": False}},
                }
            },
        ]
    }


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

    def _trace_writer_heartbeat_tasks(self) -> dict[str, asyncio.Task[None]]:
        tasks = getattr(self, "_active_trace_writer_heartbeat_tasks", None)
        if tasks is None:
            tasks = {}
            setattr(self, "_active_trace_writer_heartbeat_tasks", tasks)
        return tasks

    def _start_trace_writer_heartbeat(self, session_id: str, lease_id: str) -> None:
        tasks = self._trace_writer_heartbeat_tasks()
        task = asyncio.create_task(self._heartbeat_trace_write(session_id, lease_id))
        tasks[lease_id] = task

        def _completed(completed: asyncio.Task[None]) -> None:
            if tasks.get(lease_id) is completed:
                tasks.pop(lease_id, None)
            if completed.cancelled():
                return
            try:
                completed.exception()
            except asyncio.CancelledError:
                return

        task.add_done_callback(_completed)

    async def _heartbeat_trace_write(self, session_id: str, lease_id: str) -> None:
        while True:
            await asyncio.sleep(TRACE_WRITER_HEARTBEAT_INTERVAL_SECONDS)
            try:
                if not await self.renew_trace_write(session_id, lease_id):
                    logger.warning(
                        "Trace writer lease %s for session %s was lost",
                        lease_id,
                        session_id,
                    )
                    return
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning(
                    "Failed to heartbeat trace writer lease %s for session %s: %s",
                    lease_id,
                    session_id,
                    exc,
                )

    async def acquire_trace_write(self, session_id: str) -> str | None:
        """Acquire an expiring, identity-bearing writer lease unless deletion is fenced."""
        await self.ensure_indexes_if_needed()
        delete_field = "attachment_delete_operation"
        lease_id = uuid.uuid4().hex
        now = utc_now()
        lease = {"id": lease_id, "expires_at": now + TRACE_WRITER_LEASE_TTL}

        async def _acquire(identity: dict[str, Any]) -> bool:
            result = await self.collection.update_one(
                {**identity, delete_field: {"$exists": False}},
                {
                    "$push": {TRACE_WRITER_LEASES_FIELD: lease},
                    "$unset": {"active_trace_writers": ""},
                    "$set": {"updated_at": utc_now()},
                },
            )
            return result.matched_count > 0

        if await _acquire({"session_id": session_id}):
            self._start_trace_writer_heartbeat(session_id, lease_id)
            return lease_id
        try:
            acquired = await _acquire({"_id": ObjectId(session_id)})
        except Exception:
            return None
        if not acquired:
            return None
        self._start_trace_writer_heartbeat(session_id, lease_id)
        return lease_id

    async def renew_trace_write(self, session_id: str, lease_id: str) -> bool:
        """Extend the exact live lease; an expired lease cannot be revived."""
        now = utc_now()
        expires_at = now + TRACE_WRITER_LEASE_TTL

        async def _renew(identity: dict[str, Any]) -> bool:
            result = await self.collection.update_one(
                {
                    **identity,
                    TRACE_WRITER_LEASES_FIELD: {
                        "$elemMatch": {
                            "id": lease_id,
                            "expires_at": {"$gt": now},
                        }
                    },
                },
                {
                    "$set": {
                        f"{TRACE_WRITER_LEASES_FIELD}.$[lease].expires_at": expires_at,
                        "updated_at": now,
                    }
                },
                array_filters=[{"lease.id": lease_id}],
            )
            return result.matched_count > 0

        if await _renew({"session_id": session_id}):
            return True
        try:
            return await _renew({"_id": ObjectId(session_id)})
        except Exception:
            return False

    async def release_trace_write(self, session_id: str, lease_id: str) -> None:
        """Release a writer lease acquired with :meth:`acquire_trace_write`."""
        heartbeat = self._trace_writer_heartbeat_tasks().pop(lease_id, None)
        if heartbeat is not None and heartbeat is not asyncio.current_task():
            heartbeat.cancel()
            try:
                await heartbeat
            except asyncio.CancelledError:
                pass

        async def _release(identity: dict[str, Any]) -> bool:
            result = await self.collection.update_one(
                {
                    **identity,
                    TRACE_WRITER_LEASES_FIELD: {"$elemMatch": {"id": lease_id}},
                },
                {
                    "$pull": {TRACE_WRITER_LEASES_FIELD: {"id": lease_id}},
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

        async def _claim(identity: dict[str, Any]) -> dict[str, Any] | None:
            result = await self.collection.find_one_and_update(
                {
                    **identity,
                    field: {"$exists": False},
                    **_without_live_trace_writers(utc_now()),
                },
                {
                    "$set": {field: operation, "updated_at": utc_now()},
                    "$unset": {"active_trace_writers": ""},
                },
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

        async def _delete(identity: dict[str, Any]) -> bool:
            result = await self.collection.delete_one(
                {
                    **identity,
                    f"{field}.id": operation_id,
                    **_without_live_trace_writers(utc_now()),
                }
            )
            return result.deleted_count > 0

        if await _delete({"session_id": session_id}):
            return True
        try:
            return await _delete({"_id": ObjectId(session_id)})
        except Exception:
            return False
