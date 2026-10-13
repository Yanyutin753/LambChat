"""Team resolver extraction preserves fresh authorization and custom child scopes."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from src.agents.team_agent.prompt import build_team_member_subagent_type
from src.agents.team_agent.subagent_scope import create_team_subagent_resolver
from src.kernel.schemas.model import ModelConfig, ModelProfile


def _options():
    context = SimpleNamespace(user_id="owner")
    current_tools = [SimpleNamespace(name="currently_allowed")]
    fresh = SimpleNamespace(
        filter_tools=lambda: current_tools,
        deferred_manager=None,
        skills=[{"name": "allowed-skill"}, {"name": "revoked-skill"}],
    )
    return {
        "context": context,
        "runtime_subagent_specs": {
            "context-worker": {
                "name": "context-worker",
                "mode": "fork",
                "system_prompt": "CUSTOM_FORK",
                "tools": ["stale"],
            }
        },
        "model_id": "main-model",
        "llm": object(),
        "thinking_config": {"enabled": False},
        "team": None,
        "team_id": "selected-team",
        "user_input": "Review",
        "session_id": "session-1",
        "agent_options": {"response_language": "en"},
        "persona_sections": ["PERSONA_SECTION"],
        "memory_guide": "MEMORY_GUIDE",
        "sandbox_active": False,
        "image_url_mode": "url",
        "supports_vision": False,
        "subagent_display_names": {},
        "subagent_avatars": {},
        "build_subagent_middleware": Mock(return_value=["fresh middleware"]),
        "refresh_context": AsyncMock(return_value=fresh),
        "resolve_team": AsyncMock(return_value=None),
        "resolve_member_model": AsyncMock(return_value=None),
        "resolve_member_agent": AsyncMock(return_value="fast"),
        "get_model": AsyncMock(return_value="fresh model"),
    }


async def test_fallback_keeps_fork_prompt_and_reloads_tools_each_execution():
    options = _options()
    resolver = create_team_subagent_resolver(**options)
    first = await resolver("context-worker")
    second = await resolver("context-worker")
    assert first["mode"] == second["mode"] == "fork"
    assert first["system_prompt"] == "CUSTOM_FORK"
    assert first["tools"] == options["refresh_context"].return_value.filter_tools()
    assert options["runtime_subagent_specs"]["context-worker"]["tools"] == ["stale"]
    assert options["refresh_context"].await_count == 2
    options["resolve_member_model"].assert_awaited_with("main-model", user_id="owner")
    assert (
        options["build_subagent_middleware"].call_args.kwargs["tool_context"]
        is options["refresh_context"].return_value
    )
    assert options["build_subagent_middleware"].call_args.kwargs["prompt_sections"] == [
        "PERSONA_SECTION",
        "MEMORY_GUIDE",
    ]


async def test_resumed_cloud_child_drops_desktop_tool_from_fresh_context():
    options = _options()
    options["agent_options"] = {"sandbox": "cloud"}
    options["refresh_context"].return_value.filter_tools = lambda: [
        SimpleNamespace(name="computer_use"),
        SimpleNamespace(name="web_search"),
    ]
    spec = await create_team_subagent_resolver(**options)("context-worker")
    assert [tool.name for tool in spec["tools"]] == ["web_search"]


async def test_persona_rechecks_access_and_updates_display_metadata(monkeypatch):
    options = _options()
    monkeypatch.setattr("src.agents.team_agent.subagent_scope.settings.ENABLE_SKILLS", True)
    snapshot = SimpleNamespace(
        name="Reviewer",
        system_prompt="CURRENT_TRUSTED_ROLE",
        skill_names=["allowed-skill"],
        missing_skill_names=[],
        mcp_server_names=[],
        avatar="/avatar.png",
    )
    load_role = AsyncMock(return_value=snapshot)
    monkeypatch.setattr("src.infra.tool.team_tool.resolve_persona_for_subagent", load_role)
    resolver = create_team_subagent_resolver(**options)
    spec = await resolver("persona:p1")
    load_role.assert_awaited_once_with("p1", user_id="owner")
    assert spec["model"] is options["llm"]
    assert options["subagent_display_names"]["persona:p1"] == "Reviewer"
    assert options["subagent_avatars"]["persona:p1"] == "/avatar.png"
    skill_search = next(tool for tool in spec["tools"] if tool.name == "search_skills")
    assert "Name: allowed-skill" in skill_search._run("select:allowed-skill")
    assert "No Skills matched" in skill_search._run("select:revoked-skill")
    assert (
        "CURRENT_TRUSTED_ROLE"
        in options["build_subagent_middleware"].call_args.kwargs["prompt_sections"][0]
    )


async def test_selected_team_rebuilds_member_model_and_role_from_current_snapshot(monkeypatch):
    options = _options()
    member = SimpleNamespace(
        member_id="m1",
        role_name="Reviewer",
        persona_preset_id="p1",
        agent_id="fast",
        model_id="member-model",
        role_instructions="CURRENT_INSTRUCTIONS",
    )
    role = build_team_member_subagent_type(member)
    team = SimpleNamespace(
        active_members=[member], name="Current team", team_instructions="CURRENT_TEAM_RULES"
    )
    options.update(
        team=object(), runtime_subagent_specs={role: {"name": role, "model": "stale model"}}
    )
    options["resolve_team"].return_value = team
    current_model = ModelConfig(
        id="member-model",
        label="Current member model",
        value="current-model",
        api_key="private-test-key",
        profile=ModelProfile(supports_vision=True, image_url_mode="base64"),
    )
    options["resolve_member_model"].side_effect = [None, current_model]
    current_preset = SimpleNamespace(
        system_prompt="CURRENT_ROLE",
        mcp_server_names=[],
        skill_names=["allowed-skill"],
        missing_skill_names=[],
    )
    preset_manager = SimpleNamespace(use_preset=AsyncMock(return_value=current_preset))
    monkeypatch.setattr(
        "src.infra.persona_preset.manager.get_persona_preset_manager", lambda: preset_manager
    )
    spec = await create_team_subagent_resolver(**options)(role)
    options["resolve_team"].assert_awaited_once_with(
        team_id="selected-team", context=options["context"], user_input="Review"
    )
    preset_manager.use_preset.assert_awaited_once_with("p1", user_id="owner", is_admin=False)
    options["resolve_member_agent"].assert_awaited_once_with("fast", user_id="owner")
    assert spec["model"] == "fresh model"
    assert options["get_model"].call_args.kwargs["model_config"]["api_key"] is None
    kwargs = options["build_subagent_middleware"].call_args.kwargs
    assert kwargs["member_image_url_mode"] == "base64"
    assert kwargs["member_supports_vision"] is True
    assert any("CURRENT_ROLE" in text for text in kwargs["prompt_sections"])
    assert any("CURRENT_TEAM_RULES" in text for text in kwargs["prompt_sections"])
    assert kwargs["tool_context"] is options["refresh_context"].return_value


async def test_revoked_team_member_and_main_model_fail_before_building_child():
    options = _options()
    options.update(team=object())
    options["resolve_team"].return_value = SimpleNamespace(active_members=[])
    with pytest.raises(ValueError, match="no longer available"):
        await create_team_subagent_resolver(**options)("context-worker")
    options["build_subagent_middleware"].assert_not_called()
    options["resolve_member_model"].side_effect = PermissionError("revoked model")
    with pytest.raises(PermissionError, match="revoked model"):
        await create_team_subagent_resolver(**options)("context-worker")
    assert options["refresh_context"].await_count == 1
