from typing import Any

import pytest
from langchain_core.tools import BaseTool

from src.kernel.schemas.mcp import MCPRoleQuota, MCPServerCreate


def test_mcp_create_schema_preserves_role_quotas() -> None:
    server = MCPServerCreate.model_validate(
        {
            "name": "github",
            "transport": "sse",
            "url": "https://example.test/sse",
            "allowed_roles": ["user"],
            "role_quotas": {
                "user": {
                    "daily_limit": 10,
                    "weekly_limit": 50,
                }
            },
        }
    )

    assert server.role_quotas == {
        "user": MCPRoleQuota(daily_limit=10, weekly_limit=50),
    }


def test_resolve_role_quota_uses_most_permissive_user_role() -> None:
    from src.infra.mcp.quota import resolve_role_quota

    quota = resolve_role_quota(
        {
            "user": MCPRoleQuota(daily_limit=10, weekly_limit=50),
            "vip": MCPRoleQuota(daily_limit=None, weekly_limit=200),
        },
        ["user", "vip"],
    )

    assert quota.daily_limit is None
    assert quota.weekly_limit == 200


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, int] = {}
        self.expirations: dict[str, int] = {}

    async def eval(self, script: str, numkeys: int, *args: Any) -> list[Any]:
        del script, numkeys
        daily_key, weekly_key = args[0], args[1]
        daily_limit, weekly_limit = int(args[2]), int(args[3])
        daily_ttl, weekly_ttl = int(args[4]), int(args[5])

        daily_current = self.values.get(daily_key, 0)
        weekly_current = self.values.get(weekly_key, 0)
        if daily_limit >= 0 and daily_current >= daily_limit:
            return [0, "daily", daily_current, daily_limit, daily_ttl]
        if weekly_limit >= 0 and weekly_current >= weekly_limit:
            return [0, "weekly", weekly_current, weekly_limit, weekly_ttl]

        if daily_limit >= 0:
            self.values[daily_key] = daily_current + 1
            self.expirations[daily_key] = daily_ttl
        if weekly_limit >= 0:
            self.values[weekly_key] = weekly_current + 1
            self.expirations[weekly_key] = weekly_ttl
        return [
            1,
            "",
            self.values.get(daily_key, daily_current),
            daily_limit,
            daily_ttl,
            self.values.get(weekly_key, weekly_current),
            weekly_limit,
            weekly_ttl,
        ]


@pytest.mark.asyncio
async def test_limiter_blocks_when_daily_quota_is_exhausted() -> None:
    from src.infra.mcp.quota import MCPUsageLimiter

    redis = _FakeRedis()
    limiter = MCPUsageLimiter(redis=redis)
    quota = MCPRoleQuota(daily_limit=1, weekly_limit=10)

    first = await limiter.check_and_consume(
        user_id="user-1",
        server_name="github",
        quota=quota,
    )
    second = await limiter.check_and_consume(
        user_id="user-1",
        server_name="github",
        quota=quota,
    )

    assert first.allowed is True
    assert second.allowed is False
    assert second.period == "daily"
    assert second.limit == 1


class _FakeOriginalTool(BaseTool):
    name: str = "search"
    description: str = "Search"

    def _run(self, *args: Any, **kwargs: Any) -> str:
        return "sync"

    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        return "called"


@pytest.mark.asyncio
async def test_mcp_tool_wrapper_returns_quota_error_without_calling_original(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from src.infra.mcp.quota import MCPQuotaResult
    from src.infra.tool.mcp_client import MCPToolWithRetry

    calls: list[str] = []

    async def fake_check_and_consume(*args: Any, **kwargs: Any) -> MCPQuotaResult:
        calls.append("quota")
        return MCPQuotaResult(
            allowed=False,
            period="daily",
            limit=1,
            current=1,
            reset_at="2026-04-23T00:00:00+00:00",
        )

    monkeypatch.setattr(
        "src.infra.mcp.quota.check_and_consume_mcp_quota",
        fake_check_and_consume,
    )

    tool = MCPToolWithRetry(
        _FakeOriginalTool(),
        user_id="user-1",
        server_name="github",
        user_roles=["user"],
        is_admin=False,
        role_quotas={"user": MCPRoleQuota(daily_limit=1)},
    )

    result = await tool._arun(query="hello")

    assert calls == ["quota"]
    assert "MCP quota exceeded" in result
    assert "github" in result
