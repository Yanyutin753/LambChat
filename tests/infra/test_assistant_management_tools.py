from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from tests.infra.test_assistant_service import assistant, user


@pytest.mark.parametrize("kind,child", [("assistant", False), ("group", False), ("chief", True)])
async def test_management_rejects_non_chief_or_child_context(monkeypatch, kind, child):
    from src.infra.assistant.store import AssistantStore
    from src.infra.tool import assistant_tool as module

    monkeypatch.setattr(module, "resolve_tool_user", AsyncMock(return_value=user()))
    monkeypatch.setattr(
        AssistantStore,
        "for_session",
        AsyncMock(return_value=assistant().model_copy(update={"kind": kind})),
    )
    runtime = SimpleNamespace(
        config={
            "configurable": {"context": SimpleNamespace(user_id="owner", session_id="s")},
            "metadata": {"lambchat_subagent_id": "child"} if child else {},
        },
        tool_call_id="call",
    )
    with pytest.raises(Exception):
        await module.chief_context(runtime, "chat:write")


async def test_create_tool_reuses_call_identity_and_returns_navigation(monkeypatch):
    from src.infra.tool import assistant_tool as module

    monkeypatch.setattr(module, "chief_context", AsyncMock(return_value=user()))
    create = AsyncMock(return_value=assistant())
    monkeypatch.setattr(module, "AssistantService", lambda: SimpleNamespace(create=create))
    runtime = SimpleNamespace(
        config={"configurable": {"thread_id": "thread", "run_id": "run"}}, tool_call_id="call"
    )
    result = await module.create_assistant.coroutine(
        name="Writer", instructions="Write clearly", runtime=runtime
    )
    assert result["url"] == "/assistants/assistant"
    first = create.call_args.kwargs["identity"]
    await module.create_assistant.coroutine(
        name="Writer", instructions="Write clearly", runtime=runtime
    )
    assert create.call_args.kwargs["identity"] == first


@pytest.mark.parametrize("local", [False, True])
async def test_update_preserves_execution_settings_and_expected_revision(monkeypatch, local):
    from src.infra.tool import assistant_tool as module
    from src.kernel.schemas.project import ProjectWorkspace

    monkeypatch.setattr(module, "chief_context", AsyncMock(return_value=user()))
    workspace = (
        ProjectWorkspace(id="local-" + "a" * 32, machineId="machine", path="/work/test")
        if local
        else None
    )
    current = assistant(
        model_id="model",
        project_id="project",
        instructions="original",
        sandbox="local" if local else None,
        workspace=workspace,
    )
    update = AsyncMock(return_value=current)
    monkeypatch.setattr(
        module,
        "AssistantService",
        lambda: SimpleNamespace(get=AsyncMock(return_value=current), update=update),
    )
    await module.update_assistant.coroutine(assistant_id="assistant", revision=7, name="Renamed")
    draft = update.call_args.args[2]
    assert draft.revision == 7
    assert draft.model_id == "model" and draft.project_id == "project"
    assert draft.instructions == "original" and draft.name == "Renamed"
    assert draft.workspace == workspace and draft.sandbox == current.sandbox


async def test_management_rechecks_revoked_permissions(monkeypatch):
    from src.infra.tool import assistant_tool as module
    from src.kernel.errors import AppError

    monkeypatch.setattr(
        module,
        "resolve_tool_user",
        AsyncMock(return_value=user().model_copy(update={"permissions": []})),
    )
    runtime = SimpleNamespace(
        config={"configurable": {"context": SimpleNamespace(user_id="owner")}}, tool_call_id="call"
    )
    with pytest.raises(AppError):
        await module.chief_context(runtime, "chat:write")


async def test_chief_allows_root_tool_node_but_rejects_nested_namespace(monkeypatch):
    from src.infra.assistant.store import AssistantStore
    from src.infra.tool import assistant_tool as module
    from src.kernel.errors import AppError

    owner = user()
    monkeypatch.setattr(module, "resolve_tool_user", AsyncMock(return_value=owner))
    chief = assistant().model_copy(update={"kind": "chief"})
    monkeypatch.setattr(AssistantStore, "for_session", AsyncMock(return_value=chief))
    runtime = SimpleNamespace(
        config={
            "configurable": {
                "context": SimpleNamespace(user_id="owner", session_id=chief.session_id),
                "thread_id": chief.session_id,
                "checkpoint_ns": "tools:root",
            }
        }
    )
    assert await module.chief_context(runtime, "chat:write") == owner
    runtime.config["configurable"]["checkpoint_ns"] = "tools:root|tools:child"
    with pytest.raises(AppError):
        await module.chief_context(runtime, "chat:write")


async def test_coordinator_change_requires_explicit_instructions_before_any_write(monkeypatch):
    from src.infra.tool import assistant_tool as module
    from src.kernel.errors import AppError, ErrorCode

    monkeypatch.setattr(module, "chief_context", AsyncMock(return_value=user()))
    current = assistant().model_copy(
        update={
            "kind": "group",
            "member_ids": ["writer", "reviewer"],
            "leader_id": "writer",
            "instructions": "Writer coordinates. Reviewer checks sources.",
        }
    )
    update = AsyncMock(return_value=current)
    monkeypatch.setattr(
        module,
        "AssistantService",
        lambda: SimpleNamespace(
            get=AsyncMock(return_value=current),
            update=update,
        ),
    )
    with pytest.raises(AppError) as caught:
        await module.update_assistant.coroutine(
            assistant_id=current.id,
            revision=7,
            leader_id="reviewer",
        )
    assert caught.value.error_code == ErrorCode.VALIDATION_ERROR
    update.assert_not_awaited()


@pytest.mark.parametrize(
    "instructions",
    [
        "Reviewer coordinates. Writer gathers sources; formerly Writer coordinated.",
        "Check sources together.",
        "",
    ],
)
@pytest.mark.parametrize("local", [False, True])
async def test_coordinator_and_reviewed_purpose_use_one_versioned_update(
    monkeypatch, instructions, local
):
    from src.infra.tool import assistant_tool as module
    from src.kernel.schemas.project import ProjectWorkspace

    monkeypatch.setattr(module, "chief_context", AsyncMock(return_value=user()))
    workspace = (
        ProjectWorkspace(id="local-" + "b" * 32, machineId="machine", path="/work/group")
        if local
        else None
    )
    current = assistant(
        model_id="model", sandbox="local" if local else None, workspace=workspace
    ).model_copy(
        update={
            "kind": "group",
            "member_ids": ["writer", "reviewer"],
            "leader_id": "writer",
            "instructions": "Check sources together.",
        }
    )
    update = AsyncMock(return_value=current)
    monkeypatch.setattr(
        module,
        "AssistantService",
        lambda: SimpleNamespace(
            get=AsyncMock(return_value=current),
            update=update,
        ),
    )
    await module.update_assistant.coroutine(
        assistant_id=current.id,
        revision=7,
        leader_id="reviewer",
        instructions=instructions,
    )
    update.assert_awaited_once()
    draft = update.call_args.args[2]
    assert (draft.leader_id, draft.instructions, draft.revision) == ("reviewer", instructions, 7)
    assert draft.member_ids == current.member_ids and draft.model_id == "model"
    assert draft.workspace == workspace and draft.sandbox == current.sandbox


async def test_unchanged_coordinator_does_not_require_rewriting_purpose(monkeypatch):
    from src.infra.tool import assistant_tool as module

    monkeypatch.setattr(module, "chief_context", AsyncMock(return_value=user()))
    current = assistant().model_copy(
        update={
            "kind": "group",
            "member_ids": ["writer", "reviewer"],
            "leader_id": "writer",
            "instructions": "Writer coordinates.",
        }
    )
    update = AsyncMock(return_value=current)
    monkeypatch.setattr(
        module,
        "AssistantService",
        lambda: SimpleNamespace(
            get=AsyncMock(return_value=current),
            update=update,
        ),
    )
    await module.update_assistant.coroutine(
        assistant_id=current.id,
        revision=7,
        name="Renamed",
        leader_id="writer",
    )
    assert update.call_args.args[2].instructions == current.instructions


@pytest.mark.parametrize("kind", ["assistant", "group"])
async def test_update_presentation_preserves_duties_and_returns_saved_fields(monkeypatch, kind):
    from src.infra.tool import assistant_tool as module
    from src.kernel.schemas.assistant import AssistantCreate

    monkeypatch.setattr(module, "chief_context", AsyncMock(return_value=user()))
    current = assistant().model_copy(
        update={
            "kind": kind,
            "member_ids": ["a", "b"] if kind == "group" else [],
            "leader_id": "a" if kind == "group" else None,
        }
    )

    async def save(owner, identity, draft):
        return type(current).model_validate({**current.model_dump(), **draft.model_dump()})

    update = AsyncMock(side_effect=save)
    monkeypatch.setattr(
        module,
        "AssistantService",
        lambda: SimpleNamespace(get=AsyncMock(return_value=current), update=update),
    )
    prompts = [
        {
            "icon": "🔎",
            "text": {
                "zh": "核对来源",
                "en": "Check sources",
                "ja": "出典を確認",
                "ko": "출처 확인",
                "ru": "Проверить источники",
            },
        }
    ]
    payload = module.update_assistant.args_schema.model_validate(
        {"assistant_id": current.id, "revision": 7, "avatar": "🔎", "starter_prompts": prompts}
    )
    result = await module.update_assistant.coroutine(
        assistant_id=current.id,
        revision=7,
        avatar=payload.avatar,
        starter_prompts=payload.starter_prompts,
    )
    draft = update.call_args.args[2]
    assert draft.avatar == "🔎"
    assert draft.instructions == current.instructions
    assert result["avatar"] == "🔎"
    assert result["starter_prompts"] == prompts
    assert "starter_prompts" in AssistantCreate.model_fields


async def test_update_runtime_configuration_and_clear_bindings(monkeypatch):
    from src.infra.tool import assistant_tool as module
    from src.kernel.schemas.project import ProjectWorkspace

    monkeypatch.setattr(module, "chief_context", AsyncMock(return_value=user()))
    current = assistant(
        model_id="old",
        persona_preset_id="role",
        project_id="project",
        memory_mode="project",
        sandbox="local",
        workspace=ProjectWorkspace(id="local-" + "a" * 32, machineId="machine", path="/work"),
    )
    update = AsyncMock(return_value=current)
    monkeypatch.setattr(
        module,
        "AssistantService",
        lambda: SimpleNamespace(get=AsyncMock(return_value=current), update=update),
    )
    await module.update_assistant.coroutine(
        assistant_id=current.id,
        revision=7,
        model_id="new",
        persona_preset_id="",
        team_id="team",
        project_id="",
        memory_mode="private",
        sandbox="inherit",
    )
    draft = update.call_args.args[2]
    assert draft.model_id == "new" and draft.team_id == "team"
    assert draft.persona_preset_id is None and draft.project_id is None
    assert draft.memory_mode == "private"
    assert draft.sandbox is None and draft.workspace is None
    assert draft.instructions == current.instructions


async def test_create_tool_accepts_presentation_and_execution_configuration(monkeypatch):
    from src.infra.tool import assistant_tool as module

    monkeypatch.setattr(module, "chief_context", AsyncMock(return_value=user()))
    create = AsyncMock(return_value=assistant())
    monkeypatch.setattr(module, "AssistantService", lambda: SimpleNamespace(create=create))
    runtime = SimpleNamespace(
        config={"configurable": {"thread_id": "thread", "run_id": "run"}}, tool_call_id="call"
    )
    payload = module.create_assistant.args_schema.model_validate(
        {
            "name": "Writer",
            "instructions": "Write clearly",
            "avatar": "✍️",
            "starter_prompts": [{"icon": "📝", "text": {"en": "Draft", "zh": "起草"}}],
            "model_id": "model",
            "project_id": "project",
            "memory_mode": "project",
            "sandbox": "cloud",
        }
    )
    await module.create_assistant.coroutine(
        **{key: getattr(payload, key) for key in payload.model_fields_set}, runtime=runtime
    )
    draft = create.call_args.args[1]
    assert draft.avatar == "✍️"
    assert draft.starter_prompts[0].text["zh"] == "起草"
    assert draft.model_id == "model" and draft.project_id == "project"
    assert draft.memory_mode == "project" and draft.sandbox == "cloud"


async def test_update_preserves_or_explicitly_clears_presentation(monkeypatch):
    from src.infra.tool import assistant_tool as module
    from src.kernel.schemas.persona_preset import PersonaStarterPrompt

    monkeypatch.setattr(module, "chief_context", AsyncMock(return_value=user()))
    current = assistant(avatar="🔎", starter_prompts=[PersonaStarterPrompt(text="Research")])
    update = AsyncMock(return_value=current)
    monkeypatch.setattr(
        module,
        "AssistantService",
        lambda: SimpleNamespace(get=AsyncMock(return_value=current), update=update),
    )
    await module.update_assistant.coroutine(assistant_id=current.id, revision=7, name="New")
    assert update.call_args.args[2].starter_prompts == current.starter_prompts
    assert update.call_args.args[2].avatar == current.avatar
    await module.update_assistant.coroutine(
        assistant_id=current.id, revision=7, avatar="", starter_prompts=[]
    )
    assert update.call_args.args[2].avatar == ""
    assert update.call_args.args[2].starter_prompts == []


async def test_list_can_find_archived_configuration_for_restoration(monkeypatch):
    from src.infra.tool import assistant_tool as module

    monkeypatch.setattr(module, "chief_context", AsyncMock(return_value=user()))
    store = SimpleNamespace(
        list=AsyncMock(return_value=[assistant(model_id="model")]), count=AsyncMock(return_value=1)
    )
    monkeypatch.setattr(module, "AssistantStore", lambda: store)
    result = await module.list_assistants.coroutine(archived=True)
    store.list.assert_awaited_once_with("owner", skip=0, limit=50, archived=True)
    store.count.assert_awaited_once_with("owner", archived=True)
    assert result["assistants"][0]["model_id"] == "model"
    assert "user_id" not in result["assistants"][0]


def test_listed_workspace_can_be_reused_without_losing_picker_identity():
    from src.infra.tool.assistant_tool import public_assistant
    from src.kernel.schemas.project import ProjectWorkspace

    receipt = ProjectWorkspace(id="local-" + "a" * 32, machineId="machine", path="/work")
    listed = public_assistant(assistant(sandbox="local", workspace=receipt))
    assert ProjectWorkspace.model_validate(listed["workspace"]) == receipt


async def test_invalid_group_settings_fail_before_update(monkeypatch):
    from pydantic import ValidationError

    from src.infra.tool import assistant_tool as module

    monkeypatch.setattr(module, "chief_context", AsyncMock(return_value=user()))
    current = assistant().model_copy(
        update={"kind": "group", "member_ids": ["a", "b"], "leader_id": "a"}
    )
    update = AsyncMock()
    monkeypatch.setattr(
        module,
        "AssistantService",
        lambda: SimpleNamespace(get=AsyncMock(return_value=current), update=update),
    )
    with pytest.raises(ValidationError):
        await module.update_assistant.coroutine(assistant_id=current.id, revision=7, team_id="team")
    update.assert_not_awaited()


async def test_configuration_choices_are_permission_scoped_and_exclude_secrets(monkeypatch):
    from src.api.routes.agent import model as model_route
    from src.infra.folder import storage as project_storage
    from src.infra.team.storage import TeamStorage
    from src.infra.tool import assistant_tool as module
    from src.infra.utils.datetime import utc_now
    from src.kernel.schemas.project import Project

    owner = user().model_copy(
        update={"permissions": ["session:read", "agent:read", "project:read", "team:read"]}
    )
    monkeypatch.setattr(module, "chief_context", AsyncMock(return_value=owner))
    monkeypatch.setattr(
        module,
        "AssistantStore",
        lambda: SimpleNamespace(list=AsyncMock(return_value=[]), count=AsyncMock(return_value=0)),
    )
    models = AsyncMock(
        return_value=SimpleNamespace(
            models=[SimpleNamespace(id="model", label="Model", api_key="secret")]
        )
    )
    monkeypatch.setattr(model_route, "list_available_models", models)
    projects = SimpleNamespace(
        list_projects=AsyncMock(
            return_value=[
                Project(
                    id="p",
                    name="Project",
                    user_id="owner",
                    created_at=utc_now(),
                    updated_at=utc_now(),
                )
            ]
        )
    )
    monkeypatch.setattr(project_storage, "get_project_storage", lambda: projects)
    teams = AsyncMock(return_value=([SimpleNamespace(id="t", name="Team")], 1))
    monkeypatch.setattr(TeamStorage, "list_teams", teams)
    result = await module.list_assistants.coroutine(include_options=True)
    options = result["configuration_options"]
    assert options["models"] == [{"id": "model", "name": "Model"}]
    assert options["projects"][0]["id"] == "p"
    assert options["teams"] == [{"id": "t", "name": "Team"}]
    projects.list_projects.assert_awaited_once_with("owner")
    teams.assert_awaited_once_with(owner_user_id="owner", skip=0, limit=50)
    owner.permissions = ["session:read"]
    models.reset_mock()
    projects.list_projects.reset_mock()
    teams.reset_mock()
    result = await module.list_assistants.coroutine(include_options=True)
    assert result["configuration_options"] == {}
    models.assert_not_awaited()
    projects.list_projects.assert_not_awaited()
    teams.assert_not_awaited()
