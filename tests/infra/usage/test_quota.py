from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from src.infra.usage.quota import quota_windows, resolve_budgets, usd_units
from src.kernel.schemas.role import RoleLimits


def test_new_and_builtin_roles_default_to_unlimited_monetary_usage():
    from src.infra.auth.rbac import RBACManager
    from src.kernel.schemas.role import RoleCreate

    defaults = [RoleCreate(name="custom").limits, RoleLimits()]
    defaults.extend(
        RoleLimits(**(role.get("limits") or {})) for role in RBACManager().get_default_roles()
    )
    for limits in defaults:
        assert resolve_budgets([SimpleNamespace(limits=limits)]) == (None, None)


def test_both_window_candidates_start_now_and_last_five_hours_or_seven_days():
    windows = quota_windows(datetime(2026, 10, 18, 14, 30, tzinfo=UTC))
    assert windows[0][0] == "f20261018143000000000"
    assert windows[1][0] == "w20261018143000000000"
    assert windows[0][1].isoformat() == "2026-10-19T03:30:00+08:00"
    assert windows[1][1].isoformat() == "2026-10-25T22:30:00+08:00"


def test_unconfigured_roles_do_not_erase_another_roles_budget():
    roles = [
        SimpleNamespace(limits=RoleLimits()),
        SimpleNamespace(limits=RoleLimits(five_hour_budget_usd=1, weekly_budget_usd=5)),
        SimpleNamespace(limits=RoleLimits(five_hour_budget_usd=3, weekly_budget_usd=8)),
    ]
    assert resolve_budgets(roles) == (3, 8)
    assert resolve_budgets([]) == (None, None)
    assert resolve_budgets([SimpleNamespace(limits=RoleLimits(five_hour_budget_usd=0))]) == (
        0,
        None,
    )


@pytest.mark.parametrize("value", [-1, float("inf"), float("nan"), True])
def test_role_budget_rejects_invalid_money(value):
    with pytest.raises(ValidationError):
        RoleLimits(five_hour_budget_usd=value)


def test_reservations_round_up_to_nanodollars():
    assert usd_units(0.0000000001) == 1
    assert usd_units(1.23) == 1_230_000_000


def test_quota_only_update_cannot_change_system_permissions():
    from src.kernel.schemas.role import RoleQuotaUpdate

    with pytest.raises(ValidationError):
        RoleQuotaUpdate(five_hour_budget_usd=1, permissions=[])
    assert RoleQuotaUpdate(five_hour_budget_usd=0).model_dump(exclude_unset=True) == {
        "five_hour_budget_usd": 0
    }


async def test_budget_policy_reads_authoritative_roles_instead_of_optional_cache(monkeypatch):
    from unittest.mock import AsyncMock

    from src.infra.usage.quota import user_budgets

    class Cursor:
        def __aiter__(self):
            return self

        async def __anext__(self):
            if getattr(self, "done", False):
                raise StopAsyncIteration
            self.done = True
            return {"name": "member", "limits": {"five_hour_budget_usd": 0}}

    cached = AsyncMock(return_value=[SimpleNamespace(name="member", limits=RoleLimits())])
    roles = SimpleNamespace(
        collection=SimpleNamespace(find=lambda *args, **kwargs: Cursor()), get_by_names=cached
    )
    monkeypatch.setattr("src.infra.role.storage.RoleStorage", lambda: roles)
    monkeypatch.setattr(
        "src.infra.user.storage.UserStorage.get_by_id",
        AsyncMock(return_value=SimpleNamespace(is_active=True, roles=["member"])),
    )
    assert await user_budgets("user") == (0, None)
    cached.assert_not_awaited()
