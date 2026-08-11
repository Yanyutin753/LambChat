"""Session-anchor operations for attachment cleanup and trace writer fencing."""

import asyncio
import uuid
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from bson import ObjectId

from src.infra.logging import get_logger
from src.infra.utils.datetime import utc_now

logger = get_logger(__name__)
TRACE_WRITER_LEASES_FIELD = "trace_writer_leases"
TRACE_WRITER_LEASE_TTL = timedelta(minutes=5)
TRACE_WRITER_HEARTBEAT_INTERVAL_SECONDS = 60.0
TRACE_WRITER_CAS_ATTEMPTS = 5
_MISSING = object()


def _legacy_trace_writer_counter_is_safe(document: dict[str, Any]) -> bool:
    """Fail closed until an old scalar counter is explicitly reconciled to zero.

    Operators may set a stranded counter to zero only after confirming that no
    process using the legacy counter protocol can still be writing this session.
    A zero counter is atomically removed when the first identity lease is acquired.
    """
    counter = document.get("active_trace_writers", _MISSING)
    return counter is _MISSING or (type(counter) is int and counter == 0)


def _validated_trace_writer_leases(document: dict[str, Any]) -> list[dict[str, Any]] | None:
    raw_leases = document.get(TRACE_WRITER_LEASES_FIELD, _MISSING)
    if raw_leases is _MISSING:
        return []
    if not isinstance(raw_leases, list):
        return None
    leases: list[dict[str, Any]] = []
    lease_ids: set[str] = set()
    for raw_lease in raw_leases:
        if not isinstance(raw_lease, dict):
            return None
        lease_id = raw_lease.get("id")
        expires_at = raw_lease.get("expires_at")
        if (
            not isinstance(lease_id, str)
            or not lease_id
            or lease_id in lease_ids
            or not isinstance(expires_at, datetime)
        ):
            return None
        lease_ids.add(lease_id)
        leases.append(raw_lease)
    return leases


def _trace_writer_snapshot_query(document: dict[str, Any]) -> dict[str, Any]:
    return {
        "active_trace_writers": (
            document["active_trace_writers"]
            if "active_trace_writers" in document
            else {"$exists": False}
        ),
        TRACE_WRITER_LEASES_FIELD: (
            document[TRACE_WRITER_LEASES_FIELD]
            if TRACE_WRITER_LEASES_FIELD in document
            else {"$exists": False}
        ),
    }


def _all_trace_writer_leases_expired(
    leases: list[dict[str, Any]],
    now: datetime,
) -> bool:
    try:
        return all(lease["expires_at"] <= now for lease in leases)
    except TypeError:
        return False


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

    def _trace_writer_lease_identities(self) -> dict[str, dict[str, Any]]:
        identities = getattr(self, "_active_trace_writer_lease_identities", None)
        if identities is None:
            identities = {}
            setattr(self, "_active_trace_writer_lease_identities", identities)
        return identities

    async def _resolve_trace_writer_session(
        self,
        session_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        """Resolve a custom id first and pin every later CAS to that document's ``_id``."""
        document = await self.collection.find_one({"session_id": session_id})
        if document is not None:
            identity = (
                {"_id": document["_id"]}
                if document.get("_id") is not None
                else {"session_id": session_id}
            )
            return identity, document
        try:
            object_id = ObjectId(session_id)
        except Exception:
            return None
        document = await self.collection.find_one({"_id": object_id})
        return ({"_id": object_id}, document) if document is not None else None

    async def _load_trace_writer_session(
        self,
        session_id: str,
        *,
        lease_id: str | None = None,
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        identity = (
            self._trace_writer_lease_identities().get(lease_id)
            if lease_id is not None
            else None
        )
        if identity is None:
            return await self._resolve_trace_writer_session(session_id)
        document = await self.collection.find_one(identity)
        return (identity, document) if document is not None else None

    def _start_trace_writer_heartbeat(self, session_id: str, lease_id: str) -> None:
        tasks = self._trace_writer_heartbeat_tasks()
        owner = asyncio.current_task()
        task = asyncio.create_task(self._heartbeat_trace_write(session_id, lease_id, owner))
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

    async def _heartbeat_trace_write(
        self,
        session_id: str,
        lease_id: str,
        owner: asyncio.Task[Any] | None,
    ) -> None:
        while True:
            await asyncio.sleep(TRACE_WRITER_HEARTBEAT_INTERVAL_SECONDS)
            try:
                if not await self.renew_trace_write(session_id, lease_id):
                    logger.warning(
                        "Trace writer lease %s for session %s was lost",
                        lease_id,
                        session_id,
                    )
                    if owner is not None and not owner.done():
                        owner.cancel()
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
        resolved = await self._resolve_trace_writer_session(session_id)
        if resolved is None:
            return None
        identity, document = resolved
        for _attempt in range(TRACE_WRITER_CAS_ATTEMPTS):
            leases = _validated_trace_writer_leases(document)
            if (
                not _legacy_trace_writer_counter_is_safe(document)
                or leases is None
                or "attachment_delete_operation" in document
            ):
                return None
            result = await self.collection.update_one(
                {
                    **identity,
                    delete_field: {"$exists": False},
                    **_trace_writer_snapshot_query(document),
                },
                {
                    "$push": {TRACE_WRITER_LEASES_FIELD: lease},
                    "$unset": {"active_trace_writers": ""},
                    "$set": {"updated_at": utc_now()},
                },
            )
            if result.matched_count > 0:
                self._trace_writer_lease_identities()[lease_id] = identity
                self._start_trace_writer_heartbeat(session_id, lease_id)
                return lease_id
            refreshed = await self.collection.find_one(identity)
            if refreshed is None:
                return None
            document = refreshed
        return None

    async def renew_trace_write(self, session_id: str, lease_id: str) -> bool:
        """Extend the exact live lease; an expired lease cannot be revived."""
        loaded = await self._load_trace_writer_session(session_id, lease_id=lease_id)
        if loaded is None:
            return False
        identity, document = loaded
        for _attempt in range(TRACE_WRITER_CAS_ATTEMPTS):
            now = utc_now()
            leases = _validated_trace_writer_leases(document)
            if leases is None or not _legacy_trace_writer_counter_is_safe(document):
                return False
            owned_lease = next((lease for lease in leases if lease["id"] == lease_id), None)
            if owned_lease is None:
                return False
            try:
                if owned_lease["expires_at"] <= now:
                    return False
            except TypeError:
                return False
            result = await self.collection.update_one(
                {
                    **identity,
                    **_trace_writer_snapshot_query(document),
                },
                {
                    "$set": {
                        f"{TRACE_WRITER_LEASES_FIELD}.$[lease].expires_at": (
                            now + TRACE_WRITER_LEASE_TTL
                        ),
                        "updated_at": now,
                    }
                },
                array_filters=[{"lease.id": lease_id}],
            )
            if result.matched_count > 0:
                return True
            refreshed = await self.collection.find_one(identity)
            if refreshed is None:
                return False
            document = refreshed
        return False

    async def validate_trace_write(self, session_id: str, lease_id: str) -> bool:
        """Confirm the exact lease is still live on its originally resolved session anchor."""
        loaded = await self._load_trace_writer_session(session_id, lease_id=lease_id)
        if loaded is None:
            return False
        _identity, document = loaded
        leases = _validated_trace_writer_leases(document)
        if (
            leases is None
            or not _legacy_trace_writer_counter_is_safe(document)
            or "attachment_delete_operation" in document
        ):
            return False
        now = utc_now()
        for lease in leases:
            if lease["id"] != lease_id:
                continue
            try:
                return bool(lease["expires_at"] > now)
            except TypeError:
                return False
        return False

    async def trace_write_session_is_fenced_or_missing(
        self,
        session_id: str,
        lease_id: str,
    ) -> bool:
        """Allow compensation only after the pinned anchor is deleted or delete-fenced."""
        loaded = await self._load_trace_writer_session(session_id, lease_id=lease_id)
        if loaded is None:
            return True
        _identity, document = loaded
        return "attachment_delete_operation" in document

    async def release_trace_write(self, session_id: str, lease_id: str) -> None:
        """Release a writer lease acquired with :meth:`acquire_trace_write`."""
        heartbeat = self._trace_writer_heartbeat_tasks().pop(lease_id, None)
        if heartbeat is not None and heartbeat is not asyncio.current_task():
            heartbeat.cancel()
            try:
                await heartbeat
            except asyncio.CancelledError:
                pass

        loaded = await self._load_trace_writer_session(session_id, lease_id=lease_id)
        if loaded is None:
            self._trace_writer_lease_identities().pop(lease_id, None)
            return
        identity, document = loaded
        for _attempt in range(TRACE_WRITER_CAS_ATTEMPTS):
            leases = _validated_trace_writer_leases(document)
            if leases is None or not any(lease["id"] == lease_id for lease in leases):
                break
            result = await self.collection.update_one(
                {
                    **identity,
                    **_trace_writer_snapshot_query(document),
                },
                {
                    "$pull": {TRACE_WRITER_LEASES_FIELD: {"id": lease_id}},
                    "$set": {"updated_at": utc_now()},
                },
            )
            if result.matched_count > 0:
                break
            refreshed = await self.collection.find_one(identity)
            if refreshed is None:
                break
            document = refreshed
        self._trace_writer_lease_identities().pop(lease_id, None)

    async def claim_attachment_delete_operation(self, session_id: str) -> dict[str, Any] | None:
        """Fence new trace writers only when no writer lease is active."""
        await self.ensure_indexes_if_needed()
        field = "attachment_delete_operation"
        operation = {"id": uuid.uuid4().hex, "claimed_at": utc_now()}

        resolved = await self._resolve_trace_writer_session(session_id)
        if resolved is None:
            return None
        identity, document = resolved
        for _attempt in range(TRACE_WRITER_CAS_ATTEMPTS):
            existing_operation = document.get(field)
            if isinstance(existing_operation, dict):
                return {**existing_operation, "acquired": False}
            if field in document:
                return None
            leases = _validated_trace_writer_leases(document)
            now = utc_now()
            if (
                not _legacy_trace_writer_counter_is_safe(document)
                or leases is None
                or not _all_trace_writer_leases_expired(leases, now)
            ):
                return None
            result = await self.collection.find_one_and_update(
                {
                    **identity,
                    field: {"$exists": False},
                    **_trace_writer_snapshot_query(document),
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
            refreshed = await self.collection.find_one(identity)
            if refreshed is None:
                return None
            document = refreshed
        return None

    async def cancel_attachment_delete_operation(self, session_id: str, operation_id: str) -> bool:
        """Remove the exact delete fence after a fail-closed refusal."""
        field = "attachment_delete_operation"

        resolved = await self._resolve_trace_writer_session(session_id)
        if resolved is None:
            return False
        identity, _document = resolved
        result = await self.collection.update_one(
            {**identity, f"{field}.id": operation_id},
            {"$unset": {field: ""}, "$set": {"updated_at": utc_now()}},
        )
        return result.modified_count > 0

    async def delete_claimed_session(self, session_id: str, operation_id: str) -> bool:
        """Atomically delete the exact fenced session when all writers are gone."""
        await self.ensure_indexes_if_needed()
        field = "attachment_delete_operation"

        resolved = await self._resolve_trace_writer_session(session_id)
        if resolved is None:
            return False
        identity, document = resolved
        for _attempt in range(TRACE_WRITER_CAS_ATTEMPTS):
            operation = document.get(field)
            leases = _validated_trace_writer_leases(document)
            now = utc_now()
            if (
                not isinstance(operation, dict)
                or operation.get("id") != operation_id
                or not _legacy_trace_writer_counter_is_safe(document)
                or leases is None
                or not _all_trace_writer_leases_expired(leases, now)
            ):
                return False
            result = await self.collection.delete_one(
                {
                    **identity,
                    f"{field}.id": operation_id,
                    **_trace_writer_snapshot_query(document),
                }
            )
            if result.deleted_count > 0:
                return True
            refreshed = await self.collection.find_one(identity)
            if refreshed is None:
                return False
            document = refreshed
        return False
