"""Tests for session pin toggle functionality."""

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId

from src.infra.session.storage import SessionStorage


@pytest.fixture
def storage():
    instance = SessionStorage()
    # Skip real index creation; the class-level lock/task state cannot be
    # shared across the per-test event loops pytest-asyncio creates.
    instance.ensure_indexes_if_needed = AsyncMock()
    return instance


@pytest.mark.asyncio
async def test_toggle_pin_initial_pin(storage):
    """Pinning an unpinned session sets is_pinned=True."""
    session_id = str(ObjectId())
    user_id = "user_1"
    now_mock = "2026-08-16T00:00:00"

    fake_doc = {
        "_id": ObjectId(session_id),
        "user_id": user_id,
        "metadata": {},
        "updated_at": "2026-08-15T00:00:00",
        "name": "Test Session",
    }
    updated_doc = {
        **fake_doc,
        "metadata": {"is_pinned": True},
        "updated_at": now_mock,
    }

    storage._collection = MagicMock()
    # Legacy sessions carry no session_id field: only the _id lookup matches.
    storage._collection.find_one = AsyncMock(
        side_effect=lambda query: fake_doc if "_id" in query else None
    )
    storage._collection.find_one_and_update = AsyncMock(side_effect=[None, updated_doc])

    with patch("src.infra.session.storage.utc_now", return_value=now_mock):
        result = await storage.toggle_pin(session_id, user_id)

    assert result is not None
    assert result.metadata["is_pinned"] is True

    # The session_id query misses, so the _id fallback performs the update.
    assert storage._collection.find_one_and_update.await_count == 2
    call_args = storage._collection.find_one_and_update.call_args
    assert call_args.args[0] == {"_id": ObjectId(session_id), "user_id": user_id}
    assert call_args.args[1]["$set"]["metadata.is_pinned"] is True
    assert call_args.args[1]["$set"]["updated_at"] == now_mock


@pytest.mark.asyncio
async def test_toggle_pin_unpin(storage):
    """Unpinning a pinned session sets is_pinned=False."""
    session_id = str(ObjectId())
    user_id = "user_1"

    fake_doc = {
        "_id": ObjectId(session_id),
        "user_id": user_id,
        "metadata": {"is_pinned": True},
        "updated_at": "2026-08-15T00:00:00",
        "name": "Test Session",
    }
    updated_doc = {
        **fake_doc,
        "metadata": {"is_pinned": False},
        "updated_at": "2026-08-15T00:01:00",
    }

    storage._collection = MagicMock()
    storage._collection.find_one = AsyncMock(
        side_effect=lambda query: fake_doc if "_id" in query else None
    )
    storage._collection.find_one_and_update = AsyncMock(side_effect=[None, updated_doc])

    result = await storage.toggle_pin(session_id, user_id)

    assert result is not None
    assert result.metadata["is_pinned"] is False
    call_args = storage._collection.find_one_and_update.call_args
    assert call_args.args[0] == {"_id": ObjectId(session_id), "user_id": user_id}
    assert call_args.args[1]["$set"]["metadata.is_pinned"] is False


@pytest.mark.asyncio
async def test_toggle_pin_custom_string_session_id(storage):
    """Pinning works for sessions created with custom UUID string ids."""
    session_id = str(uuid.uuid4())
    user_id = "user_1"
    now_mock = "2026-08-16T00:00:00"

    fake_doc = {
        "session_id": session_id,
        "user_id": user_id,
        "metadata": {"is_pinned": False},
        "updated_at": "2026-08-15T00:00:00",
        "name": "Task Session",
    }
    updated_doc = {
        **fake_doc,
        "metadata": {"is_pinned": True},
        "updated_at": now_mock,
    }

    storage._collection = MagicMock()
    storage._collection.find_one = AsyncMock(return_value=fake_doc)
    storage._collection.find_one_and_update = AsyncMock(return_value=updated_doc)

    with patch("src.infra.session.storage.utc_now", return_value=now_mock):
        result = await storage.toggle_pin(session_id, user_id)

    assert result is not None
    assert result.id == session_id
    assert result.metadata["is_pinned"] is True

    # Found via the custom session_id field, never via ObjectId.
    storage._collection.find_one.assert_awaited_once_with({"session_id": session_id})
    storage._collection.find_one_and_update.assert_called_once()
    call_args = storage._collection.find_one_and_update.call_args
    assert call_args.args[0] == {"session_id": session_id, "user_id": user_id}
    assert call_args.args[1]["$set"]["metadata.is_pinned"] is True
    assert call_args.args[1]["$set"]["updated_at"] == now_mock


@pytest.mark.asyncio
async def test_toggle_pin_session_not_found(storage):
    """Returns None when session doesn't exist."""
    storage._collection = MagicMock()
    storage._collection.find_one = AsyncMock(return_value=None)

    result = await storage.toggle_pin("nonexistent", "user_1")
    assert result is None
    storage._collection.find_one_and_update.assert_not_called()


@pytest.mark.asyncio
async def test_toggle_pin_wrong_user(storage):
    """Returns None when session belongs to a different user."""
    session_id = str(ObjectId())
    fake_doc = {
        "_id": ObjectId(session_id),
        "user_id": "other_user",
        "metadata": {},
    }

    storage._collection = MagicMock()
    storage._collection.find_one = AsyncMock(return_value=fake_doc)

    result = await storage.toggle_pin(session_id, "user_1")
    assert result is None
    storage._collection.find_one_and_update.assert_not_called()


@pytest.mark.asyncio
async def test_list_sessions_sorts_pinned_first(storage):
    """Verify list_sessions uses compound sort with pinned first."""
    user_id = "user_1"

    mock_cursor = MagicMock()
    mock_cursor.skip = MagicMock(return_value=mock_cursor)
    mock_cursor.limit = MagicMock(return_value=mock_cursor)
    mock_cursor.sort = MagicMock(return_value=mock_cursor)
    mock_cursor.to_list = AsyncMock(return_value=[])
    mock_cursor.count_documents = AsyncMock(return_value=0)

    storage._collection = MagicMock()
    storage._collection.find = MagicMock(return_value=mock_cursor)
    storage._collection.count_documents = AsyncMock(return_value=0)
    storage._collection.create_index = AsyncMock()

    await storage.list_sessions(user_id=user_id, skip=0, limit=20)

    mock_cursor.sort.assert_called_once_with([("metadata.is_pinned", -1), ("updated_at", -1)])
