"""Redis-backed per-user usage quotas for system MCP servers."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from src.infra.logging import get_logger
from src.infra.storage.redis import get_redis_client
from src.kernel.schemas.mcp import MCPRoleQuota

logger = get_logger(__name__)

_UNLIMITED = -1

_CHECK_AND_CONSUME_SCRIPT = """
local daily_key = KEYS[1]
local weekly_key = KEYS[2]
local daily_limit = tonumber(ARGV[1])
local weekly_limit = tonumber(ARGV[2])
local daily_ttl = tonumber(ARGV[3])
local weekly_ttl = tonumber(ARGV[4])

local daily_current = tonumber(redis.call("get", daily_key) or "0")
local weekly_current = tonumber(redis.call("get", weekly_key) or "0")

if daily_limit >= 0 and daily_current >= daily_limit then
    return {0, "daily", daily_current, daily_limit, daily_ttl}
end

if weekly_limit >= 0 and weekly_current >= weekly_limit then
    return {0, "weekly", weekly_current, weekly_limit, weekly_ttl}
end

if daily_limit >= 0 then
    daily_current = redis.call("incr", daily_key)
    if daily_current == 1 then
        redis.call("expire", daily_key, daily_ttl)
    end
end

if weekly_limit >= 0 then
    weekly_current = redis.call("incr", weekly_key)
    if weekly_current == 1 then
        redis.call("expire", weekly_key, weekly_ttl)
    end
end

return {1, "", daily_current, daily_limit, daily_ttl, weekly_current, weekly_limit, weekly_ttl}
"""


@dataclass(frozen=True)
class MCPQuotaResult:
    """Result of a quota check."""

    allowed: bool
    period: str = ""
    limit: int | None = None
    current: int = 0
    reset_at: str = ""


def _quota_from_value(value: MCPRoleQuota | dict[str, Any]) -> MCPRoleQuota:
    if isinstance(value, MCPRoleQuota):
        return value
    return MCPRoleQuota.model_validate(value)


def _merge_limit(values: list[int | None]) -> int | None:
    if not values:
        return None
    if any(value is None for value in values):
        return None
    return max(value for value in values if value is not None)


def resolve_role_quota(
    role_quotas: Mapping[str, MCPRoleQuota | dict[str, Any]] | None,
    user_roles: list[str] | None,
) -> MCPRoleQuota | None:
    """Resolve the most permissive quota across the user's matching roles."""
    if not role_quotas or not user_roles:
        return None

    matched = [
        _quota_from_value(role_quotas[role_name])
        for role_name in user_roles
        if role_name in role_quotas
    ]
    if not matched:
        return None

    return MCPRoleQuota(
        daily_limit=_merge_limit([quota.daily_limit for quota in matched]),
        weekly_limit=_merge_limit([quota.weekly_limit for quota in matched]),
    )


def _safe_key_part(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]


def _window_info(now: datetime | None = None) -> tuple[str, int, str, int]:
    current = now or datetime.now(UTC)
    current = current.astimezone(UTC)

    next_day = (current + timedelta(days=1)).date()
    day_end = datetime(next_day.year, next_day.month, next_day.day, tzinfo=UTC)
    daily_ttl = max(1, int((day_end - current).total_seconds()))

    iso_year, iso_week, _ = current.isocalendar()
    start_of_week = current - timedelta(days=current.weekday())
    start_of_week = datetime(
        start_of_week.year,
        start_of_week.month,
        start_of_week.day,
        tzinfo=UTC,
    )
    week_end = start_of_week + timedelta(days=7)
    weekly_ttl = max(1, int((week_end - current).total_seconds()))

    return current.strftime("%Y%m%d"), daily_ttl, f"{iso_year}-W{iso_week:02d}", weekly_ttl


class MCPUsageLimiter:
    """Atomic Redis limiter for per-user MCP server calls."""

    def __init__(self, redis: Any | None = None) -> None:
        self._redis = redis

    @property
    def redis(self) -> Any:
        if self._redis is None:
            self._redis = get_redis_client()
        return self._redis

    async def check_and_consume(
        self,
        *,
        user_id: str,
        server_name: str,
        quota: MCPRoleQuota,
    ) -> MCPQuotaResult:
        if quota.daily_limit is None and quota.weekly_limit is None:
            return MCPQuotaResult(allowed=True)

        day_id, daily_ttl, week_id, weekly_ttl = _window_info()
        user_key = _safe_key_part(user_id)
        server_key = _safe_key_part(server_name)
        daily_key = f"mcp:usage:{user_key}:{server_key}:daily:{day_id}"
        weekly_key = f"mcp:usage:{user_key}:{server_key}:weekly:{week_id}"

        raw = await self.redis.eval(
            _CHECK_AND_CONSUME_SCRIPT,
            2,
            daily_key,
            weekly_key,
            quota.daily_limit if quota.daily_limit is not None else _UNLIMITED,
            quota.weekly_limit if quota.weekly_limit is not None else _UNLIMITED,
            daily_ttl,
            weekly_ttl,
        )
        if int(raw[0]) == 1:
            return MCPQuotaResult(allowed=True)

        period, current, limit, ttl = raw[1], raw[2], raw[3], raw[4]
        reset_at = datetime.now(UTC) + timedelta(seconds=int(ttl))
        return MCPQuotaResult(
            allowed=False,
            period=str(period),
            current=int(current),
            limit=int(limit),
            reset_at=reset_at.isoformat(),
        )


async def check_and_consume_mcp_quota(
    *,
    user_id: str | None,
    server_name: str | None,
    user_roles: list[str] | None,
    role_quotas: Mapping[str, MCPRoleQuota | dict[str, Any]] | None,
    is_admin: bool = False,
) -> MCPQuotaResult:
    """Resolve and consume quota for a known MCP server policy."""
    if is_admin or not user_id or not server_name:
        return MCPQuotaResult(allowed=True)

    quota = resolve_role_quota(role_quotas, user_roles)
    if quota is None:
        return MCPQuotaResult(allowed=True)

    try:
        return await MCPUsageLimiter().check_and_consume(
            user_id=user_id,
            server_name=server_name,
            quota=quota,
        )
    except Exception as exc:
        logger.error("[MCP Quota] Redis quota check failed: %s", exc)
        return MCPQuotaResult(allowed=True)


async def resolve_user_mcp_access(user_id: str) -> tuple[list[str], bool]:
    """Resolve user's role names and whether they have MCP admin permission."""
    try:
        from src.infra.role.storage import RoleStorage
        from src.infra.user.storage import UserStorage

        user = await UserStorage().get_by_id(user_id)
        if not user or not user.roles:
            return [], False

        role_storage = RoleStorage()
        roles = await role_storage.get_by_names(user.roles)
        resolved_roles: list[str] = []
        permissions: set[str] = set()
        for role in roles:
            resolved_roles.append(role.name)
            for permission in role.permissions:
                permissions.add(permission if isinstance(permission, str) else permission.value)
        return resolved_roles, "mcp:admin" in permissions
    except Exception as exc:
        logger.warning("[MCP Quota] Failed to resolve user MCP access: %s", exc)
        return [], False


async def check_and_consume_system_mcp_quota(
    *,
    user_id: str | None,
    server_name: str | None,
) -> MCPQuotaResult:
    """Resolve and consume quota for a persisted system MCP server."""
    if not user_id or not server_name:
        return MCPQuotaResult(allowed=True)

    try:
        from src.infra.mcp.storage import MCPStorage

        server = await MCPStorage().get_system_server(server_name)
        if not server:
            return MCPQuotaResult(allowed=True)

        user_roles, is_admin = await resolve_user_mcp_access(user_id)
        return await check_and_consume_mcp_quota(
            user_id=user_id,
            server_name=server_name,
            user_roles=user_roles,
            role_quotas=server.role_quotas,
            is_admin=is_admin,
        )
    except Exception as exc:
        logger.error("[MCP Quota] Failed to check system MCP quota: %s", exc)
        return MCPQuotaResult(allowed=True)


def quota_error_json(server_name: str, result: MCPQuotaResult) -> str:
    """Serialize a quota denial in a tool-friendly shape."""
    return json.dumps(
        {
            "error": "MCP quota exceeded",
            "server": server_name,
            "period": result.period,
            "limit": result.limit,
            "current": result.current,
            "reset_at": result.reset_at,
        },
        ensure_ascii=False,
    )
