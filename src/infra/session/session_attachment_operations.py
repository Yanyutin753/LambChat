"""Session-anchor operations for attachment cleanup and trace writer fencing."""

import asyncio
import uuid
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from bson import ObjectId

from src.infra.logging import get_logger
from src.infra.session.session_clear_release_operations import SessionClearReleaseOperationsMixin
from src.infra.utils.datetime import utc_now

logger = get_logger(__name__)
TRACE_WRITER_LEASES_FIELD = "trace_writer_leases"
TRACE_WRITER_LEASE_TTL = timedelta(minutes=5)
TRACE_WRITER_HEARTBEAT_INTERVAL_SECONDS = 60.0
TRACE_WRITER_CAS_ATTEMPTS = 5
TRACE_CLEANUP_GUARD_TTL = timedelta(minutes=5)
_DELETE_OPERATION_FIELD = "attachment_delete_operation"
_TRACE_CLEANUP_GUARD_FIELD = "cleanup_guard"
_DELETE_CANCEL_REQUESTED_FIELD = "cancel_requested"
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


def _validated_trace_cleanup_guard(
    operation: dict[str, Any],
) -> tuple[bool, dict[str, Any] | None]:
    raw_guard = operation.get(_TRACE_CLEANUP_GUARD_FIELD, _MISSING)
    if raw_guard is _MISSING:
        return True, None
    if not isinstance(raw_guard, dict):
        return False, None
    guard_id = raw_guard.get("id")
    writer_lease_id = raw_guard.get("writer_lease_id")
    expires_at = raw_guard.get("expires_at")
    if (
        not isinstance(guard_id, str)
        or not guard_id
        or not isinstance(writer_lease_id, str)
        or not writer_lease_id
        or not isinstance(expires_at, datetime)
    ):
        return False, None
    return True, raw_guard


def _validated_delete_cancel_requested(operation: dict[str, Any]) -> bool | None:
    raw_value = operation.get(_DELETE_CANCEL_REQUESTED_FIELD, _MISSING)
    if raw_value is _MISSING:
        return False
    return raw_value if type(raw_value) is bool else None


def _trace_cleanup_guard_is_active(
    guard: dict[str, Any],
    now: datetime,
) -> bool | None:
    try:
        return bool(guard["expires_at"] > now)
    except TypeError:
        return None


def _delete_cancel_snapshot_query(
    operation: dict[str, Any],
) -> object:
    return (
        operation[_DELETE_CANCEL_REQUESTED_FIELD]
        if _DELETE_CANCEL_REQUESTED_FIELD in operation
        else {"$exists": False}
    )


def _trace_cleanup_guard_snapshot_query(
    operation: dict[str, Any],
    guard: dict[str, Any] | None,
) -> dict[str, Any]:
    field = _DELETE_OPERATION_FIELD
    query: dict[str, Any] = {
        f"{field}.id": operation["id"],
        f"{field}.{_DELETE_CANCEL_REQUESTED_FIELD}": _delete_cancel_snapshot_query(operation),
    }
    guard_field = f"{field}.{_TRACE_CLEANUP_GUARD_FIELD}"
    if guard is None:
        query[guard_field] = {"$exists": False}
    else:
        query.update(
            {
                f"{guard_field}.id": guard["id"],
                f"{guard_field}.writer_lease_id": guard["writer_lease_id"],
                f"{guard_field}.expires_at": guard["expires_at"],
            }
        )
    return query


class SessionAttachmentOperationsMixin(SessionClearReleaseOperationsMixin):
    """Attachment lifecycle state composed into the public SessionStorage class."""

    if TYPE_CHECKING:
        collection: Any
        attachment_metadata_collection: Any

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
        owner_token: str | None = None,
        owner_epoch: int | None = None,
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
                    **(
                        {
                            f"{field}.groups.{group_id}.release_owner_token": owner_token,
                            f"{field}.groups.{group_id}.release_owner_epoch": owner_epoch,
                        }
                        if owner_token is not None and owner_epoch is not None
                        else {}
                    ),
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

    def _trace_cleanup_guard_identities(self) -> dict[str, dict[str, Any]]:
        identities = getattr(self, "_active_trace_cleanup_guard_identities", None)
        if identities is None:
            identities = {}
            setattr(self, "_active_trace_cleanup_guard_identities", identities)
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
            self._trace_writer_lease_identities().get(lease_id) if lease_id is not None else None
        )
        if identity is None:
            return await self._resolve_trace_writer_session(session_id)
        document = await self.collection.find_one(identity)
        return (identity, document) if document is not None else None

    async def _load_trace_cleanup_guard_session(
        self,
        session_id: str,
        guard_id: str,
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        identity = self._trace_cleanup_guard_identities().get(guard_id)
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

    async def acquire_trace_cleanup_guard(
        self,
        session_id: str,
        writer_lease_id: str,
    ) -> dict[str, Any] | None:
        """Claim exact cleanup ownership while the pinned session is delete-fenced."""
        if not writer_lease_id:
            return None
        loaded = await self._load_trace_writer_session(
            session_id,
            lease_id=writer_lease_id,
        )
        if loaded is None:
            return {
                "id": None,
                "delete_operation_id": None,
                "session_missing": True,
            }
        identity, document = loaded
        for _attempt in range(TRACE_WRITER_CAS_ATTEMPTS):
            leases = _validated_trace_writer_leases(document)
            operation = document.get(_DELETE_OPERATION_FIELD)
            if (
                leases is None
                or not _legacy_trace_writer_counter_is_safe(document)
                or not isinstance(operation, dict)
            ):
                return None
            operation_id = operation.get("id")
            cancel_requested = _validated_delete_cancel_requested(operation)
            guard_is_valid, existing_guard = _validated_trace_cleanup_guard(operation)
            if (
                not isinstance(operation_id, str)
                or not operation_id
                or cancel_requested is not False
                or not guard_is_valid
            ):
                return None
            now = utc_now()
            if not _all_trace_writer_leases_expired(leases, now):
                return None
            if existing_guard is not None:
                guard_is_active = _trace_cleanup_guard_is_active(existing_guard, now)
                if guard_is_active is not False:
                    return None
            guard_id = uuid.uuid4().hex
            guard = {
                "id": guard_id,
                "writer_lease_id": writer_lease_id,
                "expires_at": now + TRACE_CLEANUP_GUARD_TTL,
            }
            result = await self.collection.update_one(
                {
                    **identity,
                    **_trace_writer_snapshot_query(document),
                    **_trace_cleanup_guard_snapshot_query(operation, existing_guard),
                },
                {
                    "$set": {
                        f"{_DELETE_OPERATION_FIELD}.{_TRACE_CLEANUP_GUARD_FIELD}": guard,
                        "updated_at": utc_now(),
                    }
                },
            )
            if result.matched_count > 0:
                self._trace_cleanup_guard_identities()[guard_id] = identity
                return {
                    **guard,
                    "delete_operation_id": operation_id,
                    "session_missing": False,
                }
            refreshed = await self.collection.find_one(identity)
            if refreshed is None:
                return {
                    "id": None,
                    "delete_operation_id": None,
                    "session_missing": True,
                }
            document = refreshed
        return None

    async def release_trace_cleanup_guard(
        self,
        session_id: str,
        delete_operation_id: str,
        guard_id: str,
    ) -> bool:
        """Release the exact guard and atomically apply any pending fence cancel."""
        if not delete_operation_id or not guard_id:
            return False
        loaded = await self._load_trace_cleanup_guard_session(session_id, guard_id)
        if loaded is None:
            self._trace_cleanup_guard_identities().pop(guard_id, None)
            return False
        identity, document = loaded
        for _attempt in range(TRACE_WRITER_CAS_ATTEMPTS):
            operation = document.get(_DELETE_OPERATION_FIELD)
            if not isinstance(operation, dict) or operation.get("id") != delete_operation_id:
                return False
            cancel_requested = _validated_delete_cancel_requested(operation)
            guard_is_valid, guard = _validated_trace_cleanup_guard(operation)
            if (
                cancel_requested is None
                or not guard_is_valid
                or guard is None
                or guard.get("id") != guard_id
            ):
                return False
            unset_field = (
                _DELETE_OPERATION_FIELD
                if cancel_requested
                else f"{_DELETE_OPERATION_FIELD}.{_TRACE_CLEANUP_GUARD_FIELD}"
            )
            result = await self.collection.update_one(
                {
                    **identity,
                    **_trace_cleanup_guard_snapshot_query(operation, guard),
                },
                {
                    "$unset": {unset_field: ""},
                    "$set": {"updated_at": utc_now()},
                },
            )
            if result.matched_count > 0:
                self._trace_cleanup_guard_identities().pop(guard_id, None)
                return True
            refreshed = await self.collection.find_one(identity)
            if refreshed is None:
                self._trace_cleanup_guard_identities().pop(guard_id, None)
                return False
            document = refreshed
        return False

    async def renew_trace_cleanup_guard(
        self,
        session_id: str,
        delete_operation_id: str,
        guard_id: str,
        writer_lease_id: str,
    ) -> bool:
        """Extend the exact live cleanup guard without reviving stale ownership."""
        if not delete_operation_id or not guard_id or not writer_lease_id:
            return False
        loaded = await self._load_trace_cleanup_guard_session(session_id, guard_id)
        if loaded is None:
            return False
        identity, document = loaded
        for _attempt in range(TRACE_WRITER_CAS_ATTEMPTS):
            operation = document.get(_DELETE_OPERATION_FIELD)
            if not isinstance(operation, dict) or operation.get("id") != delete_operation_id:
                return False
            cancel_requested = _validated_delete_cancel_requested(operation)
            guard_is_valid, guard = _validated_trace_cleanup_guard(operation)
            if (
                cancel_requested is None
                or not guard_is_valid
                or guard is None
                or guard.get("id") != guard_id
                or guard.get("writer_lease_id") != writer_lease_id
            ):
                return False
            now = utc_now()
            if _trace_cleanup_guard_is_active(guard, now) is not True:
                return False
            result = await self.collection.update_one(
                {
                    **identity,
                    **_trace_cleanup_guard_snapshot_query(operation, guard),
                },
                {
                    "$set": {
                        (f"{_DELETE_OPERATION_FIELD}.{_TRACE_CLEANUP_GUARD_FIELD}.expires_at"): now
                        + TRACE_CLEANUP_GUARD_TTL,
                        "updated_at": now,
                    }
                },
            )
            if result.matched_count > 0:
                return True
            refreshed = await self.collection.find_one(identity)
            if refreshed is None:
                return False
            document = refreshed
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
        field = _DELETE_OPERATION_FIELD
        operation = {"id": uuid.uuid4().hex, "claimed_at": utc_now()}

        resolved = await self._resolve_trace_writer_session(session_id)
        if resolved is None:
            return None
        identity, document = resolved
        for _attempt in range(TRACE_WRITER_CAS_ATTEMPTS):
            existing_operation = document.get(field)
            if isinstance(existing_operation, dict):
                cancel_requested = _validated_delete_cancel_requested(existing_operation)
                guard_is_valid, guard = _validated_trace_cleanup_guard(existing_operation)
                if cancel_requested is None or cancel_requested or not guard_is_valid:
                    return None
                if guard is not None:
                    guard_is_active = _trace_cleanup_guard_is_active(guard, utc_now())
                    if guard_is_active is not False:
                        return None
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
        """Cancel exactly, deferring fence removal while cleanup owns a live guard."""
        field = _DELETE_OPERATION_FIELD

        resolved = await self._resolve_trace_writer_session(session_id)
        if resolved is None:
            return False
        identity, document = resolved
        for _attempt in range(TRACE_WRITER_CAS_ATTEMPTS):
            operation = document.get(field)
            if not isinstance(operation, dict) or operation.get("id") != operation_id:
                return False
            cancel_requested = _validated_delete_cancel_requested(operation)
            guard_is_valid, guard = _validated_trace_cleanup_guard(operation)
            if cancel_requested is None or not guard_is_valid:
                return False
            if guard is None:
                if cancel_requested:
                    return False
                update = {
                    "$unset": {field: ""},
                    "$set": {"updated_at": utc_now()},
                }
            else:
                guard_is_active = _trace_cleanup_guard_is_active(guard, utc_now())
                if guard_is_active is None:
                    return False
                if guard_is_active:
                    if cancel_requested:
                        return True
                    update = {
                        "$set": {
                            f"{field}.{_DELETE_CANCEL_REQUESTED_FIELD}": True,
                            "updated_at": utc_now(),
                        }
                    }
                else:
                    update = {
                        "$unset": {field: ""},
                        "$set": {"updated_at": utc_now()},
                    }
            result = await self.collection.update_one(
                {
                    **identity,
                    **_trace_cleanup_guard_snapshot_query(operation, guard),
                },
                update,
            )
            if result.matched_count > 0:
                return True
            refreshed = await self.collection.find_one(identity)
            if refreshed is None:
                return False
            document = refreshed
        return False

    async def delete_claimed_session(self, session_id: str, operation_id: str) -> bool:
        """Atomically delete the exact fenced session when all writers are gone."""
        await self.ensure_indexes_if_needed()
        field = _DELETE_OPERATION_FIELD

        resolved = await self._resolve_trace_writer_session(session_id)
        if resolved is None:
            return False
        identity, document = resolved
        for _attempt in range(TRACE_WRITER_CAS_ATTEMPTS):
            operation = document.get(field)
            leases = _validated_trace_writer_leases(document)
            now = utc_now()
            if not isinstance(operation, dict):
                return False
            cancel_requested = _validated_delete_cancel_requested(operation)
            guard_is_valid, guard = _validated_trace_cleanup_guard(operation)
            if cancel_requested is not False or not guard_is_valid:
                return False
            if guard is not None:
                guard_is_active = _trace_cleanup_guard_is_active(guard, now)
                if guard_is_active is not False:
                    return False
            if (
                operation.get("id") != operation_id
                or not _legacy_trace_writer_counter_is_safe(document)
                or leases is None
                or not _all_trace_writer_leases_expired(leases, now)
            ):
                return False
            result = await self.collection.delete_one(
                {
                    **identity,
                    **_trace_writer_snapshot_query(document),
                    **_trace_cleanup_guard_snapshot_query(operation, guard),
                }
            )
            if result.deleted_count > 0:
                return True
            refreshed = await self.collection.find_one(identity)
            if refreshed is None:
                return False
            document = refreshed
        return False
