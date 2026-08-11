from __future__ import annotations

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

    async def delete_many(self, query: dict[str, Any]):
        self.delete_calls.append(deepcopy(query))
        kept: list[dict[str, Any]] = []
        deleted_count = 0
        skipped: set[object] = set()
        for document in self.documents:
            document_id = document.get("_id")
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
        return {
            "events": deepcopy(self.events),
            "trace_ids": trace_ids,
            "parent_ids": ["snapshot-parent"] if self.events else [],
            "chunk_ids": [],
        }

    async def delete_trace_snapshot_strict(self, _parent_ids: list, _chunk_ids: list) -> int:
        if self.delete_error:
            raise self.delete_error
        self.deleted_session_ids.append(self.snapshot_session_id)
        return len(_parent_ids)

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

    async def persist_attachment_clear_snapshot(
        self,
        _session_id: str,
        operation_id: str,
        counts: dict,
        trace_ids: list[str],
        *,
        parent_ids: list,
        chunk_ids: list,
    ) -> dict:
        assert self.server_operation and operation_id == self.server_operation["id"]
        self.server_operation.setdefault("counts", counts)
        self.server_operation.setdefault("trace_ids", trace_ids)
        self.server_operation.setdefault("parent_ids", parent_ids)
        self.server_operation.setdefault("chunk_ids", chunk_ids)
        return self.server_operation

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
    ) -> dict:
        assert self.server_operation and operation_id == self.server_operation["id"]
        self.server_operation.update(
            {
                "counts": counts,
                "trace_ids": trace_ids,
                "parent_ids": parent_ids,
                "chunk_ids": chunk_ids,
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
async def test_clear_session_messages_preserves_traces_when_counted_release_fails() -> None:
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

    assert trace_storage.deleted_session_ids == []


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
    assert len(file_records.operation_ids) == 2
    assert file_records.operation_ids[0] == file_records.operation_ids[1]
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
        ):
            assert operation_id == "server-operation"
            self.server_operation.update(
                {
                    "counts": counts,
                    "trace_ids": trace_ids,
                    "parent_ids": parent_ids,
                    "chunk_ids": chunk_ids,
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
    assert file_records.operation_ids == ["server-operation"]


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
    )

    assert persisted is not None
    assert persisted["counts"] == {"owned-key": 2}
    assert persisted["parent_ids"] == ["parent-terminal", "parent-without-trace-id"]
    assert persisted["chunk_ids"] == ["chunk-terminal"]
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

    assert counts == Counter({"parent-key": 1, "no-trace-key": 1, "chunk-key": 1})
    assert trace_ids == ["trace-user", "trace-no-user"]
    assert parent_ids == ["parent-user", "parent-no-user", "parent-no-trace-id"]
    assert chunk_ids == ["chunk-user", "chunk-no-user"]

    await trace_storage.delete_trace_snapshot_strict(parent_ids, chunk_ids)

    assert parents.ids() == {"parent-active", "parent-post-cutoff"}
    assert chunks.ids() == {"chunk-unrelated", "chunk-active"}
    assert parents.delete_calls == [{"_id": {"$in": parent_ids}}]
    assert chunks.delete_calls == [{"_id": {"$in": chunk_ids}}]
    assert parents.find_one_calls == [{"_id": {"$in": parent_ids}}]
    assert chunks.find_one_calls == [{"_id": {"$in": chunk_ids}}]


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
    assert file_records.released_counts == [Counter()]
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

    with pytest.raises(RuntimeError, match="session_chunk_delete_incomplete"):
        await manager.clear_session_messages("session-1")

    assert operation_storage.server_operation is not None
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
    assert file_records.operation_ids == ["server-operation-1", "server-operation-1"]
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
