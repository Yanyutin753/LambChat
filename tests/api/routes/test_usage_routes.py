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
                    "error_message": "Error code: 429 - rate limit exceeded",
                    "error_type": "RateLimitError",
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
    assert response.items[0].error_message == "Error code: 429 - rate limit exceeded"
    assert response.items[0].error_type == "RateLimitError"
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
        start_date=None,
        user=user,
    )

    assert response.total_tokens == 15
    assert storage.calls[0]["user_id"] == "user-2"
    assert storage.calls[0]["start_date"] == "2026-06-14T00:00:00+00:00"
    assert storage.calls[0]["skip"] == 0
    assert storage.calls[0]["limit"] == 1


@pytest.mark.asyncio
async def test_get_usage_stats_prefers_explicit_start_date(monkeypatch) -> None:
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

    await usage_routes.get_usage_stats(
        user_id=None,
        period="today",
        start_date="2026-06-14T00:00:00+08:00",
        user=user,
    )

    # 显式 start_date（客户端本地 0 点）优先于 period 推导的 UTC 0 点
    assert storage.calls[0]["start_date"] == "2026-06-14T00:00:00+08:00"


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
        start_date=None,
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
async def test_get_usage_dashboard_prefers_explicit_start_date(monkeypatch) -> None:
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

    await usage_routes.get_usage_dashboard(
        user_id=None,
        period="today",
        search=None,
        start_date="2026-06-14T00:00:00+08:00",
        user=user,
    )

    # 与 /stats 一致：显式 start_date（客户端本地 0 点）优先于 period 推导
    assert storage.calls[-1]["start_date"] == "2026-06-14T00:00:00+08:00"


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
        start_date=None,
        user=user,
    )

    assert storage.calls[-1]["user_id"] is None
    assert storage.calls[-1]["search"] == "Ada"
    assert storage.calls[-1]["start_date"] is None


@pytest.mark.asyncio
async def test_get_usage_stats_defaults_admin_to_own_usage(monkeypatch) -> None:
    """管理员不传 user_id 时也应查自己的用量（输入框当日个人用量 chip 依赖此语义）。"""
    storage = _FakeUsageStorage()
    monkeypatch.setattr(usage_routes, "get_usage_storage", lambda: storage)
    user = TokenPayload(
        sub="admin-1",
        username="Admin",
        permissions=["usage:read", "usage:admin"],
    )

    await usage_routes.get_usage_stats(
        user_id=None,
        period="today",
        start_date="2026-06-14T00:00:00+08:00",
        user=user,
    )

    assert storage.calls[0]["user_id"] == "admin-1"


@pytest.mark.asyncio
async def test_dashboard_exposes_cache_read_share(monkeypatch) -> None:
    """缓存命中率指标必须透出：summary.cache_read_share + 每日趋势——
    命中率塌了能在用量页第一时间看到，不用手动查库。"""

    # 层1：_format_dashboard 从聚合管道输出计算命中率
    from src.infra.usage.storage import _format_dashboard

    formatted = _format_dashboard(
        {
            "summary": [
                {
                    "total_requests": 10,
                    "total_tokens": 1000,
                    "total_input_tokens": 800,
                    "total_output_tokens": 200,
                    "total_cache_read_tokens": 600,
                    "total_duration": 5.0,
                    "total_tool_calls": 3,
                    "total_cost_usd": 0.1,
                    "unpriced_requests": 0,
                    "scheduled_runs": 0,
                    "failed_requests": 0,
                    "successful_requests": 10,
                }
            ],
            "daily": [
                {
                    "_id": "2026-09-03",
                    "requests": 4,
                    "tokens": 400,
                    "duration": 2.0,
                    "cost_usd": 0.04,
                    "scheduled_runs": 0,
                    "failed_requests": 0,
                    "tool_calls": 1,
                    "input_tokens": 300,
                    "cache_creation_tokens": 50,
                    "cache_read_tokens": 250,
                }
            ],
            "agents": [],
            "teams": [],
            "personas": [],
            "models": [],
            "users": [],
            "sources": [],
            "triggers": [],
        }
    )
    assert abs(formatted["summary"]["cache_read_share"] - 0.75) < 1e-6
    assert abs(formatted["daily"][0]["cache_read_share"] - 250 / 300) < 1e-6

    # 层2：响应模型透传（schema 已声明 cache_read_share，不再被 pydantic 丢弃）
    class _Storage:
        async def get_usage_dashboard(self, **kwargs):
            return formatted

    monkeypatch.setattr(usage_routes, "get_usage_storage", lambda: _Storage())
    user = TokenPayload(sub="admin-1", username="Admin", permissions=["usage:read"])

    resp = await usage_routes.get_usage_dashboard(
        user_id=None, period="7d", search=None, start_date=None, user=user
    )

    assert abs(resp.summary.cache_read_share - 0.75) < 1e-6
    assert resp.daily[0].cache_read_tokens == 250
    assert abs(resp.daily[0].cache_read_share - 250 / 300) < 1e-6
