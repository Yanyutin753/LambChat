"""Result notifications reuse the journal without masquerading as a human run completion."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.infra.scheduler.results import publish_result_notification


@pytest.mark.parametrize("fresh", [True, False])
async def test_result_notification_retry_does_not_increment_unread_again(fresh):
    sessions = SimpleNamespace(increment_unread_count=AsyncMock())
    executor = SimpleNamespace(_send_task_notification=AsyncMock())
    manager = SimpleNamespace(_ensure_executor=lambda: executor)
    with (
        patch("src.infra.session.storage.SessionStorage", return_value=sessions),
        patch("src.infra.task.manager.get_task_manager", return_value=manager),
    ):
        await publish_result_notification(
            SimpleNamespace(id="task", owner_id="owner"), "parent", "scheduled-1", fresh=fresh
        )
    assert sessions.increment_unread_count.await_count == int(fresh)
    prepared = executor._send_task_notification.call_args.kwargs["prepared_completion"]
    assert prepared["session_id"] == "parent"
    assert prepared["notification_kind"] == "scheduled_result"
    assert prepared["dedupe_key"] == "scheduled-result:scheduled-1"
