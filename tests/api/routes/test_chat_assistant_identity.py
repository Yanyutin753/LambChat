from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.api.routes.chat_request_config import build_assistant_identity
from src.kernel.schemas.agent import AgentRequest
from src.kernel.schemas.persona_preset import PersonaPresetSnapshot


@pytest.mark.asyncio
async def test_role_identity_uses_the_resolved_snapshot() -> None:
    request = AgentRequest(message="hello", persona_preset_id="role-1")
    request.persona_snapshot = PersonaPresetSnapshot(
        preset_id="role-1", name="Reviewer", system_prompt="Review", avatar="generated:role-1"
    )
    assert await build_assistant_identity("fast", request, "owner", "en") == {
        "seed": "role-1",
        "name": "Reviewer",
        "avatar": "generated:role-1",
    }


@pytest.mark.asyncio
async def test_agent_identity_keeps_catalog_avatar_and_localized_name(monkeypatch) -> None:
    catalog = SimpleNamespace(
        id="fast",
        name="agents.fast.name",
        icon="🤖",
        labels={"zh": SimpleNamespace(name="快速助手")},
    )
    storage = SimpleNamespace(get_catalog_config=AsyncMock(return_value=[catalog]))
    monkeypatch.setattr("src.infra.agent.config_storage.get_agent_config_storage", lambda: storage)
    monkeypatch.setattr(
        "src.agents.core.AgentFactory.list_agents",
        lambda: [{"id": "fast", "name": "agents.fast.name", "icon": "Zap"}],
    )
    assert await build_assistant_identity("fast", AgentRequest(message="hello"), "owner", "zh") == {
        "seed": "fast",
        "name": "快速助手",
        "avatar": "🤖",
    }


@pytest.mark.asyncio
async def test_team_identity_keeps_the_selected_team_and_default_member_avatar(monkeypatch) -> None:
    team = SimpleNamespace(
        name="Review team",
        avatar=None,
        default_member_id="reviewer",
        members=[SimpleNamespace(member_id="reviewer", enabled=True, role_avatar="🦉")],
    )
    manager = SimpleNamespace(get_team=AsyncMock(return_value=team))
    monkeypatch.setattr("src.infra.team.manager.get_team_manager", lambda: manager)
    assert await build_assistant_identity(
        "team", AgentRequest(message="hello", team_id="team-1"), "owner", "en"
    ) == {
        "seed": "Review team",
        "name": "Review team",
        "avatar": "🦉",
    }
    manager.get_team.assert_awaited_once_with("team-1", owner_user_id="owner")
