from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from src.api.routes import session as session_routes
from src.infra.session import storage as session_storage


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

    with pytest.raises(HTTPException) as exc_info:
        await session_routes.mark_session_read(
            "missing-session",
            user=SimpleNamespace(sub="user-1"),
        )

    assert exc_info.value.status_code == 404


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

    with pytest.raises(HTTPException) as exc_info:
        await session_routes.mark_session_read(
            "session-1",
            user=SimpleNamespace(sub="user-1"),
        )

    assert exc_info.value.status_code == 403
