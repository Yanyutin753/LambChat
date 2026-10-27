import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from src.infra.backend.workspace_selection import resolve_workspace_options
from src.kernel.errors import AppError, ErrorCode
from src.kernel.schemas.project import ProjectWorkspace

WORKSPACE = {"id": "local-" + "a" * 32, "machineId": "mac", "path": "/repo"}
BOUND = {
    "sandbox": "local",
    "sandbox_machine_id": "mac",
    "sandbox_workspace": json.dumps(WORKSPACE),
}


@pytest.fixture
def projects():
    storage = AsyncMock()
    storage.get_by_id.return_value = SimpleNamespace(workspace=ProjectWorkspace(**WORKSPACE))
    with patch("src.infra.folder.storage.get_project_storage", return_value=storage):
        yield storage


async def test_new_project_chat_inherits_owned_workspace_without_mutating_options(projects):
    options = {"model_id": "model"}
    result = await resolve_workspace_options(options, "owner", project_id="project")
    assert result == {**BOUND, **options}
    assert options == {"model_id": "model"}
    projects.get_by_id.assert_awaited_once_with("project", "owner")


@pytest.mark.parametrize("options", [{"sandbox": "cloud"}, {"sandbox_workspace": ""}, BOUND])
async def test_explicit_workspace_choice_overrides_project_default(projects, options):
    assert await resolve_workspace_options(options, "owner", project_id="project") == options


@pytest.mark.parametrize("metadata", [{}, {"agent_options": BOUND}])
async def test_existing_chat_never_rebinds_after_project_changes(projects, metadata):
    result = await resolve_workspace_options(
        {"model_id": "model"}, "owner", project_id="changed-project", existing_metadata=metadata
    )
    assert result == {**metadata.get("agent_options", {}), "model_id": "model"}
    projects.get_by_id.assert_not_awaited()


async def test_existing_chat_explicit_cloud_does_not_carry_old_local_binding(projects):
    assert await resolve_workspace_options(
        {"sandbox": "cloud"}, "owner", existing_metadata={"agent_options": BOUND}
    ) == {"sandbox": "cloud"}


@pytest.mark.parametrize("status", ["active", "waiting_human"])
@pytest.mark.parametrize("options", [{"sandbox": "cloud"}, {**BOUND, "sandbox_workspace": ""}])
async def test_chat_submission_cannot_retarget_an_active_goal(status, options):
    with pytest.raises(AppError) as error:
        await resolve_workspace_options(
            options,
            "owner",
            existing_metadata={"agent_options": BOUND, "persistent_goal_status": status},
        )
    assert error.value.error_code == ErrorCode.CONFLICT


@pytest.mark.parametrize(
    "options", [{}, {**BOUND, "sandbox_workspace": json.dumps(WORKSPACE, separators=(",", ":"))}]
)
async def test_goal_continuation_accepts_omitted_or_equivalent_binding(options):
    result = await resolve_workspace_options(
        options,
        "owner",
        existing_metadata={"agent_options": BOUND, "persistent_goal_status": "active"},
    )
    assert json.loads(result["sandbox_workspace"]) == WORKSPACE


async def test_missing_or_foreign_project_is_rejected(projects):
    projects.get_by_id.return_value = None
    with pytest.raises(AppError):
        await resolve_workspace_options({}, "owner", project_id="foreign")


async def test_temporary_chat_does_not_resolve_a_project(projects):
    assert await resolve_workspace_options({}, "owner") == {}
    projects.get_by_id.assert_not_awaited()


async def test_session_creation_persists_workspace_snapshot(projects):
    from src.infra.session.manager import SessionManager
    from src.kernel.schemas.session import SessionCreate

    manager = SessionManager()
    manager.storage = AsyncMock()
    data = SessionCreate(metadata={"project_id": "project", "agent_options": {"model_id": "m"}})
    await manager.create_session(data, "owner")
    saved = manager.storage.create.call_args.args[0]
    assert saved.metadata["agent_options"] == {**BOUND, "model_id": "m"}
    assert data.metadata["agent_options"] == {"model_id": "m"}
