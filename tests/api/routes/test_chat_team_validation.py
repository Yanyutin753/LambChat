from __future__ import annotations

from types import SimpleNamespace

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


def test_validate_team_agent_request_uses_runtime_agent_declaration() -> None:
    request = AgentRequest(
        message="hello",
        team_id="team-1",
        persona_preset_id="persona-1",
        persona_system_prompt="Write solo.",
        enabled_skills=["solo-skill"],
    )
    runtime = SimpleNamespace(
        plugin_for_agent=lambda agent_id: "agent_team" if agent_id == "team_plus" else None
    )

    validate_team_agent_request("team_plus", request, plugin_runtime=runtime)

    assert request.persona_preset_id is None
    assert request.persona_system_prompt is None
    assert request.enabled_skills is None


def test_conversation_metadata_writes_agent_team_selection_as_plugin_option() -> None:
    from src.api.routes.chat import build_conversation_config

    request = AgentRequest(message="hello", team_id="team-1")
    metadata = build_conversation_config("run-1", "team", request, "en")

    assert "team_id" not in metadata
    assert metadata["plugin_options"] == {
        "agent_team": {"SELECTED_TEAM_ID": "team-1"}
    }


def test_conversation_metadata_uses_runtime_agent_declaration() -> None:
    from src.api.routes.chat import build_conversation_config

    request = AgentRequest(message="hello", team_id="team-1")
    runtime = SimpleNamespace(
        plugin_for_agent=lambda agent_id: "agent_team" if agent_id == "team_plus" else None
    )

    metadata = build_conversation_config(
        "run-1",
        "team_plus",
        request,
        "en",
        plugin_runtime=runtime,
    )

    assert metadata["plugin_options"] == {
        "agent_team": {"SELECTED_TEAM_ID": "team-1"}
    }
