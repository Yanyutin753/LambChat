from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.kernel.schemas.persona_preset import (
    PersonaPreset,
    PersonaPresetScope,
    PersonaPresetStatus,
    PersonaPresetVisibility,
)
from src.kernel.schemas.team import TeamMemberResponse, TeamResponse, TeamVisibility


class _Runtime:
    def __init__(self, user_id: str | None) -> None:
        context = SimpleNamespace(user_id=user_id) if user_id is not None else None
        self.config = {"configurable": {"context": context}}


def _preset(preset_id: str, name: str) -> PersonaPreset:
    return PersonaPreset(
        id=preset_id,
        scope=PersonaPresetScope.USER,
        owner_user_id="user-1",
        name=name,
        description=f"{name} description",
        avatar=None,
        tags=[name.lower()],
        system_prompt=f"You are {name}.",
        starter_prompts=[],
        skill_names=[],
        visibility=PersonaPresetVisibility.PRIVATE,
        status=PersonaPresetStatus.DRAFT,
        version=1,
        usage_count=0,
        created_by="user-1",
        updated_by="user-1",
    )


def test_team_tool_descriptions_guide_llm_team_creation() -> None:
    from src.infra.tool import team_tool

    search_description = team_tool.search_persona_presets.description
    create_description = team_tool.create_agent_team.description
    create_fields = team_tool.create_agent_team.args_schema.model_fields

    assert "Use this tool first" in search_description
    assert "create_agent_team" in search_description
    assert "search_persona_presets" in create_description
    assert "save_persona_preset" in create_description
    normalized_create_description = " ".join(create_description.split())
    assert "creating or editing a Team in the UI" in normalized_create_description
    assert "Leave `team_id` empty to create a new team" in normalized_create_description
    assert "Pass `team_id` to update an existing team" in normalized_create_description
    assert "Optional existing Team id to update" in create_fields["team_id"].description
    assert "Always provide an emoji or avatar image URL" in create_fields["avatar"].description
    assert "Do not invent persona_preset_id values" in create_fields["members"].description
    assert "agent_id" not in create_fields["members"].description
    assert "sandbox backend" in create_fields["run_in_sandbox"].description
    assert "role_avatar" in create_fields["members"].description
    assert "emoji or avatar image URL" in create_fields["members"].description
    assert "Never use placeholder ids such as 'general-purpose'" in (
        create_fields["members"].description
    )
    assert "Researcher gathers evidence first" in create_fields["team_instructions"].description
    starter_description = create_fields["starter_prompts"].description
    assert (
        "{'zh': '帮我分析这三个竞品', 'en': 'Analyze these three competitors'}"
        in starter_description
    )
    assert "single emoji" in starter_description


@pytest.mark.asyncio
async def test_search_persona_presets_returns_visible_personas(
    monkeypatch: pytest.MonkeyPatch,
):
    from src.infra.tool import team_tool

    manager = MagicMock()
    manager.list_presets = AsyncMock(return_value=[_preset("preset-research", "Researcher")])
    monkeypatch.setattr(team_tool, "PersonaPresetManager", lambda: manager)
    monkeypatch.setattr(
        team_tool,
        "_resolve_user",
        AsyncMock(return_value=SimpleNamespace(permissions=["team:read"])),
    )

    result = json.loads(
        await team_tool.search_persona_presets.coroutine(
            query="research",
            runtime=_Runtime("user-1"),
        )
    )

    assert result["success"] is True
    assert result["presets"][0]["id"] == "preset-research"
    assert result["presets"][0]["name"] == "Researcher"
    manager.list_presets.assert_awaited_once()
    assert manager.list_presets.await_args.kwargs["q"] == "research"


@pytest.mark.asyncio
async def test_search_persona_presets_offloads_result_json(
    monkeypatch: pytest.MonkeyPatch,
):
    from src.infra.tool import team_tool

    calls: list[object] = []
    manager = MagicMock()
    manager.list_presets = AsyncMock(
        return_value=[_preset(f"preset-{index}", f"Persona {index}") for index in range(5)]
    )

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(team_tool, "PersonaPresetManager", lambda: manager)
    monkeypatch.setattr(
        team_tool,
        "_resolve_user",
        AsyncMock(return_value=SimpleNamespace(permissions=["team:read"])),
    )
    monkeypatch.setattr(team_tool, "run_blocking_io", fake_run_blocking_io, raising=False)

    result = json.loads(
        await team_tool.search_persona_presets.coroutine(
            query="persona",
            runtime=_Runtime("user-1"),
        )
    )

    assert result["success"] is True
    assert len(result["presets"]) == 5
    assert json.dumps in calls


@pytest.mark.asyncio
async def test_search_persona_presets_offloads_error_result_json(
    monkeypatch: pytest.MonkeyPatch,
):
    from src.infra.tool import team_tool

    calls: list[object] = []

    async def fake_run_blocking_io(func, *args, **kwargs):
        calls.append(func)
        return func(*args, **kwargs)

    monkeypatch.setattr(team_tool, "run_blocking_io", fake_run_blocking_io, raising=False)

    result = json.loads(
        await team_tool.search_persona_presets.coroutine(
            query="persona",
            runtime=_Runtime(None),
        )
    )

    assert result == {"error": "No user context available"}
    assert json.dumps in calls


@pytest.mark.asyncio
async def test_create_agent_team_saves_llm_supplied_team(monkeypatch: pytest.MonkeyPatch):
    from src.infra.tool import team_tool

    created = TeamResponse(
        id="team-1",
        owner_user_id="user-1",
        name="竞品分析团队",
        members=[
            TeamMemberResponse(
                member_id="m-research",
                persona_preset_id="preset-research",
                role_name="Market Research Lead",
                enabled=True,
            )
        ],
        visibility=TeamVisibility.PRIVATE,
    )
    manager = MagicMock()
    manager.create_team = AsyncMock(return_value=created)
    monkeypatch.setattr(team_tool, "TeamManager", lambda: manager)
    monkeypatch.setattr(
        team_tool,
        "_resolve_user",
        AsyncMock(return_value=SimpleNamespace(permissions=["chat:write"])),
    )

    result = json.loads(
        await team_tool.create_agent_team.coroutine(
            name="竞品分析团队",
            description="Analyze competitors and write a report.",
            avatar="🧭",
            members=[
                {
                    "member_id": "m-research",
                    "persona_preset_id": "preset-research",
                    "role_name": "Market Research Lead",
                    "role_avatar": "🔎",
                    "role_instructions": "Find competitors and evidence.",
                }
            ],
            default_member_id="m-research",
            team_instructions="Research first, then synthesize.",
            tags=["analysis"],
            runtime=_Runtime("user-1"),
        )
    )

    assert result["success"] is True
    assert result["entity_type"] == "team"
    assert result["action"] == "created"
    assert result["team_id"] == "team-1"
    body = manager.create_team.await_args.args[0]
    assert body.name == "竞品分析团队"
    assert body.avatar == "🧭"
    assert body.members[0].role_name == "Market Research Lead"
    assert body.members[0].role_avatar == "🔎"
    assert body.default_member_id == "m-research"
    assert body.team_instructions == "Research first, then synthesize."
    assert body.run_in_sandbox is False
    assert body.tags == ["analysis"]
    assert manager.create_team.await_args.kwargs["user"].permissions == ["chat:write"]


@pytest.mark.asyncio
async def test_create_agent_team_updates_existing_team_when_team_id_is_supplied(
    monkeypatch: pytest.MonkeyPatch,
):
    from src.infra.tool import team_tool

    updated = TeamResponse(
        id="team-1",
        owner_user_id="user-1",
        name="Updated Team",
        members=[],
        visibility=TeamVisibility.PRIVATE,
    )
    manager = MagicMock()
    manager.update_team = AsyncMock(return_value=updated)
    monkeypatch.setattr(team_tool, "TeamManager", lambda: manager)
    monkeypatch.setattr(
        team_tool,
        "_resolve_user",
        AsyncMock(return_value=SimpleNamespace(permissions=["team:write"])),
    )

    result = json.loads(
        await team_tool.create_agent_team.coroutine(
            team_id="team-1",
            name="Updated Team",
            description="Updated description.",
            members=[
                {
                    "member_id": "m-review",
                    "persona_preset_id": "preset-review",
                    "role_name": "Reviewer",
                }
            ],
            runtime=_Runtime("user-1"),
        )
    )

    assert result["success"] is True
    assert result["entity_type"] == "team"
    assert result["action"] == "updated"
    assert result["updated"] is True
    assert result["team_id"] == "team-1"
    manager.update_team.assert_awaited_once()
    assert manager.update_team.await_args.args[0] == "team-1"
    body = manager.update_team.await_args.args[1]
    assert body.name == "Updated Team"
    assert body.members[0].role_name == "Reviewer"
    assert manager.update_team.await_args.kwargs["user"].permissions == ["team:write"]


@pytest.mark.asyncio
async def test_create_agent_team_passes_member_model_id_to_manager(
    monkeypatch: pytest.MonkeyPatch,
):
    from src.infra.tool import team_tool

    created = TeamResponse(
        id="team-1",
        owner_user_id="user-1",
        name="Model Team",
        members=[
            TeamMemberResponse(
                member_id="m-research",
                persona_preset_id="preset-research",
                model_id="model-member",
                role_name="Market Research Lead",
                enabled=True,
            )
        ],
        visibility=TeamVisibility.PRIVATE,
    )
    manager = MagicMock()
    manager.create_team = AsyncMock(return_value=created)
    user = SimpleNamespace(
        sub="user-1",
        username="tester",
        roles=["user"],
        permissions=["chat:write"],
    )
    monkeypatch.setattr(team_tool, "TeamManager", lambda: manager)
    monkeypatch.setattr(team_tool, "_resolve_user", AsyncMock(return_value=user))

    result = json.loads(
        await team_tool.create_agent_team.coroutine(
            name="Model Team",
            avatar="model",
            members=[
                {
                    "member_id": "m-research",
                    "persona_preset_id": "preset-research",
                    "model_id": "model-member",
                    "role_name": "Market Research Lead",
                }
            ],
            runtime=_Runtime("user-1"),
        )
    )

    assert result["success"] is True
    body = manager.create_team.await_args.args[0]
    assert body.members[0].model_id == "model-member"
    assert manager.create_team.await_args.kwargs["user"] is user


@pytest.mark.asyncio
async def test_create_agent_team_ignores_member_agent_id_and_sets_team_sandbox(
    monkeypatch: pytest.MonkeyPatch,
):
    from src.infra.tool import team_tool

    created = TeamResponse(
        id="team-1",
        owner_user_id="user-1",
        name="Sandbox Team",
        members=[
            TeamMemberResponse(
                member_id="m-research",
                persona_preset_id="preset-research",
                role_name="Market Research Lead",
                enabled=True,
            )
        ],
        visibility=TeamVisibility.PRIVATE,
    )
    manager = MagicMock()
    manager.create_team = AsyncMock(return_value=created)
    user = SimpleNamespace(
        sub="user-1",
        username="tester",
        roles=["user"],
        permissions=["chat:write"],
    )
    monkeypatch.setattr(team_tool, "TeamManager", lambda: manager)
    monkeypatch.setattr(team_tool, "_resolve_user", AsyncMock(return_value=user))

    result = json.loads(
        await team_tool.create_agent_team.coroutine(
            name="Mode Team",
            avatar="mode",
            run_in_sandbox=True,
            members=[
                {
                    "member_id": "m-research",
                    "persona_preset_id": "preset-research",
                    "agent_id": "search",
                    "role_name": "Market Research Lead",
                }
            ],
            runtime=_Runtime("user-1"),
        )
    )

    assert result["success"] is True
    body = manager.create_team.await_args.args[0]
    assert not hasattr(body.members[0], "agent_id")
    assert body.run_in_sandbox is True
    assert manager.create_team.await_args.kwargs["user"] is user


@pytest.mark.asyncio
async def test_create_agent_team_requires_members(monkeypatch: pytest.MonkeyPatch):
    from src.infra.tool import team_tool

    monkeypatch.setattr(
        team_tool,
        "_resolve_user",
        AsyncMock(return_value=SimpleNamespace(permissions=["chat:write"])),
    )

    result = json.loads(
        await team_tool.create_agent_team.coroutine(
            name="Empty Team",
            members=[],
            runtime=_Runtime("user-1"),
        )
    )

    assert result == {"error": "At least one team member is required"}


@pytest.mark.asyncio
async def test_create_agent_team_rejects_placeholder_persona_ids(
    monkeypatch: pytest.MonkeyPatch,
):
    from src.infra.tool import team_tool

    manager = MagicMock()
    manager.create_team = AsyncMock()
    monkeypatch.setattr(team_tool, "TeamManager", lambda: manager)
    monkeypatch.setattr(
        team_tool,
        "_resolve_user",
        AsyncMock(return_value=SimpleNamespace(permissions=["chat:write"])),
    )

    result = json.loads(
        await team_tool.create_agent_team.coroutine(
            name="素材团队",
            members=[
                {
                    "member_id": "m-planner",
                    "persona_preset_id": "general-purpose",
                    "role_name": "素材策划",
                }
            ],
            runtime=_Runtime("user-1"),
        )
    )

    assert result == {
        "error": (
            "Invalid persona_preset_id 'general-purpose'. Search for an existing persona "
            "or call save_persona_preset first, then use the returned preset.id."
        )
    }
    manager.create_team.assert_not_called()


@pytest.mark.asyncio
async def test_create_agent_team_requires_write_permission(monkeypatch: pytest.MonkeyPatch):
    from src.infra.tool import team_tool

    monkeypatch.setattr(
        team_tool,
        "_resolve_user",
        AsyncMock(return_value=SimpleNamespace(permissions=["team:read"])),
    )

    result = json.loads(
        await team_tool.create_agent_team.coroutine(
            name="竞品分析团队",
            members=[
                {
                    "member_id": "m-research",
                    "persona_preset_id": "preset-research",
                    "role_name": "Market Research Lead",
                }
            ],
            runtime=_Runtime("user-1"),
        )
    )

    assert result == {"error": "Permission denied: team:write required"}
