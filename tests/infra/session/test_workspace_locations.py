from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.session.storage import SessionStorage
from src.kernel.errors import AppError
from src.kernel.schemas.session import SessionUpdate


@pytest.fixture
def storage(monkeypatch):
    value = SessionStorage()
    value.ensure_indexes_if_needed = AsyncMock()
    value._find_doc = AsyncMock(
        return_value={
            "_id": "mongo-id",
            "session_id": "chat-a",
            "user_id": "owner",
            "metadata": {"agent_options": {"sandbox": "cloud"}},
        }
    )
    value._collection = SimpleNamespace(find_one_and_update=AsyncMock(return_value=None))
    return value


async def test_binding_change_preserves_previous_location_before_switch(storage, monkeypatch):
    from src.infra.session import workspace_locations

    remember = AsyncMock()
    monkeypatch.setattr(workspace_locations, "remember_workspace_location", remember)
    with pytest.raises(AppError):
        await storage.update(
            "chat-a",
            SessionUpdate(
                metadata={
                    "agent_options": {"sandbox": "local", "sandbox_machine_id": "machine-a"},
                }
            ),
        )
    remember.assert_awaited_once_with("owner", "chat-a", {"sandbox": "cloud"})
    query = storage.collection.find_one_and_update.call_args.args[0]
    assert query["_id"] == "mongo-id"
    assert query["metadata.agent_options"] == {"sandbox": "cloud"}
    assert storage.collection.find_one_and_update.await_count == 1


async def test_failed_location_record_keeps_original_binding(storage, monkeypatch):
    from src.infra.session import workspace_locations

    monkeypatch.setattr(
        workspace_locations,
        "remember_workspace_location",
        AsyncMock(side_effect=OSError("storage unavailable")),
    )
    with pytest.raises(OSError):
        await storage.update("chat-a", SessionUpdate(metadata={"agent_options.sandbox": "local"}))
    storage.collection.find_one_and_update.assert_not_awaited()


async def test_non_workspace_option_change_does_not_archive_or_add_a_cas(storage, monkeypatch):
    from src.infra.session import workspace_locations

    remember = AsyncMock()
    monkeypatch.setattr(workspace_locations, "remember_workspace_location", remember)
    await storage.update("chat-a", SessionUpdate(metadata={"agent_options.thinking": "high"}))
    remember.assert_not_awaited()
    storage._find_doc.assert_not_awaited()


async def test_unchanged_full_options_cannot_undo_a_concurrent_workspace_switch(
    storage, monkeypatch
):
    from src.infra.session import workspace_locations

    remember = AsyncMock()
    monkeypatch.setattr(workspace_locations, "remember_workspace_location", remember)
    with pytest.raises(AppError):
        await storage.update(
            "chat-a",
            SessionUpdate(
                metadata={
                    "agent_options": {"sandbox": "cloud", "thinking": "high"},
                }
            ),
        )
    remember.assert_not_awaited()
    query = storage.collection.find_one_and_update.call_args.args[0]
    assert query["metadata.agent_options"] == {"sandbox": "cloud"}
    assert storage.collection.find_one_and_update.await_count == 1
