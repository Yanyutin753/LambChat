from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

from src.infra.session.trace_storage import TraceStorage


class _UpdateResult:
    modified_count = 1


class _UpdateCollection:
    def __init__(self) -> None:
        self.calls: list[tuple[dict, dict]] = []

    async def update_one(self, query: dict, update: dict) -> _UpdateResult:
        self.calls.append((query, update))
        return _UpdateResult()


class _TraceCursor:
    def __init__(self, traces: list[dict]) -> None:
        self.traces = traces

    def sort(self, *_args):
        return self

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for trace in self.traces:
            yield trace


class _ReadCollection:
    def __init__(self, traces: list[dict]) -> None:
        self.traces = traces
        self.projection: dict | None = None

    def find(self, _query: dict, projection: dict) -> _TraceCursor:
        self.projection = projection
        return _TraceCursor(self.traces)


@pytest.mark.asyncio
async def test_set_run_recommend_questions_persists_a_bounded_normalized_field() -> None:
    collection = _UpdateCollection()
    storage = TraceStorage()
    storage._collection = collection
    storage.ensure_indexes_if_needed = AsyncMock()  # type: ignore[method-assign]

    updated = await storage.set_run_recommend_questions(
        "session-1",
        "run-1",
        ["  问题一？  ", "", "问题二？", "问题三？", "问题四？"],
    )

    assert updated is True
    assert collection.calls[0][0] == {
        "session_id": "session-1",
        "run_id": "run-1",
        "attachment_chunk_write_operation": {"$exists": False},
    }
    assert collection.calls[0][1]["$inc"] == {"event_revision": 1}
    set_fields = collection.calls[0][1]["$set"]
    assert set_fields["recommend_questions"] == ["问题一？", "问题二？", "问题三？"]
    assert "recommend_questions_updated_at" in set_fields


@pytest.mark.asyncio
async def test_active_running_trace_does_not_synthesize_recommend_event() -> None:
    collection = _ReadCollection(
        [
            {
                "trace_id": "trace-1",
                "run_id": "run-1",
                "status": "running",
                "started_at": "2026-09-10T02:57:40Z",
                "updated_at": datetime.now(timezone.utc),
                "recommend_questions": ["问题一？"],
                "recommend_questions_updated_at": "2026-09-10T03:18:04Z",
            }
        ]
    )
    storage = TraceStorage()
    storage._collection = collection
    storage.read_trace_events_batch_compat = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "trace-1": [
                {
                    "event_type": "user:message",
                    "data": {"content": "hello"},
                    "timestamp": "2026-09-10T02:57:41Z",
                },
                {
                    "event_type": "message:chunk",
                    "data": {"content": "partial"},
                    "timestamp": "2026-09-10T03:00:00Z",
                },
            ]
        }
    )

    snapshot = await storage.get_session_events_snapshot("session-1", active_run_id="run-1")

    # 活跃 run 的历史快照只回 user:message（正文等 SSE 重放）；
    # 此时合成 recommend:questions 会折叠出零正文的孤儿助手轮次。
    assert [event["event_type"] for event in snapshot.events] == ["user:message"]
    assert snapshot.history_mode == "active_user_only"
    assert snapshot.stream_run_id == "run-1"


@pytest.mark.asyncio
async def test_session_event_read_synthesizes_legacy_recommend_event_from_run_field() -> None:
    collection = _ReadCollection(
        [
            {
                "trace_id": "trace-1",
                "run_id": "run-1",
                "started_at": "2026-08-09T00:00:00Z",
                "recommend_questions": ["问题一？", "问题二？"],
                "recommend_questions_updated_at": "2026-08-09T00:01:00Z",
            }
        ]
    )
    storage = TraceStorage()
    storage._collection = collection
    storage.read_trace_events_batch_compat = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "trace-1": [
                {
                    "event_type": "done",
                    "data": {},
                    "timestamp": "2026-08-09T00:00:30Z",
                }
            ]
        }
    )

    events = await storage.get_session_events("session-1")

    assert [event["event_type"] for event in events] == ["done", "recommend:questions"]
    assert events[-1]["run_id"] == "run-1"
    assert events[-1]["trace_id"] == "trace-1"
    assert events[-1]["seq"] == 2
    assert events[-1]["data"] == {"questions": ["问题一？", "问题二？"]}
    assert collection.projection is not None
    assert collection.projection["recommend_questions"] == 1


@pytest.mark.asyncio
async def test_session_event_read_keeps_legacy_recommend_event_without_duplicate() -> None:
    collection = _ReadCollection(
        [
            {
                "trace_id": "trace-1",
                "run_id": "run-1",
                "started_at": "2026-08-09T00:00:00Z",
                "recommend_questions": {"questions": ["新字段问题？"]},
            }
        ]
    )
    storage = TraceStorage()
    storage._collection = collection
    storage.read_trace_events_batch_compat = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "trace-1": [
                {
                    "event_type": "followup:questions",
                    "data": {"questions": ["旧事件问题？"]},
                    "timestamp": "2026-08-09T00:00:30Z",
                }
            ]
        }
    )

    events = await storage.get_session_events("session-1")

    assert len(events) == 1
    assert events[0]["event_type"] == "followup:questions"
    assert events[0]["data"] == {"questions": ["旧事件问题？"]}


@pytest.mark.asyncio
async def test_session_event_read_preserves_requested_legacy_followup_alias() -> None:
    collection = _ReadCollection(
        [
            {
                "trace_id": "trace-1",
                "run_id": "run-1",
                "started_at": "2026-08-09T00:00:00Z",
                "recommend_questions": ["问题一？"],
            }
        ]
    )
    storage = TraceStorage()
    storage._collection = collection
    storage.read_trace_events_batch_compat = AsyncMock(  # type: ignore[method-assign]
        return_value={"trace-1": []}
    )

    events = await storage.get_session_events(
        "session-1",
        event_types=["followup:questions"],
    )

    assert [event["event_type"] for event in events] == ["followup:questions"]
    assert events[0]["data"] == {"questions": ["问题一？"]}
