from pathlib import Path
from types import SimpleNamespace

import pytest

from src.kernel.schemas.team import TeamMemberResponse, TeamResponse


def test_shared_content_response_includes_team_display_metadata() -> None:
    source = Path("src/api/routes/share.py").read_text(encoding="utf-8")

    assert "from src.infra.team.storage import TeamStorage" in source
    assert "agent_uses_agent_team_options" in source
    assert "selected_agent_team_id_from_metadata" in source
    assert "agent_uses_agent_team_options(session.agent_id)" in source
    assert "async def _attach_shared_team_metadata" in source
    assert "session.agent_id == \"team\"" not in source
    assert 'session_info["team_id"] = team_id' in source
    assert "await TeamStorage().get_team" in source
    assert 'session_info["team_name"] = team.name' in source
    assert "_resolve_shared_team_avatar" in source
    assert "await _attach_shared_team_metadata(session_info, session, share)" in source


@pytest.mark.asyncio
async def test_shared_team_metadata_uses_default_member_avatar_when_team_avatar_is_empty(
    monkeypatch,
) -> None:
    from src.api.routes import share as share_route

    team = TeamResponse(
        id="team-1",
        owner_user_id="user-1",
        name="素材创作团队",
        avatar=None,
        members=[
            TeamMemberResponse(
                member_id="member-1",
                persona_preset_id="preset-1",
                role_name="写手",
                role_avatar="https://example.com/writer.webp",
                role_tags=[],
                role_instructions="",
                position=0,
                enabled=True,
            )
        ],
        default_member_id="member-1",
    )

    class FakeTeamStorage:
        async def get_team(self, team_id: str, *, owner_user_id: str):
            assert team_id == "team-1"
            assert owner_user_id == "user-1"
            return team

    monkeypatch.setattr(share_route, "TeamStorage", FakeTeamStorage)

    session_info = {}
    session = SimpleNamespace(
        agent_id="team",
        metadata={"plugin_options": {"agent_team": {"SELECTED_TEAM_ID": "team-1"}}},
        user_id="user-1",
    )
    share = SimpleNamespace(owner_id="owner-1")

    await share_route._attach_shared_team_metadata(session_info, session, share)

    assert session_info["team_id"] == "team-1"
    assert session_info["team_name"] == "素材创作团队"
    assert session_info["team_avatar"] == "https://example.com/writer.webp"


@pytest.mark.asyncio
async def test_shared_team_metadata_keeps_legacy_team_id_fallback(monkeypatch) -> None:
    from src.api.routes import share as share_route

    team = TeamResponse(
        id="legacy-team",
        owner_user_id="user-1",
        name="Legacy Team",
        avatar="https://example.com/team.webp",
        members=[],
        default_member_id=None,
    )

    class FakeTeamStorage:
        async def get_team(self, team_id: str, *, owner_user_id: str):
            assert team_id == "legacy-team"
            assert owner_user_id == "user-1"
            return team

    monkeypatch.setattr(share_route, "TeamStorage", FakeTeamStorage)

    session_info = {}
    session = SimpleNamespace(
        agent_id="team",
        metadata={"team_id": "legacy-team"},
        user_id="user-1",
    )
    share = SimpleNamespace(owner_id="owner-1")

    await share_route._attach_shared_team_metadata(session_info, session, share)

    assert session_info["team_id"] == "legacy-team"
    assert session_info["team_name"] == "Legacy Team"
    assert session_info["team_avatar"] == "https://example.com/team.webp"
