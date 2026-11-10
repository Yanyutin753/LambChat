"""Configuration is not a lasting permission grant."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.assistant import Assistant, AssistantCreate, AssistantUpdate
from src.kernel.schemas.user import TokenPayload


def user():
    return TokenPayload(
        sub="owner", username="owner", roles=["user"], permissions=["session:read", "chat:write"]
    )


def assistant(**changes):
    from src.infra.utils.datetime import utc_now

    return Assistant(
        id="assistant",
        user_id="owner",
        session_id="123456789012345678901234",
        revision=1,
        status="active",
        name="Helper",
        created_at=utc_now(),
        updated_at=utc_now(),
        **changes,
    )


async def test_missing_or_foreign_assistant_returns_not_found():
    from src.infra.assistant.service import AssistantService

    store = SimpleNamespace(get=AsyncMock(return_value=None))
    with pytest.raises(AppError) as caught:
        await AssistantService(store=store).get(user(), "foreign")
    assert caught.value.error_code == ErrorCode.NOT_FOUND
    store.get.assert_awaited_once_with("owner", "foreign")


async def test_stale_update_cannot_overwrite_new_configuration():
    from src.infra.assistant.service import AssistantService

    store = SimpleNamespace(
        get=AsyncMock(return_value=assistant()), update=AsyncMock(return_value=None)
    )
    service = AssistantService(store=store)
    service.validate_configuration = AsyncMock()
    with pytest.raises(AppError) as caught:
        await service.update(user(), "assistant", AssistantUpdate(name="New", revision=1))
    assert caught.value.error_code == ErrorCode.CONFLICT


async def test_creation_validates_before_persisting():
    from src.infra.assistant.service import AssistantService

    store = SimpleNamespace(create=AsyncMock())
    service = AssistantService(store=store)
    service.validate_configuration = AsyncMock(side_effect=AppError(ErrorCode.FORBIDDEN))
    with pytest.raises(AppError):
        await service.create(user(), AssistantCreate(name="Helper"))
    store.create.assert_not_awaited()


async def test_foreign_project_is_not_accepted(monkeypatch):
    from src.infra.assistant.service import AssistantService
    from src.infra.folder.storage import ProjectStorage

    lookup = AsyncMock(return_value=None)
    monkeypatch.setattr(ProjectStorage, "get_by_id", lookup)
    with pytest.raises(AppError) as caught:
        await AssistantService().validate_configuration(
            user(), AssistantCreate(name="Helper", project_id="foreign")
        )
    assert caught.value.error_code == ErrorCode.PROJECT_NOT_FOUND
    lookup.assert_awaited_once_with("foreign", "owner")


async def test_request_uses_current_configuration_not_client_values(monkeypatch):
    from src.infra.assistant.service import prepare_assistant_request
    from src.infra.folder.storage import ProjectStorage
    from src.kernel.schemas.agent import AgentRequest

    monkeypatch.setattr(
        ProjectStorage, "get_by_id", AsyncMock(return_value=SimpleNamespace(workspace=None))
    )
    value = assistant(model_id="chosen", project_id="project", persona_preset_id="persona")
    service = SimpleNamespace(
        store=SimpleNamespace(for_session=AsyncMock(return_value=value)),
        validate_configuration=AsyncMock(),
    )
    request = AgentRequest(
        message="hello",
        session_id=value.session_id,
        agent_options={
            "model_id": "other",
            "model": "other",
            "_resolved_model_config": {"api_key": "secret"},
        },
    )
    found = await prepare_assistant_request(
        request, user(), {"assistant_id": value.id}, service=service
    )
    assert found == value
    assert request.persona_preset_id == "persona"
    assert request.project_id == "project"
    assert request.agent_options == {"model_id": "chosen"}


@pytest.mark.parametrize("status", ["paused", "archived"])
async def test_inactive_assistant_cannot_start_work_through_chat(status):
    from src.infra.assistant.service import prepare_assistant_request
    from src.kernel.schemas.agent import AgentRequest

    value = assistant().model_copy(update={"status": status})
    service = SimpleNamespace(
        store=SimpleNamespace(for_session=AsyncMock(return_value=value)),
        validate_configuration=AsyncMock(),
    )
    with pytest.raises(AppError) as caught:
        await prepare_assistant_request(
            AgentRequest(message="go", session_id=value.session_id),
            user(),
            {"assistant_id": value.id},
            service=service,
        )
    assert caught.value.error_code == ErrorCode.CONFLICT


async def test_copying_assistant_metadata_does_not_grant_identity():
    from src.infra.assistant.service import prepare_assistant_request
    from src.kernel.schemas.agent import AgentRequest

    service = SimpleNamespace(
        store=SimpleNamespace(for_session=AsyncMock(return_value=assistant())),
        validate_configuration=AsyncMock(),
    )
    with pytest.raises(AppError) as caught:
        await prepare_assistant_request(
            AgentRequest(message="go", session_id="forged"),
            user(),
            {"assistant_id": "assistant"},
            service=service,
        )
    assert caught.value.error_code == ErrorCode.FORBIDDEN


async def test_open_uses_atomic_session_creation_and_keeps_existing_history():
    from bson import ObjectId

    from src.infra.assistant.service import AssistantService

    value = assistant()
    document = {
        "_id": ObjectId(value.session_id),
        "user_id": "owner",
        "name": "Helper",
        "metadata": {"assistant_id": "assistant"},
        "created_at": value.created_at,
        "updated_at": value.updated_at,
        "is_active": True,
    }
    collection = SimpleNamespace(find_one_and_update=AsyncMock(return_value=document))
    sessions = SimpleNamespace(collection=collection, ensure_indexes_if_needed=AsyncMock())
    service = AssistantService(
        store=SimpleNamespace(get=AsyncMock(return_value=value)), sessions=sessions
    )
    service.validate_configuration = AsyncMock()
    first = await service.open_conversation(user(), "assistant")
    second = await service.open_conversation(user(), "assistant")
    assert first.id == second.id == value.session_id
    query, update = collection.find_one_and_update.call_args.args
    assert query == {
        "_id": ObjectId(value.session_id),
        "user_id": "owner",
        "metadata.assistant_id": "assistant",
    }
    assert set(update) == {"$setOnInsert"}
    assert service.validate_configuration.await_count == 2


async def test_clone_does_not_inherit_coordinator_identity():
    from src.kernel.schemas.session import clone_session_metadata

    result = clone_session_metadata({"assistant_id": "private", "project_id": "project"})
    assert "assistant_id" not in result
    assert result["project_id"] == "project"


async def test_assistant_environment_uses_server_configuration():
    from src.infra.assistant.service import prepare_assistant_request
    from src.kernel.schemas.agent import AgentRequest

    value = assistant(sandbox="cloud")
    service = SimpleNamespace(
        store=SimpleNamespace(for_session=AsyncMock(return_value=value)),
        validate_configuration=AsyncMock(),
    )
    request = AgentRequest(
        message="hello",
        session_id=value.session_id,
        agent_options={"sandbox": "local", "sandbox_machine_id": "forged"},
    )
    await prepare_assistant_request(request, user(), {}, service=service)
    assert request.agent_options == {"sandbox": "cloud"}


def test_local_environment_requires_a_picker_receipt():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        AssistantCreate(name="Local", sandbox="local")
    with pytest.raises(ValidationError):
        AssistantCreate(
            name="Cloud",
            sandbox="cloud",
            workspace={"id": "local-" + "a" * 32, "machineId": "machine", "path": "/work"},
        )


def test_local_environment_round_trips_its_receipt():
    value = AssistantCreate(
        name="Local",
        sandbox="local",
        workspace={"id": "local-" + "a" * 32, "machineId": "machine", "path": "/work"},
    )
    assert AssistantCreate.model_validate(value.model_dump(by_alias=True)) == value


async def test_changed_project_default_does_not_reuse_previous_environment(monkeypatch):
    import json

    from src.infra.assistant.service import prepare_assistant_request
    from src.infra.folder.storage import ProjectStorage
    from src.kernel.schemas.agent import AgentRequest
    from src.kernel.schemas.project import ProjectWorkspace

    selection = ProjectWorkspace(id="local-" + "b" * 32, machineId="new-machine", path="/new")
    monkeypatch.setattr(
        ProjectStorage, "get_by_id", AsyncMock(return_value=SimpleNamespace(workspace=selection))
    )
    value = assistant(project_id="new-project")
    service = SimpleNamespace(
        store=SimpleNamespace(for_session=AsyncMock(return_value=value)),
        validate_configuration=AsyncMock(),
    )
    request = AgentRequest(message="new work", session_id=value.session_id)
    await prepare_assistant_request(
        request, user(), {"agent_options": {"sandbox": "cloud"}}, service=service
    )
    assert request.agent_options["sandbox"] == "local"
    assert request.agent_options["sandbox_machine_id"] == "new-machine"
    assert json.loads(request.agent_options["sandbox_workspace"])["id"] == selection.id


async def test_assistant_team_must_belong_to_the_authenticated_owner(monkeypatch):
    from src.infra.assistant.service import AssistantService
    from src.infra.team.storage import TeamStorage

    lookup = AsyncMock(return_value=None)
    monkeypatch.setattr(TeamStorage, "get_team", lookup)
    with pytest.raises(AppError) as caught:
        await AssistantService().validate_configuration(
            user(), AssistantCreate(name="Group", team_id="foreign")
        )
    assert caught.value.error_code is ErrorCode.TEAM_NOT_FOUND
    lookup.assert_awaited_once_with("foreign", owner_user_id="owner")


def test_team_assistant_uses_the_existing_coordinator_and_rejects_conflicting_persona():
    from pydantic import ValidationError

    from src.infra.assistant.service import assistant_agent

    assert assistant_agent(AssistantCreate(name="Solo")) == "search"
    assert assistant_agent(AssistantCreate(name="Group", team_id="team")) == "team"
    with pytest.raises(ValidationError):
        AssistantCreate(name="Conflicting", team_id="team", persona_preset_id="role")


async def test_scheduled_assistant_child_uses_canonical_target_and_rejects_retargeting(monkeypatch):
    from src.infra.assistant.memory import session_assistant_partition
    from src.infra.assistant.service import AssistantService, prepare_assistant_request
    from src.infra.scheduler import storage
    from src.infra.session.manager import SessionManager
    from src.kernel.schemas.agent import AgentRequest

    value = assistant(model_id="chosen")
    task = SimpleNamespace(
        id="schedule",
        owner_id="owner",
        execution_mode="conversation",
        target_session_id=value.session_id,
    )
    metadata = {"scheduled_task_id": "schedule", "scheduled_target_session_id": value.session_id}
    session = SimpleNamespace(user_id="owner", metadata=metadata)
    monkeypatch.setattr(SessionManager, "get_session", AsyncMock(return_value=session))
    monkeypatch.setattr(
        storage,
        "get_scheduled_task_storage",
        lambda: SimpleNamespace(get_task=AsyncMock(return_value=task)),
    )
    monkeypatch.setattr(
        "src.infra.assistant.service.AssistantStore.for_session", AsyncMock(return_value=value)
    )
    monkeypatch.setattr(AssistantService, "validate_configuration", AsyncMock())
    request = AgentRequest(
        message="Check", session_id="sch_conversation_schedule", agent_options={"model_id": "wrong"}
    )
    assert await prepare_assistant_request(request, user(), metadata) == value
    assert request.agent_options["model_id"] == "chosen"
    assert (
        await session_assistant_partition(request.session_id, "owner", metadata)
        == "assistant-memory:assistant"
    )
    task.target_session_id = "other-conversation"
    with pytest.raises(AppError):
        await prepare_assistant_request(request, user(), metadata)
