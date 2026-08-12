from __future__ import annotations

import asyncio

import pytest

from src.infra.feedback.manager import FeedbackManager
from src.kernel.schemas.feedback import FeedbackStats


class _ConcurrentFeedbackStorage:
    def __init__(self, *, fail_count: bool = False) -> None:
        self.started: set[str] = set()
        self.observed: dict[str, set[str]] = {}
        self.fail_count = fail_count

    async def _wait_for_all(self, name: str) -> None:
        self.started.add(name)
        for _ in range(20):
            if self.started == {"list", "count", "stats"}:
                break
            await asyncio.sleep(0)
        self.observed[name] = set(self.started)

    async def list(self, *_args):
        await self._wait_for_all("list")
        return []

    async def count(self, *_args):
        await self._wait_for_all("count")
        if self.fail_count:
            raise RuntimeError("count failed")
        return 0

    async def get_stats(self, *_args):
        await self._wait_for_all("stats")
        return FeedbackStats()


@pytest.mark.asyncio
async def test_list_feedback_starts_items_count_and_stats_concurrently() -> None:
    storage = _ConcurrentFeedbackStorage()
    manager = FeedbackManager()
    manager.storage = storage  # type: ignore[assignment]

    response = await manager.list_feedback(session_id="session-1")

    assert response.items == []
    assert response.total == 0
    assert response.stats == FeedbackStats()
    assert storage.observed == {
        "list": {"list", "count", "stats"},
        "count": {"list", "count", "stats"},
        "stats": {"list", "count", "stats"},
    }


@pytest.mark.asyncio
async def test_list_feedback_propagates_read_failure_without_partial_response() -> None:
    storage = _ConcurrentFeedbackStorage(fail_count=True)
    manager = FeedbackManager()
    manager.storage = storage  # type: ignore[assignment]

    with pytest.raises(RuntimeError, match="count failed"):
        await manager.list_feedback(session_id="session-1")

    assert storage.started == {"list", "count", "stats"}
