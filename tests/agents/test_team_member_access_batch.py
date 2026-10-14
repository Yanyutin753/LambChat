from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.agents.team_agent.member_config import resolve_team_member_agent_id


@pytest.mark.parametrize("allowed", [True, False])
async def test_member_agent_permission_reads_are_batched_and_fail_closed(monkeypatch, allowed):
    roles = AsyncMock(return_value=[SimpleNamespace(id="r1"), SimpleNamespace(id="r2")])
    access = AsyncMock(return_value={"r1": ["fast"], "r2": None})
    monkeypatch.setattr("src.agents.core.base.AgentFactory.list_agents", lambda: [{"id": "fast"}])
    monkeypatch.setattr(
        "src.agents.core.base.AgentFactory.get_filtered_agents",
        AsyncMock(return_value=[{"id": "fast"}] if allowed else []),
    )
    monkeypatch.setattr(
        "src.infra.user.storage.UserStorage",
        lambda: SimpleNamespace(
            get_by_id=AsyncMock(return_value=SimpleNamespace(roles=["one", "two"]))
        ),
    )
    monkeypatch.setattr(
        "src.infra.role.manager.get_role_manager", lambda: SimpleNamespace(get_roles_by_names=roles)
    )
    monkeypatch.setattr(
        "src.infra.agent.config_storage.get_agent_config_storage",
        lambda: SimpleNamespace(get_role_agents_by_ids=access),
    )
    if allowed:
        assert await resolve_team_member_agent_id("fast", user_id="u") == "fast"
    else:
        with pytest.raises(ValueError, match="team_member_agent_not_allowed"):
            await resolve_team_member_agent_id("fast", user_id="u")
    roles.assert_awaited_once_with(["one", "two"])
    access.assert_awaited_once_with(["r1", "r2"])
