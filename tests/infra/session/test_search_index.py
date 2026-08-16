from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pytest

from src.infra.session.storage import SessionStorage
from src.kernel.schemas.session import Session


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


async def _noop_async():
    return None


@dataclass
class _FakeUpdateResult:
    modified_count: int = 1


def _sort_value(doc: dict[str, Any], field: str) -> tuple[int, Any]:
    """Resolve dotted paths into a type-safe sort key.

    Missing values sort before present ones; booleans are ranked by int value
    so compound sorts like metadata.is_pinned stay comparable.
    """
    value: Any = doc
    for part in field.split("."):
        if not isinstance(value, dict):
            value = None
            break
        value = value.get(part)
    if isinstance(value, bool):
        return (1, int(value))
    if value is None or value == "":
        return (0, 0)
    return (2, value)


class _FakeCursor:
    def __init__(self, docs: list[dict[str, Any]]):
        self._docs = [dict(doc) for doc in docs]
        self._skip = 0
        self._limit: int | None = None

    def sort(self, key_or_list: Any, direction: int | None = None):
        # Mirror pymongo: sort("field", direction) or sort([(field, direction), ...]).
        pairs = (
            [(key_or_list, direction if direction is not None else 1)]
            if isinstance(key_or_list, str)
            else list(key_or_list)
        )
        # Stable sort: apply keys from least to most significant.
        for field, dir_ in reversed(pairs):
            self._docs.sort(key=lambda doc: _sort_value(doc, field), reverse=dir_ < 0)
        return self

    def skip(self, value: int):
        self._skip = value
        return self

    def limit(self, value: int):
        self._limit = value
        return self

    async def to_list(self, length: int | None = None):
        docs = self._docs[self._skip :]
        cap = self._limit if self._limit is not None else length
        if cap is not None:
            docs = docs[:cap]
        return [dict(doc) for doc in docs]


class _FakeCollection:
    def __init__(self, docs: list[dict[str, Any]]):
        self.docs = [dict(doc) for doc in docs]
        self.last_query: dict[str, Any] | None = None
        self.last_update: dict[str, Any] | None = None
        self.last_update_query: dict[str, Any] | None = None
        self.created_indexes: list[tuple[Any, dict[str, Any]]] = []
        self.find_one_calls = 0

    async def create_index(self, keys, **kwargs):
        self.created_indexes.append((keys, kwargs))
        return kwargs.get("name", "idx")

    async def count_documents(self, query: dict[str, Any]) -> int:
        self.last_query = query
        return len([doc for doc in self.docs if _matches_query(doc, query)])

    def find(self, query: dict[str, Any], projection=None):
        self.last_query = query
        matched = [
            _apply_projection(doc, projection) for doc in self.docs if _matches_query(doc, query)
        ]
        return _FakeCursor(matched)

    async def find_one(self, query: dict[str, Any], projection=None):
        self.find_one_calls += 1
        for doc in self.docs:
            if _matches_query(doc, query):
                return _apply_projection(doc, projection)
        return None

    async def update_one(self, query: dict[str, Any], update: dict[str, Any]):
        self.last_update_query = dict(query)
        self.last_update = dict(update)
        for doc in self.docs:
            if _matches_query(doc, query):
                for key, value in update.get("$set", {}).items():
                    _set_nested(doc, key, value)
                return _FakeUpdateResult(modified_count=1)
        return _FakeUpdateResult(modified_count=0)


def _apply_projection(doc: dict[str, Any], projection: dict[str, Any] | None):
    result = dict(doc)
    if not projection:
        return result
    if any(value == 1 for value in projection.values()):
        projected: dict[str, Any] = {}
        for key, value in projection.items():
            if value == 1 and key in result:
                projected[key] = result[key]
        return projected
    return result


def _get_nested(doc: dict[str, Any], dotted_key: str):
    current: Any = doc
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            return None
        current = current[part]
    return current


def _set_nested(doc: dict[str, Any], dotted_key: str, value: Any):
    parts = dotted_key.split(".")
    current = doc
    for part in parts[:-1]:
        current = current.setdefault(part, {})
    current[parts[-1]] = value


def _matches_query(doc: dict[str, Any], query: dict[str, Any]) -> bool:
    for key, value in query.items():
        if key == "$or":
            if not any(_matches_query(doc, condition) for condition in value):
                return False
            continue
        if key == "$and":
            if not all(_matches_query(doc, condition) for condition in value):
                return False
            continue

        actual = _get_nested(doc, key)

        if isinstance(value, dict):
            if "$all" in value:
                if not isinstance(actual, list) or not all(
                    item in actual for item in value["$all"]
                ):
                    return False
            elif "$lt" in value:
                if actual is None or not (actual < value["$lt"]):
                    return False
            elif "$ne" in value:
                if actual == value["$ne"]:
                    return False
            elif "$in" in value:
                if actual not in value["$in"]:
                    return False
            elif "$not" in value:
                nested = value["$not"]
                if "$regex" not in nested:
                    raise AssertionError(f"Unsupported $not query in test fake: {value}")
                if isinstance(actual, str) and re.search(nested["$regex"], actual):
                    return False
            else:
                raise AssertionError(f"Unsupported query operator in test fake: {value}")
            continue

        if actual != value:
            return False
    return True


def test_build_search_terms_supports_mixed_language_queries() -> None:
    from src.infra.session.search_index import build_search_terms

    terms = build_search_terms("Compile 编译错误")

    assert "compile" in terms
    assert "com" in terms
    assert "omp" in terms
    assert "编译" in terms
    assert "译错" in terms
    assert "错误" in terms


def test_build_search_preview_prefers_single_matching_message_line() -> None:
    from src.infra.session.search_index import build_search_preview

    preview = build_search_preview(
        "生成一个好看的mermaid 直接发给我 不要文件\n"
        "生成一个好看的mermaid 直接发给我 不要文件\n"
        "报错了 你改一下\n"
        "报错了 你改一下",
        "mermaid",
    )

    assert preview == "生成一个好看的mermaid 直接发给我 不要文件"


def test_append_message_to_search_index_preserves_message_boundaries() -> None:
    from src.infra.session.search_index import append_message_to_search_index

    payload = append_message_to_search_index(
        session_name="Demo",
        existing_message_search_terms=[],
        existing_search_text="第一条消息\n第二条消息",
        latest_user_message="第三条消息",
    )

    assert payload.search_text == "第一条消息\n第二条消息\n第三条消息"


def test_merge_search_state_preserves_message_boundaries_and_overlap() -> None:
    from src.infra.session.search_index import merge_search_state

    payload = merge_search_state(
        session_name="Demo",
        base_message_terms=["alpha", "beta"],
        base_search_text="第一条消息\n第二条消息\n第三条消息",
        base_latest_user_message="第三条消息",
        extra_message_terms=["beta", "gamma"],
        extra_search_text="第二条消息\n第三条消息\n第四条消息",
        extra_latest_user_message="第四条消息",
    )

    assert payload.search_text == "第一条消息\n第二条消息\n第三条消息\n第四条消息"
    assert payload.latest_user_message == "第四条消息"


@pytest.mark.asyncio
async def test_append_user_message_search_updates_session_document() -> None:
    from src.infra.session.search_index import SESSION_SEARCH_INDEX_VERSION

    now = _utc_now()
    storage = SessionStorage()
    storage.ensure_indexes_if_needed = _noop_async  # type: ignore[method-assign]
    storage._indexes_done = True
    storage._collection = _FakeCollection(  # type: ignore[assignment]
        docs=[
            {
                "_id": "session-1",
                "session_id": "session-1",
                "user_id": "user-1",
                "name": "Parser planning",
                "name_search_terms": ["parser", "planning"],
                "message_search_terms": ["older", "note"],
                "search_terms": ["parser", "planning", "older", "note"],
                "search_text": "older note",
                "latest_user_message": "older note",
                "search_index_updated_at": now,
                "created_at": now,
                "updated_at": now,
                "is_active": True,
                "agent_id": "search",
                "metadata": {},
            }
        ]
    )

    updated = await storage.append_user_message_search_content(
        "session-1",
        "Need to fix 编译错误 in parser module",
    )

    assert updated is True
    assert storage.collection.last_update_query == {
        "session_id": "session-1",
        "search_index_updated_at": now,
    }
    assert storage.collection.last_update is not None

    payload: dict = storage.collection.last_update["$set"]  # type: ignore[assignment]
    assert payload["search_index_version"] == SESSION_SEARCH_INDEX_VERSION
    assert payload["search_index_updated_at"] != now
    assert payload["latest_user_message"] == "Need to fix 编译错误 in parser module"
    assert "parser" in payload["search_terms"]
    assert "编译" in payload["search_terms"]
    assert "错误" in payload["search_terms"]
    assert "older note" in payload["search_text"]
    assert "Need to fix 编译错误 in parser module" in payload["search_text"]
    assert storage.collection.docs[0]["updated_at"] == now


@pytest.mark.asyncio
async def test_list_sessions_can_match_user_message_terms_and_attach_preview() -> None:
    from src.infra.session.search_index import SESSION_SEARCH_INDEX_VERSION, build_search_terms

    now = _utc_now()
    storage = SessionStorage()
    storage.ensure_indexes_if_needed = _noop_async  # type: ignore[method-assign]
    storage._indexes_done = True
    storage._collection = _FakeCollection(  # type: ignore[assignment]
        docs=[
            {
                "_id": "session-1",
                "session_id": "session-1",
                "user_id": "user-1",
                "name": "Parser planning",
                "name_search_terms": ["parser", "planning"],
                "message_search_terms": build_search_terms("Need to fix 编译错误 in parser module"),
                "search_terms": build_search_terms(
                    "Parser planning Need to fix 编译错误 in parser module"
                ),
                "search_text": "Need to fix 编译错误 in parser module",
                "latest_user_message": "Need to fix 编译错误 in parser module",
                "search_index_version": SESSION_SEARCH_INDEX_VERSION,
                "search_index_updated_at": now,
                "created_at": now,
                "updated_at": now,
                "is_active": True,
                "agent_id": "search",
                "metadata": {},
            },
            {
                "_id": "session-2",
                "session_id": "session-2",
                "user_id": "user-1",
                "name": "Unrelated session",
                "name_search_terms": ["unrelated", "session"],
                "message_search_terms": build_search_terms("Totally different topic"),
                "search_terms": build_search_terms("Unrelated session Totally different topic"),
                "search_text": "Totally different topic",
                "latest_user_message": "Totally different topic",
                "search_index_version": SESSION_SEARCH_INDEX_VERSION,
                "search_index_updated_at": now,
                "created_at": now,
                "updated_at": now,
                "is_active": True,
                "agent_id": "search",
                "metadata": {},
            },
        ]
    )

    sessions, total = await storage.list_sessions(
        user_id="user-1",
        search="编译错误",
        limit=20,
    )

    assert total == 1
    assert [session.id for session in sessions] == ["session-1"]

    matched_session: Session = sessions[0]
    assert matched_session.metadata["search_match"] == "Need to fix 编译错误 in parser module"
    assert matched_session.metadata["search_match_source"] == "user_message"


@pytest.mark.asyncio
async def test_list_sessions_supports_english_substring_search_terms() -> None:
    from src.infra.session.search_index import SESSION_SEARCH_INDEX_VERSION, build_search_terms

    now = _utc_now()
    storage = SessionStorage()
    storage.ensure_indexes_if_needed = _noop_async  # type: ignore[method-assign]
    storage._indexes_done = True
    storage._collection = _FakeCollection(  # type: ignore[assignment]
        docs=[
            {
                "_id": "session-compiler",
                "session_id": "session-compiler",
                "user_id": "user-1",
                "name": "Compiler work",
                "name_search_terms": build_search_terms("Compiler work"),
                "message_search_terms": build_search_terms("Need compiler module cleanup"),
                "search_terms": build_search_terms("Compiler work Need compiler module cleanup"),
                "search_text": "Need compiler module cleanup",
                "latest_user_message": "Need compiler module cleanup",
                "search_index_version": SESSION_SEARCH_INDEX_VERSION,
                "search_index_updated_at": now,
                "created_at": now,
                "updated_at": now,
                "is_active": True,
                "agent_id": "search",
                "metadata": {},
            }
        ]
    )

    sessions, total = await storage.list_sessions(
        user_id="user-1",
        search="compile",
        limit=20,
    )

    assert total == 1
    assert [session.id for session in sessions] == ["session-compiler"]


@pytest.mark.asyncio
async def test_append_user_message_retries_after_concurrent_update() -> None:
    now = _utc_now()

    class _ConcurrentAppendCollection(_FakeCollection):
        async def update_one(self, query: dict[str, Any], update: dict[str, Any]):
            self.last_update_query = dict(query)
            self.last_update = dict(update)
            expected_search_index_updated_at = query.get("search_index_updated_at")
            doc = self.docs[0]

            if self.find_one_calls == 1 and expected_search_index_updated_at == now:
                doc["message_search_terms"] = ["older", "gamma"]
                doc["search_text"] = "older\nconcurrent gamma"
                doc["latest_user_message"] = "concurrent gamma"
                doc["search_terms"] = ["parser", "older", "gamma"]
                doc["search_index_version"] = 1
                doc["search_index_updated_at"] = now.replace(microsecond=1)
                doc["updated_at"] = now.replace(microsecond=1)
                return _FakeUpdateResult(modified_count=0)

            if _matches_query(doc, query):
                for key, value in update.get("$set", {}).items():
                    _set_nested(doc, key, value)
                return _FakeUpdateResult(modified_count=1)
            return _FakeUpdateResult(modified_count=0)

    storage = SessionStorage()
    storage.ensure_indexes_if_needed = _noop_async  # type: ignore[method-assign]
    storage._indexes_done = True
    storage._collection = _ConcurrentAppendCollection(  # type: ignore[assignment]
        docs=[
            {
                "_id": "session-1",
                "session_id": "session-1",
                "user_id": "user-1",
                "name": "Parser planning",
                "message_search_terms": ["older"],
                "search_terms": ["parser", "older"],
                "search_text": "older",
                "latest_user_message": "older",
                "search_index_version": 1,
                "search_index_updated_at": now,
                "created_at": now,
                "updated_at": now,
                "is_active": True,
                "agent_id": "search",
                "metadata": {},
            }
        ]
    )

    updated = await storage.append_user_message_search_content("session-1", "delta fix")

    assert updated is True
    assert "gamma" in storage.collection.docs[0]["message_search_terms"]
    assert "delta" in storage.collection.docs[0]["message_search_terms"]
    assert "concurrent gamma" in storage.collection.docs[0]["search_text"]
    assert "delta fix" in storage.collection.docs[0]["search_text"]


@pytest.mark.asyncio
async def test_rebuild_search_index_preserves_new_live_message() -> None:
    now = _utc_now()
    storage = SessionStorage()
    storage.ensure_indexes_if_needed = _noop_async  # type: ignore[method-assign]
    storage._indexes_done = True
    storage._collection = _FakeCollection(  # type: ignore[assignment]
        docs=[
            {
                "_id": "session-1",
                "session_id": "session-1",
                "user_id": "user-1",
                "name": "Parser planning",
                "message_search_terms": ["recent", "note"],
                "search_terms": ["parser", "recent", "note"],
                "search_text": "recent live note",
                "latest_user_message": "recent live note",
                "search_index_version": 1,
                "search_index_updated_at": now,
                "created_at": now,
                "updated_at": now,
                "is_active": True,
                "agent_id": "search",
                "metadata": {},
            }
        ]
    )

    class _TraceStorage:
        async def get_session_events(self, *_args, **_kwargs):
            return [
                {"data": {"content": "older historical question"}},
            ]

    import src.infra.session.trace_storage as trace_storage_module

    original_get_trace_storage = trace_storage_module.get_trace_storage
    trace_storage_module.get_trace_storage = lambda: _TraceStorage()
    try:
        rebuilt = await storage.rebuild_search_index("session-1")
    finally:
        trace_storage_module.get_trace_storage = original_get_trace_storage

    assert rebuilt is True
    doc = storage.collection.docs[0]
    assert "older" in doc["message_search_terms"]
    assert "recent" in doc["message_search_terms"]
    assert "recent live note" == doc["latest_user_message"]
    assert "older historical question" in doc["search_text"]
    assert "recent live note" in doc["search_text"]
    assert doc["search_text"].count("recent live note") == 1


@pytest.mark.asyncio
async def test_rebuild_search_index_uses_bounded_event_read() -> None:
    now = _utc_now()
    storage = SessionStorage()
    storage.ensure_indexes_if_needed = _noop_async  # type: ignore[method-assign]
    storage._indexes_done = True
    storage._collection = _FakeCollection(  # type: ignore[assignment]
        docs=[
            {
                "_id": "session-1",
                "session_id": "session-1",
                "user_id": "user-1",
                "name": "Parser planning",
                "message_search_terms": [],
                "search_terms": [],
                "search_text": "",
                "latest_user_message": "",
                "search_index_version": 1,
                "search_index_updated_at": now,
                "created_at": now,
                "updated_at": now,
                "is_active": True,
                "agent_id": "search",
                "metadata": {},
            }
        ]
    )

    class _TraceStorage:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        async def get_session_events(self, *_args, **kwargs):
            self.calls.append(kwargs)
            return [
                {"data": {"content": "older historical question"}},
            ]

    trace_storage = _TraceStorage()

    import src.infra.session.trace_storage as trace_storage_module

    original_get_trace_storage = trace_storage_module.get_trace_storage
    trace_storage_module.get_trace_storage = lambda: trace_storage
    try:
        rebuilt = await storage.rebuild_search_index("session-1")
    finally:
        trace_storage_module.get_trace_storage = original_get_trace_storage

    assert rebuilt is True
    assert trace_storage.calls == [
        {
            "event_types": ["user:message"],
            "completed_only": False,
            "max_events": 1000,
        }
    ]


@pytest.mark.asyncio
async def test_rebuild_search_index_offloads_backfilled_index_build(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    now = _utc_now()
    storage = SessionStorage()
    storage.ensure_indexes_if_needed = _noop_async  # type: ignore[method-assign]
    storage._indexes_done = True
    storage._collection = _FakeCollection(  # type: ignore[assignment]
        docs=[
            {
                "_id": "session-1",
                "session_id": "session-1",
                "user_id": "user-1",
                "name": "Parser planning",
                "message_search_terms": [],
                "search_terms": [],
                "search_text": "",
                "latest_user_message": "",
                "search_index_version": 1,
                "search_index_updated_at": now,
                "created_at": now,
                "updated_at": now,
                "is_active": True,
                "agent_id": "search",
                "metadata": {},
            }
        ]
    )

    class _TraceStorage:
        async def get_session_events(self, *_args, **_kwargs):
            return [
                {"data": {"content": "first historical question"}},
                {"data": {"content": "second historical question"}},
            ]

    import src.infra.session.storage as storage_module
    import src.infra.session.trace_storage as trace_storage_module

    offloaded: list[str] = []

    async def fake_run_blocking_io(func, /, *args, **kwargs):
        offloaded.append(func.__name__)
        return func(*args, **kwargs)

    original_get_trace_storage = trace_storage_module.get_trace_storage
    trace_storage_module.get_trace_storage = lambda: _TraceStorage()
    monkeypatch.setattr(storage_module, "run_blocking_io", fake_run_blocking_io, raising=False)
    try:
        rebuilt = await storage.rebuild_search_index("session-1")
    finally:
        trace_storage_module.get_trace_storage = original_get_trace_storage

    assert rebuilt is True
    assert offloaded == ["build_backfilled_search_index"]


@pytest.mark.asyncio
async def test_backfill_search_indexes_clamps_batch_size() -> None:
    class _BackfillCursor:
        def __init__(self) -> None:
            self.limit_value: int | None = None
            self.to_list_length: int | None = None

        def sort(self, *_args):
            return self

        def limit(self, value: int):
            self.limit_value = value
            return self

        async def to_list(self, length: int | None = None):
            self.to_list_length = length
            cap = length or 0
            return [
                {"_id": f"session-{index}", "session_id": f"session-{index}"}
                for index in range(cap)
            ]

    class _BackfillCollection:
        def __init__(self) -> None:
            self.cursor = _BackfillCursor()

        def find(self, *_args):
            return self.cursor

    storage = SessionStorage()
    storage.ensure_indexes_if_needed = _noop_async  # type: ignore[method-assign]
    storage._indexes_done = True
    storage._collection = _BackfillCollection()  # type: ignore[assignment]

    calls: list[str] = []

    async def _fake_rebuild(session_id: str) -> bool:
        calls.append(session_id)
        return True

    storage.rebuild_search_index = _fake_rebuild  # type: ignore[method-assign]

    rebuilt = await storage.backfill_search_indexes(batch_size=10_000)

    assert rebuilt == storage.SEARCH_BACKFILL_BATCH_MAX
    assert len(calls) == storage.SEARCH_BACKFILL_BATCH_MAX
    assert storage.collection.cursor.limit_value == storage.SEARCH_BACKFILL_BATCH_MAX
    assert storage.collection.cursor.to_list_length == storage.SEARCH_BACKFILL_BATCH_MAX


@pytest.mark.asyncio
async def test_session_indexes_are_initialized_once_across_instances() -> None:
    shared_collection = _FakeCollection(docs=[])

    first = SessionStorage()
    second = SessionStorage()
    first._collection = shared_collection
    second._collection = shared_collection

    original_task = getattr(SessionStorage, "_indexes_task", None)
    original_done = getattr(SessionStorage, "_indexes_done", False)
    original_lock = getattr(SessionStorage, "_indexes_lock", None)

    SessionStorage._indexes_task = None
    SessionStorage._indexes_done = False
    SessionStorage._indexes_lock = None

    try:
        await first.ensure_indexes_if_needed()
        await second.ensure_indexes_if_needed()
    finally:
        SessionStorage._indexes_task = original_task
        SessionStorage._indexes_done = original_done
        SessionStorage._indexes_lock = original_lock

    assert len(shared_collection.created_indexes) == 7
