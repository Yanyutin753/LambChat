"""消息书签存储层测试

覆盖 toggle 幂等语义、用户/会话/消息三维隔离、列表联查会话名与失效会话过滤。
"""

from datetime import datetime
from types import SimpleNamespace

import pytest

from src.infra.bookmark.storage import BookmarkStorage
from src.kernel.schemas.bookmark import Bookmark, BookmarkWithSession


def _make_doc(
    *,
    user_id="user-1",
    session_id="session-1",
    message_id="message-1",
    run_id="run-1",
    label="大纲摘要",
    created_at=None,
):
    return {
        "_id": f"oid-{message_id}-{user_id}-{session_id}",
        "user_id": user_id,
        "session_id": session_id,
        "message_id": message_id,
        "run_id": run_id,
        "label": label,
        "created_at": created_at or datetime(2026, 8, 1, 12, 0, 0),
    }


class _FakeCursor:
    """模拟 mongo cursor：支持 .sort() 与异步迭代。"""

    def __init__(self, docs):
        self._docs = list(docs)

    def sort(self, key, direction):
        return _FakeCursor(sorted(self._docs, key=lambda d: d[key], reverse=direction < 0))

    def limit(self, _count):
        return self

    async def __aiter__(self):
        for doc in list(self._docs):
            yield dict(doc)


class _FakeBookmarkCollection:
    """模拟 bookmarks collection（仅支持等值匹配）。"""

    def __init__(self, docs=None):
        self.docs = [dict(d) for d in (docs or [])]

    def _match(self, query):
        return [d for d in self.docs if all(d.get(k) == v for k, v in query.items())]

    async def find_one(self, query):
        matched = self._match(query)
        return dict(matched[0]) if matched else None

    async def insert_one(self, doc):
        stored = dict(doc)
        stored["_id"] = f"oid-{len(self.docs) + 1}"
        self.docs.append(stored)
        return SimpleNamespace(inserted_id=stored["_id"])

    async def delete_one(self, query):
        matched = self._match(query)
        for doc in matched:
            self.docs.remove(doc)
        return SimpleNamespace(deleted_count=len(matched))

    def find(self, query):
        return _FakeCursor(self._match(query))


class _FakeSessionsCollection:
    """模拟 sessions collection，支持 $in / $or 匹配。"""

    def __init__(self, docs=None):
        self.docs = [dict(d) for d in (docs or [])]

    def _match_doc(self, doc, cond):
        for key, value in cond.items():
            if isinstance(value, dict) and "$in" in value:
                if doc.get(key) not in value["$in"]:
                    return False
            elif doc.get(key) != value:
                return False
        return True

    def find(self, query):
        if "$or" in query:
            matched = [
                d for d in self.docs if any(self._match_doc(d, cond) for cond in query["$or"])
            ]
        else:
            matched = [d for d in self.docs if self._match_doc(d, query)]
        return _FakeCursor(matched)


def _make_storage(bookmark_docs=None, session_docs=None):
    storage = BookmarkStorage()
    storage._collection = _FakeBookmarkCollection(bookmark_docs)
    storage._sessions_collection = _FakeSessionsCollection(session_docs)
    return storage


@pytest.mark.asyncio
async def test_toggle_adds_bookmark_when_absent():
    storage = _make_storage()

    bookmarked, bookmark = await storage.toggle(
        user_id="user-1",
        session_id="session-1",
        message_id="message-1",
        run_id="run-1",
        label="季度规划大纲",
    )

    assert bookmarked is True
    assert isinstance(bookmark, Bookmark)
    assert bookmark.user_id == "user-1"
    assert bookmark.session_id == "session-1"
    assert bookmark.message_id == "message-1"
    assert bookmark.run_id == "run-1"
    assert bookmark.label == "季度规划大纲"
    assert bookmark.created_at is not None


@pytest.mark.asyncio
async def test_toggle_removes_existing_bookmark():
    storage = _make_storage([_make_doc()])

    bookmarked, bookmark = await storage.toggle(
        user_id="user-1",
        session_id="session-1",
        message_id="message-1",
    )

    assert bookmarked is False
    assert bookmark is None
    assert storage._collection.docs == []


@pytest.mark.asyncio
async def test_toggle_is_scoped_to_user_session_message():
    storage = _make_storage(
        [
            _make_doc(),
            _make_doc(session_id="session-2"),
            _make_doc(user_id="user-2"),
        ]
    )

    bookmarked, _ = await storage.toggle(
        user_id="user-1",
        session_id="session-1",
        message_id="message-1",
    )

    # 只删除 user-1 + session-1 + message-1 维度的书签，其余保留
    assert bookmarked is False
    assert len(storage._collection.docs) == 2


@pytest.mark.asyncio
async def test_get_returns_none_when_absent():
    storage = _make_storage([_make_doc(user_id="user-2")])

    assert await storage.get("user-1", "session-1", "message-1") is None


@pytest.mark.asyncio
async def test_list_for_user_joins_session_and_filters_deleted_sessions():
    later = datetime(2026, 8, 2, 12, 0, 0)
    storage = _make_storage(
        bookmark_docs=[
            _make_doc(message_id="message-1", run_id="run-1", label="早期书签"),
            _make_doc(
                session_id="session-2",
                message_id="message-2",
                run_id="run-2",
                label="较新书签",
                created_at=later,
            ),
            _make_doc(session_id="session-gone", message_id="message-3"),
        ],
        session_docs=[
            {"session_id": "session-1", "name": "产品规划", "is_active": False},
            {"_id": "legacy-oid", "session_id": "session-2"},
        ],
    )

    items = await storage.list_for_user("user-1")

    # session-gone 的书签被过滤；按 created_at 倒序
    assert [item.message_id for item in items] == ["message-2", "message-1"]
    assert all(isinstance(item, BookmarkWithSession) for item in items)
    # 缺 name 的会话回落到 session_id，is_active 缺省视为 True
    assert items[0].session_name == "session-2"
    assert items[0].session_is_active is True
    assert items[1].session_name == "产品规划"
    assert items[1].session_is_active is False


@pytest.mark.asyncio
async def test_list_for_user_only_returns_own_bookmarks():
    storage = _make_storage(
        [_make_doc(user_id="user-2"), _make_doc(user_id="user-1", message_id="mine")],
        session_docs=[{"session_id": "session-1", "name": "任意会话"}],
    )

    items = await storage.list_for_user("user-1")

    assert [item.message_id for item in items] == ["mine"]
