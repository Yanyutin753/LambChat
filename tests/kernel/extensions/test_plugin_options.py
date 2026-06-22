import pytest

from src.kernel.extensions import PluginManifest, PluginRuntime, build_agent_team_plugin_manifest
from src.kernel.extensions.plugin_options import (
    agent_uses_agent_team_options,
    declared_plugin_options_from_metadata,
    declared_session_options_from_project_defaults,
    filter_declared_plugin_options,
    plugin_id_for_agent,
    plugin_option_from_metadata,
    plugin_options_from_metadata,
    plugin_session_option_visible_for_agent,
    plugin_session_options_suppress_core_persona,
    selected_agent_team_id_from_metadata,
    with_plugin_option,
)


def test_plugin_options_from_metadata_returns_normalized_copy() -> None:
    metadata = {
        "plugin_options": {
            "agent_team": {"SELECTED_TEAM_ID": "team-1"},
            "bad": "not-a-dict",
        }
    }

    options = plugin_options_from_metadata(metadata)
    options["agent_team"]["SELECTED_TEAM_ID"] = "changed"

    assert plugin_options_from_metadata(metadata) == {
        "agent_team": {"SELECTED_TEAM_ID": "team-1"}
    }


def test_with_plugin_option_writes_and_clears_plugin_namespace() -> None:
    metadata = with_plugin_option(
        {"existing": True},
        plugin_id="agent_team",
        key="SELECTED_TEAM_ID",
        value="team-1",
    )

    assert plugin_option_from_metadata(
        metadata,
        plugin_id="agent_team",
        key="SELECTED_TEAM_ID",
    ) == "team-1"

    cleared = with_plugin_option(
        metadata,
        plugin_id="agent_team",
        key="SELECTED_TEAM_ID",
        value=None,
    )

    assert cleared == {"existing": True, "plugin_options": {}}


def test_selected_agent_team_id_prefers_plugin_option_and_keeps_legacy_fallback() -> None:
    assert selected_agent_team_id_from_metadata(
        {
            "team_id": "legacy-team",
            "plugin_options": {"agent_team": {"SELECTED_TEAM_ID": "plugin-team"}},
        }
    ) == "plugin-team"
    assert selected_agent_team_id_from_metadata({"team_id": "legacy-team"}) == "legacy-team"


def test_filter_declared_plugin_options_keeps_only_manifest_owned_scope_keys() -> None:
    manifest = PluginManifest(
        id="workflow_runner",
        name="Workflow Runner",
        version="1.0.0",
        api_version="v1",
        permissions=["workflow_runner:read"],
        settings=[
            {
                "key": "SELECTED_WORKFLOW_ID",
                "type": "string",
                "scope": "session",
            },
            {
                "key": "DEFAULT_WORKFLOW_ID",
                "type": "string",
                "scope": "project",
            },
        ],
        frontend={
            "session_options": [
                {
                    "key": "SELECTED_WORKFLOW_ID",
                    "type": "string",
                    "label": "workflow.selected",
                }
            ],
            "project_options": [
                {
                    "key": "DEFAULT_WORKFLOW_ID",
                    "type": "string",
                    "label": "workflow.default",
                }
            ],
        },
    )
    runtime = PluginRuntime([manifest])
    metadata = {
        "plugin_options": {
            "workflow_runner": {
                "SELECTED_WORKFLOW_ID": "workflow-1",
                "DEFAULT_WORKFLOW_ID": "project-only",
                "UNDECLARED": "drop-me",
            },
            "missing_plugin": {"ANY": "drop-me"},
        }
    }

    assert filter_declared_plugin_options(runtime, metadata, scope="session") == {
        "workflow_runner": {"SELECTED_WORKFLOW_ID": "workflow-1"}
    }


def test_filter_declared_plugin_options_keeps_compat_without_runtime() -> None:
    metadata = {"plugin_options": {"future_plugin": {"ANY": "kept"}}}

    assert filter_declared_plugin_options(None, metadata, scope="session") == {
        "future_plugin": {"ANY": "kept"}
    }


def test_declared_plugin_options_imports_manifest_legacy_payload_keys() -> None:
    manifest = PluginManifest(
        id="workflow_runner",
        name="Workflow Runner",
        version="1.0.0",
        api_version="v1",
        permissions=["workflow_runner:read"],
        settings=[
            {
                "key": "SELECTED_WORKFLOW_ID",
                "type": "string",
                "scope": "scheduled_task",
            }
        ],
        frontend={
            "scheduled_task_options": [
                {
                    "key": "SELECTED_WORKFLOW_ID",
                    "type": "string",
                    "label": "workflow.selected",
                    "legacy_payload_keys": ["workflow_id"],
                }
            ]
        },
    )
    runtime = PluginRuntime([manifest])

    assert declared_plugin_options_from_metadata(
        runtime,
        {"workflow_id": "workflow-1"},
        scope="scheduled_task",
    ) == {"workflow_runner": {"SELECTED_WORKFLOW_ID": "workflow-1"}}


def test_declared_session_options_from_project_defaults_uses_manifest_projection() -> None:
    manifest = PluginManifest(
        id="workflow_runner",
        name="Workflow Runner",
        version="1.0.0",
        api_version="v1",
        settings=[
            {"key": "DEFAULT_WORKFLOW_ID", "type": "string", "scope": "project"},
            {"key": "SELECTED_WORKFLOW_ID", "type": "string", "scope": "session"},
        ],
        frontend={
            "project_options": [
                {
                    "key": "DEFAULT_WORKFLOW_ID",
                    "type": "string",
                    "label": "workflow.default",
                    "applies_to_session_key": "SELECTED_WORKFLOW_ID",
                }
            ],
            "session_options": [
                {
                    "key": "SELECTED_WORKFLOW_ID",
                    "type": "string",
                    "label": "workflow.selected",
                }
            ],
        },
    )

    assert declared_session_options_from_project_defaults(
        PluginRuntime([manifest]),
        {"plugin_options": {"workflow_runner": {"DEFAULT_WORKFLOW_ID": "workflow-1"}}},
    ) == {"workflow_runner": {"SELECTED_WORKFLOW_ID": "workflow-1"}}


def test_project_option_projection_requires_declared_session_option() -> None:
    with pytest.raises(ValueError, match="project:DEFAULT_WORKFLOW_ID->SELECTED_WORKFLOW_ID"):
        PluginManifest(
            id="workflow_runner",
            name="Workflow Runner",
            version="1.0.0",
            api_version="v1",
            settings=[
                {"key": "DEFAULT_WORKFLOW_ID", "type": "string", "scope": "project"},
            ],
            frontend={
                "project_options": [
                    {
                        "key": "DEFAULT_WORKFLOW_ID",
                        "type": "string",
                        "label": "workflow.default",
                        "applies_to_session_key": "SELECTED_WORKFLOW_ID",
                    }
                ]
            },
        )


def test_declared_plugin_options_imports_legacy_key_even_when_visibility_context_missing() -> None:
    runtime = PluginRuntime([build_agent_team_plugin_manifest()])

    assert declared_plugin_options_from_metadata(
        runtime,
        {"team_id": "legacy-team"},
        scope="channel",
    ) == {"agent_team": {"SELECTED_TEAM_ID": "legacy-team"}}


def test_declared_plugin_options_explicit_legacy_none_clears_existing_value() -> None:
    runtime = PluginRuntime([build_agent_team_plugin_manifest()])

    metadata = {
        "team_id": None,
        "plugin_options": {"agent_team": {"SELECTED_TEAM_ID": "team-old"}},
    }

    assert declared_plugin_options_from_metadata(
        runtime,
        metadata,
        scope="channel",
        legacy_payload_keys_provided={"team_id"},
    ) == {}


def test_declared_plugin_options_saved_plugin_value_wins_over_legacy_payload_by_default() -> None:
    runtime = PluginRuntime([build_agent_team_plugin_manifest()])
    metadata = {
        "team_id": "legacy-team",
        "plugin_options": {"agent_team": {"SELECTED_TEAM_ID": "plugin-team"}},
    }

    assert declared_plugin_options_from_metadata(
        runtime,
        metadata,
        scope="channel",
    ) == {"agent_team": {"SELECTED_TEAM_ID": "plugin-team"}}


def test_declared_plugin_options_can_filter_non_executable_plugins() -> None:
    runtime = PluginRuntime([build_agent_team_plugin_manifest()])
    runtime.disable_plugin("agent_team")

    assert declared_plugin_options_from_metadata(
        runtime,
        {"team_id": "team-1"},
        scope="scheduled_task",
        agent_id="team",
    ) == {"agent_team": {"SELECTED_TEAM_ID": "team-1"}}
    assert declared_plugin_options_from_metadata(
        runtime,
        {"team_id": "team-1"},
        scope="scheduled_task",
        agent_id="team",
        executable_only=True,
    ) == {}


def test_plugin_id_for_agent_uses_runtime_declarations() -> None:
    runtime = PluginRuntime([build_agent_team_plugin_manifest()])

    assert plugin_id_for_agent("team", runtime=runtime) == "agent_team"
    assert agent_uses_agent_team_options("team", runtime=runtime) is True
    assert plugin_id_for_agent("search", runtime=runtime) is None


def test_agent_team_option_agent_check_falls_back_to_builtin_manifests() -> None:
    assert agent_uses_agent_team_options("team") is True
    assert agent_uses_agent_team_options("search") is False


def test_plugin_session_option_visible_for_agent_uses_manifest_visible_when() -> None:
    manifest = build_agent_team_plugin_manifest()

    assert plugin_session_option_visible_for_agent(
        manifest,
        "SELECTED_TEAM_ID",
        "team",
    ) is True
    assert plugin_session_option_visible_for_agent(
        manifest,
        "SELECTED_TEAM_ID",
        "search",
    ) is False
    assert plugin_session_option_visible_for_agent(
        manifest,
        "MISSING",
        "team",
    ) is False


def test_plugin_session_options_suppress_core_persona_from_manifest_contract() -> None:
    manifest = PluginManifest(
        id="workflow_runner",
        name="Workflow Runner",
        version="1.0.0",
        api_version="v1",
        settings=[
            {"key": "SELECTED_WORKFLOW_ID", "type": "string", "scope": "session"},
        ],
        agents=[
            {
                "id": "workflow",
                "module": "plugins.workflow.agent.WorkflowAgent",
            }
        ],
        frontend={
            "session_options": [
                {
                    "key": "SELECTED_WORKFLOW_ID",
                    "type": "string",
                    "label": "workflow.selected",
                    "suppresses_core_persona_selector": True,
                    "legacy_payload_keys": ["workflow_id"],
                }
            ]
        },
    )
    runtime = PluginRuntime([manifest])

    assert plugin_session_options_suppress_core_persona(
        "workflow",
        {"plugin_options": {"workflow_runner": {"SELECTED_WORKFLOW_ID": "flow-1"}}},
        runtime=runtime,
    ) is True
    assert plugin_session_options_suppress_core_persona(
        "workflow",
        {"workflow_id": "flow-legacy"},
        runtime=runtime,
    ) is True
    assert plugin_session_options_suppress_core_persona(
        "search",
        {"plugin_options": {"workflow_runner": {"SELECTED_WORKFLOW_ID": "flow-1"}}},
        runtime=runtime,
    ) is False


def test_plugin_session_options_can_target_core_agent_with_visible_when() -> None:
    manifest = PluginManifest(
        id="workflow_runner",
        name="Workflow Runner",
        version="1.0.0",
        api_version="v1",
        settings=[
            {"key": "SELECTED_WORKFLOW_ID", "type": "string", "scope": "session"},
        ],
        frontend={
            "session_options": [
                {
                    "key": "SELECTED_WORKFLOW_ID",
                    "type": "string",
                    "label": "workflow.selected",
                    "suppresses_core_persona_selector": True,
                    "visible_when": {"agent_id": "search"},
                }
            ]
        },
    )

    assert plugin_session_options_suppress_core_persona(
        "search",
        {"plugin_options": {"workflow_runner": {"SELECTED_WORKFLOW_ID": "flow-1"}}},
        runtime=PluginRuntime([manifest]),
    ) is True
