import pytest

from src.infra.extensions import InMemoryPluginSettingsStorage, PluginSettingsService
from src.infra.extensions.scoped_options import (
    plugin_options_with_settings,
    scoped_option_definition,
    scoped_plugin_is_executable,
    sync_plugin_options_to_settings,
    validate_scoped_plugin_option_value,
)
from src.kernel.extensions import PluginRuntime, build_agent_team_plugin_manifest


@pytest.mark.asyncio
async def test_scoped_options_helpers_cover_project_session_channel_and_scheduled_task() -> None:
    manifest = build_agent_team_plugin_manifest()
    runtime = PluginRuntime([manifest], core_dependencies=())
    storage = InMemoryPluginSettingsStorage()
    service = PluginSettingsService(storage=storage)

    assert scoped_option_definition(
        runtime,
        scope="project",
        plugin_id="agent_team",
        key="DEFAULT_TEAM_ID",
    ).key == "DEFAULT_TEAM_ID"
    assert scoped_option_definition(
        runtime,
        scope="session",
        plugin_id="agent_team",
        key="SELECTED_TEAM_ID",
    ).key == "SELECTED_TEAM_ID"
    assert scoped_option_definition(
        runtime,
        scope="channel",
        plugin_id="agent_team",
        key="SELECTED_TEAM_ID",
    ).key == "SELECTED_TEAM_ID"
    assert scoped_option_definition(
        runtime,
        scope="scheduled_task",
        plugin_id="agent_team",
        key="SELECTED_TEAM_ID",
    ).key == "SELECTED_TEAM_ID"

    await sync_plugin_options_to_settings(
        runtime=runtime,
        service=service,
        scope="session",
        subject_id="session-1",
        plugin_options={"agent_team": {"SELECTED_TEAM_ID": "team-session"}},
        updated_by="user-1",
    )
    await sync_plugin_options_to_settings(
        runtime=runtime,
        service=service,
        scope="project",
        subject_id="project-1",
        plugin_options={"agent_team": {"DEFAULT_TEAM_ID": "team-project"}},
        updated_by="user-1",
    )

    session_options = await plugin_options_with_settings(
        runtime=runtime,
        service=service,
        scope="session",
        subject_id="session-1",
        plugin_options={},
    )
    project_options = await plugin_options_with_settings(
        runtime=runtime,
        service=service,
        scope="project",
        subject_id="project-1",
        plugin_options={},
    )

    assert session_options == {"agent_team": {"SELECTED_TEAM_ID": "team-session"}}
    assert project_options == {"agent_team": {"DEFAULT_TEAM_ID": "team-project"}}
    assert scoped_plugin_is_executable(runtime, "agent_team") is True


def test_scoped_option_value_validation_reuses_manifest_type_contract() -> None:
    runtime = PluginRuntime([build_agent_team_plugin_manifest()], core_dependencies=())
    option = scoped_option_definition(
        runtime,
        scope="project",
        plugin_id="agent_team",
        key="DEFAULT_TEAM_ID",
    )

    assert validate_scoped_plugin_option_value(option, "team-1") == "team-1"
    with pytest.raises(ValueError):
        validate_scoped_plugin_option_value(option, 123)
