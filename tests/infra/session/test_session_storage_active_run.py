from __future__ import annotations

import pytest

from src.infra.session.storage import SessionStorage


class _FakeResult:
    def __init__(self, matched_count: int = 1) -> None:
        self.matched_count = matched_count


class _FakeCollection:
    def __init__(self, matched_count: int = 1) -> None:
        self.matched_count = matched_count
        self.calls: list[tuple[dict, dict]] = []

    async def update_one(self, query: dict, update: dict):
        self.calls.append((query, update))
        return _FakeResult(self.matched_count)


@pytest.mark.asyncio
async def test_update_metadata_if_active_run_requires_matching_run() -> None:
    storage = SessionStorage()
    storage._collection = _FakeCollection(matched_count=1)  # type: ignore[attr-defined]

    result = await storage.update_metadata_if_active_run(
        "session-1",
        "run-1",
        {"task_status": "failed", "active_run_id": None},
    )

    assert result is True
    query, update = storage._collection.calls[0]
    assert query["session_id"] == "session-1"
    assert update["$set"]["metadata.task_status"] == "failed"
    assert update["$set"]["metadata.active_run_id"] is None


@pytest.mark.asyncio
async def test_update_metadata_if_active_run_refuses_stale_run() -> None:
    storage = SessionStorage()
    storage._collection = _FakeCollection(matched_count=0)  # type: ignore[attr-defined]

    result = await storage.update_metadata_if_active_run(
        "session-1",
        "run-old",
        {"task_status": "failed"},
    )

    assert result is False
    assert storage._collection.calls
