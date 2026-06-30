from src.kernel.extensions import (
    WORKFLOW_PLUGIN_ID,
    PluginResourceType,
    PluginRuntime,
    build_workflow_plugin_manifest,
)
from src.kernel.types import Permission


def _workflow_manifest():
    return build_workflow_plugin_manifest()


def test_workflow_manifest_declares_agent_team_sibling_app_entry() -> None:
    manifest = _workflow_manifest()

    assert manifest.name == "workflowPlugin.plugin.name"
    assert manifest.description == "workflowPlugin.plugin.description"

    tabs = {tab.tab: tab for tab in manifest.frontend.app_tabs}
    panels = {panel.tab: panel for panel in manifest.frontend.app_panels}

    assert list(tabs) == ["workflows", "workflows-editor", "workflows-run"]
    assert tabs["workflows"].id == "workflow:workflows-tab"
    assert tabs["workflows"].path == "/workflows"
    assert tabs["workflows"].panel == "workflow:workflows-panel"
    assert tabs["workflows"].insert_after == "agent-team"
    assert tabs["workflows"].permissions == [Permission.WORKFLOW_READ.value]
    assert tabs["workflows-editor"].path == "/workflows/:workflowId/editor"
    assert tabs["workflows-editor"].panel == "workflow:workflow-editor-panel"
    assert tabs["workflows-editor"].insert_after == "workflows"
    assert tabs["workflows-run"].path == "/workflows/:workflowId/runs/:runId"
    assert tabs["workflows-run"].panel == "workflow:workflow-run-panel"
    assert tabs["workflows-run"].insert_after == "workflows-editor"

    assert panels["workflows"].renderer == "workflow.WorkflowPanel"
    assert panels["workflows-editor"].renderer == "workflow.WorkflowPanel"
    assert panels["workflows-run"].renderer == "workflow.WorkflowPanel"

    assert manifest.frontend.sidebar_items[0].id == "workflow:workflows-nav"
    assert manifest.frontend.sidebar_items[0].path == "/workflows"
    assert manifest.frontend.sidebar_items[0].icon == "Workflow"
    assert manifest.frontend.sidebar_items[0].permissions == [
        Permission.WORKFLOW_READ.value
    ]


def test_workflow_manifest_declares_workflow_owned_call_boundaries() -> None:
    manifest = _workflow_manifest()

    tools = {tool.name: tool for tool in manifest.tools}
    assert list(tools) == [
        "workflow_run",
        "workflow_list",
        "workflow_get_schema",
        "workflow_get_run",
        "workflow_resume",
    ]
    assert tools["workflow_run"].required_permissions == [
        Permission.WORKFLOW_RUN.value
    ]
    assert tools["workflow_run"].legacy_ids == ["workflow_run"]
    assert tools["workflow_list"].legacy_ids == ["workflow_list"]
    assert tools["workflow_get_schema"].legacy_ids == ["workflow_get_schema"]
    assert tools["workflow_get_run"].legacy_ids == ["workflow_get_run"]
    assert tools["workflow_resume"].required_permissions == [
        Permission.WORKFLOW_RUN.value
    ]
    assert tools["workflow_resume"].legacy_ids == ["workflow_resume"]
    assert manifest.routers[0].tags == ["workflowPlugin.nav.label"]

    chat_option = manifest.frontend.chat_input_options[0]
    chat_panel = manifest.frontend.chat_input_panels[0]
    assert chat_option.id == "workflow:select-workflow"
    assert chat_option.panel == "workflow:workflow-picker"
    assert chat_option.selected_renderer == "workflow.SelectedWorkflowChip"
    assert chat_option.shortcut == "mod+w"
    assert chat_option.option_binding is not None
    assert chat_option.option_binding.plugin_id == WORKFLOW_PLUGIN_ID
    assert chat_option.option_binding.key == "SELECTED_WORKFLOW_ID"
    assert chat_option.option_binding.scope == "session"
    assert chat_panel.id == "workflow:workflow-picker"
    assert chat_panel.renderer == "workflow.WorkflowPickerModal"
    assert chat_panel.create_path == "/workflows?create=blank"
    assert chat_panel.manage_path == "/workflows"


def test_workflow_manifest_declares_storage_indexes_created_at_startup() -> None:
    runtime = PluginRuntime([build_workflow_plugin_manifest()])

    indexes_by_id = {
        resource.resource_id: resource.metadata
        for resource in runtime.resource_ledger.list(
            plugin_id=WORKFLOW_PLUGIN_ID,
            resource_type=PluginResourceType.DB_INDEX,
        )
    }

    assert indexes_by_id == {
        "workflow_definitions.workflow_id_unique": {
            "collection": "workflow_definitions",
            "fields": "workflow_id",
            "unique": "true",
        },
        "workflow_definitions.owner_updated_at_lookup": {
            "collection": "workflow_definitions",
            "fields": "owner_user_id,updated_at:-1",
        },
        "workflow_versions.version_id_unique": {
            "collection": "workflow_versions",
            "fields": "version_id",
            "unique": "true",
        },
        "workflow_versions.workflow_version_lookup": {
            "collection": "workflow_versions",
            "fields": "workflow_id,version_number",
        },
        "workflow_runs.run_id_unique": {
            "collection": "workflow_runs",
            "fields": "run_id",
            "unique": "true",
        },
        "workflow_runs.workflow_started_at_lookup": {
            "collection": "workflow_runs",
            "fields": "workflow_id,started_at:-1",
        },
        "workflow_run_events.run_sequence_lookup": {
            "collection": "workflow_run_events",
            "fields": "run_id,sequence",
        },
        "workflow_credentials.credential_id_unique": {
            "collection": "workflow_credentials",
            "fields": "credential_id",
            "unique": "true",
        },
        "workflow_credentials.owner_ref_unique": {
            "collection": "workflow_credentials",
            "fields": "owner_user_id,ref",
            "unique": "true",
        },
        "workflow_credentials.owner_updated_at_lookup": {
            "collection": "workflow_credentials",
            "fields": "owner_user_id,updated_at:-1",
        },
    }
