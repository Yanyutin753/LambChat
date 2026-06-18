from src.kernel.extensions import (
    ADVANCED_FILE_VIEWERS_PLUGIN_ID,
    PluginDryRunAction,
    PluginResourceType,
    PluginRuntime,
    PluginRuntimeStatus,
    build_advanced_file_viewers_plugin_manifest,
    build_uninstall_dry_run,
)


def test_advanced_file_viewers_manifest_declares_frontend_viewers() -> None:
    manifest = build_advanced_file_viewers_plugin_manifest()

    assert manifest.id == ADVANCED_FILE_VIEWERS_PLUGIN_ID
    assert manifest.tools == []
    assert manifest.routers == []
    assert manifest.frontend.file_viewers == [
        "advanced_file_viewers:pdf",
        "advanced_file_viewers:ppt",
        "advanced_file_viewers:word",
        "advanced_file_viewers:excel",
        "advanced_file_viewers:cad",
        "advanced_file_viewers:excalidraw",
        "advanced_file_viewers:html",
        "advanced_file_viewers:markdown",
        "advanced_file_viewers:code",
    ]
    assert manifest.frontend.i18n_namespaces == [
        "advanced_file_viewers:documents"
    ]


def test_advanced_file_viewers_runtime_is_enabled_and_has_no_backend_routes() -> None:
    runtime = PluginRuntime([build_advanced_file_viewers_plugin_manifest()])

    state = runtime.get_state(ADVANCED_FILE_VIEWERS_PLUGIN_ID)

    assert state is not None
    assert state.status is PluginRuntimeStatus.ENABLED
    assert state.issues == []
    assert runtime.routes() == []
    assert runtime.tools() == []


def test_advanced_file_viewers_resources_and_dry_run_are_non_destructive() -> None:
    runtime = PluginRuntime([build_advanced_file_viewers_plugin_manifest()])
    dry_run = build_uninstall_dry_run(
        plugin_id=ADVANCED_FILE_VIEWERS_PLUGIN_ID,
        ledger=runtime.resource_ledger,
    )
    resource_keys = {
        (resource.resource_type, resource.resource_id)
        for resource in runtime.resource_ledger.list(
            plugin_id=ADVANCED_FILE_VIEWERS_PLUGIN_ID
        )
    }
    actions_by_id = {resource.resource_id: resource.action for resource in dry_run.resources}

    assert (PluginResourceType.FILE_VIEWER, "advanced_file_viewers:pdf") in resource_keys
    assert (
        PluginResourceType.FILE_VIEWER,
        "advanced_file_viewers:excalidraw",
    ) in resource_keys
    assert (
        PluginResourceType.I18N_NAMESPACE,
        "advanced_file_viewers:documents",
    ) in resource_keys
    assert (PluginResourceType.CACHE_KEY, "document-preview-cache") in resource_keys
    assert (PluginResourceType.FILE, "preview-blob-urls") in resource_keys
    assert actions_by_id["advanced_file_viewers:pdf"] is PluginDryRunAction.KEEP
    assert actions_by_id["document-preview-cache"] is PluginDryRunAction.KEEP
    assert dry_run.resource_count == 12
    assert dry_run.will_delete == []
    assert dry_run.needs_manual_review == []
    assert dry_run.forbidden_to_delete == []
