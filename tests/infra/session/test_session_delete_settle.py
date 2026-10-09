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
