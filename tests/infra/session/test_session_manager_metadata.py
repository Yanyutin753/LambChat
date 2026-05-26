from __future__ import annotations

import pytest

from src.infra.session.manager import SessionManager


class _FakeStorage:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def update_metadata_if_active_run(self, session_id: str, run_id: str, metadata: dict):
        self.calls.append((session_id, metadata))
        return True

    async def update_metadata_only(self, session_id: str, metadata: dict):
        self.calls.append((session_id, metadata))
        return True


@pytest.mark.asyncio
async def test_update_session_metadata_uses_active_run_guard_for_run_metadata() -> None:
    manager = SessionManager()
    manager.storage = _FakeStorage()  # type: ignore[assignment]

    await manager.update_session_metadata(
        "session-1",
        {"current_run_id": "run-1", "active_run_id": "run-1"},
    )

    assert manager.storage.calls[0][0] == "session-1"
    assert manager.storage.calls[0][1]["current_run_id"] == "run-1"


@pytest.mark.asyncio
async def test_update_session_metadata_uses_plain_update_without_run_metadata() -> None:
    manager = SessionManager()
    manager.storage = _FakeStorage()  # type: ignore[assignment]

    await manager.update_session_metadata("session-1", {"agent_id": "search"})

    assert manager.storage.calls[0][1] == {"agent_id": "search"}
