from src.kernel.extensions import (
    USAGE_REPORTS_PLUGIN_ID,
    PluginDryRunAction,
    PluginResourceType,
    PluginRuntime,
    PluginRuntimeStatus,
    build_uninstall_dry_run,
    build_usage_reports_plugin_manifest,
)
from src.kernel.types import Permission


def test_usage_reports_plugin_manifest_preserves_legacy_api_and_permissions() -> None:
    manifest = build_usage_reports_plugin_manifest()

    assert manifest.id == USAGE_REPORTS_PLUGIN_ID
    assert manifest.api_version == "v1"
    assert manifest.routers[0].prefix == "/api/usage"
    assert manifest.routers[0].module == "src.api.routes.usage"
    assert manifest.routers[0].tags == ["Usage"]
    assert manifest.tools == []
    assert manifest.declared_permissions() == [
        Permission.USAGE_READ.value,
        Permission.USAGE_ADMIN.value,
    ]
    assert manifest.frontend.routes == ["usage_reports:usage-route"]
    assert manifest.frontend.panels == ["usage_reports:usage-panel"]
    assert manifest.frontend.nav_items == ["usage_reports:usage-menu"]


def test_usage_reports_plugin_is_runtime_executable() -> None:
    runtime = PluginRuntime([build_usage_reports_plugin_manifest()])

    state = runtime.get_state(USAGE_REPORTS_PLUGIN_ID)

    assert state is not None
    assert state.status is PluginRuntimeStatus.ENABLED
    assert state.issues == []
    assert [(route.plugin_id, route.name, route.prefix) for route in runtime.routes()] == [
        (USAGE_REPORTS_PLUGIN_ID, "usage_reports-api", "/api/usage")
    ]
    assert Permission.USAGE_READ.value in runtime.permissions()


def test_usage_reports_plugin_resources_enter_ledger() -> None:
    runtime = PluginRuntime([build_usage_reports_plugin_manifest()])

    resource_keys = {
        (resource.resource_type, resource.resource_id)
        for resource in runtime.resource_ledger.list(plugin_id=USAGE_REPORTS_PLUGIN_ID)
    }

    assert (PluginResourceType.BACKEND_ROUTE, "usage_reports-api") in resource_keys
    assert (
        PluginResourceType.FRONTEND_ROUTE,
        "usage_reports:usage-route",
    ) in resource_keys
    assert (PluginResourceType.PANEL, "usage_reports:usage-panel") in resource_keys
    assert (PluginResourceType.NAV_ITEM, "usage_reports:usage-menu") in resource_keys
    assert (PluginResourceType.PERMISSION, Permission.USAGE_READ.value) in resource_keys
    assert (PluginResourceType.DB_COLLECTION, "usage_logs") in resource_keys
    assert (PluginResourceType.DB_INDEX, "usage_logs.trace_id_unique_idx") in resource_keys


def test_usage_reports_uninstall_dry_run_keeps_usage_data_and_archives_indexes() -> None:
    runtime = PluginRuntime([build_usage_reports_plugin_manifest()])
    dry_run = build_uninstall_dry_run(
        plugin_id=USAGE_REPORTS_PLUGIN_ID,
        ledger=runtime.resource_ledger,
    )
    actions_by_id = {resource.resource_id: resource.action for resource in dry_run.resources}

    assert actions_by_id["usage_logs"] is PluginDryRunAction.KEEP
    assert actions_by_id["usage_logs.trace_id_unique_idx"] is PluginDryRunAction.ARCHIVE
    assert actions_by_id[Permission.USAGE_READ.value] is PluginDryRunAction.ARCHIVE
    assert dry_run.resource_count == 12
    assert dry_run.will_delete == []
    assert dry_run.needs_manual_review == []
    assert dry_run.forbidden_to_delete == []
