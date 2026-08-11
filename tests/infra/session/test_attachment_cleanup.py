from __future__ import annotations

from collections import Counter
from types import SimpleNamespace

import pytest

from src.infra.session.manager import SessionManager
from src.infra.session.trace_storage import TraceStorage


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
        self, _session_id: str, operation_id: str, counts: dict, trace_ids: list[str]
    ) -> dict:
        assert self.server_operation and operation_id == self.server_operation["id"]
        self.server_operation.setdefault("counts", counts)
        self.server_operation.setdefault("trace_ids", trace_ids)
        return self.server_operation

    async def complete_attachment_clear_operation(
        self, _session_id: str, operation_id: str
    ) -> bool:
        pending = self.server_operation
        if pending is None or pending.get("id") != operation_id:
            return False
        self.server_operation = None
        return True


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
            self, _session_id: str, operation_id: str, counts: dict, trace_ids: list[str]
        ):
            assert operation_id == "server-operation"
            self.server_operation.update({"counts": counts, "trace_ids": trace_ids})
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
