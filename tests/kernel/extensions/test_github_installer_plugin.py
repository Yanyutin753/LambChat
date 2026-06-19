from src.kernel.extensions import (
    GITHUB_INSTALLER_PLUGIN_ID,
    PluginDryRunAction,
    PluginResourceType,
    PluginRuntime,
    PluginRuntimeStatus,
    build_github_installer_plugin_manifest,
    build_uninstall_dry_run,
)
from src.kernel.types import Permission


def test_github_installer_manifest_preserves_legacy_api_and_permissions() -> None:
    manifest = build_github_installer_plugin_manifest()

    assert manifest.id == GITHUB_INSTALLER_PLUGIN_ID
    assert manifest.depends_on == ["skill_core"]
    assert manifest.routers[0].prefix == "/api/github"
    assert manifest.routers[0].module == "src.api.routes.github"
    assert manifest.routers[0].tags == ["GitHub"]
    assert [importer.id for importer in manifest.frontend.skill_importers] == [
        "github_installer:github-import"
    ]
    assert manifest.frontend.skill_importers[0].source == "github"
    assert manifest.frontend.i18n_namespaces == ["github_installer:skills"]
    assert set(manifest.declared_permissions()) == {
        Permission.SKILL_READ.value,
        Permission.SKILL_WRITE.value,
    }


def test_github_installer_runtime_requires_skill_core_dependency() -> None:
    runtime_without_core = PluginRuntime([build_github_installer_plugin_manifest()])
    blocked_state = runtime_without_core.get_state(GITHUB_INSTALLER_PLUGIN_ID)

    assert blocked_state is not None
    assert blocked_state.status is PluginRuntimeStatus.ERROR
    assert [issue.code for issue in blocked_state.issues] == ["missing_dependency"]

    runtime = PluginRuntime(
        [build_github_installer_plugin_manifest()],
        core_dependencies=("skill_core",),
    )
    state = runtime.get_state(GITHUB_INSTALLER_PLUGIN_ID)

    assert state is not None
    assert state.status is PluginRuntimeStatus.ENABLED
    assert state.executable is True
    assert [
        (route.plugin_id, route.name, route.prefix)
        for route in runtime.routes()
    ] == [(GITHUB_INSTALLER_PLUGIN_ID, "github_installer-api", "/api/github")]


def test_github_installer_resources_and_dry_run_protect_skill_core_data() -> None:
    runtime = PluginRuntime(
        [build_github_installer_plugin_manifest()],
        core_dependencies=("skill_core",),
    )
    resources = runtime.resource_ledger.list(plugin_id=GITHUB_INSTALLER_PLUGIN_ID)
    resource_keys = {
        (resource.resource_type, resource.resource_id)
        for resource in resources
    }
    dry_run = build_uninstall_dry_run(
        plugin_id=GITHUB_INSTALLER_PLUGIN_ID,
        ledger=runtime.resource_ledger,
    )
    actions_by_id = {resource.resource_id: resource.action for resource in dry_run.resources}

    assert (PluginResourceType.BACKEND_ROUTE, "github_installer-api") in resource_keys
    assert (PluginResourceType.SKILL_IMPORTER, "github_installer:github-import") in resource_keys
    assert (PluginResourceType.PERMISSION, Permission.SKILL_READ.value) in resource_keys
    assert (PluginResourceType.PERMISSION, Permission.SKILL_WRITE.value) in resource_keys
    assert (PluginResourceType.CACHE_KEY, "github.com/api/repos/contents") in resource_keys
    assert (PluginResourceType.FILE, "user-skills/{user_id}/{skill_name}") in resource_keys
    assert actions_by_id["github_installer-api"] is PluginDryRunAction.KEEP
    assert actions_by_id["github_installer:github-import"] is PluginDryRunAction.KEEP
    assert actions_by_id["github.com/api/repos/contents"] is PluginDryRunAction.ARCHIVE
    assert actions_by_id["user-skills/{user_id}/{skill_name}"] is PluginDryRunAction.FORBID_DELETE
