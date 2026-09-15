"""会话列表 projection：搜索索引重字段不该被侧边栏整档拉回。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pytest

from src.infra.session.storage import SessionStorage

HEAVY_FIELDS = (
    "search_text",
    "search_terms",
    "name_search_terms",
    "message_search_terms",
    "latest_user_message",
    "search_index_version",
    "search_index_updated_at",
    "active_trace_writers",
)


def _session_doc() -> dict[str, Any]:
    return {
        "_id": "s-1",
        "session_id": "s-1",
        "name": "会话",
        "metadata": {},
        "user_id": "u-1",
        "agent_id": "fast",
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "is_active": True,
        "unread_count": 0,
        "search_text": "很长的全文拼接 " * 500,
        "search_terms": ["很长的全文拼接", "会话"],
        "name_search_terms": ["会话"],
        "message_search_terms": ["很长的全文拼接"],
        "latest_user_message": "最近一条消息预览",
        "search_index_version": 2,
        "search_index_updated_at": datetime.now(timezone.utc),
        "active_trace_writers": [],
    }


class _FakeCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = docs

    def skip(self, _n: int) -> "_FakeCursor":
        return self

    def limit(self, _n: int) -> "_FakeCursor":
        return self

    def sort(self, *_args: Any) -> "_FakeCursor":
        return self

    async def to_list(self, length: int | None = None) -> list[dict[str, Any]]:
        del length
        return self._docs


class _ProjectionCapturingCollection:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = docs
        self.last_projection: dict[str, Any] | None = None

    async def create_index(self, *_args: Any, **_kwargs: Any) -> str:
        return "idx"

    async def count_documents(self, _query: dict[str, Any]) -> int:
        return len(self._docs)

    def find(self, _query: dict[str, Any], projection: dict[str, Any] | None = None):
        self.last_projection = projection
        return _FakeCursor([dict(doc) for doc in self._docs])


def _make_storage(
    collection: _ProjectionCapturingCollection,
    monkeypatch: pytest.MonkeyPatch,
) -> SessionStorage:
    monkeypatch.setattr(SessionStorage, "_indexes_done", True)
    storage = SessionStorage.__new__(SessionStorage)
    storage._collection = collection  # type: ignore[attr-defined]
    return storage


@pytest.mark.asyncio
async def test_list_sessions_projects_out_heavy_search_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collection = _ProjectionCapturingCollection([_session_doc()])

    sessions, total = await _make_storage(collection, monkeypatch).list_sessions(user_id="u-1")

    assert total == 1
    assert sessions[0].id == "s-1"
    assert collection.last_projection is not None
    for field in HEAVY_FIELDS:
        assert collection.last_projection.get(field) == 0, field


@pytest.mark.asyncio
async def test_list_sessions_keeps_search_text_when_searching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """搜索路径要用 search_text 生成命中预览,不能投影掉。"""
    doc = _session_doc()
    doc["search_terms"] = ["关键词"]
    collection = _ProjectionCapturingCollection([doc])

    await _make_storage(collection, monkeypatch).list_sessions(user_id="u-1", search="关键词")

    assert collection.last_projection is not None
    assert "search_text" not in collection.last_projection
    # 其余重字段仍然排除
    assert collection.last_projection.get("search_terms") == 0
    assert collection.last_projection.get("message_search_terms") == 0


@pytest.mark.asyncio
async def test_list_sessions_for_task_projects_out_heavy_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collection = _ProjectionCapturingCollection([_session_doc()])

    await _make_storage(collection, monkeypatch).list_sessions_for_task(
        scheduled_task_id="task-1", user_id="u-1"
    )

    assert collection.last_projection is not None
    for field in HEAVY_FIELDS:
        assert collection.last_projection.get(field) == 0, field
