from __future__ import annotations

import asyncio
from collections import Counter
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest
from bson import ObjectId

from src.infra.session.manager import SessionManager
from src.infra.session.storage import SessionStorage
from src.infra.session.trace_storage import TraceStorage
from src.kernel.exceptions import SessionError

_MISSING = object()


def _get_nested(document: dict[str, Any], dotted_key: str) -> object:
    value: object = document
    for part in dotted_key.split("."):
        if not isinstance(value, dict) or part not in value:
            return _MISSING
        value = value[part]
    return value


def _set_nested(document: dict[str, Any], dotted_key: str, value: object) -> None:
    parts = dotted_key.split(".")
    target = document
    for part in parts[:-1]:
        nested = target.get(part)
        if not isinstance(nested, dict):
            nested = {}
            target[part] = nested
        target = nested
    target[parts[-1]] = deepcopy(value)


def _unset_nested(document: dict[str, Any], dotted_key: str) -> None:
    parts = dotted_key.split(".")
    target = document
    for part in parts[:-1]:
        nested = target.get(part)
        if not isinstance(nested, dict):
            return
        target = nested
    target.pop(parts[-1], None)


def _matches(document: dict[str, Any], query: dict[str, Any]) -> bool:
    for key, expected in query.items():
        if key == "$or":
            if not any(_matches(document, clause) for clause in expected):
                return False
            continue
        if key == "$nor":
            if any(_matches(document, clause) for clause in expected):
                return False
            continue

        actual = _get_nested(document, key)
        if isinstance(expected, dict):
            for operator, operand in expected.items():
                if operator == "$exists":
                    if (actual is not _MISSING) is not bool(operand):
                        return False
                elif operator == "$in":
                    if actual is _MISSING or actual not in operand:
                        return False
                elif operator == "$ne":
                    if actual is not _MISSING and actual == operand:
                        return False
                elif operator == "$lte":
                    if actual is _MISSING or actual > operand:
                        return False
                elif operator == "$gt":
                    if actual is _MISSING:
                        return False
                    try:
                        if actual <= operand:
                            return False
                    except TypeError:
                        # Mongo comparisons are type bracketed; a value with the
                        # wrong BSON type does not satisfy a date comparison.
                        return False
                elif operator == "$elemMatch":
                    if not isinstance(actual, list) or not any(
                        isinstance(item, dict) and _matches(item, operand) for item in actual
                    ):
                        return False
                else:
                    raise AssertionError(f"Unsupported query operator: {operator}")
            continue

        if actual is _MISSING or actual != expected:
            return False
    return True


def _project(document: dict[str, Any], projection: dict[str, int] | None) -> dict[str, Any]:
    if not projection or not any(value for value in projection.values()):
        return deepcopy(document)
    projected: dict[str, Any] = {}
    for key, included in projection.items():
        value = _get_nested(document, key)
        if included and value is not _MISSING:
            _set_nested(projected, key, value)
    return projected


def _resolve_update_value(value: object, document: dict[str, Any]) -> object:
    if isinstance(value, str) and value.startswith("$"):
        resolved = _get_nested(document, value[1:])
        return None if resolved is _MISSING else deepcopy(resolved)
    if isinstance(value, dict):
        return {key: _resolve_update_value(item, document) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_update_value(item, document) for item in value]
    return deepcopy(value)


def _apply_update(document: dict[str, Any], update: dict | list[dict]) -> None:
    stages = update if isinstance(update, list) else [update]
    for stage in stages:
        for key, value in stage.get("$inc", {}).items():
            current = _get_nested(document, key)
            if current is _MISSING:
                current = 0
            _set_nested(document, key, current + value)
        for key, value in stage.get("$set", {}).items():
            _set_nested(document, key, _resolve_update_value(value, document))
        for key in stage.get("$unset", {}):
            _unset_nested(document, key)
        for key, value in stage.get("$push", {}).items():
            current = _get_nested(document, key)
            items = [] if current is _MISSING else list(current)
            items.append(deepcopy(value))
            _set_nested(document, key, items)
        for key, value in stage.get("$pull", {}).items():
            current = _get_nested(document, key)
            if not isinstance(current, list):
                continue
            _set_nested(
                document,
                key,
                [
                    item
                    for item in current
                    if not (isinstance(item, dict) and _matches(item, value))
                ],
            )


class _FilterAwareCursor:
    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self.documents = documents
        self.limit_value: int | None = None

    def sort(self, field: str, direction: int):
        self.documents.sort(key=lambda document: document.get(field), reverse=direction < 0)
        return self

    def limit(self, value: int):
        self.limit_value = value
        return self

    def __aiter__(self):
        documents = self.documents
        if self.limit_value is not None:
            documents = documents[: self.limit_value]

        async def _iterate():
            for document in documents:
                yield deepcopy(document)

        return _iterate()

    async def to_list(self, length: int | None = None) -> list[dict[str, Any]]:
        limit = self.limit_value if self.limit_value is not None else length
        documents = self.documents if limit is None else self.documents[:limit]
        return deepcopy(documents)


class _FilterAwareCollection:
    def __init__(self, documents: list[dict[str, Any]]) -> None:
        self.documents = deepcopy(documents)
        self.find_calls: list[dict[str, Any]] = []
        self.find_one_calls: list[dict[str, Any]] = []
        self.delete_calls: list[dict[str, Any]] = []
        self.skip_delete_once: set[object] = set()
        self.fail_delete_once: set[object] = set()

    def find(self, query: dict[str, Any], projection: dict[str, int] | None = None):
        self.find_calls.append(deepcopy(query))
        return _FilterAwareCursor(
            [
                _project(document, projection)
                for document in self.documents
                if _matches(document, query)
            ]
        )

    async def find_one(
        self, query: dict[str, Any], projection: dict[str, int] | None = None
    ) -> dict[str, Any] | None:
        self.find_one_calls.append(deepcopy(query))
        return next(
            (
                _project(document, projection)
                for document in self.documents
                if _matches(document, query)
            ),
            None,
        )

    async def find_one_and_update(
        self, query: dict[str, Any], update: dict | list[dict], **_kwargs
    ) -> dict[str, Any] | None:
        for document in self.documents:
            if _matches(document, query):
                _apply_update(document, update)
                return deepcopy(document)
        return None

    async def update_one(self, query: dict[str, Any], update: dict, **kwargs):
        for document in self.documents:
            if _matches(document, query):
                before = deepcopy(document)
                array_filters = kwargs.get("array_filters") or []
                if array_filters and "$set" in update:
                    positional_updates = {
                        key: value for key, value in update["$set"].items() if ".$[lease]." in key
                    }
                    ordinary_update = deepcopy(update)
                    ordinary_update["$set"] = {
                        key: value
                        for key, value in ordinary_update["$set"].items()
                        if key not in positional_updates
                    }
                    _apply_update(document, ordinary_update)
                    lease_id = array_filters[0]["lease.id"]
                    for lease in document.get("trace_writer_leases", []):
                        if lease.get("id") != lease_id:
                            continue
                        for key, value in positional_updates.items():
                            field = key.split(".$[lease].", 1)[1]
                            _set_nested(lease, field, value)
                else:
                    _apply_update(document, update)
                return SimpleNamespace(
                    matched_count=1,
                    modified_count=int(document != before),
                )
        return SimpleNamespace(matched_count=0, modified_count=0)

    async def insert_one(self, document: dict[str, Any]):
        self.documents.append(deepcopy(document))
        return SimpleNamespace(inserted_id=document.get("_id", "inserted"))

    async def insert_many(self, documents: list[dict[str, Any]]):
        self.documents.extend(deepcopy(documents))
        return SimpleNamespace(inserted_ids=[doc.get("_id") for doc in documents])

    async def delete_one(self, query: dict[str, Any]):
        result = await self.delete_many(query)
        return SimpleNamespace(deleted_count=min(result.deleted_count, 1))

    async def delete_many(self, query: dict[str, Any]):
        self.delete_calls.append(deepcopy(query))
        kept: list[dict[str, Any]] = []
        deleted_count = 0
        skipped: set[object] = set()
        for index, document in enumerate(self.documents):
            document_id = document.get("_id")
            if _matches(document, query) and document_id in self.fail_delete_once:
                self.fail_delete_once.remove(document_id)
                self.documents = kept + deepcopy(self.documents[index:])
                raise RuntimeError(f"delete failed for {document_id}")
            if _matches(document, query) and document_id not in self.skip_delete_once:
                deleted_count += 1
                continue
            if _matches(document, query) and document_id in self.skip_delete_once:
                skipped.add(document_id)
            kept.append(document)
        self.skip_delete_once.difference_update(skipped)
        self.documents = kept
        return SimpleNamespace(deleted_count=deleted_count)

    def ids(self) -> set[object]:
        return {document["_id"] for document in self.documents}


class _ReleaseEpochMetadata:
    def __init__(self, *, lose_replies: int = 0) -> None:
        self.epoch = 0
        self.lose_replies = lose_replies

    async def update_one(self, _query: dict, update: dict, **_kwargs):
        self.epoch = max(self.epoch, int(update["$max"]["epoch"]))
        return SimpleNamespace(modified_count=1)

    async def find_one_and_update(self, _query: dict, update: dict, **_kwargs):
        self.epoch += int(update["$inc"]["epoch"])
        if self.lose_replies:
            self.lose_replies -= 1
            raise ConnectionError("release epoch reply lost")
        return {"epoch": self.epoch}


class _FileRecordStorage:
    def __init__(self) -> None:
        self.released_counts: list[Counter[str]] = []
        self.operation_ids: list[str] = []
        self.applied_operation_ids: set[str] = set()
        self.release_error: Exception | None = None
        self.forget_error: Exception | None = None
        self.forgot_operation_ids: list[str] = []
        self.live_operations: dict[str, tuple[int, bool]] = {}

    async def adopt_release_operation_epoch(
        self,
        _keys: list[str],
        *,
        operation_id: str,
        owner_epoch: int,
        uploaded_by: str,
    ) -> bool:
        assert uploaded_by == "owner-a"
        current = self.live_operations.get(operation_id)
        if current is not None and current[0] > owner_epoch:
            return False
        self.live_operations[operation_id] = (
            owner_epoch,
            current[1] if current is not None else operation_id in self.applied_operation_ids,
        )
        return True

    async def release_reference_counts(
        self,
        counts: Counter[str],
        *,
        operation_id: str,
        uploaded_by: str,
        owner_epoch: int,
    ) -> int:
        assert uploaded_by == "owner-a"
        if self.release_error:
            raise self.release_error
        self.operation_ids.append(operation_id)
        operation = self.live_operations.get(operation_id)
        if operation != (owner_epoch, False):
            return 0
        self.applied_operation_ids.add(operation_id)
        self.live_operations[operation_id] = (owner_epoch, True)
        self.released_counts.append(counts)
        return len(counts)

    async def forget_release_operation(
        self,
        keys: object,
        *,
        operation_id: str,
        owner_epoch: int,
        uploaded_by: str,
    ) -> bool:
        assert uploaded_by == "owner-a"
        if self.forget_error:
            raise self.forget_error
        if self.live_operations.get(operation_id) == (owner_epoch, True):
            self.live_operations.pop(operation_id)
            self.applied_operation_ids.discard(operation_id)
        self.forgot_operation_ids.append(operation_id)
        return True


class _TraceStorage:
    def __init__(self) -> None:
        self.get_session_events_calls: list[tuple[str, dict]] = []
        self.deleted_session_ids: list[str] = []
        self.events: list[dict] = []
        self.read_error: Exception | None = None
        self.delete_error: Exception | None = None

    async def get_session_events(self, _session_id: str, **kwargs) -> list[dict]:
        self.get_session_events_calls.append((_session_id, kwargs))
        return self.events

    async def iter_session_events_for_cleanup(self, _session_id: str, **kwargs):
        if self.read_error:
            raise self.read_error
        for event in self.events:
            yield event

    async def snapshot_session_traces_for_cleanup(self, session_id: str, _cutoff: object) -> dict:
        if self.read_error:
            raise self.read_error
        self.snapshot_session_id = session_id
        trace_ids = sorted(
            {str(event["trace_id"]) for event in self.events if event.get("trace_id")}
        )
        groups = (
            [
                {
                    "id": "parent-0",
                    "kind": "parent",
                    "document_id": "snapshot-parent",
                    "trace_id": trace_ids[0] if trace_ids else "trace-fixture",
                    "updated_at": "snapshot-version",
                    "terminal_status": "completed",
                    "events": deepcopy(self.events),
                }
            ]
            if self.events
            else []
        )
        return {
            "events": deepcopy(self.events),
            "trace_ids": trace_ids,
            "parent_ids": ["snapshot-parent"] if self.events else [],
            "chunk_ids": [],
            "groups": groups,
        }

    async def delete_attachment_clear_group(self, _session_id: str, _group: dict) -> str:
        if self.delete_error:
            raise self.delete_error
        self.deleted_session_ids.append(self.snapshot_session_id)
        self.events = []
        return "deleted"

    async def has_session_trace_documents(self, _session_id: str) -> bool:
        return bool(self.events)

    async def delete_session_traces_strict(self, session_id: str, **_kwargs) -> int:
        if self.delete_error:
            raise self.delete_error
        self.deleted_session_ids.append(session_id)
        return 0


class _SessionOperationStorage:
    def __init__(self) -> None:
        self.metadata: dict = {}
        self.metadata_updates: list[dict] = []
        self.server_operation: dict | None = None
        self.operation_number = 0
        self.delete_operation: dict | None = None
        self.release_epoch = 0

    async def get_by_session_id(self, session_id: str):
        return SimpleNamespace(id=session_id, metadata=self.metadata.copy())

    async def get_by_id(self, _session_id: str):
        return None

    async def update_metadata_only(self, _session_id: str, metadata: dict) -> bool:
        self.metadata.update(metadata)
        self.metadata_updates.append(metadata)
        return True

    async def claim_attachment_clear_operation(self, _session_id: str) -> dict:
        if self.server_operation is None:
            self.operation_number += 1
            self.server_operation = {
                "id": f"server-operation-{self.operation_number}",
                "cutoff": f"cutoff-{self.operation_number}",
                "uploaded_by": "owner-a",
            }
        return self.server_operation

    async def claim_attachment_delete_operation(self, _session_id: str) -> dict:
        if self.delete_operation is None:
            self.delete_operation = {"id": "delete-operation-1"}
            return {**self.delete_operation, "acquired": True}
        return {**self.delete_operation, "acquired": False}

    async def cancel_attachment_delete_operation(self, _session_id: str, operation_id: str) -> bool:
        if not self.delete_operation or self.delete_operation.get("id") != operation_id:
            return False
        self.delete_operation = None
        return True

    async def delete_claimed_session(self, session_id: str, operation_id: str) -> bool:
        if not self.delete_operation or self.delete_operation.get("id") != operation_id:
            return False
        return await self.delete(session_id)

    async def delete(self, _session_id: str) -> bool:
        self.delete_operation = None
        return True

    async def persist_attachment_clear_snapshot(
        self,
        _session_id: str,
        operation_id: str,
        counts: dict,
        trace_ids: list[str],
        *,
        parent_ids: list,
        chunk_ids: list,
        groups: dict,
    ) -> dict:
        assert self.server_operation and operation_id == self.server_operation["id"]
        self.server_operation.setdefault("counts", counts)
        self.server_operation.setdefault("trace_ids", trace_ids)
        self.server_operation.setdefault("parent_ids", parent_ids)
        self.server_operation.setdefault("chunk_ids", chunk_ids)
        self.server_operation.setdefault("groups", groups)
        return self.server_operation

    async def set_attachment_clear_group_status(
        self,
        _session_id: str,
        operation_id: str,
        group_id: str,
        *,
        expected_status: str,
        status: str,
        owner_token: str | None = None,
        owner_epoch: int | None = None,
    ) -> bool:
        assert self.server_operation and operation_id == self.server_operation["id"]
        group = self.server_operation["groups"][group_id]
        if group["status"] != expected_status:
            return False
        if owner_token is not None and (
            group.get("release_owner_token") != owner_token
            or group.get("release_owner_epoch") != owner_epoch
        ):
            return False
        group["status"] = status
        return True

    async def claim_attachment_clear_group_release(
        self,
        _session_id: str,
        operation_id: str,
        group_id: str,
        owner_token: str,
    ) -> dict | None:
        assert self.server_operation and self.server_operation["id"] == operation_id
        group = self.server_operation["groups"][group_id]
        if group.get("status") not in {"deleted", "releasing"}:
            return None
        if group.get("release_owner_token") == owner_token:
            return {"token": owner_token, "epoch": group["release_owner_epoch"]}
        self.release_epoch += 1
        group.update(
            {
                "status": "releasing",
                "release_owner_token": owner_token,
                "release_owner_epoch": self.release_epoch,
            }
        )
        return {"token": owner_token, "epoch": self.release_epoch}

    async def renew_attachment_clear_group_release(self, *_args, **_kwargs) -> bool:
        return True

    async def complete_attachment_clear_operation(
        self, _session_id: str, operation_id: str
    ) -> bool:
        pending = self.server_operation
        if pending is None or pending.get("id") != operation_id:
            return False
        self.server_operation = None
        return True


class _ExactSessionOperationStorage(_SessionOperationStorage):
    def __init__(self, cutoff: datetime) -> None:
        super().__init__()
        self.cutoff = cutoff

    async def claim_attachment_clear_operation(self, _session_id: str) -> dict:
        if self.server_operation is None:
            self.operation_number += 1
            self.server_operation = {
                "id": f"server-operation-{self.operation_number}",
                "cutoff": self.cutoff,
                "uploaded_by": "owner-a",
            }
        return self.server_operation

    async def persist_attachment_clear_snapshot(
        self,
        _session_id: str,
        operation_id: str,
        counts: dict,
        trace_ids: list[str],
        *,
        parent_ids: list,
        chunk_ids: list,
        groups: dict,
    ) -> dict:
        assert self.server_operation and operation_id == self.server_operation["id"]
        self.server_operation.update(
            {
                "counts": counts,
                "trace_ids": trace_ids,
                "parent_ids": parent_ids,
                "chunk_ids": chunk_ids,
                "groups": groups,
            }
        )
        return self.server_operation


def _trace_storage_with_documents(
    parents: list[dict[str, Any]], chunks: list[dict[str, Any]]
) -> tuple[TraceStorage, _FilterAwareCollection, _FilterAwareCollection]:
    trace_storage = TraceStorage()
    parent_collection = _FilterAwareCollection(parents)
    chunks_collection = _FilterAwareCollection(chunks)
    trace_storage._collection = parent_collection
    trace_storage._chunks_collection = chunks_collection
    return trace_storage, parent_collection, chunks_collection


@pytest.mark.asyncio
async def test_strict_trace_delete_removes_and_verifies_orphaned_session_chunks() -> None:
    class _Cursor:
        def __init__(self, docs: list[dict]) -> None:
            self.docs = docs

        async def to_list(self, *, length):
            del length
            return [doc.copy() for doc in self.docs]

    class _Collection:
        def __init__(self, docs: list[dict]) -> None:
            self.docs = docs

        def find(self, query: dict, _projection: dict):
            return _Cursor(
                [doc for doc in self.docs if doc.get("session_id") == query["session_id"]]
            )

        async def delete_many(self, query: dict):
            before = len(self.docs)
            self.docs = [doc for doc in self.docs if doc.get("session_id") != query["session_id"]]
            return SimpleNamespace(deleted_count=before - len(self.docs))

        async def find_one(self, query: dict, _projection: dict):
            return next(
                (doc.copy() for doc in self.docs if doc.get("session_id") == query["session_id"]),
                None,
            )

    class _ChunksCollection(_Collection):
        async def delete_many(self, query: dict):
            before = len(self.docs)
            if "trace_id" in query:
                trace_ids = set(query["trace_id"]["$in"])
                self.docs = [doc for doc in self.docs if doc.get("trace_id") not in trace_ids]
            else:
                self.docs = [
                    doc for doc in self.docs if doc.get("session_id") != query["session_id"]
                ]
            return SimpleNamespace(deleted_count=before - len(self.docs))

    storage = TraceStorage()
    storage._collection = _Collection(
        [
            {"session_id": "session-1", "trace_id": "trace-a"},
            {"session_id": "session-1"},
        ]
    )
    storage._chunks_collection = _ChunksCollection(
        [
            {"session_id": "session-1", "trace_id": "trace-a"},
            {"session_id": "session-1", "trace_id": "orphaned"},
        ]
    )

    deleted = await storage.delete_session_traces_strict(
        "session-1", trace_ids=["trace-a"], cutoff="cutoff"
    )

    assert deleted == 2
    assert storage.collection.docs == []
    assert storage.chunks_collection.docs == []


@pytest.mark.asyncio
async def test_clear_session_messages_releases_each_key_once_per_user_message() -> None:
    manager = SessionManager()
    file_records = _FileRecordStorage()
    trace_storage = _TraceStorage()
    trace_storage.events = [
        {
            "event_type": "user:message",
            "data": {
                "attachments": [
                    {"key": "attachments/u1/a.png"},
                    {"key": "attachments/u1/a.png"},
                    {"key": " attachments/u1/b.txt "},
                ]
            },
        },
        {
            "event_type": "user:message",
            "data": {"attachments": [{"key": "attachments/u1/a.png"}]},
        },
    ]
    manager._file_record_storage = file_records
    manager._trace_storage = trace_storage
    manager.storage = _SessionOperationStorage()

    released = await manager.clear_session_messages("session-1")

    assert released == 2
    assert file_records.released_counts == [
        Counter({"attachments/u1/a.png": 2, "attachments/u1/b.txt": 1})
    ]
    assert trace_storage.deleted_session_ids == ["session-1"]


@pytest.mark.asyncio
async def test_clear_session_messages_persists_deleted_group_when_counted_release_fails() -> None:
    manager = SessionManager()
    file_records = _FileRecordStorage()
    file_records.release_error = RuntimeError("database unavailable")
    trace_storage = _TraceStorage()
    trace_storage.events = [
        {
            "event_type": "user:message",
            "data": {"attachments": [{"key": "attachments/u1/a.png"}]},
        }
    ]
    manager._file_record_storage = file_records
    manager._trace_storage = trace_storage
    manager.storage = _SessionOperationStorage()

    with pytest.raises(RuntimeError, match="database unavailable"):
        await manager.clear_session_messages("session-1")

    assert trace_storage.deleted_session_ids == ["session-1"]
    assert manager.storage.server_operation is not None
    assert manager.storage.server_operation["groups"]["parent-0"]["status"] == "releasing"

    file_records.release_error = None
    assert await manager.clear_session_messages("session-1") == 1
    assert file_records.released_counts == [Counter({"attachments/u1/a.png": 1})]
    assert manager.storage.server_operation is None


@pytest.mark.asyncio
async def test_clear_session_messages_retries_marker_cleanup_without_releasing_twice() -> None:
    manager = SessionManager()
    file_records = _FileRecordStorage()
    file_records.forget_error = RuntimeError("marker cleanup unavailable")
    trace_storage = _TraceStorage()
    trace_storage.events = [
        {
            "event_type": "user:message",
            "data": {"attachments": [{"key": "attachments/u1/a.png"}]},
        }
    ]
    manager._file_record_storage = file_records
    manager._trace_storage = trace_storage
    manager.storage = _SessionOperationStorage()

    with pytest.raises(RuntimeError, match="marker cleanup unavailable"):
        await manager.clear_session_messages("session-1")

    assert manager.storage.server_operation is not None
    assert manager.storage.server_operation["groups"]["parent-0"]["status"] == "released"
    assert file_records.released_counts == [Counter({"attachments/u1/a.png": 1})]

    file_records.forget_error = None
    assert await manager.clear_session_messages("session-1") == 1
    assert file_records.released_counts == [Counter({"attachments/u1/a.png": 1})]
    assert file_records.forgot_operation_ids == ["server-operation-1:parent-0"]
    assert manager.storage.server_operation is None


@pytest.mark.asyncio
async def test_late_first_clear_cannot_decrement_after_second_caller_compacts_marker() -> None:
    storage = _SessionOperationStorage()
    trace_storage = _TraceStorage()
    trace_storage.events = [
        {
            "event_type": "user:message",
            "data": {"attachments": [{"key": "attachments/u1/a.png"}]},
        }
    ]
    first_release_started = asyncio.Event()
    resume_first_release = asyncio.Event()

    class _DelayedFirstRelease(_FileRecordStorage):
        def __init__(self) -> None:
            super().__init__()
            self.reference_count = 2
            self.release_calls = 0

        async def release_reference_counts(
            self,
            counts: Counter[str],
            *,
            operation_id: str,
            uploaded_by: str,
            owner_epoch: int,
        ) -> int:
            self.release_calls += 1
            if self.release_calls == 1:
                first_release_started.set()
                await resume_first_release.wait()
            released = await super().release_reference_counts(
                counts,
                operation_id=operation_id,
                uploaded_by=uploaded_by,
                owner_epoch=owner_epoch,
            )
            if released:
                self.reference_count -= sum(counts.values())
            return released

    file_records = _DelayedFirstRelease()
    first = SessionManager()
    second = SessionManager()
    for manager in (first, second):
        manager.storage = storage
        manager._trace_storage = trace_storage
        manager._file_record_storage = file_records

    first_call = asyncio.create_task(first.clear_session_messages("session-1"))
    await asyncio.wait_for(first_release_started.wait(), timeout=1)
    assert await second.clear_session_messages("session-1") == 1
    resume_first_release.set()
    first_result = await asyncio.gather(first_call, return_exceptions=True)

    assert isinstance(first_result[0], BaseException)
    assert file_records.reference_count == 1
    assert file_records.applied_operation_ids == set()


@pytest.mark.asyncio
async def test_repeated_cancellation_cannot_interrupt_fenced_group_release() -> None:
    release_started = asyncio.Event()
    finish_release = asyncio.Event()

    class _BlockingRelease(_FileRecordStorage):
        async def release_reference_counts(self, *args, **kwargs) -> int:
            release_started.set()
            await finish_release.wait()
            return await super().release_reference_counts(*args, **kwargs)

    file_records = _BlockingRelease()
    trace_storage = _TraceStorage()
    trace_storage.events = [
        {
            "event_type": "user:message",
            "data": {"attachments": [{"key": "attachments/u1/a.png"}]},
        }
    ]
    manager = SessionManager()
    manager.storage = _SessionOperationStorage()
    manager._trace_storage = trace_storage
    manager._file_record_storage = file_records

    clear_task = asyncio.create_task(manager.clear_session_messages("session-1"))
    await asyncio.wait_for(release_started.wait(), timeout=1)
    clear_task.cancel()
    await asyncio.sleep(0)
    clear_task.cancel()
    finish_release.set()

    assert await clear_task == 1
    assert file_records.released_counts == [Counter({"attachments/u1/a.png": 1})]
    assert file_records.live_operations == {}


@pytest.mark.asyncio
async def test_delete_session_continues_when_checkpoint_cleanup_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = SessionManager()
    manager._trace_storage = _TraceStorage()
    manager._file_record_storage = _FileRecordStorage()

    deleted_sessions: list[str] = []

    class _Storage(_SessionOperationStorage):
        def __init__(self) -> None:
            super().__init__()

        async def delete(self, session_id: str) -> bool:
            deleted_sessions.append(session_id)
            return True

    async def _fail_delete_checkpoints(_session_id: str) -> None:
        raise RuntimeError("checkpoint cleanup failed")

    class _RevealedStorage:
        async def delete_by_session(self, _session_id: str) -> int:
            return 0

    manager.storage = _Storage()
    monkeypatch.setattr(
        "src.infra.session.manager.delete_checkpoints_for_thread",
        _fail_delete_checkpoints,
    )
    monkeypatch.setattr(
        "src.infra.revealed_file.storage.get_revealed_file_storage",
        lambda: _RevealedStorage(),
    )

    deleted = await manager.delete_session("session-1")

    assert deleted is True
    assert deleted_sessions == ["session-1"]


@pytest.mark.asyncio
async def test_delete_session_cleans_checkpoints_after_session_document_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = SessionManager()
    manager._trace_storage = _TraceStorage()
    manager._file_record_storage = _FileRecordStorage()
    calls: list[str] = []

    class _Storage(_SessionOperationStorage):
        def __init__(self) -> None:
            super().__init__()

        async def delete(self, _session_id: str) -> bool:
            calls.append("session")
            return True

    async def _delete_checkpoints(_session_id: str) -> None:
        calls.append("checkpoints")

    class _RevealedStorage:
        async def delete_by_session(self, _session_id: str) -> int:
            return 0

    manager.storage = _Storage()
    monkeypatch.setattr(
        "src.infra.session.manager.delete_checkpoints_for_thread",
        _delete_checkpoints,
    )
    monkeypatch.setattr(
        "src.infra.revealed_file.storage.get_revealed_file_storage",
        lambda: _RevealedStorage(),
    )

    deleted = await manager.delete_session("session-1")

    assert deleted is True
    assert calls == ["session", "checkpoints"]


@pytest.mark.asyncio
async def test_collect_user_attachment_reference_counts_reads_all_user_messages_strictly() -> None:
    manager = SessionManager()

    class _AttachmentTraceStorage:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict]] = []

        async def iter_session_events_for_cleanup(self, session_id: str, **kwargs):
            self.calls.append((session_id, kwargs))
            events = [
                {
                    "event_type": "user:message",
                    "data": {
                        "attachments": [
                            {"key": "attachments/u1/a.png"},
                            {"key": "attachments/u1/a.png"},
                            {"key": " attachments/u1/b.txt "},
                        ]
                    },
                },
                {
                    "event_type": "assistant:message",
                    "data": {"attachments": [{"key": "attachments/u1/ignored.png"}]},
                },
                {
                    "event_type": "user:message",
                    "data": {"attachments": [{"key": "attachments/u1/a.png"}, {"key": ""}]},
                },
                {"event_type": "user:message", "data": ["malformed"]},
            ]
            for event in events:
                yield event

    trace_storage = _AttachmentTraceStorage()
    manager._trace_storage = trace_storage

    counts = await manager._collect_user_attachment_reference_counts("session-1")

    assert counts == Counter({"attachments/u1/a.png": 2, "attachments/u1/b.txt": 1})
    assert trace_storage.calls == [("session-1", {"event_types": ["user:message"]})]


@pytest.mark.asyncio
async def test_clear_session_messages_counts_more_than_one_thousand_user_messages() -> None:
    manager = SessionManager()
    file_records = _FileRecordStorage()
    trace_storage = _TraceStorage()
    trace_storage.events = [
        {"event_type": "user:message", "data": {"attachments": [{"key": "key-a"}]}}
        for _ in range(1001)
    ]
    manager._file_record_storage = file_records
    manager._trace_storage = trace_storage
    manager.storage = _SessionOperationStorage()

    released = await manager.clear_session_messages("session-1")

    assert released == 1
    assert file_records.released_counts == [Counter({"key-a": 1001})]


@pytest.mark.asyncio
async def test_clear_session_messages_preserves_traces_when_strict_read_fails() -> None:
    manager = SessionManager()
    file_records = _FileRecordStorage()
    trace_storage = _TraceStorage()
    trace_storage.read_error = RuntimeError("trace read unavailable")
    manager._file_record_storage = file_records
    manager._trace_storage = trace_storage
    manager.storage = _SessionOperationStorage()

    with pytest.raises(RuntimeError, match="trace read unavailable"):
        await manager.clear_session_messages("session-1")

    assert file_records.released_counts == []
    assert trace_storage.deleted_session_ids == []


@pytest.mark.asyncio
async def test_clear_retry_reuses_pending_operation_after_trace_delete_failure() -> None:
    manager = SessionManager()
    file_records = _FileRecordStorage()
    trace_storage = _TraceStorage()
    trace_storage.events = [
        {"event_type": "user:message", "data": {"attachments": [{"key": "key-a"}]}}
    ]
    trace_storage.delete_error = RuntimeError("trace delete unavailable")
    operation_storage = _SessionOperationStorage()
    manager._file_record_storage = file_records
    manager._trace_storage = trace_storage
    manager.storage = operation_storage

    with pytest.raises(RuntimeError, match="trace delete unavailable"):
        await manager.clear_session_messages("session-1")

    trace_storage.delete_error = None
    released = await manager.clear_session_messages("session-1")

    assert released == 1
    assert file_records.operation_ids == ["server-operation-1:parent-0"]
    assert file_records.released_counts == [Counter({"key-a": 1})]
    assert operation_storage.server_operation is None


@pytest.mark.asyncio
async def test_second_successful_clear_uses_a_new_operation_id() -> None:
    manager = SessionManager()
    file_records = _FileRecordStorage()
    trace_storage = _TraceStorage()
    operation_storage = _SessionOperationStorage()
    manager._file_record_storage = file_records
    manager._trace_storage = trace_storage
    manager.storage = operation_storage
    trace_storage.events = [
        {"event_type": "user:message", "data": {"attachments": [{"key": "key-a"}]}}
    ]

    await manager.clear_session_messages("session-1")
    trace_storage.events = [
        {"event_type": "user:message", "data": {"attachments": [{"key": "key-b"}]}}
    ]
    await manager.clear_session_messages("session-1")

    assert file_records.released_counts == [Counter({"key-a": 1}), Counter({"key-b": 1})]
    assert file_records.operation_ids[0] != file_records.operation_ids[1]


@pytest.mark.asyncio
async def test_clear_ignores_client_metadata_operation_and_uses_server_claim() -> None:
    manager = SessionManager()
    file_records = _FileRecordStorage()
    trace_storage = _TraceStorage()
    trace_storage.events = [
        {
            "trace_id": "trace-a",
            "event_type": "user:message",
            "data": {"attachments": [{"key": "owned-key"}]},
        }
    ]

    class _ServerOnlyOperations(_SessionOperationStorage):
        def __init__(self) -> None:
            super().__init__()
            self.metadata["attachment_clear_operation"] = {
                "id": "client-controlled",
                "counts": {"foreign-key": 99},
            }
            self.server_operation = None

        async def claim_attachment_clear_operation(self, _session_id: str):
            if self.server_operation is None:
                self.server_operation = {
                    "id": "server-operation",
                    "cutoff": "server-cutoff",
                    "uploaded_by": "owner-a",
                }
            return self.server_operation

        async def persist_attachment_clear_snapshot(
            self,
            _session_id: str,
            operation_id: str,
            counts: dict,
            trace_ids: list[str],
            *,
            parent_ids: list,
            chunk_ids: list,
            groups: dict,
        ):
            assert operation_id == "server-operation"
            self.server_operation.update(
                {
                    "counts": counts,
                    "trace_ids": trace_ids,
                    "parent_ids": parent_ids,
                    "chunk_ids": chunk_ids,
                    "groups": groups,
                }
            )
            return self.server_operation

        async def complete_attachment_clear_operation(
            self, _session_id: str, operation_id: str
        ) -> bool:
            assert operation_id == "server-operation"
            self.server_operation = None
            return True

    operations = _ServerOnlyOperations()
    manager._file_record_storage = file_records
    manager._trace_storage = trace_storage
    manager.storage = operations

    released = await manager.clear_session_messages("session-1")

    assert released == 1
    assert file_records.released_counts == [Counter({"owned-key": 1})]
    assert file_records.operation_ids == ["server-operation:parent-0"]


@pytest.mark.asyncio
async def test_retry_after_delete_failure_preserves_post_cutoff_trace_for_later_clear() -> None:
    manager = SessionManager()
    file_records = _FileRecordStorage()
    trace_storage = _TraceStorage()
    trace_storage.events = [
        {
            "trace_id": "trace-old",
            "event_type": "user:message",
            "data": {"attachments": [{"key": "old-key"}]},
        }
    ]
    trace_storage.delete_error = RuntimeError("delete failed")
    manager._file_record_storage = file_records
    manager._trace_storage = trace_storage
    manager.storage = _SessionOperationStorage()

    with pytest.raises(RuntimeError, match="delete failed"):
        await manager.clear_session_messages("session-1")

    trace_storage.events.append(
        {
            "trace_id": "trace-new",
            "event_type": "user:message",
            "data": {"attachments": [{"key": "new-key"}]},
        }
    )
    trace_storage.delete_error = None
    await manager.clear_session_messages("session-1")

    assert file_records.released_counts == [Counter({"old-key": 1})]
    assert trace_storage.deleted_session_ids == ["session-1"]


@pytest.mark.asyncio
async def test_object_id_session_clear_operation_persists_and_completes_exact_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _skip_indexes(_storage: SessionStorage) -> None:
        return None

    monkeypatch.setattr(SessionStorage, "ensure_indexes_if_needed", _skip_indexes)
    session_object_id = ObjectId()
    collection = _FilterAwareCollection([{"_id": session_object_id, "user_id": "owner-a"}])
    storage = SessionStorage()
    storage._collection = collection

    claimed = await storage.claim_attachment_clear_operation(str(session_object_id))

    assert claimed is not None
    assert claimed["uploaded_by"] == "owner-a"

    persisted = await storage.persist_attachment_clear_snapshot(
        str(session_object_id),
        claimed["id"],
        {"owned-key": 2},
        ["trace-terminal"],
        parent_ids=["parent-terminal", "parent-without-trace-id"],
        chunk_ids=["chunk-terminal"],
        groups={
            "parent-0": {
                "id": "parent-0",
                "kind": "parent",
                "document_id": "parent-terminal",
                "trace_id": "trace-terminal",
                "updated_at": claimed["cutoff"],
                "terminal_status": "completed",
                "counts": {"owned-key": 2},
                "status": "pending",
                "release_operation_id": f"{claimed['id']}:parent-0",
            }
        },
    )

    assert persisted is not None
    assert persisted["counts"] == {"owned-key": 2}
    assert persisted["parent_ids"] == ["parent-terminal", "parent-without-trace-id"]
    assert persisted["chunk_ids"] == ["chunk-terminal"]
    assert persisted["groups"]["parent-0"]["counts"] == {"owned-key": 2}
    assert await storage.set_attachment_clear_group_status(
        str(session_object_id),
        claimed["id"],
        "parent-0",
        expected_status="pending",
        status="deleted",
    )
    assert (
        collection.documents[0]["attachment_clear_operation"]["groups"]["parent-0"]["status"]
        == "deleted"
    )
    assert await storage.complete_attachment_clear_operation(str(session_object_id), claimed["id"])
    assert "attachment_clear_operation" not in collection.documents[0]


@pytest.mark.asyncio
async def test_clear_group_release_epochs_are_global_idempotent_and_takeover_expired_owner() -> (
    None
):
    now = datetime.now(timezone.utc)

    def _document(session_id: str, operation_id: str) -> dict:
        return {
            "session_id": session_id,
            "attachment_clear_operation": {
                "id": operation_id,
                "groups": {"parent-0": {"status": "deleted"}},
            },
        }

    collection = _FilterAwareCollection(
        [_document("session-1", "clear-1"), _document("session-2", "clear-2")]
    )
    metadata = _ReleaseEpochMetadata()
    storage = SessionStorage()
    storage._collection = collection
    storage._attachment_metadata_collection = metadata

    first = await storage.claim_attachment_clear_group_release(
        "session-1", "clear-1", "parent-0", "owner-a"
    )
    retry = await storage.claim_attachment_clear_group_release(
        "session-1", "clear-1", "parent-0", "owner-a"
    )
    second = await storage.claim_attachment_clear_group_release(
        "session-2", "clear-2", "parent-0", "owner-b"
    )

    assert first == retry == {"token": "owner-a", "epoch": 1}
    assert second == {"token": "owner-b", "epoch": 2}

    group = collection.documents[0]["attachment_clear_operation"]["groups"]["parent-0"]
    group["release_owner_expires_at"] = now - timedelta(seconds=1)
    takeover = await storage.claim_attachment_clear_group_release(
        "session-1", "clear-1", "parent-0", "owner-c"
    )

    assert takeover == {"token": "owner-c", "epoch": 3}
    assert not await storage.set_attachment_clear_group_status(
        "session-1",
        "clear-1",
        "parent-0",
        expected_status="releasing",
        status="released",
        owner_token="owner-a",
        owner_epoch=1,
    )
    assert await storage.set_attachment_clear_group_status(
        "session-1",
        "clear-1",
        "parent-0",
        expected_status="releasing",
        status="released",
        owner_token="owner-c",
        owner_epoch=3,
    )


@pytest.mark.asyncio
async def test_clear_group_release_counter_reply_loss_consumes_gap() -> None:
    collection = _FilterAwareCollection(
        [
            {
                "session_id": "session-1",
                "attachment_clear_operation": {
                    "id": "clear-1",
                    "groups": {"parent-0": {"status": "deleted"}},
                },
            }
        ]
    )
    storage = SessionStorage()
    storage._collection = collection
    storage._attachment_metadata_collection = _ReleaseEpochMetadata(lose_replies=1)

    with pytest.raises(ConnectionError, match="release epoch reply lost"):
        await storage.claim_attachment_clear_group_release(
            "session-1", "clear-1", "parent-0", "owner-a"
        )

    claimed = await storage.claim_attachment_clear_group_release(
        "session-1", "clear-1", "parent-0", "owner-a"
    )
    assert claimed == {"token": "owner-a", "epoch": 2}


@pytest.mark.asyncio
async def test_clear_group_release_recovers_exact_binding_after_reply_loss() -> None:
    class _LoseBindingReply(_FilterAwareCollection):
        def __init__(self, documents: list[dict[str, Any]]) -> None:
            super().__init__(documents)
            self.lose_reply = True

        async def find_one_and_update(self, query: dict, update: dict | list[dict], **kwargs):
            result = await super().find_one_and_update(query, update, **kwargs)
            if (
                self.lose_reply
                and result is not None
                and any(
                    key.endswith(".release_owner_epoch")
                    for key in (update.get("$set", {}) if isinstance(update, dict) else {})
                )
            ):
                self.lose_reply = False
                raise ConnectionError("binding reply lost")
            return result

    collection = _LoseBindingReply(
        [
            {
                "session_id": "session-1",
                "attachment_clear_operation": {
                    "id": "clear-1",
                    "groups": {"parent-0": {"status": "deleted"}},
                },
            }
        ]
    )
    metadata = _ReleaseEpochMetadata()
    storage = SessionStorage()
    storage._collection = collection
    storage._attachment_metadata_collection = metadata

    claimed = await storage.claim_attachment_clear_group_release(
        "session-1", "clear-1", "parent-0", "owner-a"
    )
    retried = await storage.claim_attachment_clear_group_release(
        "session-1", "clear-1", "parent-0", "owner-a"
    )

    assert claimed == retried == {"token": "owner-a", "epoch": 1}
    assert metadata.epoch == 1


@pytest.mark.asyncio
async def test_cleanup_snapshot_deletes_every_terminal_parent_and_only_its_exact_chunks() -> None:
    cutoff = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
    before = cutoff - timedelta(minutes=1)
    after = cutoff + timedelta(minutes=1)
    trace_storage, parents, chunks = _trace_storage_with_documents(
        [
            {
                "_id": "parent-user",
                "session_id": "session-1",
                "trace_id": "trace-user",
                "status": "completed",
                "updated_at": before,
                "events": [
                    {
                        "seq": 1,
                        "event_type": "user:message",
                        "data": {"attachments": [{"key": "parent-key"}]},
                    }
                ],
            },
            {
                "_id": "parent-no-user",
                "session_id": "session-1",
                "trace_id": "trace-no-user",
                "status": "error",
                "updated_at": before,
                "events": [{"event_type": "assistant:message", "data": {}}],
            },
            {
                "_id": "parent-no-trace-id",
                "session_id": "session-1",
                "status": "completed",
                "updated_at": before,
                "events": [
                    {
                        "event_type": "user:message",
                        "data": {"attachments": [{"key": "no-trace-key"}]},
                    }
                ],
            },
            {
                "_id": "parent-active",
                "session_id": "session-1",
                "trace_id": "trace-active",
                "status": "running",
                "updated_at": before,
                "events": [
                    {
                        "event_type": "user:message",
                        "data": {"attachments": [{"key": "active-key"}]},
                    }
                ],
            },
            {
                "_id": "parent-post-cutoff",
                "session_id": "session-1",
                "trace_id": "trace-post-cutoff",
                "status": "completed",
                "updated_at": after,
                "events": [
                    {
                        "event_type": "user:message",
                        "data": {"attachments": [{"key": "post-cutoff-key"}]},
                    }
                ],
            },
            {
                "_id": "parent-unknown-status",
                "session_id": "session-1",
                "trace_id": "trace-unknown-status",
                "status": "queued",
                "updated_at": before,
                "events": [
                    {
                        "event_type": "user:message",
                        "data": {"attachments": [{"key": "unknown-status-key"}]},
                    }
                ],
            },
        ],
        [
            {
                "_id": "chunk-user",
                "session_id": "session-1",
                "trace_id": "trace-user",
                "chunk_index": 0,
                "start_seq": 2,
                "updated_at": before,
                "events": [
                    {
                        "seq": 2,
                        "event_type": "user:message",
                        "data": {"attachments": [{"key": "chunk-key"}]},
                    }
                ],
            },
            {
                "_id": "chunk-no-user",
                "session_id": "session-1",
                "trace_id": "trace-no-user",
                "chunk_index": 0,
                "start_seq": 1,
                "updated_at": before,
                "events": [{"event_type": "assistant:message", "data": {}}],
            },
            {
                "_id": "chunk-unrelated",
                "session_id": "session-1",
                "trace_id": "trace-without-parent",
                "updated_at": before,
                "events": [
                    {
                        "event_type": "user:message",
                        "data": {"attachments": [{"key": "unrelated-key"}]},
                    }
                ],
            },
            {
                "_id": "chunk-active",
                "session_id": "session-1",
                "trace_id": "trace-active",
                "updated_at": after,
                "events": [
                    {
                        "event_type": "user:message",
                        "data": {"attachments": [{"key": "active-post-cutoff-key"}]},
                    }
                ],
            },
        ],
    )
    manager = SessionManager()
    manager._trace_storage = trace_storage

    counts, trace_ids, parent_ids, chunk_ids = await manager._collect_attachment_clear_snapshot(
        "session-1", cutoff
    )

    assert counts == Counter(
        {
            "parent-key": 1,
            "no-trace-key": 1,
            "chunk-key": 1,
            "unrelated-key": 1,
        }
    )
    assert trace_ids == ["trace-user", "trace-no-user"]
    assert parent_ids == ["parent-user", "parent-no-user", "parent-no-trace-id"]
    assert chunk_ids == ["chunk-user", "chunk-no-user", "chunk-unrelated"]
    assert parents.ids() == {
        "parent-active",
        "parent-post-cutoff",
        "parent-unknown-status",
        "parent-user",
        "parent-no-user",
        "parent-no-trace-id",
    }
    assert chunks.ids() == {
        "chunk-user",
        "chunk-no-user",
        "chunk-unrelated",
        "chunk-active",
    }
    assert parents.delete_calls == []
    assert chunks.delete_calls == []


@pytest.mark.asyncio
async def test_cleanup_snapshot_counts_legacy_chunk_overlap_once_per_message() -> None:
    cutoff = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
    events = [
        {
            "seq": 1,
            "event_type": "user:message",
            "data": {"attachments": [{"key": "key-a"}]},
        },
        {
            "seq": 2,
            "event_type": "user:message",
            "data": {"attachments": [{"key": "key-b"}]},
        },
    ]
    trace_storage, _parents, _chunks = _trace_storage_with_documents(
        [
            {
                "_id": "parent-1",
                "session_id": "session-1",
                "trace_id": "trace-1",
                "status": "completed",
                "updated_at": cutoff - timedelta(minutes=1),
                "events": events,
            }
        ],
        [
            {
                "_id": "chunk-1",
                "session_id": "session-1",
                "trace_id": "trace-1",
                "chunk_index": 0,
                "start_seq": 1,
                "updated_at": cutoff - timedelta(seconds=30),
                "events": events,
            }
        ],
    )
    manager = SessionManager()
    manager._trace_storage = trace_storage

    counts, _trace_ids, _parent_ids, _chunk_ids = await manager._collect_attachment_clear_snapshot(
        "session-1", cutoff
    )

    assert counts == Counter({"key-a": 1, "key-b": 1})


@pytest.mark.asyncio
async def test_clear_preserves_active_pre_cutoff_trace_with_post_cutoff_events() -> None:
    cutoff = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
    before = cutoff - timedelta(minutes=1)
    after = cutoff + timedelta(minutes=1)
    trace_storage, parents, chunks = _trace_storage_with_documents(
        [
            {
                "_id": "parent-active",
                "session_id": "session-1",
                "trace_id": "trace-active",
                "status": "running",
                "started_at": before,
                "updated_at": before,
                "events": [],
            }
        ],
        [
            {
                "_id": "chunk-active",
                "session_id": "session-1",
                "trace_id": "trace-active",
                "trace_started_at": before,
                "updated_at": after,
                "events": [
                    {
                        "timestamp": before,
                        "event_type": "user:message",
                        "data": {"attachments": [{"key": "pre-cutoff-key"}]},
                    },
                    {
                        "timestamp": after,
                        "event_type": "user:message",
                        "data": {"attachments": [{"key": "post-cutoff-key"}]},
                    },
                ],
            }
        ],
    )
    manager = SessionManager()
    file_records = _FileRecordStorage()
    manager._trace_storage = trace_storage
    manager._file_record_storage = file_records
    manager.storage = _ExactSessionOperationStorage(cutoff)

    released = await manager.clear_session_messages("session-1")

    assert released == 0
    assert file_records.released_counts == []
    assert parents.ids() == {"parent-active"}
    assert chunks.ids() == {"chunk-active"}


@pytest.mark.asyncio
async def test_clear_preserves_chunk_created_after_exact_snapshot() -> None:
    cutoff = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
    before = cutoff - timedelta(minutes=1)
    after = cutoff + timedelta(minutes=1)
    trace_storage, parents, chunks = _trace_storage_with_documents(
        [
            {
                "_id": "parent-terminal",
                "session_id": "session-1",
                "trace_id": "trace-terminal",
                "status": "completed",
                "updated_at": before,
                "events": [],
            }
        ],
        [
            {
                "_id": "chunk-snapshot",
                "session_id": "session-1",
                "trace_id": "trace-terminal",
                "updated_at": before,
                "events": [
                    {
                        "event_type": "user:message",
                        "data": {"attachments": [{"key": "snapshot-key"}]},
                    }
                ],
            }
        ],
    )

    class _AppendAfterSnapshotFileRecords(_FileRecordStorage):
        async def release_reference_counts(
            self,
            counts: Counter[str],
            *,
            operation_id: str,
            uploaded_by: str,
            owner_epoch: int,
        ) -> int:
            chunks.documents.append(
                {
                    "_id": "chunk-post-snapshot",
                    "session_id": "session-1",
                    "trace_id": "trace-terminal",
                    "updated_at": after,
                    "events": [
                        {
                            "event_type": "user:message",
                            "data": {"attachments": [{"key": "post-snapshot-key"}]},
                        }
                    ],
                }
            )
            return await super().release_reference_counts(
                counts,
                operation_id=operation_id,
                uploaded_by=uploaded_by,
                owner_epoch=owner_epoch,
            )

    manager = SessionManager()
    file_records = _AppendAfterSnapshotFileRecords()
    manager._trace_storage = trace_storage
    manager._file_record_storage = file_records
    manager.storage = _ExactSessionOperationStorage(cutoff)

    released = await manager.clear_session_messages("session-1")

    assert released == 1
    assert file_records.released_counts == [Counter({"snapshot-key": 1})]
    assert parents.ids() == set()
    assert chunks.ids() == {"chunk-post-snapshot"}


@pytest.mark.asyncio
async def test_exact_snapshot_postcondition_keeps_operation_retryable() -> None:
    cutoff = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
    before = cutoff - timedelta(minutes=1)
    trace_storage, parents, chunks = _trace_storage_with_documents(
        [
            {
                "_id": "parent-terminal",
                "session_id": "session-1",
                "trace_id": "trace-terminal",
                "status": "completed",
                "updated_at": before,
                "events": [],
            }
        ],
        [
            {
                "_id": "chunk-terminal",
                "session_id": "session-1",
                "trace_id": "trace-terminal",
                "updated_at": before,
                "events": [
                    {
                        "event_type": "user:message",
                        "data": {"attachments": [{"key": "owned-key"}]},
                    }
                ],
            }
        ],
    )
    chunks.skip_delete_once.add("chunk-terminal")
    manager = SessionManager()
    file_records = _FileRecordStorage()
    operation_storage = _ExactSessionOperationStorage(cutoff)
    manager._trace_storage = trace_storage
    manager._file_record_storage = file_records
    manager.storage = operation_storage

    assert await manager.clear_session_messages("session-1") == 0
    assert operation_storage.server_operation is None
    assert parents.ids() == set()
    assert chunks.ids() == {"chunk-terminal"}
    assert file_records.released_counts == []
    chunks.documents.append(
        {
            "_id": "chunk-post-snapshot",
            "session_id": "session-1",
            "trace_id": "trace-terminal",
            "updated_at": cutoff + timedelta(minutes=1),
            "events": [],
        }
    )

    released = await manager.clear_session_messages("session-1")

    assert released == 1
    assert parents.ids() == set()
    assert chunks.ids() == {"chunk-post-snapshot"}
    assert file_records.released_counts == [Counter({"owned-key": 1})]
    assert file_records.operation_ids == ["server-operation-2:orphan-chunk-0"]
    assert operation_storage.server_operation is None


@pytest.mark.asyncio
async def test_clear_fails_closed_for_pending_operation_without_exact_document_ids() -> None:
    manager = SessionManager()
    file_records = _FileRecordStorage()
    trace_storage = _TraceStorage()
    operation_storage = _SessionOperationStorage()
    operation_storage.server_operation = {
        "id": "legacy-operation",
        "cutoff": "legacy-cutoff",
        "uploaded_by": "owner-a",
        "counts": {"owned-key": 1},
        "trace_ids": ["trace-legacy"],
    }
    manager._file_record_storage = file_records
    manager._trace_storage = trace_storage
    manager.storage = operation_storage

    with pytest.raises(SessionError, match="attachment_clear_operation_invalid"):
        await manager.clear_session_messages("session-1")

    assert file_records.released_counts == []
    assert trace_storage.deleted_session_ids == []


@pytest.mark.asyncio
async def test_parent_mutated_after_snapshot_survives_then_releases_exact_counts_next_clear() -> (
    None
):
    first_cutoff = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
    original_updated_at = first_cutoff - timedelta(minutes=1)
    mutated_updated_at = first_cutoff + timedelta(seconds=1)
    trace_storage, parents, _chunks = _trace_storage_with_documents(
        [
            {
                "_id": "parent-mutated",
                "session_id": "session-1",
                "trace_id": "trace-mutated",
                "status": "completed",
                "updated_at": original_updated_at,
                "events": [
                    {
                        "seq": 1,
                        "event_type": "user:message",
                        "data": {"attachments": [{"key": "old-key"}]},
                    }
                ],
            }
        ],
        [],
    )

    class _MutatingOperationStorage(_ExactSessionOperationStorage):
        mutated = False

        async def persist_attachment_clear_snapshot(self, *args, **kwargs):
            operation = await super().persist_attachment_clear_snapshot(*args, **kwargs)
            if not self.mutated:
                self.mutated = True
                parents.documents[0]["updated_at"] = mutated_updated_at
                parents.documents[0]["events"].append(
                    {
                        "seq": 2,
                        "event_type": "user:message",
                        "data": {"attachments": [{"key": "new-key"}]},
                    }
                )
            return operation

    operations = _MutatingOperationStorage(first_cutoff)
    manager = SessionManager()
    file_records = _FileRecordStorage()
    manager._trace_storage = trace_storage
    manager._file_record_storage = file_records
    manager.storage = operations

    assert await manager.clear_session_messages("session-1") == 0
    assert parents.ids() == {"parent-mutated"}
    assert file_records.released_counts == []

    operations.cutoff = mutated_updated_at + timedelta(minutes=1)
    assert await manager.clear_session_messages("session-1") == 2
    assert parents.ids() == set()
    assert file_records.released_counts == [Counter({"old-key": 1, "new-key": 1})]


@pytest.mark.asyncio
async def test_partial_group_delete_retry_releases_only_each_removed_groups_counts_once() -> None:
    cutoff = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
    before = cutoff - timedelta(minutes=1)
    trace_storage, parents, _chunks = _trace_storage_with_documents(
        [
            {
                "_id": "parent-a",
                "session_id": "session-1",
                "trace_id": "trace-a",
                "status": "completed",
                "updated_at": before,
                "events": [
                    {
                        "event_type": "user:message",
                        "data": {"attachments": [{"key": "key-a"}]},
                    }
                ],
            },
            {
                "_id": "parent-b",
                "session_id": "session-1",
                "trace_id": "trace-b",
                "status": "error",
                "updated_at": before,
                "events": [
                    {
                        "event_type": "user:message",
                        "data": {"attachments": [{"key": "key-b"}]},
                    }
                ],
            },
        ],
        [],
    )
    parents.fail_delete_once.add("parent-b")
    manager = SessionManager()
    file_records = _FileRecordStorage()
    operations = _ExactSessionOperationStorage(cutoff)
    manager._trace_storage = trace_storage
    manager._file_record_storage = file_records
    manager.storage = operations

    with pytest.raises(RuntimeError, match="delete failed for parent-b"):
        await manager.clear_session_messages("session-1")

    assert parents.ids() == {"parent-b"}
    assert file_records.released_counts == [Counter({"key-a": 1})]
    assert operations.server_operation is not None
    assert {
        group_id: group["release_operation_id"]
        for group_id, group in operations.server_operation["groups"].items()
    } == {
        "parent-0": "server-operation-1:parent-0",
        "parent-1": "server-operation-1:parent-1",
    }

    assert await manager.clear_session_messages("session-1") == 2
    assert parents.ids() == set()
    assert file_records.released_counts == [Counter({"key-a": 1}), Counter({"key-b": 1})]
    assert len(set(file_records.operation_ids)) == 2
    assert operations.server_operation is None


@pytest.mark.asyncio
async def test_post_snapshot_chunk_is_discovered_as_orphan_and_released_on_second_clear() -> None:
    first_cutoff = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
    before = first_cutoff - timedelta(minutes=1)
    after = first_cutoff + timedelta(minutes=1)
    trace_storage, parents, chunks = _trace_storage_with_documents(
        [
            {
                "_id": "parent-terminal",
                "session_id": "session-1",
                "trace_id": "trace-terminal",
                "status": "completed",
                "updated_at": before,
                "events": [],
            }
        ],
        [
            {
                "_id": "chunk-snapshot",
                "session_id": "session-1",
                "trace_id": "trace-terminal",
                "chunk_index": 0,
                "start_seq": 1,
                "updated_at": before,
                "events": [
                    {
                        "seq": 1,
                        "event_type": "user:message",
                        "data": {"attachments": [{"key": "snapshot-key"}]},
                    }
                ],
            }
        ],
    )

    class _CreatingOperationStorage(_ExactSessionOperationStorage):
        created = False

        async def persist_attachment_clear_snapshot(self, *args, **kwargs):
            operation = await super().persist_attachment_clear_snapshot(*args, **kwargs)
            if not self.created:
                self.created = True
                chunks.documents.append(
                    {
                        "_id": "chunk-post-snapshot",
                        "session_id": "session-1",
                        "trace_id": "trace-terminal",
                        "chunk_index": 1,
                        "start_seq": 2,
                        "updated_at": after,
                        "events": [
                            {
                                "seq": 2,
                                "event_type": "user:message",
                                "data": {"attachments": [{"key": "later-key"}]},
                            }
                        ],
                    }
                )
            return operation

    operations = _CreatingOperationStorage(first_cutoff)
    manager = SessionManager()
    file_records = _FileRecordStorage()
    manager._trace_storage = trace_storage
    manager._file_record_storage = file_records
    manager.storage = operations

    assert await manager.clear_session_messages("session-1") == 1
    assert parents.ids() == set()
    assert chunks.ids() == {"chunk-post-snapshot"}
    assert file_records.released_counts == [Counter({"snapshot-key": 1})]

    operations.cutoff = after + timedelta(minutes=1)
    assert await manager.clear_session_messages("session-1") == 1
    assert chunks.ids() == set()
    assert file_records.released_counts == [
        Counter({"snapshot-key": 1}),
        Counter({"later-key": 1}),
    ]


@pytest.mark.asyncio
async def test_delete_session_refuses_to_remove_anchor_while_running_trace_survives(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cutoff = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
    trace_storage, parents, _chunks = _trace_storage_with_documents(
        [
            {
                "_id": "parent-running",
                "session_id": "session-1",
                "trace_id": "trace-running",
                "status": "running",
                "updated_at": cutoff - timedelta(minutes=1),
                "events": [],
            }
        ],
        [],
    )
    deleted_sessions: list[str] = []

    class _Storage(_ExactSessionOperationStorage):
        async def delete(self, session_id: str) -> bool:
            deleted_sessions.append(session_id)
            return True

    class _RevealedStorage:
        async def delete_by_session(self, _session_id: str) -> int:
            return 0

    manager = SessionManager()
    manager._trace_storage = trace_storage
    manager._file_record_storage = _FileRecordStorage()
    manager.storage = _Storage(cutoff)
    monkeypatch.setattr(
        "src.infra.revealed_file.storage.get_revealed_file_storage",
        lambda: _RevealedStorage(),
    )

    with pytest.raises(SessionError, match="session_delete_has_trace_survivors"):
        await manager.delete_session("session-1")

    assert parents.ids() == {"parent-running"}
    assert deleted_sessions == []


@pytest.mark.asyncio
async def test_chunk_rewrite_with_stale_parent_version_does_not_mutate_chunks() -> None:
    snapshot_updated_at = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
    current_updated_at = snapshot_updated_at + timedelta(seconds=1)
    trace_storage, parents, chunks = _trace_storage_with_documents(
        [
            {
                "_id": "parent-terminal",
                "session_id": "session-1",
                "trace_id": "trace-terminal",
                "status": "completed",
                "updated_at": current_updated_at,
                "events": [
                    {
                        "seq": 1,
                        "event_type": "user:message",
                        "data": {"attachments": [{"key": "old-key"}]},
                    }
                ],
            }
        ],
        [
            {
                "_id": "chunk-existing",
                "session_id": "session-1",
                "trace_id": "trace-terminal",
                "updated_at": current_updated_at,
                "events": [],
            }
        ],
    )

    rewritten = await trace_storage.replace_trace_events_with_chunks(
        {
            "_id": "parent-terminal",
            "session_id": "session-1",
            "trace_id": "trace-terminal",
            "status": "completed",
            "updated_at": snapshot_updated_at,
        },
        [
            {
                "event_type": "user:message",
                "data": {"attachments": [{"key": "old-key"}]},
            },
            {
                "event_type": "user:message",
                "data": {"attachments": [{"key": "new-key"}]},
            },
        ],
    )

    assert rewritten is False
    assert parents.ids() == {"parent-terminal"}
    assert chunks.ids() == {"chunk-existing"}
    assert chunks.delete_calls == []


@pytest.mark.asyncio
async def test_delete_session_fence_blocks_parent_creation_between_probe_and_anchor_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _skip_session_indexes(_storage: SessionStorage) -> None:
        return None

    async def _skip_trace_indexes(_storage: TraceStorage) -> None:
        return None

    async def _skip_checkpoints(_session_id: str) -> None:
        return None

    monkeypatch.setattr(SessionStorage, "ensure_indexes_if_needed", _skip_session_indexes)
    monkeypatch.setattr(TraceStorage, "ensure_indexes_if_needed", _skip_trace_indexes)
    monkeypatch.setattr(
        "src.infra.session.manager.delete_checkpoints_for_thread", _skip_checkpoints
    )

    session_collection = _FilterAwareCollection(
        [{"_id": "session-doc", "session_id": "session-1", "user_id": "owner-a"}]
    )
    trace_storage, parents, _chunks = _trace_storage_with_documents([], [])

    class _RacingStorage(SessionStorage):
        writer_result: bool | None = None

        async def delete_claimed_session(self, session_id: str, operation_id: str) -> bool:
            self.writer_result = await trace_storage.create_trace(
                "trace-racing",
                session_id,
                user_id="owner-a",
            )
            return await super().delete_claimed_session(session_id, operation_id)

    storage = _RacingStorage()
    storage._collection = session_collection
    trace_storage._session_storage = storage
    manager = SessionManager()
    manager.storage = storage
    manager._trace_storage = trace_storage
    manager._file_record_storage = _FileRecordStorage()

    class _RevealedStorage:
        async def delete_by_session(self, _session_id: str) -> int:
            return 0

    monkeypatch.setattr(
        "src.infra.revealed_file.storage.get_revealed_file_storage",
        lambda: _RevealedStorage(),
    )

    assert await manager.delete_session("session-1") is True
    assert storage.writer_result is False
    assert parents.ids() == set()
    assert session_collection.ids() == set()


@pytest.mark.asyncio
async def test_concurrent_delete_claim_has_one_owner_and_only_fenced_owner_can_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _skip_indexes(_storage: SessionStorage) -> None:
        return None

    monkeypatch.setattr(SessionStorage, "ensure_indexes_if_needed", _skip_indexes)
    collection = _FilterAwareCollection(
        [
            {
                "_id": "session-doc",
                "session_id": "session-1",
                "user_id": "owner-a",
                "active_trace_writers": 0,
            }
        ]
    )
    storage = SessionStorage()
    storage._collection = collection

    first_claim, second_claim = await asyncio.gather(
        storage.claim_attachment_delete_operation("session-1"),
        storage.claim_attachment_delete_operation("session-1"),
    )

    assert first_claim is not None and second_claim is not None
    claims = [first_claim, second_claim]
    assert [claim["acquired"] for claim in claims].count(True) == 1
    assert [claim["acquired"] for claim in claims].count(False) == 1
    owner_claim = next(claim for claim in claims if claim["acquired"])
    observer_claim = next(claim for claim in claims if not claim["acquired"])
    assert observer_claim["id"] == owner_claim["id"]

    assert await storage.delete_claimed_session("session-1", f"{owner_claim['id']}-forged") is False
    assert collection.ids() == {"session-doc"}
    assert await storage.delete_claimed_session("session-1", owner_claim["id"]) is True
    assert collection.ids() == set()


@pytest.mark.asyncio
async def test_crashed_trace_writer_lease_expires_without_permanently_blocking_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _skip_indexes(_storage: SessionStorage) -> None:
        return None

    now = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(SessionStorage, "ensure_indexes_if_needed", _skip_indexes)
    monkeypatch.setattr(
        "src.infra.session.session_attachment_operations.utc_now",
        lambda: now,
    )
    collection = _FilterAwareCollection(
        [
            {
                "_id": "session-doc",
                "session_id": "session-1",
                "user_id": "owner-a",
                "trace_writer_leases": [
                    {
                        "id": "crashed-writer",
                        "expires_at": now - timedelta(seconds=1),
                    }
                ],
            }
        ]
    )
    storage = SessionStorage()
    storage._collection = collection

    claim = await storage.claim_attachment_delete_operation("session-1")

    assert claim is not None
    assert claim["acquired"] is True
    assert await storage.delete_claimed_session("session-1", claim["id"]) is True
    assert collection.ids() == set()


@pytest.mark.asyncio
async def test_legacy_nonzero_writer_counter_fails_closed_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _skip_indexes(_storage: SessionStorage) -> None:
        return None

    monkeypatch.setattr(SessionStorage, "ensure_indexes_if_needed", _skip_indexes)
    collection = _FilterAwareCollection(
        [
            {
                "_id": "session-doc",
                "session_id": "session-1",
                "user_id": "owner-a",
                "active_trace_writers": 1,
            }
        ]
    )
    storage = SessionStorage()
    storage._collection = collection

    assert await storage.acquire_trace_write("session-1") is None
    assert await storage.claim_attachment_delete_operation("session-1") is None
    assert collection.documents[0]["active_trace_writers"] == 1
    assert "trace_writer_leases" not in collection.documents[0]
    assert "attachment_delete_operation" not in collection.documents[0]


@pytest.mark.asyncio
async def test_legacy_zero_writer_counter_atomically_migrates_on_acquire(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _skip_indexes(_storage: SessionStorage) -> None:
        return None

    monkeypatch.setattr(SessionStorage, "ensure_indexes_if_needed", _skip_indexes)
    collection = _FilterAwareCollection(
        [
            {
                "_id": "session-doc",
                "session_id": "session-1",
                "user_id": "owner-a",
                "active_trace_writers": 0,
            }
        ]
    )
    storage = SessionStorage()
    storage._collection = collection

    lease_id = await storage.acquire_trace_write("session-1")

    assert isinstance(lease_id, str)
    assert "active_trace_writers" not in collection.documents[0]
    assert [lease["id"] for lease in collection.documents[0]["trace_writer_leases"]] == [lease_id]
    await storage.release_trace_write("session-1", lease_id)


@pytest.mark.asyncio
async def test_custom_session_identity_never_falls_back_to_colliding_object_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _skip_indexes(_storage: SessionStorage) -> None:
        return None

    now = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
    custom_id = "64b000000000000000000001"
    monkeypatch.setattr(SessionStorage, "ensure_indexes_if_needed", _skip_indexes)
    collection = _FilterAwareCollection(
        [
            {
                "_id": "custom-document",
                "session_id": custom_id,
                "trace_writer_leases": [
                    {"id": "live-custom-writer", "expires_at": now + timedelta(minutes=1)}
                ],
            },
            {
                "_id": ObjectId(custom_id),
                "session_id": "different-session",
            },
        ]
    )
    storage = SessionStorage()
    storage._collection = collection
    monkeypatch.setattr(
        "src.infra.session.session_attachment_operations.utc_now",
        lambda: now,
    )

    assert await storage.claim_attachment_delete_operation(custom_id) is None
    assert "attachment_delete_operation" not in collection.documents[0]
    assert "attachment_delete_operation" not in collection.documents[1]


@pytest.mark.asyncio
async def test_legacy_object_id_only_session_remains_compatible_with_delete_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _skip_indexes(_storage: SessionStorage) -> None:
        return None

    legacy_id = ObjectId("64b000000000000000000002")
    monkeypatch.setattr(SessionStorage, "ensure_indexes_if_needed", _skip_indexes)
    collection = _FilterAwareCollection([{"_id": legacy_id, "user_id": "owner-a"}])
    storage = SessionStorage()
    storage._collection = collection

    claim = await storage.claim_attachment_delete_operation(str(legacy_id))

    assert claim is not None
    assert claim["acquired"] is True
    assert await storage.delete_claimed_session(str(legacy_id), claim["id"]) is True
    assert collection.ids() == set()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "malformed_leases",
    [
        {"id": "not-an-array", "expires_at": "future"},
        [42],
        "corrupt",
        [{"id": "wrong-expiry-type", "expires_at": "2099-01-01T00:00:00Z"}],
    ],
)
async def test_malformed_trace_writer_lease_shapes_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    malformed_leases: object,
) -> None:
    async def _skip_indexes(_storage: SessionStorage) -> None:
        return None

    monkeypatch.setattr(SessionStorage, "ensure_indexes_if_needed", _skip_indexes)
    collection = _FilterAwareCollection(
        [
            {
                "_id": "session-doc",
                "session_id": "session-1",
                "trace_writer_leases": malformed_leases,
            }
        ]
    )
    storage = SessionStorage()
    storage._collection = collection

    assert await storage.claim_attachment_delete_operation("session-1") is None
    assert collection.documents[0]["trace_writer_leases"] == malformed_leases
    assert "attachment_delete_operation" not in collection.documents[0]


@pytest.mark.asyncio
async def test_trace_cleanup_guard_defers_delete_cancel_until_cross_collection_cleanup_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _skip_indexes(_storage: SessionStorage) -> None:
        return None

    class _BlockingChunksCollection(_FilterAwareCollection):
        def __init__(self) -> None:
            super().__init__(
                [
                    {
                        "_id": "chunk-a",
                        "session_id": "session-1",
                        "trace_id": "trace-a",
                    }
                ]
            )
            self.delete_started = asyncio.Event()
            self.allow_delete = asyncio.Event()

        async def delete_many(self, query: dict[str, Any]):
            self.delete_started.set()
            await self.allow_delete.wait()
            return await super().delete_many(query)

    now = datetime(2026, 8, 11, 14, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(SessionStorage, "ensure_indexes_if_needed", _skip_indexes)
    monkeypatch.setattr(
        "src.infra.session.session_attachment_operations.utc_now",
        lambda: now,
    )
    session_collection = _FilterAwareCollection(
        [
            {
                "_id": "session-doc",
                "session_id": "session-1",
                "trace_writer_leases": [
                    {
                        "id": "writer-a",
                        "expires_at": now - timedelta(seconds=1),
                    }
                ],
                "attachment_delete_operation": {
                    "id": "delete-1",
                    "claimed_at": now,
                },
            }
        ]
    )
    parents = _FilterAwareCollection(
        [
            {
                "_id": "parent-a",
                "session_id": "session-1",
                "trace_id": "trace-a",
                "events": [],
                "event_count": 0,
            }
        ]
    )
    chunks = _BlockingChunksCollection()
    session_storage = SessionStorage()
    session_storage._collection = session_collection
    trace_storage = TraceStorage()
    trace_storage._collection = parents
    trace_storage._chunks_collection = chunks
    trace_storage._session_storage = session_storage

    cleanup = asyncio.create_task(
        trace_storage.discard_session_trace_writes_after_lease_loss(
            "session-1",
            "writer-a",
            ["trace-a"],
        )
    )
    await chunks.delete_started.wait()
    operation_during_cleanup = deepcopy(
        session_collection.documents[0]["attachment_delete_operation"]
    )
    cancel_result = await session_storage.cancel_attachment_delete_operation(
        "session-1",
        "delete-1",
    )
    writer_during_cleanup = await session_storage.acquire_trace_write("session-1")
    if writer_during_cleanup is not None:
        assert (
            await trace_storage.append_event(
                "trace-a",
                "message:chunk",
                {"content": "must-not-be-deleted"},
            )
            is True
        )

    chunks.allow_delete.set()
    cleanup_result = await cleanup
    if writer_during_cleanup is not None:
        await session_storage.release_trace_write("session-1", writer_during_cleanup)
    writer_after_cleanup = await session_storage.acquire_trace_write("session-1")
    if writer_after_cleanup is not None:
        await session_storage.release_trace_write("session-1", writer_after_cleanup)

    assert isinstance(operation_during_cleanup.get("cleanup_guard", {}).get("id"), str)
    assert cancel_result is True
    assert writer_during_cleanup is None
    assert cleanup_result is True
    assert chunks.documents == []
    assert parents.documents == []
    assert "attachment_delete_operation" not in session_collection.documents[0]
    assert isinstance(writer_after_cleanup, str)


@pytest.mark.asyncio
async def test_trace_cleanup_snapshot_expiry_aborts_before_any_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _skip_indexes(_storage: SessionStorage) -> None:
        return None

    class _BlockingSnapshotCursor:
        def __init__(
            self,
            collection: _FilterAwareCollection,
            query: dict[str, Any],
            projection: dict[str, int] | None,
        ) -> None:
            self.collection = collection
            self.query = deepcopy(query)
            self.projection = deepcopy(projection)

        async def to_list(self, length: int | None = None) -> list[dict[str, Any]]:
            snapshot_started.set()
            await allow_stale_operation.wait()
            documents = [
                _project(document, self.projection)
                for document in self.collection.documents
                if _matches(document, self.query)
            ]
            return documents if length is None else documents[:length]

    class _SnapshotOrLegacyDeleteBlockingChunks(_FilterAwareCollection):
        def find(self, query: dict[str, Any], projection: dict[str, int] | None = None):
            self.find_calls.append(deepcopy(query))
            return _BlockingSnapshotCursor(self, query, projection)

        async def delete_many(self, query: dict[str, Any]):
            legacy_delete_started.set()
            await allow_stale_operation.wait()
            return await super().delete_many(query)

    started_at = datetime(2026, 8, 11, 14, 0, tzinfo=timezone.utc)
    clock = {"now": started_at}
    monkeypatch.setattr(SessionStorage, "ensure_indexes_if_needed", _skip_indexes)
    monkeypatch.setattr(
        "src.infra.session.session_attachment_operations.utc_now",
        lambda: clock["now"],
    )
    monkeypatch.setattr(
        "src.infra.session.trace_storage_writes.utc_now",
        lambda: clock["now"],
    )
    snapshot_started = asyncio.Event()
    legacy_delete_started = asyncio.Event()
    allow_stale_operation = asyncio.Event()
    session_collection = _FilterAwareCollection(
        [
            {
                "_id": "session-doc",
                "session_id": "session-1",
                "trace_writer_leases": [
                    {
                        "id": "writer-a",
                        "expires_at": started_at - timedelta(seconds=1),
                    }
                ],
                "attachment_delete_operation": {
                    "id": "delete-1",
                    "claimed_at": started_at,
                },
            }
        ]
    )
    parents = _FilterAwareCollection(
        [
            {
                "_id": "parent-a",
                "session_id": "session-1",
                "trace_id": "trace-a",
                "events": [],
                "event_count": 0,
                "event_revision": 0,
                "updated_at": started_at,
            }
        ]
    )
    chunks = _SnapshotOrLegacyDeleteBlockingChunks(
        [
            {
                "_id": "chunk-a",
                "session_id": "session-1",
                "trace_id": "trace-a",
                "append_fence_revision": 0,
                "event_count": 0,
                "updated_at": started_at,
            }
        ]
    )
    session_storage = SessionStorage()
    session_storage._collection = session_collection
    trace_storage = TraceStorage()
    trace_storage._collection = parents
    trace_storage._chunks_collection = chunks
    trace_storage._session_storage = session_storage

    stale_cleanup = asyncio.create_task(
        trace_storage.discard_session_trace_writes_after_lease_loss(
            "session-1",
            "writer-a",
            ["trace-a"],
        )
    )
    snapshot_waiter = asyncio.create_task(snapshot_started.wait())
    legacy_delete_waiter = asyncio.create_task(legacy_delete_started.wait())
    done, pending = await asyncio.wait(
        {snapshot_waiter, legacy_delete_waiter},
        return_when=asyncio.FIRST_COMPLETED,
    )
    assert done
    for waiter in pending:
        waiter.cancel()

    clock["now"] = started_at + timedelta(minutes=6)
    cancelled = await session_storage.cancel_attachment_delete_operation(
        "session-1",
        "delete-1",
    )
    new_writer = await session_storage.acquire_trace_write("session-1")
    appended = await trace_storage.append_event(
        "trace-a",
        "message:chunk",
        {"content": "new-generation"},
    )

    allow_stale_operation.set()
    stale_result = await stale_cleanup
    if new_writer is not None:
        await session_storage.release_trace_write("session-1", new_writer)

    assert cancelled is True
    assert isinstance(new_writer, str)
    assert appended is True
    assert stale_result is False
    assert chunks.delete_calls == []
    assert parents.delete_calls == []
    assert chunks.ids() == {"chunk-a"}
    assert parents.ids() == {"parent-a"}
    assert parents.documents[0]["events"][0]["data"] == {"content": "new-generation"}


@pytest.mark.asyncio
async def test_expired_cleanup_delete_cannot_remove_newer_parent_or_chunk_versions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _skip_indexes(_storage: SessionStorage) -> None:
        return None

    class _BlockingChunksDelete(_FilterAwareCollection):
        def __init__(self, documents: list[dict[str, Any]]) -> None:
            super().__init__(documents)
            self.delete_started = asyncio.Event()
            self.allow_delete = asyncio.Event()

        async def delete_many(self, query: dict[str, Any]):
            self.delete_started.set()
            await self.allow_delete.wait()
            return await super().delete_many(query)

    started_at = datetime(2026, 8, 11, 14, 0, tzinfo=timezone.utc)
    clock = {"now": started_at}
    monkeypatch.setattr(SessionStorage, "ensure_indexes_if_needed", _skip_indexes)
    monkeypatch.setattr(
        "src.infra.session.session_attachment_operations.utc_now",
        lambda: clock["now"],
    )
    monkeypatch.setattr(
        "src.infra.session.trace_storage_writes.utc_now",
        lambda: clock["now"],
    )
    session_collection = _FilterAwareCollection(
        [
            {
                "_id": "session-doc",
                "session_id": "session-1",
                "trace_writer_leases": [
                    {
                        "id": "writer-a",
                        "expires_at": started_at - timedelta(seconds=1),
                    }
                ],
                "attachment_delete_operation": {
                    "id": "delete-1",
                    "claimed_at": started_at,
                },
            }
        ]
    )
    parents = _FilterAwareCollection(
        [
            {
                "_id": "parent-a",
                "session_id": "session-1",
                "trace_id": "trace-a",
                "events": [],
                "event_count": 0,
                "event_revision": 0,
                "updated_at": started_at,
            }
        ]
    )
    chunks = _BlockingChunksDelete(
        [
            {
                "_id": "chunk-a",
                "session_id": "session-1",
                "trace_id": "trace-a",
                "append_fence_revision": 0,
                "event_count": 0,
                "updated_at": started_at,
            }
        ]
    )
    session_storage = SessionStorage()
    session_storage._collection = session_collection
    trace_storage = TraceStorage()
    trace_storage._collection = parents
    trace_storage._chunks_collection = chunks
    trace_storage._session_storage = session_storage

    stale_cleanup = asyncio.create_task(
        trace_storage.discard_session_trace_writes_after_lease_loss(
            "session-1",
            "writer-a",
            ["trace-a"],
        )
    )
    await chunks.delete_started.wait()

    clock["now"] = started_at + timedelta(minutes=6)
    replacement_cleanup = await trace_storage.discard_session_trace_writes_after_lease_loss(
        "session-1",
        "writer-b",
        [],
    )
    cancelled = await session_storage.cancel_attachment_delete_operation(
        "session-1",
        "delete-1",
    )
    new_writer = await session_storage.acquire_trace_write("session-1")
    appended = await trace_storage.append_event(
        "trace-a",
        "message:chunk",
        {"content": "new-generation"},
    )
    await chunks.update_one(
        {"_id": "chunk-a"},
        {
            "$inc": {"append_fence_revision": 1, "event_count": 1},
            "$set": {"updated_at": clock["now"]},
        },
    )

    chunks.allow_delete.set()
    stale_result = await stale_cleanup
    if new_writer is not None:
        await session_storage.release_trace_write("session-1", new_writer)

    assert replacement_cleanup is True
    assert cancelled is True
    assert isinstance(new_writer, str)
    assert appended is True
    assert stale_result is False
    assert chunks.ids() == {"chunk-a"}
    assert chunks.documents[0]["append_fence_revision"] == 1
    assert parents.ids() == {"parent-a"}
    assert parents.documents[0]["events"][0]["data"] == {"content": "new-generation"}


@pytest.mark.asyncio
async def test_missing_session_cleanup_keeps_direct_broad_delete_contract() -> None:
    session_storage = SessionStorage()
    session_storage._collection = _FilterAwareCollection([])
    trace_storage, parents, chunks = _trace_storage_with_documents(
        [
            {
                "_id": "parent-a",
                "session_id": "session-missing",
                "trace_id": "trace-a",
            }
        ],
        [
            {
                "_id": "chunk-a",
                "session_id": "session-missing",
                "trace_id": "trace-a",
            }
        ],
    )
    trace_storage._session_storage = session_storage

    discarded = await trace_storage.discard_session_trace_writes_after_lease_loss(
        "session-missing",
        "writer-lost",
        ["trace-a"],
    )

    broad_query = {
        "session_id": "session-missing",
        "trace_id": {"$in": ["trace-a"]},
    }
    assert discarded is True
    assert parents.documents == []
    assert chunks.documents == []
    assert parents.delete_calls == [broad_query]
    assert chunks.delete_calls == [broad_query]


@pytest.mark.asyncio
async def test_active_trace_cleanup_guard_blocks_delete_claim_and_anchor_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _skip_indexes(_storage: SessionStorage) -> None:
        return None

    now = datetime(2026, 8, 11, 14, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(SessionStorage, "ensure_indexes_if_needed", _skip_indexes)
    monkeypatch.setattr(
        "src.infra.session.session_attachment_operations.utc_now",
        lambda: now,
    )
    collection = _FilterAwareCollection(
        [
            {
                "_id": "session-doc",
                "session_id": "session-1",
                "trace_writer_leases": [],
                "attachment_delete_operation": {
                    "id": "delete-1",
                    "claimed_at": now,
                    "cleanup_guard": {
                        "id": "guard-1",
                        "writer_lease_id": "writer-a",
                        "expires_at": now + timedelta(minutes=1),
                    },
                },
            }
        ]
    )
    storage = SessionStorage()
    storage._collection = collection

    observed_claim = await storage.claim_attachment_delete_operation("session-1")
    deleted = await storage.delete_claimed_session("session-1", "delete-1")

    assert observed_claim is None
    assert deleted is False
    assert collection.ids() == {"session-doc"}


@pytest.mark.asyncio
async def test_trace_cleanup_guard_refuses_fenced_session_with_a_live_writer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _skip_indexes(_storage: SessionStorage) -> None:
        return None

    now = datetime(2026, 8, 11, 14, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(SessionStorage, "ensure_indexes_if_needed", _skip_indexes)
    monkeypatch.setattr(
        "src.infra.session.session_attachment_operations.utc_now",
        lambda: now,
    )
    session_collection = _FilterAwareCollection(
        [
            {
                "_id": "session-doc",
                "session_id": "session-1",
                "trace_writer_leases": [
                    {
                        "id": "writer-live",
                        "expires_at": now + timedelta(minutes=1),
                    }
                ],
                "attachment_delete_operation": {
                    "id": "delete-1",
                    "claimed_at": now,
                },
            }
        ]
    )
    session_storage = SessionStorage()
    session_storage._collection = session_collection
    trace_storage, parents, chunks = _trace_storage_with_documents(
        [{"_id": "parent-a", "session_id": "session-1", "trace_id": "trace-a"}],
        [{"_id": "chunk-a", "session_id": "session-1", "trace_id": "trace-a"}],
    )
    trace_storage._session_storage = session_storage

    cleanup_result = await trace_storage.discard_session_trace_writes_after_lease_loss(
        "session-1",
        "writer-live",
        ["trace-a"],
    )

    assert cleanup_result is False
    assert parents.ids() == {"parent-a"}
    assert chunks.ids() == {"chunk-a"}
    assert "cleanup_guard" not in session_collection.documents[0]["attachment_delete_operation"]


@pytest.mark.asyncio
async def test_trace_cleanup_guard_exact_release_applies_pending_delete_cancel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _skip_indexes(_storage: SessionStorage) -> None:
        return None

    now = datetime(2026, 8, 11, 14, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(SessionStorage, "ensure_indexes_if_needed", _skip_indexes)
    monkeypatch.setattr(
        "src.infra.session.session_attachment_operations.utc_now",
        lambda: now,
    )
    collection = _FilterAwareCollection(
        [
            {
                "_id": "session-doc",
                "session_id": "session-1",
                "trace_writer_leases": [],
                "attachment_delete_operation": {
                    "id": "delete-1",
                    "claimed_at": now,
                    "cleanup_guard": {
                        "id": "guard-1",
                        "writer_lease_id": "writer-a",
                        "expires_at": now + timedelta(minutes=1),
                    },
                },
            }
        ]
    )
    storage = SessionStorage()
    storage._collection = collection

    assert await storage.cancel_attachment_delete_operation("session-1", "delete-1") is True
    operation_after_cancel = deepcopy(collection.documents[0].get("attachment_delete_operation"))
    wrong_operation_release = await storage.release_trace_cleanup_guard(
        "session-1",
        "delete-forged",
        "guard-1",
    )
    forged_guard_release = await storage.release_trace_cleanup_guard(
        "session-1",
        "delete-1",
        "guard-forged",
    )
    operation_after_forged_releases = deepcopy(
        collection.documents[0].get("attachment_delete_operation")
    )
    exact_release = await storage.release_trace_cleanup_guard(
        "session-1",
        "delete-1",
        "guard-1",
    )
    writer_after_release = await storage.acquire_trace_write("session-1")
    if writer_after_release is not None:
        await storage.release_trace_write("session-1", writer_after_release)

    assert isinstance(operation_after_cancel, dict)
    assert operation_after_cancel["cancel_requested"] is True
    assert wrong_operation_release is False
    assert forged_guard_release is False
    assert operation_after_forged_releases == operation_after_cancel
    assert exact_release is True
    assert "attachment_delete_operation" not in collection.documents[0]
    assert isinstance(writer_after_release, str)


@pytest.mark.asyncio
async def test_trace_cleanup_guard_renewal_extends_only_the_exact_live_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started_at = datetime(2026, 8, 11, 14, 0, tzinfo=timezone.utc)
    clock = {"now": started_at}
    monkeypatch.setattr(
        "src.infra.session.session_attachment_operations.utc_now",
        lambda: clock["now"],
    )
    collection = _FilterAwareCollection(
        [
            {
                "_id": "session-doc",
                "session_id": "session-1",
                "trace_writer_leases": [],
                "attachment_delete_operation": {
                    "id": "delete-1",
                    "claimed_at": started_at,
                },
            }
        ]
    )
    storage = SessionStorage()
    storage._collection = collection

    original_guard = await storage.acquire_trace_cleanup_guard(
        "session-1",
        "writer-a",
    )
    assert original_guard is not None
    original_guard_id = original_guard["id"]
    clock["now"] = started_at + timedelta(minutes=4)

    wrong_writer_renewal = await storage.renew_trace_cleanup_guard(
        "session-1",
        "delete-1",
        original_guard_id,
        "writer-forged",
    )
    exact_renewal = await storage.renew_trace_cleanup_guard(
        "session-1",
        "delete-1",
        original_guard_id,
        "writer-a",
    )
    clock["now"] = started_at + timedelta(minutes=6)
    premature_takeover = await storage.acquire_trace_cleanup_guard(
        "session-1",
        "writer-b",
    )
    clock["now"] = started_at + timedelta(minutes=10)
    replacement_guard = await storage.acquire_trace_cleanup_guard(
        "session-1",
        "writer-b",
    )
    stale_renewal = await storage.renew_trace_cleanup_guard(
        "session-1",
        "delete-1",
        original_guard_id,
        "writer-a",
    )

    assert wrong_writer_renewal is False
    assert exact_renewal is True
    assert premature_takeover is None
    assert replacement_guard is not None
    assert replacement_guard["id"] != original_guard_id
    assert stale_renewal is False


@pytest.mark.asyncio
async def test_expired_trace_cleanup_guard_takeover_rejects_stale_and_wrong_operation_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _skip_indexes(_storage: SessionStorage) -> None:
        return None

    now = datetime(2026, 8, 11, 14, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(SessionStorage, "ensure_indexes_if_needed", _skip_indexes)
    monkeypatch.setattr(
        "src.infra.session.session_attachment_operations.utc_now",
        lambda: now,
    )
    collection = _FilterAwareCollection(
        [
            {
                "_id": "session-doc",
                "session_id": "session-1",
                "trace_writer_leases": [],
                "attachment_delete_operation": {
                    "id": "delete-1",
                    "claimed_at": now,
                    "cleanup_guard": {
                        "id": "crashed-guard",
                        "writer_lease_id": "writer-crashed",
                        "expires_at": now - timedelta(seconds=1),
                    },
                },
            }
        ]
    )
    storage = SessionStorage()
    storage._collection = collection

    replacement = await storage.acquire_trace_cleanup_guard("session-1", "writer-a")
    assert replacement is not None
    replacement_id = replacement["id"]
    stale_release = await storage.release_trace_cleanup_guard(
        "session-1",
        "delete-1",
        "crashed-guard",
    )
    wrong_operation_release = await storage.release_trace_cleanup_guard(
        "session-1",
        "delete-forged",
        replacement_id,
    )
    operation_before_exact_release = deepcopy(
        collection.documents[0]["attachment_delete_operation"]
    )
    exact_release = await storage.release_trace_cleanup_guard(
        "session-1",
        "delete-1",
        replacement_id,
    )

    assert replacement_id != "crashed-guard"
    assert replacement["delete_operation_id"] == "delete-1"
    assert replacement["session_missing"] is False
    assert stale_release is False
    assert wrong_operation_release is False
    assert operation_before_exact_release["cleanup_guard"]["id"] == replacement_id
    assert exact_release is True
    assert "cleanup_guard" not in collection.documents[0]["attachment_delete_operation"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "malformed_guard",
    [
        "corrupt",
        {"writer_lease_id": "writer-a", "expires_at": datetime(2026, 8, 11)},
        {"id": "guard-1", "writer_lease_id": 42, "expires_at": datetime(2026, 8, 11)},
        {"id": "guard-1", "writer_lease_id": "writer-a", "expires_at": "tomorrow"},
    ],
)
async def test_malformed_trace_cleanup_guard_fails_closed_across_lifecycle(
    monkeypatch: pytest.MonkeyPatch,
    malformed_guard: object,
) -> None:
    async def _skip_indexes(_storage: SessionStorage) -> None:
        return None

    now = datetime(2026, 8, 11, 14, 0, tzinfo=timezone.utc)
    monkeypatch.setattr(SessionStorage, "ensure_indexes_if_needed", _skip_indexes)
    monkeypatch.setattr(
        "src.infra.session.session_attachment_operations.utc_now",
        lambda: now,
    )
    original_session = {
        "_id": "session-doc",
        "session_id": "session-1",
        "trace_writer_leases": [],
        "attachment_delete_operation": {
            "id": "delete-1",
            "claimed_at": now,
            "cleanup_guard": malformed_guard,
        },
    }
    session_collection = _FilterAwareCollection([original_session])
    session_storage = SessionStorage()
    session_storage._collection = session_collection
    trace_storage, parents, chunks = _trace_storage_with_documents(
        [{"_id": "parent-a", "session_id": "session-1", "trace_id": "trace-a"}],
        [{"_id": "chunk-a", "session_id": "session-1", "trace_id": "trace-a"}],
    )
    trace_storage._session_storage = session_storage

    cleanup_result = await trace_storage.discard_session_trace_writes_after_lease_loss(
        "session-1",
        "writer-a",
        ["trace-a"],
    )
    writer_result = await session_storage.acquire_trace_write("session-1")
    claim_result = await session_storage.claim_attachment_delete_operation("session-1")
    delete_result = await session_storage.delete_claimed_session("session-1", "delete-1")
    cancel_result = await session_storage.cancel_attachment_delete_operation(
        "session-1",
        "delete-1",
    )

    assert cleanup_result is False
    assert writer_result is None
    assert claim_result is None
    assert delete_result is False
    assert cancel_result is False
    assert session_collection.documents == [original_session]
    assert parents.ids() == {"parent-a"}
    assert chunks.ids() == {"chunk-a"}


@pytest.mark.asyncio
async def test_trace_writer_lease_renewal_and_exact_release_keep_live_writer_fenced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _skip_indexes(_storage: SessionStorage) -> None:
        return None

    clock = {"now": datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)}
    monkeypatch.setattr(SessionStorage, "ensure_indexes_if_needed", _skip_indexes)
    monkeypatch.setattr(
        "src.infra.session.session_attachment_operations.utc_now",
        lambda: clock["now"],
    )
    collection = _FilterAwareCollection(
        [{"_id": "session-doc", "session_id": "session-1", "user_id": "owner-a"}]
    )
    storage = SessionStorage()
    storage._collection = collection

    first_lease = await storage.acquire_trace_write("session-1")
    second_lease = await storage.acquire_trace_write("session-1")

    assert isinstance(first_lease, str)
    assert isinstance(second_lease, str)
    assert second_lease != first_lease

    initial_expiry = next(
        lease["expires_at"]
        for lease in collection.documents[0]["trace_writer_leases"]
        if lease["id"] == first_lease
    )
    clock["now"] += timedelta(minutes=4)
    assert await storage.renew_trace_write("session-1", first_lease) is True
    renewed_expiry = next(
        lease["expires_at"]
        for lease in collection.documents[0]["trace_writer_leases"]
        if lease["id"] == first_lease
    )
    assert renewed_expiry > initial_expiry

    # The second lease is now stale, but the first lease remains live because it heartbeated.
    clock["now"] += timedelta(minutes=2)
    await storage.release_trace_write("session-1", f"{first_lease}-forged")
    assert await storage.claim_attachment_delete_operation("session-1") is None

    await storage.release_trace_write("session-1", first_lease)
    claim = await storage.claim_attachment_delete_operation("session-1")

    assert claim is not None
    assert claim["acquired"] is True
    await storage.release_trace_write("session-1", second_lease)


@pytest.mark.asyncio
async def test_create_trace_compensates_a_late_insert_after_session_is_delete_fenced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _skip_session_indexes(_storage: SessionStorage) -> None:
        return None

    async def _skip_trace_indexes(_storage: TraceStorage) -> None:
        return None

    class _BlockingTraceCollection(_FilterAwareCollection):
        def __init__(self) -> None:
            super().__init__([])
            self.insert_started = asyncio.Event()
            self.allow_insert = asyncio.Event()

        async def insert_one(self, document: dict[str, Any]):
            self.insert_started.set()
            await self.allow_insert.wait()
            stored = {**document, "_id": "late-trace"}
            return await super().insert_one(stored)

    monkeypatch.setattr(SessionStorage, "ensure_indexes_if_needed", _skip_session_indexes)
    monkeypatch.setattr(TraceStorage, "ensure_indexes_if_needed", _skip_trace_indexes)
    monkeypatch.setattr(
        "src.infra.session.session_attachment_operations.TRACE_WRITER_HEARTBEAT_INTERVAL_SECONDS",
        0.001,
    )
    session_collection = _FilterAwareCollection(
        [{"_id": "session-doc", "session_id": "session-1", "user_id": "owner-a"}]
    )
    trace_collection = _BlockingTraceCollection()
    session_storage = SessionStorage()
    session_storage._collection = session_collection
    trace_storage = TraceStorage()
    trace_storage._collection = trace_collection
    trace_storage._chunks_collection = _FilterAwareCollection([])
    trace_storage._session_storage = session_storage

    writer = asyncio.create_task(
        trace_storage.create_trace("trace-late", "session-1", user_id="owner-a")
    )
    await trace_collection.insert_started.wait()
    session_collection.documents[0]["trace_writer_leases"][0]["expires_at"] = datetime.now(
        timezone.utc
    ) - timedelta(seconds=1)
    claim = await session_storage.claim_attachment_delete_operation("session-1")
    assert claim is not None and claim["acquired"] is True
    for _attempt in range(1000):
        if writer.cancelling():
            break
        await asyncio.sleep(0.001)
    assert writer.cancelling()

    trace_collection.allow_insert.set()

    assert await writer is False
    assert trace_collection.documents == []
    assert session_collection.documents[0]["attachment_delete_operation"]["id"] == claim["id"]


@pytest.mark.asyncio
async def test_create_trace_keeps_new_writer_events_when_expired_lease_is_not_delete_fenced(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _skip_session_indexes(_storage: SessionStorage) -> None:
        return None

    async def _skip_trace_indexes(_storage: TraceStorage) -> None:
        return None

    class _BlockingMarkerCleanupCollection(_FilterAwareCollection):
        def __init__(self) -> None:
            super().__init__([])
            self.cleanup_started = asyncio.Event()
            self.allow_cleanup = asyncio.Event()

        async def insert_one(self, document: dict[str, Any]):
            return await super().insert_one({**document, "_id": "shared-trace"})

        async def update_one(self, query: dict[str, Any], update: dict, **kwargs):
            if "_session_trace_write_lease_id" in update.get("$unset", {}):
                self.cleanup_started.set()
                await self.allow_cleanup.wait()
            return await super().update_one(query, update, **kwargs)

    monkeypatch.setattr(SessionStorage, "ensure_indexes_if_needed", _skip_session_indexes)
    monkeypatch.setattr(TraceStorage, "ensure_indexes_if_needed", _skip_trace_indexes)
    session_collection = _FilterAwareCollection(
        [{"_id": "session-doc", "session_id": "session-1", "user_id": "owner-a"}]
    )
    trace_collection = _BlockingMarkerCleanupCollection()
    session_storage = SessionStorage()
    session_storage._collection = session_collection
    trace_storage = TraceStorage()
    trace_storage._collection = trace_collection
    trace_storage._chunks_collection = _FilterAwareCollection([])
    trace_storage._session_storage = session_storage

    writer_a = asyncio.create_task(
        trace_storage.create_trace("trace-shared", "session-1", user_id="owner-a")
    )
    await trace_collection.cleanup_started.wait()
    lease_a = session_collection.documents[0]["trace_writer_leases"][0]["id"]
    session_collection.documents[0]["trace_writer_leases"][0]["expires_at"] = datetime.now(
        timezone.utc
    ) - timedelta(seconds=1)
    lease_b = await session_storage.acquire_trace_write("session-1")
    assert isinstance(lease_b, str) and lease_b != lease_a
    assert (
        await trace_storage.append_event(
            "trace-shared",
            "message:chunk",
            {"content": "new-writer-event"},
        )
        is True
    )

    writer_a.cancel()
    trace_collection.allow_cleanup.set()
    writer_result = await writer_a
    documents_after_recovery = deepcopy(trace_collection.documents)
    await session_storage.release_trace_write("session-1", lease_b)

    assert writer_result is False
    assert len(documents_after_recovery) == 1
    assert documents_after_recovery[0]["events"][0]["data"] == {"content": "new-writer-event"}
    assert documents_after_recovery[0]["event_count"] == 1
    assert "_session_trace_write_lease_id" not in documents_after_recovery[0]
    assert "attachment_delete_operation" not in session_collection.documents[0]


@pytest.mark.asyncio
async def test_create_trace_compensates_when_lease_is_lost_during_marker_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _skip_session_indexes(_storage: SessionStorage) -> None:
        return None

    async def _skip_trace_indexes(_storage: TraceStorage) -> None:
        return None

    class _BlockingMarkerCleanupCollection(_FilterAwareCollection):
        def __init__(self) -> None:
            super().__init__([])
            self.cleanup_started = asyncio.Event()
            self.allow_cleanup = asyncio.Event()

        async def insert_one(self, document: dict[str, Any]):
            return await super().insert_one({**document, "_id": "cleanup-trace"})

        async def update_one(self, query: dict[str, Any], update: dict, **kwargs):
            if "_session_trace_write_lease_id" in update.get("$unset", {}):
                self.cleanup_started.set()
                await self.allow_cleanup.wait()
            return await super().update_one(query, update, **kwargs)

    monkeypatch.setattr(SessionStorage, "ensure_indexes_if_needed", _skip_session_indexes)
    monkeypatch.setattr(TraceStorage, "ensure_indexes_if_needed", _skip_trace_indexes)
    monkeypatch.setattr(
        "src.infra.session.session_attachment_operations.TRACE_WRITER_HEARTBEAT_INTERVAL_SECONDS",
        0.001,
    )
    session_collection = _FilterAwareCollection(
        [{"_id": "session-doc", "session_id": "session-1", "user_id": "owner-a"}]
    )
    trace_collection = _BlockingMarkerCleanupCollection()
    session_storage = SessionStorage()
    session_storage._collection = session_collection
    trace_storage = TraceStorage()
    trace_storage._collection = trace_collection
    trace_storage._chunks_collection = _FilterAwareCollection([])
    trace_storage._session_storage = session_storage

    writer = asyncio.create_task(
        trace_storage.create_trace("trace-cleanup", "session-1", user_id="owner-a")
    )
    await trace_collection.cleanup_started.wait()
    session_collection.documents[0]["trace_writer_leases"][0]["expires_at"] = datetime.now(
        timezone.utc
    ) - timedelta(seconds=1)
    claim = await session_storage.claim_attachment_delete_operation("session-1")
    assert claim is not None and claim["acquired"] is True
    assert await session_storage.delete_claimed_session("session-1", claim["id"]) is True
    for _attempt in range(1000):
        if writer.cancelling():
            break
        await asyncio.sleep(0.001)
    assert writer.cancelling()

    trace_collection.allow_cleanup.set()

    assert await writer is False
    assert trace_collection.documents == []


@pytest.mark.asyncio
async def test_create_trace_survives_repeated_cancellation_until_insert_is_compensated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _skip_trace_indexes(_storage: TraceStorage) -> None:
        return None

    async def _acquire_cleanup_guard(
        _session_id: str,
        _lease_id: str,
    ) -> dict[str, Any]:
        return {
            "id": "cleanup-guard",
            "delete_operation_id": "delete-operation",
            "session_missing": False,
        }

    async def _release_cleanup_guard(
        _session_id: str,
        _delete_operation_id: str,
        _guard_id: str,
    ) -> bool:
        return True

    async def _renew_cleanup_guard(
        _session_id: str,
        _delete_operation_id: str,
        _guard_id: str,
        _writer_lease_id: str,
    ) -> bool:
        return True

    class _BlockingTraceCollection(_FilterAwareCollection):
        def __init__(self) -> None:
            super().__init__([])
            self.insert_started = asyncio.Event()
            self.allow_insert = asyncio.Event()
            self.insert_completed = False
            self.insert_cancelled = False

        async def insert_one(self, document: dict[str, Any]):
            self.insert_started.set()
            try:
                await self.allow_insert.wait()
            except asyncio.CancelledError:
                self.insert_cancelled = True
                raise
            self.insert_completed = True
            return await super().insert_one({**document, "_id": "repeated-cancel-trace"})

    class _TraceStorage(TraceStorage):
        def __init__(self) -> None:
            super().__init__()
            self._collection = _BlockingTraceCollection()
            self._chunks_collection = _FilterAwareCollection([])
            self._session_storage = SimpleNamespace(
                acquire_trace_cleanup_guard=_acquire_cleanup_guard,
                release_trace_cleanup_guard=_release_cleanup_guard,
                renew_trace_cleanup_guard=_renew_cleanup_guard,
            )
            self.owner: asyncio.Task[Any] | None = None
            self.second_cancel_turn_completed = asyncio.Event()
            self.second_cancel_scheduled = False
            self.released: list[tuple[str, str]] = []

        async def acquire_session_trace_write(self, session_id: str) -> str:
            del session_id
            self.owner = asyncio.current_task()
            return "lease-repeated-cancel"

        async def validate_session_trace_write(self, session_id: str, lease_id: str) -> bool:
            del session_id, lease_id
            if not self.second_cancel_scheduled:
                self.second_cancel_scheduled = True
                loop = asyncio.get_running_loop()

                def _cancel_owner_again() -> None:
                    assert self.owner is not None
                    self.owner.cancel()
                    loop.call_soon(self.second_cancel_turn_completed.set)

                loop.call_soon(_cancel_owner_again)
            return False

        async def release_session_trace_write(self, session_id: str, lease_id: str) -> None:
            self.released.append((session_id, lease_id))

    monkeypatch.setattr(TraceStorage, "ensure_indexes_if_needed", _skip_trace_indexes)
    trace_storage = _TraceStorage()

    writer = asyncio.create_task(
        trace_storage.create_trace("trace-repeated", "session-1", user_id="owner-a")
    )
    await trace_storage.collection.insert_started.wait()
    writer.cancel()
    trace_storage.collection.allow_insert.set()
    await trace_storage.second_cancel_turn_completed.wait()

    assert await writer is False
    assert trace_storage.collection.insert_completed is True
    assert trace_storage.collection.insert_cancelled is False
    assert trace_storage.collection.documents == []
    assert trace_storage.released == [("session-1", "lease-repeated-cancel")]


@pytest.mark.asyncio
async def test_create_trace_does_not_cancel_ambiguous_insert_while_lease_is_live(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _skip_trace_indexes(_storage: TraceStorage) -> None:
        return None

    class _AmbiguousInsertCollection(_FilterAwareCollection):
        def __init__(self) -> None:
            super().__init__([])
            self.insert_started = asyncio.Event()
            self.allow_insert = asyncio.Event()
            self.wrapper_cancelled = False
            self.server_task: asyncio.Task[Any] | None = None

        async def insert_one(self, document: dict[str, Any]):
            self.insert_started.set()

            async def _server_insert():
                await self.allow_insert.wait()
                return await super(_AmbiguousInsertCollection, self).insert_one(
                    {**document, "_id": "ambiguous-live-trace"}
                )

            self.server_task = asyncio.create_task(_server_insert())
            try:
                return await asyncio.shield(self.server_task)
            except asyncio.CancelledError:
                self.wrapper_cancelled = True
                raise

    class _TraceStorage(TraceStorage):
        def __init__(self) -> None:
            super().__init__()
            self._collection = _AmbiguousInsertCollection()
            self.lease_is_active = False
            self.released: list[tuple[str, str]] = []

        async def acquire_session_trace_write(self, session_id: str) -> str:
            del session_id
            self.lease_is_active = True
            return "lease-live-cancel"

        async def validate_session_trace_write(self, session_id: str, lease_id: str) -> bool:
            del session_id, lease_id
            return self.lease_is_active

        async def release_session_trace_write(self, session_id: str, lease_id: str) -> None:
            self.lease_is_active = False
            self.released.append((session_id, lease_id))

    monkeypatch.setattr(TraceStorage, "ensure_indexes_if_needed", _skip_trace_indexes)
    trace_storage = _TraceStorage()
    writer = asyncio.create_task(
        trace_storage.create_trace("trace-live", "session-1", user_id="owner-a")
    )
    await trace_storage.collection.insert_started.wait()

    writer.cancel()
    cancel_turn_completed = asyncio.Event()
    loop = asyncio.get_running_loop()
    loop.call_soon(lambda: loop.call_soon(cancel_turn_completed.set))
    await cancel_turn_completed.wait()
    lease_remained_active_while_insert_pending = trace_storage.lease_is_active
    wrapper_was_cancelled = trace_storage.collection.wrapper_cancelled
    trace_storage.collection.allow_insert.set()

    with pytest.raises(asyncio.CancelledError):
        await writer

    assert trace_storage.collection.server_task is not None
    await trace_storage.collection.server_task
    assert lease_remained_active_while_insert_pending is True
    assert wrapper_was_cancelled is False
    assert len(trace_storage.collection.documents) == 1
    assert "_session_trace_write_lease_id" not in trace_storage.collection.documents[0]
    assert trace_storage.released == [("session-1", "lease-live-cancel")]


@pytest.mark.asyncio
async def test_concurrent_delete_request_cannot_cancel_the_owner_fence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clear_started = asyncio.Event()
    allow_owner_to_finish = asyncio.Event()

    class _Storage(_SessionOperationStorage):
        def __init__(self) -> None:
            super().__init__()
            self.cancel_calls: list[str] = []

        async def cancel_attachment_delete_operation(
            self, session_id: str, operation_id: str
        ) -> bool:
            self.cancel_calls.append(operation_id)
            return await super().cancel_attachment_delete_operation(session_id, operation_id)

    class _Manager(SessionManager):
        async def clear_session_messages(self, _session_id: str) -> int:
            clear_started.set()
            await allow_owner_to_finish.wait()
            return 0

    class _RevealedStorage:
        async def delete_by_session(self, _session_id: str) -> int:
            return 0

    async def _skip_checkpoints(_session_id: str) -> None:
        return None

    monkeypatch.setattr(
        "src.infra.revealed_file.storage.get_revealed_file_storage",
        lambda: _RevealedStorage(),
    )
    monkeypatch.setattr(
        "src.infra.session.manager.delete_checkpoints_for_thread",
        _skip_checkpoints,
    )
    storage = _Storage()
    manager = _Manager()
    manager.storage = storage
    manager._trace_storage = _TraceStorage()

    owner = asyncio.create_task(manager.delete_session("session-1"))
    await clear_started.wait()

    with pytest.raises(SessionError, match="session_delete_in_progress"):
        await manager.delete_session("session-1")
    assert storage.cancel_calls == []
    assert storage.delete_operation == {"id": "delete-operation-1"}

    allow_owner_to_finish.set()
    assert await owner is True
    assert storage.cancel_calls == []
