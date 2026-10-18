"""Scheduled execution cards must distinguish approvals from active execution."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.api.routes.scheduled_task import list_task_sessions
from src.infra.task.status import TaskStatus
from src.kernel.schemas.scheduled_task import RunStatus


@pytest.mark.parametrize(
    ("record_status", "live_status", "display_status"),
    [
        (RunStatus.RUNNING, TaskStatus.WAITING_HUMAN, "waiting_human"),
        (RunStatus.RUNNING, TaskStatus.RUNNING, "running"),
        (RunStatus.SUCCESS, TaskStatus.WAITING_HUMAN, "success"),
    ],
)
async def test_conversation_session_card_shows_exact_run_approval_state(
    record_status, live_status, display_status
):
    task = SimpleNamespace(
        owner_id="owner",
        execution_mode="conversation",
        target_session_id="child",
        name="Scheduled task",
        agent_id="search",
    )
    record = SimpleNamespace(
        id="run",
        session_id="child",
        status=record_status,
        created_at=None,
        finished_at=None,
        started_at=None,
    )
    service = SimpleNamespace(
        get_task=AsyncMock(return_value=task),
        get_task_runs=AsyncMock(return_value=([record], 1)),
    )
    manager = SimpleNamespace(get_run_status=AsyncMock(return_value=live_status))
    with patch("src.infra.task.manager.get_task_manager", return_value=manager):
        result = await list_task_sessions(
            "task", skip=0, limit=20, user=SimpleNamespace(sub="owner"), service=service
        )
    assert result.items[0].metadata == {"run_id": "run", "run_status": display_status}
    if record_status == RunStatus.RUNNING:
        manager.get_run_status.assert_awaited_once_with("child", "run")
    else:
        manager.get_run_status.assert_not_awaited()


@pytest.mark.parametrize(
    ("user_id", "run_ids", "expected_status"),
    [
        ("owner", ["scheduled-1"], 200),
        ("other", ["scheduled-1"], 404),
        ("owner", [f"scheduled-{index}" for index in range(101)], 422),
    ],
)
async def test_progress_route_reconciles_named_runs_only_for_the_parent_owner(
    user_id, run_ids, expected_status
):
    from datetime import datetime, timezone

    from fastapi import FastAPI
    from httpx import ASGITransport, AsyncClient

    from src.api.deps import get_current_user_required
    from src.api.error_handlers import register_error_handlers
    from src.api.routes.scheduled_task import router

    record = {
        "_id": "scheduled-1",
        "task_id": "task",
        "owner_id": "owner",
        "target_session_id": "parent",
        "session_id": "sch_conversation_task",
        "conversation_state": "finished",
        "status": "failed",
        "created_at": datetime.now(timezone.utc),
    }
    queries = []

    class Cursor:
        def __aiter__(self):
            async def rows():
                yield record

            return rows()

    def find(query):
        queries.append(query)
        return Cursor()

    storage = SimpleNamespace(
        _get_collection=lambda _: SimpleNamespace(find=find),
        get_task=AsyncMock(
            return_value=SimpleNamespace(
                name="Numbers", owner_id="owner", notification_policy="always"
            )
        ),
    )
    app = FastAPI()
    app.include_router(router, prefix="/api/scheduled-tasks")
    register_error_handlers(app)
    app.dependency_overrides[get_current_user_required] = lambda: SimpleNamespace(
        sub=user_id, permissions=["chat:write"]
    )
    with (
        patch("src.infra.scheduler.storage.get_scheduled_task_storage", return_value=storage),
        patch(
            "src.infra.session.manager.SessionManager.get_session",
            AsyncMock(return_value=SimpleNamespace(user_id="owner")),
        ),
        patch(
            "src.infra.scheduler.results.get_trace_storage",
            return_value=SimpleNamespace(
                get_session_events=AsyncMock(return_value=[]),
                get_run_events=AsyncMock(return_value=[]),
            ),
        ),
        patch(
            "src.infra.task.manager.get_task_manager",
            return_value=SimpleNamespace(get_run_status=AsyncMock(return_value=TaskStatus.FAILED)),
        ),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get(
                "/api/scheduled-tasks/session/parent/progress",
                params=[("run_id", run_id) for run_id in run_ids],
            )
    assert response.status_code == expected_status
    if expected_status == 200:
        assert response.json()["progress"][0]["status"] == "failed"
        assert queries[0]["owner_id"] == "owner"
        assert queries[0]["target_session_id"] == "parent"
        assert {"_id": {"$in": ["scheduled-1"]}} in queries[0]["$or"]
    else:
        assert queries == []
