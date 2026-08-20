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
                    if actual is _MISSING or actual <= operand:
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

    async def update_one(self, query: dict[str, Any], update: dict, **_kwargs):
        for document in self.documents:
            if _matches(document, query):
                before = deepcopy(document)
                _apply_update(document, update)
                return SimpleNamespace(
                    matched_count=1,
                    modified_count=int(document != before),
                )
        return SimpleNamespace(matched_count=0, modified_count=0)

    async def update_many(self, query: dict[str, Any], update: dict, **_kwargs):
        modified_count = 0
        for document in self.documents:
            if _matches(document, query):
                before = deepcopy(document)
                _apply_update(document, update)
                modified_count += int(document != before)
        return SimpleNamespace(matched_count=modified_count, modified_count=modified_count)

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


class _FileRecordStorage:
    def __init__(self) -> None:
        self.released_counts: list[Counter[str]] = []
        self.operation_ids: list[str] = []
        self.applied_operation_ids: set[str] = set()
        self.release_error: Exception | None = None

    async def release_reference_counts(
        self, counts: Counter[str], *, operation_id: str, uploaded_by: str
    ) -> int:
        assert uploaded_by == "owner-a"
        if self.release_error:
            raise self.release_error
        self.operation_ids.append(operation_id)
        if operation_id in self.applied_operation_ids:
            return 0
        self.applied_operation_ids.add(operation_id)
        self.released_counts.append(counts)
        return len(counts)


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

    async def expire_stale_running_traces(self, _session_id: str, **_kwargs) -> int:
        return 0

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
    ) -> bool:
        assert self.server_operation and operation_id == self.server_operation["id"]
        group = self.server_operation["groups"][group_id]
        if group["status"] != expected_status:
            return False
        group["status"] = status
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
    assert manager.storage.server_operation["groups"]["parent-0"]["status"] == "deleted"

    file_records.release_error = None
    assert await manager.clear_session_messages("session-1") == 1
    assert file_records.released_counts == [Counter({"attachments/u1/a.png": 1})]
    assert manager.storage.server_operation is None


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
            self, counts: Counter[str], *, operation_id: str, uploaded_by: str
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
    # Pin "now" so the running trace stays fresh relative to the stale-TTL.
    monkeypatch.setattr("src.infra.session.trace_attachment_cleanup.utc_now", lambda: cutoff)
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
                # An in-flight chunk write marker fences any new replacement,
                # keeping the existing chunks untouched.
                "attachment_chunk_write_operation": {
                    "id": "in-flight",
                    "kind": "append",
                    "revision": 3,
                },
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


@pytest.mark.asyncio
async def test_expire_stale_running_traces_transitions_only_stale_runs() -> None:
    cutoff = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
    trace_storage, parents, _chunks = _trace_storage_with_documents(
        [
            {
                "_id": "parent-stale",
                "session_id": "session-1",
                "trace_id": "trace-stale",
                "status": "running",
                "updated_at": cutoff - timedelta(minutes=30),
                "events": [],
            },
            {
                "_id": "parent-fresh",
                "session_id": "session-1",
                "trace_id": "trace-fresh",
                "status": "running",
                "updated_at": cutoff - timedelta(minutes=1),
                "events": [],
            },
            {
                "_id": "parent-terminal",
                "session_id": "session-1",
                "trace_id": "trace-terminal",
                "status": "completed",
                "updated_at": cutoff - timedelta(hours=2),
                "events": [],
            },
            {
                "_id": "parent-other-session",
                "session_id": "session-2",
                "trace_id": "trace-other",
                "status": "running",
                "updated_at": cutoff - timedelta(hours=3),
                "events": [],
            },
        ],
        [],
    )

    expired = await trace_storage.expire_stale_running_traces("session-1", now=cutoff)

    assert expired == 1
    stale = next(d for d in parents.documents if d["_id"] == "parent-stale")
    assert stale["status"] == "error"
    assert stale["completed_at"] == cutoff
    assert stale["metadata"]["error_code"] == "stale_run_recovery"
    # updated_at is the CAS version used by the clear/delete snapshot; keep it.
    assert stale["updated_at"] == cutoff - timedelta(minutes=30)
    fresh = next(d for d in parents.documents if d["_id"] == "parent-fresh")
    assert fresh["status"] == "running"
    terminal = next(d for d in parents.documents if d["_id"] == "parent-terminal")
    assert terminal["status"] == "completed"
    other = next(d for d in parents.documents if d["_id"] == "parent-other-session")
    assert other["status"] == "running"


@pytest.mark.asyncio
async def test_delete_session_expires_stale_running_trace_instead_of_refusing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cutoff = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("src.infra.session.trace_attachment_cleanup.utc_now", lambda: cutoff)
    trace_storage, parents, _chunks = _trace_storage_with_documents(
        [
            {
                "_id": "parent-running",
                "session_id": "session-1",
                "trace_id": "trace-running",
                "status": "running",
                "updated_at": cutoff - timedelta(minutes=30),
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

    assert await manager.delete_session("session-1") is True

    assert deleted_sessions == ["session-1"]
    assert parents.ids() == set()


@pytest.mark.asyncio
async def test_stale_delete_fence_is_reclaimed_by_new_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("src.infra.session.session_attachment_operations.utc_now", lambda: now)

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
                "attachment_delete_operation": {
                    "id": "old-fence",
                    "claimed_at": now - timedelta(minutes=11),
                },
            }
        ]
    )
    storage = SessionStorage()
    storage._collection = collection

    claim = await storage.claim_attachment_delete_operation("session-1")

    assert claim is not None
    assert claim["acquired"] is True
    assert claim["id"] != "old-fence"

    doc = collection.documents[0]
    assert doc["attachment_delete_operation"]["id"] == claim["id"]
    assert await storage.delete_claimed_session("session-1", claim["id"]) is True


@pytest.mark.asyncio
async def test_fresh_delete_fence_still_blocks_new_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = datetime(2026, 8, 11, 12, 0, tzinfo=timezone.utc)
    monkeypatch.setattr("src.infra.session.session_attachment_operations.utc_now", lambda: now)

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
                "attachment_delete_operation": {
                    "id": "active-fence",
                    "claimed_at": now - timedelta(seconds=30),
                },
            }
        ]
    )
    storage = SessionStorage()
    storage._collection = collection

    claim = await storage.claim_attachment_delete_operation("session-1")

    assert claim == {
        "id": "active-fence",
        "claimed_at": now - timedelta(seconds=30),
        "acquired": False,
    }
    assert collection.documents[0]["attachment_delete_operation"]["id"] == "active-fence"
