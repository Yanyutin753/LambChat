"""Tests for session pin toggle functionality."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from bson import ObjectId

from src.infra.session.storage import SessionStorage


@pytest.fixture
def storage():
    return SessionStorage()


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
    storage._collection.find_one = AsyncMock(return_value=fake_doc)
    storage._collection.find_one_and_update = AsyncMock(return_value=updated_doc)
    storage._build_session = MagicMock(
        return_value=MagicMock(
            metadata={"is_pinned": True},
        )
    )

    with patch("src.infra.session.storage.utc_now", return_value=now_mock):
        result = await storage.toggle_pin(session_id, user_id)

    assert result is not None
    assert result.metadata["is_pinned"] is True
    storage._collection.find_one_and_update.assert_called_once()

    # The update flips is_pinned to True and stamps updated_at.
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
        "updated_at": fake_doc["updated_at"],
    }

    storage._collection = MagicMock()
    storage._collection.find_one = AsyncMock(return_value=fake_doc)
    storage._collection.find_one_and_update = AsyncMock(return_value=updated_doc)
    storage._build_session = MagicMock(
        return_value=MagicMock(
            metadata={"is_pinned": False},
        )
    )

    result = await storage.toggle_pin(session_id, user_id)

    assert result is not None
    assert result.metadata["is_pinned"] is False
    call_args = storage._collection.find_one_and_update.call_args
    assert call_args.args[1]["$set"]["metadata.is_pinned"] is False


@pytest.mark.asyncio
async def test_toggle_pin_session_not_found(storage):
    """Returns None when session doesn't exist."""
    storage._collection = MagicMock()
    storage._collection.find_one = AsyncMock(return_value=None)

    result = await storage.toggle_pin("nonexistent", "user_1")
    assert result is None


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

    # Bypass ensure_indexes_if_needed by setting the class flag
    SessionStorage._indexes_done = True

    await storage.list_sessions(user_id=user_id, skip=0, limit=20)

    mock_cursor.sort.assert_called_once_with([("metadata.is_pinned", -1), ("updated_at", -1)])
