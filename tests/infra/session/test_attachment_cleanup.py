from __future__ import annotations

from collections import Counter

import pytest

from src.infra.session.manager import SessionManager


class _FileRecordStorage:
    def __init__(self) -> None:
        self.released_counts: list[Counter[str]] = []
        self.release_error: Exception | None = None

    async def release_reference_counts(self, counts: Counter[str]) -> int:
        if self.release_error:
            raise self.release_error
        self.released_counts.append(counts)
        return len(counts)


class _TraceStorage:
    def __init__(self) -> None:
        self.get_session_events_calls: list[tuple[str, dict]] = []
        self.deleted_session_ids: list[str] = []
        self.events: list[dict] = []

    async def get_session_events(self, _session_id: str, **kwargs) -> list[dict]:
        self.get_session_events_calls.append((_session_id, kwargs))
        return self.events

    async def delete_session_traces(self, session_id: str) -> int:
        self.deleted_session_ids.append(session_id)
        return 0


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

    class _Storage:
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

    class _Storage:
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
async def test_collect_user_attachment_reference_counts_uses_bounded_user_message_query() -> None:
    manager = SessionManager()

    class _AttachmentTraceStorage:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict]] = []

        async def get_session_events(self, session_id: str, **kwargs) -> list[dict]:
            self.calls.append((session_id, kwargs))
            return [
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

    trace_storage = _AttachmentTraceStorage()
    manager._trace_storage = trace_storage

    counts = await manager._collect_user_attachment_reference_counts("session-1")

    assert counts == Counter({"attachments/u1/a.png": 2, "attachments/u1/b.txt": 1})
    assert trace_storage.calls == [
        (
            "session-1",
            {
                "event_types": ["user:message"],
                "completed_only": False,
                "max_events": 1000,
            },
        )
    ]
