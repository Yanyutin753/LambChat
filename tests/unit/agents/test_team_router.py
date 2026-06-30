import pytest

from src.agents.team_agent.prompt import (
    build_team_member_subagent_type,
    build_team_members_description,
    build_team_router_system_prompt,
    build_team_subagent_display_names,
)
from src.kernel.schemas.team import TeamMemberResponse, TeamResponse


def test_build_team_members_description():
    team = TeamResponse(
        id="t1",
        owner_user_id="u1",
        name="Dev Team",
        members=[
            TeamMemberResponse(
                member_id="m1",
                persona_preset_id="p1",
                role_name="Researcher",
                role_instructions="Focus on facts.",
                position=0,
                enabled=True,
            ),
            TeamMemberResponse(
                member_id="m2", persona_preset_id="p2", role_name="Writer", position=1, enabled=True
            ),
        ],
    )
    desc = build_team_members_description(team)
    assert "`team-m1-researcher`" in desc
    assert "Researcher" in desc
    assert "`team-m2-writer`" in desc
    assert "Writer" in desc
    assert "Focus on facts." in desc


def test_build_team_members_description_includes_runtime_role_summaries():
    team = TeamResponse(
        id="t1",
        owner_user_id="u1",
        name="Dev Team",
        members=[
            TeamMemberResponse(
                member_id="m1",
                persona_preset_id="p1",
                role_name="Researcher",
                role_instructions="Focus on facts.",
                enabled=True,
            ),
        ],
    )

    desc = build_team_members_description(
        team,
        role_summaries={"m1": "Investigates sources and verifies claims."},
    )

    assert "Capability summary: Investigates sources and verifies claims." in desc


def test_team_router_prompt_includes_team_instructions():
    team = TeamResponse(
        id="t1",
        owner_user_id="u1",
        name="Dev Team",
        team_instructions="Research before writing; reviewer checks code changes.",
        members=[
            TeamMemberResponse(
                member_id="m1",
                persona_preset_id="p1",
                role_name="Researcher",
                enabled=True,
            ),
        ],
    )

    prompt = build_team_router_system_prompt(
        team,
        default_role="team-m1-researcher",
        role_summaries={"m1": "Finds evidence."},
    )

    assert "## Team Instructions" in prompt
    assert "Research before writing" in prompt
    assert "Finds evidence." in prompt


def test_team_router_prompt_forbids_coordination_notification_tasks():
    team = TeamResponse(
        id="t1",
        owner_user_id="u1",
        name="Dev Team",
        members=[
            TeamMemberResponse(
                member_id="m1",
                persona_preset_id="p1",
                role_name="Writer",
                enabled=True,
            ),
        ],
    )

    prompt = build_team_router_system_prompt(
        team,
        default_role="team-m1-writer",
    )

    assert "Do not dispatch onboarding, coordination, reminder, or notification messages" in prompt
    assert "The `task` tool is for work assignments only" in prompt


def test_team_router_prompt_includes_tool_progress_guidance():
    team = TeamResponse(
        id="t1",
        owner_user_id="u1",
        name="Dev Team",
        members=[
            TeamMemberResponse(
                member_id="m1",
                persona_preset_id="p1",
                role_name="Writer",
                enabled=True,
            ),
        ],
    )

    prompt = build_team_router_system_prompt(
        team,
        default_role="team-m1-writer",
    )
    lower_prompt = prompt.lower()

    assert "tool progress" in lower_prompt
    assert "before the first tool call" in lower_prompt
    assert "content may interleave text and tool calls" in lower_prompt
    assert "do not invent tool results" in lower_prompt


def test_build_team_members_description_skips_disabled():
    team = TeamResponse(
        id="t1",
        owner_user_id="u1",
        name="Team",
        members=[
            TeamMemberResponse(
                member_id="m1", persona_preset_id="p1", role_name="Active", enabled=True
            ),
            TeamMemberResponse(
                member_id="m2", persona_preset_id="p2", role_name="Disabled", enabled=False
            ),
        ],
    )
    desc = build_team_members_description(team)
    assert "Active" in desc
    assert "Disabled" not in desc


def test_build_team_member_subagent_type_slugifies_display_name():
    member = TeamMemberResponse(
        member_id="m-123456789abc",
        persona_preset_id="p1",
        role_name="Research Analyst",
    )

    assert build_team_member_subagent_type(member) == "team-m-123456789abc-research-analyst"


def test_build_team_member_subagent_type_handles_non_ascii_names():
    member = TeamMemberResponse(
        member_id="m-zh",
        persona_preset_id="p1",
        role_name="研究员",
    )

    assert build_team_member_subagent_type(member) == "team-m-zh-role"


def test_build_team_subagent_display_names_maps_internal_types_to_roles():
    team = TeamResponse(
        id="t1",
        owner_user_id="u1",
        name="Dev Team",
        members=[
            TeamMemberResponse(
                member_id="m1",
                persona_preset_id="p1",
                role_name="Researcher",
                enabled=True,
            ),
            TeamMemberResponse(
                member_id="m2",
                persona_preset_id="p2",
                role_name="Disabled Role",
                enabled=False,
            ),
        ],
    )

    assert build_team_subagent_display_names(team) == {
        "team-m1-researcher": "Researcher",
    }


def test_team_agent_does_not_silently_fallback_when_role_subagents_fail():
    from pathlib import Path

    source = Path("src/agents/team_agent/nodes.py").read_text(encoding="utf-8")

    assert "team_subagents_unavailable" in source
    assert "falling back to single" not in source


@pytest.mark.asyncio
async def test_resolve_runtime_team_returns_none_when_team_id_is_missing():
    from types import SimpleNamespace

    from src.agents.team_agent import nodes

    resolved = await nodes.resolve_runtime_team(
        team_id=None,
        context=SimpleNamespace(user_id="user-1"),
        user_input="帮我做竞品分析",
    )

    assert resolved is None


def test_no_team_fallback_uses_search_prompt_when_sandbox_is_active():
    from src.agents.search_agent.prompt import SANDBOX_SYSTEM_PROMPT
    from src.agents.team_agent import nodes

    prompt = nodes.build_no_team_fallback_system_prompt(sandbox_active=True)

    assert prompt == SANDBOX_SYSTEM_PROMPT


def test_no_team_fallback_uses_fast_prompt_without_sandbox():
    from src.agents.fast_agent.prompt import FAST_SYSTEM_PROMPT
    from src.agents.team_agent import nodes

    prompt = nodes.build_no_team_fallback_system_prompt(sandbox_active=False)

    assert prompt == FAST_SYSTEM_PROMPT
