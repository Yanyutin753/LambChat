from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api.routes import session as session_routes
from src.infra.session import storage as session_storage
from src.kernel.errors import AppError


class _UpdateResult:
    def __init__(self, matched_count: int) -> None:
        self.matched_count = matched_count
        self.modified_count = matched_count


class _RecordingCollection:
    def __init__(self, matched_count: int = 1) -> None:
        self.matched_count = matched_count
        self.update_query = None

    async def update_one(self, query, update):
        self.update_query = query
        self.update = update
        return _UpdateResult(self.matched_count)


@pytest.mark.asyncio
async def test_mark_read_for_user_is_one_owner_scoped_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    collection = _RecordingCollection()
    storage = session_storage.SessionStorage()
    storage._collection = collection

    async def _skip_indexes(_self):
        return None

    monkeypatch.setattr(session_storage.SessionStorage, "ensure_indexes_if_needed", _skip_indexes)

    assert await storage.mark_read_for_user("session-1", "user-1") is True
    assert "last_read_at" in collection.update["$set"]
    assert collection.update_query == {
        "session_id": "session-1",
        "user_id": "user-1",
    }


@pytest.mark.asyncio
async def test_mark_read_route_skips_session_read_when_atomic_update_matches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Manager:
        async def mark_read_for_user(self, session_id: str, user_id: str) -> bool:
            assert (session_id, user_id) == ("session-1", "user-1")
            return True

        async def get_session(self, _session_id: str):
            raise AssertionError("successful mark-read should not fetch the session")

    monkeypatch.setattr(session_routes, "SessionManager", lambda: _Manager())

    response = await session_routes.mark_session_read(
        "session-1",
        user=SimpleNamespace(sub="user-1"),
    )

    assert response == {"status": "ok"}


@pytest.mark.asyncio
async def test_mark_read_route_preserves_not_found_on_atomic_miss(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Manager:
        async def mark_read_for_user(self, _session_id: str, _user_id: str) -> bool:
            return False

        async def get_session(self, _session_id: str):
            return None

    monkeypatch.setattr(session_routes, "SessionManager", lambda: _Manager())

    with pytest.raises(AppError) as exc_info:
        await session_routes.mark_session_read(
            "missing-session",
            user=SimpleNamespace(sub="user-1"),
        )

    assert exc_info.value.error_code.code == "session_not_found"
    assert exc_info.value.http_status == 404


@pytest.mark.asyncio
async def test_mark_read_route_preserves_forbidden_on_owner_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _Manager:
        async def mark_read_for_user(self, _session_id: str, _user_id: str) -> bool:
            return False

        async def get_session(self, _session_id: str):
            return SimpleNamespace(user_id="other-user")

    monkeypatch.setattr(session_routes, "SessionManager", lambda: _Manager())

    with pytest.raises(AppError) as exc_info:
        await session_routes.mark_session_read(
            "session-1",
            user=SimpleNamespace(sub="user-1"),
        )

    assert exc_info.value.error_code.code == "session_access_denied"
    assert exc_info.value.http_status == 403


@pytest.fixture(autouse=True)
def read_broadcast(monkeypatch):
    from src.infra import websocket

    broadcast = AsyncMock(return_value=1)
    monkeypatch.setattr(
        websocket,
        "get_connection_manager",
        lambda: SimpleNamespace(send_to_user_with_broadcast=broadcast),
    )
    return broadcast


async def test_successful_read_broadcasts_only_to_its_owner(monkeypatch, read_broadcast):
    manager = SimpleNamespace(mark_read_for_user=AsyncMock(return_value=True))
    monkeypatch.setattr(session_routes, "SessionManager", lambda: manager)
    await session_routes.mark_session_read("s1", user=SimpleNamespace(sub="u1"))
    read_broadcast.assert_awaited_once_with(
        "u1", {"type": "sessions:read", "data": {"session_id": "s1"}}
    )


@pytest.mark.parametrize("scope", [{}, {"project_id": "p1"}, {"scheduled_task_id": "t1"}])
async def test_bulk_read_broadcasts_the_successful_scope(monkeypatch, read_broadcast, scope):
    manager = SimpleNamespace(mark_all_read=AsyncMock(return_value=2))
    monkeypatch.setattr(session_routes, "SessionManager", lambda: manager)
    result = await session_routes.mark_all_sessions_read(
        project_id=scope.get("project_id"),
        scheduled_task_id=scope.get("scheduled_task_id"),
        user=SimpleNamespace(sub="u1"),
    )
    assert result["modified_count"] == 2
    read_broadcast.assert_awaited_once_with("u1", {"type": "sessions:read", "data": scope})


async def test_failed_read_never_broadcasts(monkeypatch, read_broadcast):
    manager = SimpleNamespace(
        mark_read_for_user=AsyncMock(side_effect=RuntimeError("storage unavailable"))
    )
    monkeypatch.setattr(session_routes, "SessionManager", lambda: manager)
    with pytest.raises(RuntimeError):
        await session_routes.mark_session_read("s1", user=SimpleNamespace(sub="u1"))
    read_broadcast.assert_not_awaited()


async def test_broadcast_failure_does_not_undo_a_persisted_read(monkeypatch, read_broadcast):
    manager = SimpleNamespace(mark_read_for_user=AsyncMock(return_value=True))
    monkeypatch.setattr(session_routes, "SessionManager", lambda: manager)
    read_broadcast.side_effect = RuntimeError("offline")
    assert await session_routes.mark_session_read("s1", user=SimpleNamespace(sub="u1")) == {
        "status": "ok"
    }


async def test_bulk_read_includes_waiting_confirmation_without_unread_reply(monkeypatch):
    from datetime import datetime

    collection = SimpleNamespace(update_many=AsyncMock(return_value=_UpdateResult(1)))
    storage = session_storage.SessionStorage()
    storage._collection = collection
    monkeypatch.setattr(storage, "ensure_indexes_if_needed", AsyncMock())
    await storage.mark_all_read("u1", project_id="p1")
    query, update = collection.update_many.call_args.args
    assert query == {
        "user_id": "u1",
        "metadata.project_id": "p1",
        "$or": [{"unread_count": {"$gt": 0}}, {"metadata.task_status": "waiting_human"}],
    }
    assert update["$set"]["unread_count"] == 0
    assert isinstance(update["$set"]["last_read_at"], datetime)
