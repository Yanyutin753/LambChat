from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.infra.session.manager import SessionManager
from src.kernel.exceptions import SessionError


def manager_for_delete(monkeypatch, claims):
    manager = SessionManager()
    manager.storage = SimpleNamespace(
        claim_attachment_delete_operation=AsyncMock(side_effect=claims),
        delete_claimed_session=AsyncMock(return_value=True),
        cancel_attachment_delete_operation=AsyncMock(),
    )
    manager._trace_storage = SimpleNamespace(
        expire_stale_running_traces=AsyncMock(),
        has_session_trace_documents=AsyncMock(return_value=False),
    )
    manager._file_record_storage = SimpleNamespace(delete_private_session_files=AsyncMock())
    manager.clear_session_messages = AsyncMock()
    monkeypatch.setattr("asyncio.sleep", AsyncMock())
    monkeypatch.setattr("src.infra.session.manager.delete_checkpoints_for_thread", AsyncMock())
    monkeypatch.setattr(
        "src.infra.revealed_file.storage.get_revealed_file_storage",
        lambda: SimpleNamespace(delete_by_session=AsyncMock(return_value=0)),
    )
    return manager


async def test_delete_waits_for_finishing_trace_writer_before_claiming(monkeypatch):
    manager = manager_for_delete(monkeypatch, [None, {"id": "fence", "acquired": True}])
    assert await manager.delete_session("session") is True
    assert manager.storage.claim_attachment_delete_operation.await_count == 2
    manager.storage.delete_claimed_session.assert_awaited_once_with("session", "fence")


async def test_persistent_writer_never_bypasses_delete_fence(monkeypatch):
    manager = manager_for_delete(monkeypatch, [None] * 6)
    with pytest.raises(SessionError, match="session_delete_fence_unavailable"):
        await manager.delete_session("session")
    assert manager.storage.claim_attachment_delete_operation.await_count == 6
    manager.clear_session_messages.assert_not_awaited()
    manager.storage.delete_claimed_session.assert_not_awaited()


async def test_delete_releases_fence_and_resnapshots_a_finishing_trace(monkeypatch):
    manager = manager_for_delete(
        monkeypatch,
        [{"id": "first", "acquired": True}, {"id": "second", "acquired": True}],
    )
    manager.trace_storage.has_session_trace_documents.side_effect = [True, False]

    assert await manager.delete_session("session") is True

    manager.storage.cancel_attachment_delete_operation.assert_awaited_once_with("session", "first")
    assert manager.clear_session_messages.await_count == 2
    manager.storage.delete_claimed_session.assert_awaited_once_with("session", "second")


async def test_surviving_trace_never_allows_anchor_deletion(monkeypatch):
    manager = manager_for_delete(
        monkeypatch, [{"id": f"fence-{i}", "acquired": True} for i in range(6)]
    )
    manager.trace_storage.has_session_trace_documents.return_value = True

    with pytest.raises(SessionError, match="session_delete_has_trace_survivors"):
        await manager.delete_session("session")

    assert manager.clear_session_messages.await_count == 6
    assert manager.storage.cancel_attachment_delete_operation.await_count == 6
    manager.storage.delete_claimed_session.assert_not_awaited()
