from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from src.infra.session.conversation_history import (
    ConversationHistoryInvalidArgumentError,
    ConversationHistoryNotFoundError,
    ConversationHistoryService,
)
from src.kernel.schemas.conversation_history import ConversationSourceRef
from src.kernel.schemas.session import Session


def _nested_value(doc: dict[str, Any], key: str) -> Any:
    value: Any = doc
    for part in key.split("."):
        if not isinstance(value, dict):
            return None
        value = value.get(part)
    return value


def _matches(doc: dict[str, Any], query: dict[str, Any]) -> bool:
    for key, expected in query.items():
        if key == "$or":
            if not any(_matches(doc, item) for item in expected):
                return False
            continue
        actual = _nested_value(doc, key)
        if isinstance(expected, dict):
            if "$ne" in expected and actual == expected["$ne"]:
                return False
            if "$all" in expected and not all(item in (actual or []) for item in expected["$all"]):
                return False
            if "$in" in expected and actual not in expected["$in"]:
                return False
            if "$lt" in expected and not (actual is not None and actual < expected["$lt"]):
                return False
            continue
        if actual != expected:
            return False
    return True


class _Cursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.docs = [deepcopy(doc) for doc in docs]
        self.limit_value: int | None = None

    def sort(self, spec, direction=None):
        fields = spec if isinstance(spec, list) else [(spec, direction)]
        for field, field_direction in reversed(fields):
            self.docs.sort(
                key=lambda doc: _nested_value(doc, field) or "",
                reverse=field_direction < 0,
            )
        return self

    def limit(self, value: int):
        self.limit_value = value
        return self

    async def to_list(self, length: int | None = None):
        limit = self.limit_value if self.limit_value is not None else length
        docs = self.docs if limit is None else self.docs[:limit]
        return [deepcopy(doc) for doc in docs]

    def __aiter__(self):
        self._iterator = (
            iter(self.docs[: self.limit_value]) if self.limit_value else iter(self.docs)
        )
        return self

    async def __anext__(self):
        try:
            return deepcopy(next(self._iterator))
        except StopIteration as exc:
            raise StopAsyncIteration from exc


class _UpdateResult:
    modified_count = 1


class _TraceCollection:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.docs = [deepcopy(doc) for doc in docs]
        self.last_update: dict[str, Any] | None = None

    async def find_one(self, query, projection=None):
        del projection
        return next((deepcopy(doc) for doc in self.docs if _matches(doc, query)), None)

    def find(self, query, projection=None):
        del projection
        return _Cursor([doc for doc in self.docs if _matches(doc, query)])

    async def update_one(self, query, update):
        self.last_update = deepcopy(update)
        for doc in self.docs:
            if not _matches(doc, query):
                continue
            for key, value in update.get("$set", {}).items():
                target = doc
                parts = key.split(".")
                for part in parts[:-1]:
                    target = target.setdefault(part, {})
                target[parts[-1]] = value
            return _UpdateResult()
        return type("_Missing", (), {"modified_count": 0})()


class _TraceStorage:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self.collection = _TraceCollection(docs)

    async def ensure_indexes_if_needed(self):
        return None

    async def read_trace_events_compat(self, trace_id, event_types=None, max_events=None):
        del event_types, max_events
        doc = next(doc for doc in self.collection.docs if doc["trace_id"] == trace_id)
        return deepcopy(doc.get("events", []))

    async def read_trace_events_batch_compat(self, traces, event_types=None):
        del event_types
        return {
            trace["trace_id"]: await self.read_trace_events_compat(trace["trace_id"])
            for trace in traces
        }


class _SessionManager:
    def __init__(self, sessions: list[Session]) -> None:
        self.sessions = {session.id: session for session in sessions}

    async def get_session(self, session_id: str):
        return self.sessions.get(session_id)

    async def get_sessions(self, session_ids: list[str]):
        return {
            session_id: self.sessions[session_id]
            for session_id in session_ids
            if session_id in self.sessions
        }


@pytest.fixture
def fake_history_service():
    now = datetime.now(timezone.utc)
    sessions = [
        Session(id="session-1", user_id="user-1", name="Parser work"),
        Session(id="visible", user_id="user-1", name="Visible"),
        Session(id="other-user", user_id="user-2", name="Other"),
        Session(
            id="hidden",
            user_id="user-1",
            name="Hidden",
            metadata={"hidden_from_conversation_list": True},
        ),
        Session(
            id="scheduled",
            user_id="user-1",
            name="Scheduled",
            metadata={"scheduled_task_id": "task-1"},
        ),
    ]

    def trace(
        trace_id: str,
        session_id: str,
        run_id: str,
        minutes_ago: int,
        user_text: str,
        assistant_text: str,
        *,
        user_id: str = "user-1",
    ) -> dict[str, Any]:
        completed_at = now - timedelta(minutes=minutes_ago)
        return {
            "trace_id": trace_id,
            "session_id": session_id,
            "run_id": run_id,
            "user_id": user_id,
            "status": "completed",
            "started_at": completed_at - timedelta(seconds=30),
            "completed_at": completed_at,
            "updated_at": completed_at,
            "conversation_search": {
                "version": 1,
                "user_text": user_text,
                "assistant_final_text": assistant_text,
                "user_terms": ["编", "译", "编译"],
                "assistant_terms": ["编", "译", "编译"],
                "terms": ["编", "译", "编译"],
            },
            "events": [
                {"event_type": "user:message", "data": {"content": user_text}},
                {"event_type": "thinking", "data": {"content": "hidden thinking"}},
                {"event_type": "message:chunk", "data": {"content": assistant_text}},
            ],
        }

    docs = [
        trace("trace-3", "session-1", "run-3", 1, "编译第三轮", "第三个答案"),
        trace("trace-2", "session-1", "run-2", 2, "编译第二轮", "第二个答案"),
        trace("trace-1", "session-1", "run-1", 3, "编译第一轮", "第一个答案"),
        trace("trace-visible", "visible", "run-visible", 4, "可见", "可见答案"),
        trace("trace-other", "other-user", "run-other", 5, "其他", "其他答案", user_id="user-2"),
        trace("trace-hidden", "hidden", "run-hidden", 6, "隐藏", "隐藏答案"),
        trace("trace-scheduled", "scheduled", "run-scheduled", 7, "定时", "定时答案"),
        trace(
            "trace-mismatch",
            "other-user",
            "run-from-another-session",
            8,
            "错配",
            "错配答案",
            user_id="user-2",
        ),
    ]
    storage = _TraceStorage(docs)
    service = ConversationHistoryService(
        trace_storage=storage,
        session_manager=_SessionManager(sessions),
    )
    service.trace_collection = storage.collection
    return service


@pytest.mark.asyncio
async def test_index_trace_materializes_completed_turn(fake_history_service) -> None:
    doc = fake_history_service.trace_collection.docs[0]
    doc.pop("conversation_search")

    stored = await fake_history_service.index_trace("trace-3")

    assert stored is True
    update = fake_history_service.trace_collection.last_update["$set"]
    assert update["conversation_search.version"] == 1
    assert "编译" in update["conversation_search.terms"]


@pytest.mark.asyncio
async def test_validate_source_refs_filters_cross_user_hidden_scheduled_and_mismatched_runs(
    fake_history_service,
) -> None:
    refs = [
        ConversationSourceRef(session_id="visible", run_id="run-visible"),
        ConversationSourceRef(session_id="other-user", run_id="run-other"),
        ConversationSourceRef(session_id="hidden", run_id="run-hidden"),
        ConversationSourceRef(session_id="scheduled", run_id="run-scheduled"),
        ConversationSourceRef(session_id="visible", run_id="run-from-another-session"),
    ]

    allowed = await fake_history_service.validate_source_refs("user-1", refs)

    assert allowed == [ConversationSourceRef(session_id="visible", run_id="run-visible")]


@pytest.mark.asyncio
async def test_search_returns_stable_opaque_cursor_and_match_source(fake_history_service) -> None:
    first = await fake_history_service.search("user-1", "编译", limit=2)
    second = await fake_history_service.search(
        "user-1", "编译", limit=2, cursor=first["next_cursor"]
    )

    assert [(item["session_id"], item["run_id"]) for item in first["items"]] == [
        ("session-1", "run-3"),
        ("session-1", "run-2"),
    ]
    assert second["items"][0]["run_id"] == "run-1"
    assert first["items"][0]["match_source"] in {"user", "assistant", "both"}


@pytest.mark.asyncio
async def test_get_detail_pages_session_but_exact_run_is_single_turn(
    fake_history_service,
) -> None:
    page = await fake_history_service.get_detail("user-1", "session-1", limit=2)
    exact = await fake_history_service.get_detail("user-1", "session-1", run_id="run-1", limit=20)

    assert len(page["turns"]) == 2
    assert page["next_cursor"]
    assert [turn["run_id"] for turn in exact["turns"]] == ["run-1"]
    assert set(exact["turns"][0]) == {
        "run_id",
        "started_at",
        "completed_at",
        "user_message",
        "assistant_final",
    }
    assert "hidden thinking" not in str(page)


@pytest.mark.asyncio
async def test_invalid_cursor_uses_stable_argument_error(fake_history_service) -> None:
    with pytest.raises(ConversationHistoryInvalidArgumentError):
        await fake_history_service.search("user-1", "编译", cursor="not-a-cursor")


@pytest.mark.asyncio
async def test_unauthorized_detail_uses_same_not_found_error(fake_history_service) -> None:
    with pytest.raises(ConversationHistoryNotFoundError):
        await fake_history_service.get_detail("user-1", "other-user")
