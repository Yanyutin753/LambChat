"""Tests for team manager."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from src.infra.team.manager import TeamManager
from src.kernel.schemas.model import ModelConfig
from src.kernel.schemas.team import (
    TeamCreate,
    TeamMemberResponse,
    TeamPreferenceUpdate,
    TeamResponse,
    TeamVisibility,
)
from src.kernel.schemas.user import TokenPayload


def _make_team(
    *,
    team_id: str = "team-1",
    owner_user_id: str = "user-1",
    name: str = "Test Team",
    members: list[TeamMemberResponse] | None = None,
) -> TeamResponse:
    return TeamResponse(
        id=team_id,
        owner_user_id=owner_user_id,
        name=name,
        members=members or [],
        visibility=TeamVisibility.PRIVATE,
    )


@pytest.fixture
def mock_storage():
    storage = MagicMock()
    return storage


@pytest.fixture
def mock_persona_manager():
    pm = MagicMock()
    pm.storage = MagicMock()
    pm.storage.get_by_id = AsyncMock(return_value=None)
    pm.storage.get_by_ids = AsyncMock(return_value={})
    return pm


@pytest.fixture
def manager(mock_storage, mock_persona_manager):
    return TeamManager(storage=mock_storage, persona_manager=mock_persona_manager)


@pytest.mark.asyncio
async def test_create_team_delegates_to_storage(manager, mock_storage):
    created = _make_team(name="New Team")
    mock_storage.create_team = AsyncMock(return_value=created)

    data = TeamCreate(name="New Team")
    result = await manager.create_team(data, owner_user_id="user-1")

    mock_storage.create_team.assert_awaited_once()
    assert result.name == "New Team"


@pytest.mark.asyncio
async def test_update_team_preference_returns_team_with_user_preference(manager, mock_storage):
    team = _make_team()
    mock_storage.get_team = AsyncMock(return_value=team)
    mock_storage.update_user_preference = AsyncMock(
        return_value={"is_favorite": True, "is_pinned": False, "last_used_at": None}
    )

    result = await manager.update_preference(
        "team-1",
        TeamPreferenceUpdate(is_favorite=True),
        owner_user_id="user-1",
    )

    mock_storage.update_user_preference.assert_awaited_once_with(
        user_id="user-1",
        team_id="team-1",
        update={"is_favorite": True, "is_pinned": None},
    )
    assert result.is_favorite is True
    assert result.is_pinned is False


@pytest.mark.asyncio
async def test_create_team_preserves_member_display_metadata_for_api_response(
    manager, mock_storage
):
    created = _make_team(name="New Team")
    mock_storage.create_team = AsyncMock(return_value=created)

    data = TeamCreate(
        name="New Team",
        members=[
            {
                "member_id": "m-designer",
                "persona_preset_id": "preset-1",
                "agent_id": None,
                "model_id": None,
                "role_name": "Designer",
                "role_avatar": "icon:palette",
                "role_tags": ["design"],
            }
        ],
    )

    await manager.create_team(data, owner_user_id="user-1")

    _, kwargs = mock_storage.create_team.await_args
    assert kwargs["members"] == [
        {
            "member_id": "m-designer",
            "persona_preset_id": "preset-1",
            "agent_id": None,
            "model_id": None,
            "role_name": "Designer",
            "role_avatar": "icon:palette",
            "role_tags": ["design"],
            "role_instructions": "",
            "position": 0,
            "enabled": True,
        }
    ]


@pytest.mark.asyncio
async def test_create_team_delegates_tags_to_storage(manager, mock_storage):
    created = _make_team(name="Tagged Team")
    mock_storage.create_team = AsyncMock(return_value=created)

    data = TeamCreate(name="Tagged Team", tags=["research", "planning"])
    await manager.create_team(data, owner_user_id="user-1")

    _, kwargs = mock_storage.create_team.await_args
    assert kwargs["tags"] == ["research", "planning"]


@pytest.mark.asyncio
async def test_create_team_preserves_member_model_id(manager, mock_storage, monkeypatch):
    created = _make_team(name="Model Team")
    mock_storage.create_team = AsyncMock(return_value=created)
    model = ModelConfig(
        id="model-member",
        value="openai/member",
        label="Member",
        enabled=True,
    )

    class _ModelStorage:
        async def get_many_by_ids_and_values(self, model_ids):
            return {model_id: await self.get(model_id) for model_id in model_ids}, {}

        async def get(self, model_id):
            assert model_id == "model-member"
            return model

    import src.infra.agent.model_storage as model_storage

    monkeypatch.setattr(model_storage, "get_model_storage", lambda: _ModelStorage())

    data = TeamCreate(
        name="Model Team",
        members=[
            {
                "member_id": "m-analyst",
                "persona_preset_id": "preset-1",
                "model_id": "model-member",
            }
        ],
    )
    await manager.create_team(data, owner_user_id="user-1")

    _, kwargs = mock_storage.create_team.await_args
    assert kwargs["members"][0]["model_id"] == "model-member"


@pytest.mark.asyncio
async def test_create_team_preserves_member_agent_id(manager, mock_storage, monkeypatch):
    created = _make_team(name="Mode Team")
    mock_storage.create_team = AsyncMock(return_value=created)

    import src.agents.core.base as agent_base

    monkeypatch.setattr(
        agent_base.AgentFactory,
        "list_agents",
        classmethod(lambda cls, default_agent_id=None: [{"id": "fast"}, {"id": "search"}]),
    )

    async def fake_filtered_agents(**_kwargs):
        return [{"id": "fast"}, {"id": "search"}]

    monkeypatch.setattr(
        agent_base.AgentFactory,
        "get_filtered_agents",
        classmethod(lambda cls, **kwargs: fake_filtered_agents(**kwargs)),
    )

    data = TeamCreate(
        name="Mode Team",
        members=[
            {
                "member_id": "m-analyst",
                "persona_preset_id": "preset-1",
                "agent_id": "search",
            }
        ],
    )
    await manager.create_team(data, owner_user_id="user-1")

    _, kwargs = mock_storage.create_team.await_args
    assert kwargs["members"][0]["agent_id"] == "search"


@pytest.mark.asyncio
async def test_validate_member_agent_access_rejects_unknown_agent(manager, monkeypatch):
    import src.agents.core.base as agent_base

    monkeypatch.setattr(
        agent_base.AgentFactory,
        "list_agents",
        classmethod(lambda cls, default_agent_id=None: [{"id": "fast"}]),
    )

    with pytest.raises(ValueError, match="team_member_agent_unavailable"):
        await manager.create_team(
            TeamCreate(
                name="Unknown Mode Team",
                members=[{"persona_preset_id": "preset-1", "agent_id": "missing"}],
            ),
            owner_user_id="user-1",
        )


@pytest.mark.asyncio
async def test_validate_member_agent_access_rejects_team_agent(manager, monkeypatch):
    import src.agents.core.base as agent_base

    monkeypatch.setattr(
        agent_base.AgentFactory,
        "list_agents",
        classmethod(lambda cls, default_agent_id=None: [{"id": "fast"}, {"id": "team"}]),
    )

    with pytest.raises(ValueError, match="team_member_agent_unavailable"):
        await manager.create_team(
            TeamCreate(
                name="Recursive Team",
                members=[{"persona_preset_id": "preset-1", "agent_id": "team"}],
            ),
            owner_user_id="user-1",
        )


@pytest.mark.asyncio
async def test_validate_member_agent_access_rejects_role_disallowed_agent(manager, monkeypatch):
    import src.agents.core.base as agent_base

    monkeypatch.setattr(
        agent_base.AgentFactory,
        "list_agents",
        classmethod(lambda cls, default_agent_id=None: [{"id": "fast"}, {"id": "search"}]),
    )

    async def fake_filtered_agents(**_kwargs):
        return [{"id": "fast"}]

    monkeypatch.setattr(
        agent_base.AgentFactory,
        "get_filtered_agents",
        classmethod(lambda cls, **kwargs: fake_filtered_agents(**kwargs)),
    )

    class _RoleManager:
        def __init__(self):
            self.storage = self

        async def get_roles_by_names(self, role_names):
            return [MagicMock(id=f"role-{name}") for name in role_names]

    class _AgentConfigStorage:
        async def get_role_agents_by_ids(self, role_ids):
            return {role_id: ["fast"] for role_id in role_ids}

    import src.infra.agent.config_storage as config_storage
    import src.infra.role.manager as role_manager

    monkeypatch.setattr(config_storage, "get_agent_config_storage", lambda: _AgentConfigStorage())
    monkeypatch.setattr(role_manager, "get_role_manager", lambda: _RoleManager())

    with pytest.raises(ValueError, match="team_member_agent_not_allowed"):
        await manager.create_team(
            TeamCreate(
                name="Forbidden Mode Team",
                members=[{"persona_preset_id": "preset-1", "agent_id": "search"}],
            ),
            owner_user_id="user-1",
            user=TokenPayload(sub="user-1", username="tester", roles=["user"], permissions=[]),
        )


@pytest.mark.asyncio
async def test_validate_member_model_access_allows_empty_member_model(
    manager, mock_storage, monkeypatch
):
    called = False

    class _ModelStorage:
        async def get_many_by_ids_and_values(self, model_ids):
            return {model_id: await self.get(model_id) for model_id in model_ids}, {}

        async def get(self, _model_id):
            nonlocal called
            called = True

    import src.infra.agent.model_storage as model_storage

    monkeypatch.setattr(model_storage, "get_model_storage", lambda: _ModelStorage())
    mock_storage.create_team = AsyncMock(return_value=_make_team(name="Default Team"))

    await manager.create_team(
        TeamCreate(name="Default Team", members=[{"persona_preset_id": "preset-1"}]),
        owner_user_id="user-1",
    )

    assert called is False


@pytest.mark.asyncio
async def test_validate_member_model_access_allows_enabled_allowed_model(
    manager, mock_storage, monkeypatch
):
    model = ModelConfig(
        id="model-member",
        value="openai/member",
        label="Member",
        enabled=True,
    )

    class _ModelStorage:
        async def get_many_by_ids_and_values(self, model_ids):
            return {model_id: await self.get(model_id) for model_id in model_ids}, {}

        async def get(self, model_id):
            assert model_id == "model-member"
            return model

    async def fake_allowed(_user):
        return ["model-member"]

    import src.infra.agent.model_access as model_access
    import src.infra.agent.model_storage as model_storage

    monkeypatch.setattr(model_storage, "get_model_storage", lambda: _ModelStorage())
    monkeypatch.setattr(model_access, "resolve_user_allowed_model_ids", fake_allowed)
    mock_storage.create_team = AsyncMock(return_value=_make_team(name="Allowed Team"))

    await manager.create_team(
        TeamCreate(
            name="Allowed Team",
            members=[{"persona_preset_id": "preset-1", "model_id": "model-member"}],
        ),
        owner_user_id="user-1",
        user=TokenPayload(sub="user-1", username="tester", roles=["user"], permissions=[]),
    )

    mock_storage.create_team.assert_awaited_once()


@pytest.mark.asyncio
async def test_validate_member_model_access_rejects_missing_or_disabled_model(manager, monkeypatch):
    class _ModelStorage:
        async def get_many_by_ids_and_values(self, model_ids):
            return {model_id: await self.get(model_id) for model_id in model_ids}, {}

        async def get(self, _model_id):
            return None

    import src.infra.agent.model_storage as model_storage

    monkeypatch.setattr(model_storage, "get_model_storage", lambda: _ModelStorage())

    with pytest.raises(ValueError, match="team_member_model_unavailable"):
        await manager.create_team(
            TeamCreate(
                name="Missing Model Team",
                members=[{"persona_preset_id": "preset-1", "model_id": "missing"}],
            ),
            owner_user_id="user-1",
        )


@pytest.mark.asyncio
async def test_validate_member_model_access_rejects_role_disallowed_model(manager, monkeypatch):
    model = ModelConfig(
        id="model-member",
        value="openai/member",
        label="Member",
        enabled=True,
    )

    class _ModelStorage:
        async def get_many_by_ids_and_values(self, model_ids):
            return {model_id: await self.get(model_id) for model_id in model_ids}, {}

        async def get(self, _model_id):
            return model

    async def fake_allowed(_user):
        return ["other-model"]

    import src.infra.agent.model_access as model_access
    import src.infra.agent.model_storage as model_storage

    monkeypatch.setattr(model_storage, "get_model_storage", lambda: _ModelStorage())
    monkeypatch.setattr(model_access, "resolve_user_allowed_model_ids", fake_allowed)

    with pytest.raises(ValueError, match="team_member_model_not_allowed"):
        await manager.create_team(
            TeamCreate(
                name="Forbidden Model Team",
                members=[{"persona_preset_id": "preset-1", "model_id": "model-member"}],
            ),
            owner_user_id="user-1",
            user=TokenPayload(sub="user-1", username="tester", roles=["user"], permissions=[]),
        )


@pytest.mark.asyncio
async def test_get_team_raises_not_found(manager, mock_storage):
    mock_storage.get_team = AsyncMock(return_value=None)

    from src.kernel.exceptions import NotFoundError

    with pytest.raises(NotFoundError):
        await manager.get_team("nonexistent", owner_user_id="user-1")


@pytest.mark.asyncio
async def test_list_teams_hydrates_all_members_with_one_batch_query(
    manager, mock_storage, mock_persona_manager
):
    teams = [
        _make_team(
            team_id="team-1",
            members=[TeamMemberResponse(member_id="m-1", persona_preset_id="preset-1")],
        ),
        _make_team(
            team_id="team-2",
            members=[TeamMemberResponse(member_id="m-2", persona_preset_id="preset-2")],
        ),
    ]
    mock_storage.list_teams = AsyncMock(return_value=(teams, 2))
    mock_persona_manager.storage.get_by_ids = AsyncMock(
        return_value={
            "preset-1": {"name": "Planner", "avatar": "plan.png", "tags": ["plan"]},
            "preset-2": {"name": "Writer", "avatar": "write.png", "tags": ["write"]},
        }
    )

    result = await manager.list_teams(owner_user_id="user-1")

    mock_persona_manager.storage.get_by_ids.assert_awaited_once_with(["preset-1", "preset-2"])
    assert [team.id for team in result.teams] == ["team-1", "team-2"]
    assert [team.members[0].role_name for team in result.teams] == ["Planner", "Writer"]


@pytest.mark.asyncio
async def test_team_hydration_deduplicates_presets_in_first_seen_order(
    manager, mock_persona_manager
):
    teams = [
        _make_team(
            team_id="team-1",
            members=[
                TeamMemberResponse(member_id="m-1", persona_preset_id="preset-2"),
                TeamMemberResponse(member_id="m-2", persona_preset_id="preset-1"),
            ],
        ),
        _make_team(
            team_id="team-2",
            members=[TeamMemberResponse(member_id="m-3", persona_preset_id="preset-2")],
        ),
    ]

    result = await manager._hydrate_teams_member_display_metadata(teams)

    mock_persona_manager.storage.get_by_ids.assert_awaited_once_with(["preset-2", "preset-1"])
    assert [team.id for team in result] == ["team-1", "team-2"]
    assert [member.member_id for team in result for member in team.members] == [
        "m-1",
        "m-2",
        "m-3",
    ]


@pytest.mark.asyncio
async def test_team_hydration_preserves_members_with_missing_or_invalid_presets(
    manager, mock_persona_manager
):
    members = [
        TeamMemberResponse(
            member_id="m-invalid",
            persona_preset_id="invalid",
            role_name="Original Invalid",
            role_avatar="invalid.png",
            role_tags=["original"],
        ),
        TeamMemberResponse(
            member_id="m-missing",
            persona_preset_id="missing",
            role_name="Original Missing",
        ),
    ]
    team = _make_team(members=members)

    result = await manager._hydrate_teams_member_display_metadata([team])

    assert result[0].members == members


@pytest.mark.asyncio
async def test_team_hydration_returns_original_teams_when_batch_lookup_fails(
    manager, mock_persona_manager, caplog
):
    teams = [
        _make_team(members=[TeamMemberResponse(member_id="m-1", persona_preset_id="preset-1")])
    ]
    mock_persona_manager.storage.get_by_ids = AsyncMock(
        side_effect=RuntimeError("database unavailable")
    )

    result = await manager._hydrate_teams_member_display_metadata(teams)

    assert result is teams
    assert "Failed to hydrate team member metadata" in caplog.text


@pytest.mark.asyncio
async def test_validate_team_members_handles_missing_presets(manager, mock_persona_manager):
    members = [
        TeamMemberResponse(
            member_id="m-1",
            persona_preset_id="preset-missing",
            role_name="Agent",
            enabled=True,
        ),
    ]
    team = _make_team(members=members)
    mock_persona_manager.storage.get_by_id = AsyncMock(return_value=None)

    result = await manager.validate_team_members(team)
    assert result == []


@pytest.mark.asyncio
async def test_validate_team_members_with_valid_preset(manager, mock_persona_manager):
    mock_persona_manager.storage.get_by_ids = AsyncMock(
        return_value={"preset-1": {"name": "Helper", "avatar": "avatar.png", "tags": ["helpful"]}}
    )
    members = [
        TeamMemberResponse(
            member_id="m-1",
            persona_preset_id="preset-1",
            enabled=True,
        ),
    ]
    team = _make_team(members=members)

    result = await manager.validate_team_members(team)
    assert len(result) == 1


@pytest.mark.asyncio
async def test_resolve_team_for_runtime_returns_none_when_not_found(manager, mock_storage):
    mock_storage.get_team = AsyncMock(return_value=None)

    result = await manager.resolve_team_for_runtime("missing", owner_user_id="user-1")
    assert result is None


@pytest.mark.asyncio
async def test_resolve_team_for_runtime_returns_none_when_no_active_members(manager, mock_storage):
    team = _make_team(
        members=[
            TeamMemberResponse(
                member_id="m-1",
                persona_preset_id="preset-1",
                enabled=False,
            ),
        ]
    )
    mock_storage.get_team = AsyncMock(return_value=team)

    result = await manager.resolve_team_for_runtime("team-1", owner_user_id="user-1")
    assert result is None


@pytest.mark.asyncio
async def test_resolve_team_for_runtime_returns_team(manager, mock_storage, mock_persona_manager):
    members = [
        TeamMemberResponse(
            member_id="m-1",
            persona_preset_id="preset-1",
            enabled=True,
        ),
    ]
    team = _make_team(members=members)
    mock_storage.get_team = AsyncMock(return_value=team)
    mock_persona_manager.storage.get_by_ids = AsyncMock(return_value={"preset-1": {"name": "Bot"}})

    result = await manager.resolve_team_for_runtime("team-1", owner_user_id="user-1")
    assert result is not None
    assert result.name == "Test Team"


@pytest.mark.asyncio
async def test_resolve_team_for_runtime_returns_none_when_all_active_presets_missing(
    manager, mock_storage, mock_persona_manager
):
    members = [
        TeamMemberResponse(
            member_id="m-1",
            persona_preset_id="missing",
            enabled=True,
        ),
    ]
    team = _make_team(members=members)
    mock_storage.get_team = AsyncMock(return_value=team)
    mock_persona_manager.storage.get_by_id = AsyncMock(return_value=None)

    result = await manager.resolve_team_for_runtime("team-1", owner_user_id="user-1")

    assert result is None


@pytest.mark.asyncio
async def test_validate_team_members_batches_active_presets_preserving_order(
    manager, mock_persona_manager, caplog
):
    members = [
        TeamMemberResponse(member_id="m-1", persona_preset_id="preset-2", position=2),
        TeamMemberResponse(member_id="m-missing", persona_preset_id="missing", position=0),
        TeamMemberResponse(member_id="m-2", persona_preset_id="preset-1", position=1),
        TeamMemberResponse(member_id="m-repeat", persona_preset_id="preset-2"),
        TeamMemberResponse(member_id="m-disabled", persona_preset_id="disabled", enabled=False),
    ]
    mock_persona_manager.storage.get_by_ids.return_value = {"preset-2": {}, "preset-1": {}}

    result = await manager.validate_team_members(_make_team(members=members))

    assert result == [members[0], members[2], members[3]]
    mock_persona_manager.storage.get_by_ids.assert_awaited_once_with(
        ["preset-2", "missing", "preset-1"]
    )
    mock_persona_manager.storage.get_by_id.assert_not_awaited()
    assert "Member m-missing references missing preset missing" in caplog.text


@pytest.mark.asyncio
async def test_validate_team_members_batch_failure_skips_members(
    manager, mock_persona_manager, caplog
):
    members = [TeamMemberResponse(member_id="m-1", persona_preset_id="preset-1")]
    mock_persona_manager.storage.get_by_ids.side_effect = RuntimeError("database unavailable")

    assert await manager.validate_team_members(_make_team(members=members)) == []
    mock_persona_manager.storage.get_by_ids.assert_awaited_once_with(["preset-1"])
    assert "Failed to validate member m-1 (preset preset-1)" in caplog.text


@pytest.mark.asyncio
async def test_validate_team_members_without_active_members_skips_lookup(
    manager, mock_persona_manager
):
    assert await manager.validate_team_members(_make_team()) == []
    mock_persona_manager.storage.get_by_ids.assert_not_awaited()
    mock_persona_manager.storage.get_by_id.assert_not_awaited()


@pytest.mark.asyncio
async def test_validate_member_models_batches_ids_and_preserves_error_precedence(
    manager, monkeypatch
):
    import src.infra.agent.model_access as model_access
    import src.infra.agent.model_storage as model_storage

    models = {
        "first": ModelConfig(id="first", value="provider/first", label="First", enabled=True),
        "second": ModelConfig(id="second", value="provider/second", label="Second", enabled=True),
    }
    storage = MagicMock()
    storage.get = AsyncMock(side_effect=lambda model_id: models.get(model_id))
    storage.get_many_by_ids_and_values = AsyncMock(return_value=(models, {}))
    allowed = AsyncMock(return_value=["provider/first", "second"])
    monkeypatch.setattr(model_storage, "get_model_storage", lambda: storage)
    monkeypatch.setattr(model_access, "resolve_user_allowed_model_ids", allowed)
    user = TokenPayload(sub="user-1", username="tester", roles=["user"], permissions=[])
    members = TeamCreate(
        name="Team",
        members=[
            {"persona_preset_id": "preset", "model_id": "first"},
            {"persona_preset_id": "preset", "model_id": "second"},
            {"persona_preset_id": "preset", "model_id": "first"},
        ],
    ).members

    await manager._validate_member_model_access(members, user=user)
    storage.get_many_by_ids_and_values.assert_awaited_once_with(["first", "second"])
    storage.get.assert_not_awaited()

    models.pop("second")
    allowed.reset_mock()
    with pytest.raises(ValueError, match="team_member_model_unavailable"):
        await manager._validate_member_model_access(members, user=user)
    allowed.assert_not_awaited()


@pytest.mark.asyncio
async def test_validate_member_model_override_requires_id_not_value(manager, monkeypatch):
    import src.infra.agent.model_storage as model_storage

    model = ModelConfig(id="actual-id", value="provider/model", label="Model", enabled=True)
    storage = MagicMock()
    storage.get = AsyncMock(return_value=None)
    storage.get_many_by_ids_and_values = AsyncMock(return_value=({}, {"provider/model": model}))
    monkeypatch.setattr(model_storage, "get_model_storage", lambda: storage)
    members = TeamCreate(
        name="Team",
        members=[
            {"persona_preset_id": "preset", "model_id": "provider/model"},
        ],
    ).members

    with pytest.raises(ValueError, match="team_member_model_unavailable"):
        await manager._validate_member_model_access(members)
    storage.get_many_by_ids_and_values.assert_awaited_once_with(["provider/model"])


@pytest.mark.asyncio
async def test_validate_member_agent_access_batches_roles_without_truncating_permissions(
    manager, monkeypatch
):
    import src.agents.core.base as agent_base
    import src.infra.agent.config_storage as config_storage
    import src.infra.role.manager as role_manager
    import src.infra.role.storage as role_storage

    roles = role_manager.RoleManager()

    def found_roles(names):
        found = []
        for name in names:
            if name != "missing":
                role = MagicMock(id=f"role-{name}")
                role.name = name
                found.append(role)
        return found

    role_lookup = AsyncMock(side_effect=found_roles)
    roles.storage.get_by_names = role_lookup
    monkeypatch.setattr(role_storage, "ROLE_BATCH_LOOKUP_LIMIT", 2)
    configs = MagicMock()
    configs.get_role_agents_by_ids = AsyncMock(
        return_value={"role-first": None, "role-last": ["search"]}
    )
    monkeypatch.setattr(role_manager, "get_role_manager", lambda: roles)
    monkeypatch.setattr(config_storage, "get_agent_config_storage", lambda: configs)
    monkeypatch.setattr(
        agent_base.AgentFactory, "list_agents", classmethod(lambda cls: [{"id": "search"}])
    )
    filtered = AsyncMock(return_value=[{"id": "search"}])
    monkeypatch.setattr(agent_base.AgentFactory, "get_filtered_agents", filtered)
    members = TeamCreate(
        name="Team", members=[{"persona_preset_id": "preset", "agent_id": "search"}]
    ).members
    user = TokenPayload(
        sub="user-1", username="tester", roles=["first", "missing", "last", "first"], permissions=[]
    )

    await manager._validate_member_agent_access(members, user=user)

    assert [call.args[0] for call in role_lookup.await_args_list] == [
        ["first", "missing"],
        ["last"],
    ]
    configs.get_role_agents_by_ids.assert_awaited_once_with(
        ["role-first", "role-last", "role-first"]
    )
    filtered.assert_awaited_once_with(
        user_roles=["role-first", "role-last", "role-first"],
        role_agent_map={"role-first": None, "role-last": ["search"]},
    )
