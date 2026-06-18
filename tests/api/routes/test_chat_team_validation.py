from __future__ import annotations

from src.api.routes.chat_validation import validate_team_agent_request
from src.kernel.schemas.agent import AgentRequest
from src.kernel.schemas.persona_preset import PersonaPresetSnapshot


def test_validate_team_agent_request_allows_missing_team_id_for_fallback() -> None:
    request = AgentRequest(message="hello")

    validate_team_agent_request("team", request)


def test_validate_team_agent_request_allows_team_id() -> None:
    request = AgentRequest(message="hello", team_id="team-1")

    validate_team_agent_request("team", request)


def test_validate_team_agent_request_strips_enabled_skills_for_explicit_team() -> None:
    request = AgentRequest(
        message="hello",
        team_id="team-1",
        enabled_skills=["solo-skill"],
    )

    validate_team_agent_request("team", request)

    assert request.enabled_skills is None


def test_validate_team_agent_request_strips_persona_for_explicit_team() -> None:
    request = AgentRequest(
        message="hello",
        team_id="team-1",
        persona_preset_id="persona-1",
        persona_snapshot=PersonaPresetSnapshot(
            preset_id="persona-1",
            name="Solo Writer",
            system_prompt="Write solo.",
            skill_names=["solo-skill"],
            missing_skill_names=[],
        ),
        persona_system_prompt="Write solo.",
        enabled_skills=["solo-skill"],
    )

    validate_team_agent_request("team", request)

    assert request.persona_preset_id is None
    assert request.persona_snapshot is None
    assert request.persona_system_prompt is None
    assert request.enabled_skills is None


def test_validate_team_agent_request_keeps_persona_for_team_fallback() -> None:
    request = AgentRequest(
        message="hello",
        persona_preset_id="persona-1",
        persona_system_prompt="Write solo.",
        enabled_skills=["solo-skill"],
    )

    validate_team_agent_request("team", request)

    assert request.persona_preset_id == "persona-1"
    assert request.persona_system_prompt == "Write solo."
    assert request.enabled_skills == ["solo-skill"]


def test_validate_team_agent_request_ignores_other_agents() -> None:
    request = AgentRequest(message="hello")

    validate_team_agent_request("search", request)


def test_conversation_metadata_scopes_team_id_to_team_agent() -> None:
    from pathlib import Path

    source = Path("src/api/routes/chat.py").read_text(encoding="utf-8")

    assert 'if agent_id == "team" and request.team_id:' in source
