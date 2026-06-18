import subprocess
import sys
import textwrap

from src.kernel.extensions import (
    FEEDBACK_PLUGIN_ID,
    PluginDryRunAction,
    PluginResourceType,
    PluginRuntime,
    PluginRuntimeStatus,
    assess_feedback_plugin_migration,
    build_feedback_plugin_manifest,
    build_uninstall_dry_run,
    required_migration_gate_ids,
)
from src.kernel.types import Permission


def test_feedback_static_plugin_boundary_adapts_legacy_implementation() -> None:
    from src.api.routes import feedback as legacy_routes
    from src.infra.tool import feedback_tool as legacy_tools
    from src.plugins.feedback import lifecycle, routes, tools

    assert sys.modules["src.api.routes.feedback"] is routes
    assert sys.modules["src.infra.tool.feedback_tool"] is tools
    assert routes.router is legacy_routes.router
    assert routes.get_feedback_manager is legacy_routes.get_feedback_manager
    assert lifecycle.close_feedback_manager is legacy_routes.close_feedback_manager
    assert legacy_tools.get_feedback_tools is tools.get_feedback_tools
    assert [tool.name for tool in tools.get_feedback_tools()] == ["feedback.summary"]


def test_feedback_legacy_import_order_does_not_cycle() -> None:
    script = textwrap.dedent(
        """
        import sys
        from src.api.routes import feedback as legacy_routes
        from src.infra.tool import feedback_tool as legacy_tools
        from src.plugins.feedback import routes, tools
        from src.kernel.extensions import build_feedback_plugin_manifest

        manifest = build_feedback_plugin_manifest()
        assert sys.modules["src.api.routes.feedback"] is routes
        assert sys.modules["src.infra.tool.feedback_tool"] is tools
        assert legacy_routes is routes
        assert legacy_tools is tools
        assert manifest.routers[0].module == "src.plugins.feedback.routes"
        assert manifest.tools[0].module == "src.plugins.feedback.tools"
        """
    )

    subprocess.run([sys.executable, "-c", script], check=True)


def test_feedback_plugin_manifest_preserves_legacy_api_and_permissions() -> None:
    manifest = build_feedback_plugin_manifest()

    assert manifest.id == FEEDBACK_PLUGIN_ID
    assert manifest.api_version == "v1"
    assert manifest.routers[0].prefix == "/api/feedback"
    assert manifest.routers[0].module == "src.plugins.feedback.routes"
    assert manifest.routers[0].tags == ["Feedback"]
    assert [(tool.name, tool.module) for tool in manifest.tools] == [
        ("feedback.summary", "src.plugins.feedback.tools")
    ]
    assert [(hook.name, hook.module, hook.phase) for hook in manifest.lifespan_hooks] == [
        (
            "feedback:shutdown",
            "src.plugins.feedback.lifecycle:close_feedback_manager",
            "shutdown",
        )
    ]
    assert manifest.tools[0].required_permissions == [Permission.FEEDBACK_READ.value]
    assert manifest.declared_permissions() == [
        Permission.FEEDBACK_WRITE.value,
        Permission.FEEDBACK_READ.value,
        Permission.FEEDBACK_ADMIN.value,
    ]
    assert manifest.frontend.routes == ["feedback-route"]
    assert manifest.frontend.panels == ["feedback-panel"]
    assert manifest.frontend.nav_items == ["feedback-nav"]
    assert manifest.frontend.message_actions == ["feedback:message-feedback"]


def test_feedback_plugin_manifest_is_runtime_executable() -> None:
    runtime = PluginRuntime([build_feedback_plugin_manifest()])

    state = runtime.get_state(FEEDBACK_PLUGIN_ID)

    assert state is not None
    assert state.status is PluginRuntimeStatus.ENABLED
    assert state.issues == []
    assert [(route.plugin_id, route.name, route.prefix) for route in runtime.routes()] == [
        (FEEDBACK_PLUGIN_ID, "feedback-api", "/api/feedback")
    ]
    assert [(tool.plugin_id, tool.name) for tool in runtime.tools()] == [
        (FEEDBACK_PLUGIN_ID, "feedback.summary")
    ]
    assert Permission.FEEDBACK_READ.value in runtime.permissions()


def test_feedback_plugin_disable_hides_executable_contributions_but_keeps_ledger() -> None:
    runtime = PluginRuntime([build_feedback_plugin_manifest()])

    runtime.disable_plugin(FEEDBACK_PLUGIN_ID)

    assert runtime.get_state(FEEDBACK_PLUGIN_ID).status is PluginRuntimeStatus.DISABLED
    assert runtime.routes() == []
    assert runtime.tools() == []
    assert runtime.lifecycle_hooks() == []
    assert runtime.resource_ledger.get(
        plugin_id=FEEDBACK_PLUGIN_ID,
        resource_type=PluginResourceType.MESSAGE_ACTION,
        resource_id="feedback:message-feedback",
    ) is not None


def test_feedback_plugin_resources_enter_ledger() -> None:
    runtime = PluginRuntime([build_feedback_plugin_manifest()])

    resources = runtime.resource_ledger.list(plugin_id=FEEDBACK_PLUGIN_ID)
    resource_keys = {(resource.resource_type, resource.resource_id) for resource in resources}
    message_action = runtime.resource_ledger.get(
        plugin_id=FEEDBACK_PLUGIN_ID,
        resource_type=PluginResourceType.MESSAGE_ACTION,
        resource_id="feedback:message-feedback",
    )

    assert (PluginResourceType.BACKEND_ROUTE, "feedback-api") in resource_keys
    assert (PluginResourceType.FRONTEND_ROUTE, "feedback-route") in resource_keys
    assert (PluginResourceType.PANEL, "feedback-panel") in resource_keys
    assert (PluginResourceType.NAV_ITEM, "feedback-nav") in resource_keys
    assert (PluginResourceType.MESSAGE_ACTION, "feedback:message-feedback") in resource_keys
    assert (PluginResourceType.TOOL, "feedback.summary") in resource_keys
    assert (PluginResourceType.PERMISSION, Permission.FEEDBACK_ADMIN.value) in resource_keys
    assert (PluginResourceType.DB_COLLECTION, "feedback") in resource_keys
    assert (PluginResourceType.DB_INDEX, "feedback.user_run_unique") in resource_keys
    assert message_action is not None
    assert (
        message_action.metadata["frontend_component"]
        == "frontend/src/plugins/feedback/FeedbackButtons.tsx"
    )


def test_feedback_uninstall_dry_run_keeps_user_data_and_archives_indexes() -> None:
    runtime = PluginRuntime([build_feedback_plugin_manifest()])
    dry_run = build_uninstall_dry_run(
        plugin_id=FEEDBACK_PLUGIN_ID,
        ledger=runtime.resource_ledger,
    )

    actions_by_id = {resource.resource_id: resource.action for resource in dry_run.resources}

    assert actions_by_id["feedback"] is PluginDryRunAction.KEEP
    assert actions_by_id["feedback.user_run_unique"] is PluginDryRunAction.ARCHIVE
    assert actions_by_id["feedback.summary"] is PluginDryRunAction.KEEP
    assert actions_by_id[Permission.FEEDBACK_READ.value] is PluginDryRunAction.ARCHIVE
    assert dry_run.will_delete == []
    assert dry_run.needs_manual_review == []
    assert dry_run.forbidden_to_delete == []


def test_feedback_migration_assessment_allows_first_step_with_compatibility_notes() -> None:
    assessment = assess_feedback_plugin_migration()
    evidence_by_gate = {gate.gate_id: gate for gate in assessment.gate_evidence}

    assert assessment.plugin_id == FEEDBACK_PLUGIN_ID
    assert assessment.ready_for_first_migration_step is True
    assert set(assessment.satisfied_gates) == required_migration_gate_ids()
    assert assessment.missing_gates == ()
    assert set(evidence_by_gate) == required_migration_gate_ids()
    assert all(gate.passed for gate in assessment.gate_evidence)
    assert "message action" in evidence_by_gate["plugin_resource_ledger_present"].evidence
    assert "no delete actions" in evidence_by_gate["plugin_uninstall_dry_run_present"].evidence
    assert "removes executable route" in evidence_by_gate[
        "plugin_disabled_contributions_hidden"
    ].evidence
    assert any("/api/feedback" in note for note in assessment.compatibility_notes)
    assert any("Mongo" in risk for risk in assessment.risks)
    assert not any("core route registry" in risk for risk in assessment.risks)
    assert any("shutdown cleanup" in note for note in assessment.compatibility_notes)
    assert any("src.plugins.feedback" in note for note in assessment.compatibility_notes)
