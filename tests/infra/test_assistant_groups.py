"""Groups reuse member identities without crossing private memory or tenant boundaries."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from src.kernel.errors import AppError
from src.kernel.schemas.assistant import AssistantCreate
from tests.infra.test_assistant_service import assistant, user


def test_chief_finishes_verified_configuration_changes_without_memory_maintenance():
    from src.infra.assistant.groups import assistant_instructions

    prompt = assistant_instructions(assistant(kind="chief", instructions="Keep my preferences"))
    assert "live assistant store" in prompt
    assert "Do not mirror volatile configuration into memory" in prompt
    assert "do not repair stale configuration memories" in prompt
    assert "without a task list" in prompt
    assert prompt.endswith("Keep my preferences")
    assert (
        assistant_instructions(assistant(instructions="Remember research")) == "Remember research"
    )


def test_group_requires_distinct_members_and_member_leader():
    for changes in (
        {"member_ids": ["a", "a"], "leader_id": "a"},
        {"member_ids": ["a", "b"], "leader_id": "outside"},
        {"member_ids": ["a"], "leader_id": "a"},
    ):
        with pytest.raises(ValidationError):
            AssistantCreate(name="Room", kind="group", **changes)
    value = AssistantCreate(name="Room", kind="group", member_ids=["a", "b"], leader_id="a")
    assert value.kind == "group"


async def test_group_rechecks_member_ownership_and_active_status():
    from src.infra.assistant.groups import group_members

    group = assistant(kind="group", member_ids=["a", "b"], leader_id="a")
    store = SimpleNamespace(get=AsyncMock(side_effect=[assistant(), None]))
    with pytest.raises(AppError):
        await group_members(user(), group, store=store)
    assert store.get.await_args_list[1].args == ("owner", "b")


async def test_group_runtime_keeps_actual_member_identity_and_private_memory(monkeypatch):
    from src.infra.assistant.groups import runtime_group_team
    from src.infra.assistant.service import AssistantService

    group = assistant(kind="group", member_ids=["a", "b"], leader_id="a")
    members = [
        assistant(instructions="Research").model_copy(update={"id": "a", "name": "Researcher"}),
        assistant(model_id="review-model").model_copy(update={"id": "b", "name": "Reviewer"}),
    ]
    store = SimpleNamespace(get=AsyncMock(side_effect=members))
    monkeypatch.setattr(AssistantService, "validate_configuration", AsyncMock())
    team = await runtime_group_team(user(), group, store=store)
    assert [m.member_id for m in team.members] == ["a", "b"]
    assert team.members[1].model_id == "review-model"
    assert "private" in team.team_instructions.lower()
    assert team.default_member_id == "a"
    from src.agents.core.subagent_prompts import build_role_subagent_section
    from src.agents.team_agent.prompt import build_team_router_system_prompt

    router = build_team_router_system_prompt(team, default_role="Researcher")
    member = build_role_subagent_section(
        "Reviewer", "Check independently", team_instructions=team.team_instructions
    )
    for prompt in (router, member):
        assert "Agreement between members is not proof" in prompt
        assert "allowed changes" in prompt
        assert "final saved artifact" in prompt


async def test_coordinator_switch_replaces_live_identity_without_rewriting_history(monkeypatch):
    from src.agents.team_agent.prompt import build_team_router_system_prompt
    from src.infra.assistant.groups import runtime_group_team
    from src.infra.assistant.service import AssistantService

    group = assistant(
        kind="group",
        member_ids=["a", "b"],
        leader_id="a",
        instructions="The original plan was prepared by Researcher.",
    )
    members = {
        "a": assistant().model_copy(update={"id": "a", "name": "Researcher"}),
        "b": assistant().model_copy(update={"id": "b", "name": "Reviewer"}),
    }
    store = SimpleNamespace(get=AsyncMock(side_effect=lambda owner, identity: members[identity]))
    monkeypatch.setattr(AssistantService, "validate_configuration", AsyncMock())
    before = await runtime_group_team(user(), group, store=store)
    after = await runtime_group_team(
        user(), group.model_copy(update={"leader_id": "b"}), store=store
    )
    assert "Current coordinator: Researcher (member_id: a)." in before.team_instructions
    assert "Current coordinator: Reviewer (member_id: b)." in after.team_instructions
    assert "Current coordinator: Researcher" not in after.team_instructions
    assert "historical summaries" in after.team_instructions
    assert "prospectively" in after.team_instructions
    assert "earlier report was misattributed" in after.team_instructions
    assert group.instructions in after.team_instructions
    assert [m.member_id for m in after.members] == ["a", "b"]
    assert build_team_router_system_prompt(before, default_role="Researcher").startswith(
        "You are Researcher, the current coordinator"
    )
    assert build_team_router_system_prompt(after, default_role="Reviewer").startswith(
        "You are Reviewer, the current coordinator"
    )
    assert "You are Reviewer" not in after.team_instructions


def test_completed_work_does_not_require_acceptance():
    from src.infra.assistant.tasks import task_view
    from tests.infra.test_assistant_tasks import child, record

    assert task_view(record(), child(task_status="completed"))["state"] == "completed"


def test_group_mentions_route_only_to_real_members_and_reject_foreign_ids():
    from src.infra.assistant.groups import route_group_mentions
    from src.kernel.schemas.team import TeamMemberResponse, TeamResponse

    team = TeamResponse(
        id="group",
        owner_user_id="owner",
        name="Room",
        members=[
            TeamMemberResponse(member_id="a", persona_preset_id="", role_name="Alice"),
            TeamMemberResponse(member_id="b", persona_preset_id="", role_name="Bob"),
        ],
    )
    routed = route_group_mentions(team, "@[Bob](assistant:b) please review")
    assert [member.member_id for member in routed.members] == ["b"]
    assert route_group_mentions(team, "@Alice hello").default_member_id == "a"
    with pytest.raises(AppError):
        route_group_mentions(team, "@[Eve](assistant:foreign) leak")


async def test_group_snapshot_uses_member_duties_and_persona_without_private_history(monkeypatch):
    from src.infra.assistant.groups import group_member_snapshot
    from src.infra.assistant.store import AssistantStore

    bot = assistant(instructions="BOT_DUTIES", persona_preset_id="p")
    monkeypatch.setattr(AssistantStore, "get", AsyncMock(return_value=bot))
    from src.kernel.schemas.persona_preset import PersonaPresetSnapshot

    manager = SimpleNamespace(
        use_preset=AsyncMock(
            return_value=PersonaPresetSnapshot(
                preset_id="p",
                name="Role",
                system_prompt="ROLE_POLICY",
                mcp_server_names=["allowed"],
            )
        )
    )
    monkeypatch.setattr(
        "src.infra.persona_preset.manager.get_persona_preset_manager", lambda: manager
    )
    result = await group_member_snapshot(
        SimpleNamespace(id="assistant-group:g"), SimpleNamespace(member_id="a"), "owner"
    )
    assert result.system_prompt == "ROLE_POLICY\n\nBOT_DUTIES"
    assert result.mcp_server_names == ["allowed"]


@pytest.mark.parametrize(
    "changes", [{"status": "paused"}, {"status": "archived"}, {"team_id": "nested-team"}]
)
async def test_group_rechecks_unavailable_members(changes):
    from src.infra.assistant.groups import group_members

    group = assistant(kind="group", member_ids=["a", "b"], leader_id="a")
    store = SimpleNamespace(get=AsyncMock(return_value=assistant().model_copy(update=changes)))
    with pytest.raises(AppError):
        await group_members(user(), group, store=store)


async def test_team_runtime_resolves_the_session_group_before_single_agent_fallback(monkeypatch):
    from src.agents.team_agent import nodes

    group = SimpleNamespace(id="assistant-group:g")
    lookup = AsyncMock(return_value=group)
    monkeypatch.setattr(nodes, "resolve_group_for_session", lookup)
    context = SimpleNamespace(user_id="owner", session_id="session")
    assert (
        await nodes.resolve_runtime_team(team_id=None, context=context, user_input="@Bob hello")
        is group
    )
    lookup.assert_awaited_once_with("owner", "session", user_input="@Bob hello")


@pytest.mark.parametrize("kind", ["assistant", "chief", "group"])
def test_assistant_without_environment_explicitly_disables_sandbox(kind):
    from src.infra.assistant.service import assistant_options

    value = assistant(
        kind=kind, **({"member_ids": ["a", "b"], "leader_id": "a"} if kind == "group" else {})
    )
    assert assistant_options(value)["sandbox"] is None


async def test_team_respects_explicit_no_sandbox_without_initializing_cloud(monkeypatch):
    from src.agents.team_agent import backend_setup as module

    monkeypatch.setattr(module.settings, "ENABLE_SANDBOX", True)
    backend = object()
    monkeypatch.setattr(module, "create_persistent_backend", lambda **kwargs: backend)
    monkeypatch.setattr(module, "acreate_store", AsyncMock(return_value=None))
    monkeypatch.setattr(
        module,
        "resolve_channel_env_vars",
        AsyncMock(side_effect=AssertionError("no sandbox env needed")),
    )
    result = await module.load_backend_bundle(
        state={"session_id": "s"},
        context=SimpleNamespace(user_id="owner"),
        presenter=None,
        assistant_id="assistant",
        agent_options={"sandbox": None},
    )
    assert result == (backend, None, None, None)


async def test_group_without_environment_passes_normal_workspace_validation():
    from src.infra.assistant.service import assistant_options
    from src.infra.backend.workspace_selection import resolve_workspace_options

    group = assistant(kind="group", member_ids=["a", "b"], leader_id="a")
    options = await resolve_workspace_options(assistant_options(group), "owner")
    assert options["sandbox"] is None


async def test_chief_no_environment_uses_persistent_history_backend(monkeypatch):
    from src.agents.search_agent import nodes as module

    monkeypatch.setattr(module.settings, "ENABLE_SANDBOX", True)
    backend = object()
    monkeypatch.setattr(module, "create_persistent_backend", lambda **kwargs: backend)
    monkeypatch.setattr(module, "acreate_store", AsyncMock(return_value=None))
    monkeypatch.setattr(
        module,
        "resolve_channel_env_vars",
        AsyncMock(side_effect=AssertionError("Chief must not initialize cloud")),
    )
    result = await module._create_backend_and_prompt(
        state={"session_id": "chief"},
        context=SimpleNamespace(user_id="owner", session_id="chief"),
        presenter=None,
        assistant_id="chief",
        agent_options={"sandbox": None},
    )
    assert result[0] is backend
    assert result[3:] == (None, None)


async def test_group_projection_uses_saved_group_and_member_avatars(monkeypatch):
    from src.infra.assistant.groups import runtime_group_team
    from src.infra.assistant.service import AssistantService

    group = assistant(kind="group", member_ids=["a", "b"], leader_id="a", avatar="🧭")
    members = [
        assistant(avatar="🔎").model_copy(update={"id": "a"}),
        assistant(avatar="📝").model_copy(update={"id": "b"}),
    ]
    monkeypatch.setattr(AssistantService, "validate_configuration", AsyncMock())
    team = await runtime_group_team(
        user(), group, store=SimpleNamespace(get=AsyncMock(side_effect=members))
    )
    assert team.avatar == "🧭"
    assert [m.role_avatar for m in team.members] == ["🔎", "📝"]
