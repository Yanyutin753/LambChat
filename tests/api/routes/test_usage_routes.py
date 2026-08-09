from datetime import datetime, timezone

import pytest

from src.api.routes import usage as usage_routes
from src.kernel.schemas.user import TokenPayload


class _FakeUsageStorage:
    def __init__(self):
        self.calls = []

    async def list_usage_logs(self, **kwargs):
        self.calls.append(kwargs)
        return (
            [
                {
                    "trace_id": "trace-1",
                    "session_id": "session-1",
                    "user_id": kwargs.get("user_id") or "user-2",
                    "username": "Ada",
                    "model": "openai/gpt-5",
                    "input_tokens": 10,
                    "output_tokens": 5,
                    "total_tokens": 15,
                    "cache_creation_tokens": 2,
                    "cache_read_tokens": 3,
                    "duration": 1.5,
                    "started_at": datetime(2026, 6, 14, tzinfo=timezone.utc),
                    "completed_at": None,
                    "status": "completed",
                }
            ],
            1,
            {
                "total_requests": 1,
                "total_input_tokens": 10,
                "total_output_tokens": 5,
                "total_tokens": 15,
                "total_cache_creation_tokens": 2,
                "total_cache_read_tokens": 3,
                "total_duration": 1.5,
            },
        )

    async def get_usage_dashboard(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "summary": {
                "total_requests": 2,
                "total_tokens": 100,
                "total_input_tokens": 40,
                "total_output_tokens": 60,
                "total_cache_read_tokens": 10,
                "total_duration": 120.0,
                "total_tool_calls": 5,
                "scheduled_runs": 1,
                "success_rate": 0.5,
            },
            "daily": [
                {
                    "date": "2026-06-14",
                    "requests": 2,
                    "tokens": 100,
                    "duration": 120.0,
                    "scheduled_runs": 1,
                    "tool_calls": 5,
                }
            ],
            "top_agents": [
                {
                    "id": "Team Agent",
                    "name": "Team Agent",
                    "requests": 2,
                    "tokens": 100,
                    "duration": 120.0,
                }
            ],
            "top_teams": [
                {
                    "id": "team-1",
                    "name": "Growth Team",
                    "requests": 1,
                    "tokens": 70,
                    "duration": 80.0,
                }
            ],
            "top_personas": [
                {
                    "id": "persona-1",
                    "name": "Researcher",
                    "requests": 1,
                    "tokens": 30,
                    "duration": 40.0,
                }
            ],
            "top_models": [
                {
                    "id": "openai/gpt-5",
                    "name": "openai/gpt-5",
                    "requests": 2,
                    "tokens": 100,
                    "duration": 120.0,
                    "input_tokens": 80,
                    "cache_creation_tokens": 5,
                    "cache_read_tokens": 60,
                    "cache_read_share": 0.75,
                    "zero_cache_requests": 1,
                }
            ],
        }


@pytest.mark.asyncio
async def test_list_usage_logs_restricts_non_admin_to_current_user(monkeypatch) -> None:
    storage = _FakeUsageStorage()
    monkeypatch.setattr(usage_routes, "get_usage_storage", lambda: storage)
    user = TokenPayload(
        sub="user-1",
        username="User",
        permissions=["usage:read"],
    )

    response = await usage_routes.list_usage_logs(
        skip=0,
        limit=50,
        user_id="user-2",
        search="Ada",
        model="openai/gpt-5",
        start_date=None,
        end_date=None,
        user=user,
    )

    assert response.total == 1
    assert storage.calls == [
        {
            "user_id": "user-1",
            "model": "openai/gpt-5",
            "start_date": None,
            "end_date": None,
            "search": None,
            "skip": 0,
            "limit": 50,
        }
    ]


@pytest.mark.asyncio
async def test_list_usage_logs_allows_admin_global_search(monkeypatch) -> None:
    storage = _FakeUsageStorage()
    monkeypatch.setattr(usage_routes, "get_usage_storage", lambda: storage)
    user = TokenPayload(
        sub="admin-1",
        username="Admin",
        permissions=["usage:read", "usage:admin"],
    )

    await usage_routes.list_usage_logs(
        skip=5,
        limit=25,
        user_id=None,
        search="Ada",
        model=None,
        start_date=None,
        end_date=None,
        user=user,
    )

    assert storage.calls[0]["user_id"] is None
    assert storage.calls[0]["search"] == "Ada"
    assert storage.calls[0]["skip"] == 5
    assert storage.calls[0]["limit"] == 25


@pytest.mark.asyncio
async def test_get_usage_stats_uses_period_and_admin_scope(monkeypatch) -> None:
    storage = _FakeUsageStorage()
    monkeypatch.setattr(usage_routes, "get_usage_storage", lambda: storage)
    monkeypatch.setattr(
        usage_routes,
        "_now_utc",
        lambda: datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc),
    )
    user = TokenPayload(
        sub="admin-1",
        username="Admin",
        permissions=["usage:read", "usage:admin"],
    )

    response = await usage_routes.get_usage_stats(
        user_id="user-2",
        period="today",
        user=user,
    )

    assert response.total_tokens == 15
    assert storage.calls[0]["user_id"] == "user-2"
    assert storage.calls[0]["start_date"] == "2026-06-14T00:00:00+00:00"
    assert storage.calls[0]["skip"] == 0
    assert storage.calls[0]["limit"] == 1


@pytest.mark.asyncio
async def test_get_usage_dashboard_restricts_non_admin_to_current_user(monkeypatch) -> None:
    storage = _FakeUsageStorage()
    monkeypatch.setattr(usage_routes, "get_usage_storage", lambda: storage)
    monkeypatch.setattr(
        usage_routes,
        "_now_utc",
        lambda: datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc),
    )
    user = TokenPayload(
        sub="user-1",
        username="User",
        permissions=["usage:read"],
    )

    response = await usage_routes.get_usage_dashboard(
        user_id="user-2",
        period="week",
        search="Ada",
        user=user,
    )

    assert response.summary.total_requests == 2
    assert response.daily[0].date == "2026-06-14"
    assert response.top_models[0].cache_read_tokens == 60
    assert response.top_models[0].cache_read_share == 0.75
    assert response.top_agents[0].cache_read_tokens == 0
    assert storage.calls[-1]["user_id"] == "user-1"
    assert storage.calls[-1]["search"] is None
    assert storage.calls[-1]["start_date"] == "2026-06-07T12:00:00+00:00"


@pytest.mark.asyncio
async def test_get_usage_dashboard_allows_admin_global_search(monkeypatch) -> None:
    storage = _FakeUsageStorage()
    monkeypatch.setattr(usage_routes, "get_usage_storage", lambda: storage)
    user = TokenPayload(
        sub="admin-1",
        username="Admin",
        permissions=["usage:read", "usage:admin"],
    )

    await usage_routes.get_usage_dashboard(
        user_id=None,
        period="all",
        search="Ada",
        user=user,
    )

    assert storage.calls[-1]["user_id"] is None
    assert storage.calls[-1]["search"] == "Ada"
    assert storage.calls[-1]["start_date"] is None
