from src.kernel.extensions import (
    IMAGE_GENERATION_PLUGIN_ID,
    PluginResourceType,
    PluginRuntime,
    PluginRuntimeStatus,
    build_image_generation_plugin_manifest,
    build_uninstall_dry_run,
)
from src.kernel.types import Permission


def test_image_generation_plugin_manifest_preserves_legacy_tool_name(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.kernel.extensions.builtin_plugins.settings.ENABLE_IMAGE_GENERATION",
        True,
    )

    manifest = build_image_generation_plugin_manifest()

    assert manifest.id == IMAGE_GENERATION_PLUGIN_ID
    assert manifest.enabled_by_default is True
    assert [(tool.name, tool.legacy_ids) for tool in manifest.tools] == [
        ("image_generate", ["image_generate"])
    ]
    assert manifest.tools[0].required_permissions == [Permission.MCP_READ.value]
    assert manifest.frontend.tool_renderers[0].id == "image_generation:image-generate"
    assert manifest.frontend.tool_renderers[0].tool_names == [
        "image_generation.image_generate",
        "image_generate",
    ]
    assert manifest.setting_keys() == ["API_KEY", "BASE_URL", "MODEL", "TIMEOUT"]
    assert "ENABLE_IMAGE_GENERATION" in manifest.legacy_setting_keys()
    assert "IMAGE_GENERATION_API_KEY" in manifest.legacy_setting_keys()


def test_image_generation_plugin_runtime_can_start_disabled_by_config(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.kernel.extensions.builtin_plugins.settings.ENABLE_IMAGE_GENERATION",
        False,
    )
    runtime = PluginRuntime([build_image_generation_plugin_manifest()])

    state = runtime.get_state(IMAGE_GENERATION_PLUGIN_ID)

    assert state is not None
    assert state.status is PluginRuntimeStatus.DISABLED
    assert state.issues == []
    assert runtime.tools() == []
    assert [(tool.plugin_id, tool.name) for tool in runtime.tools(enabled_only=False)] == [
        (IMAGE_GENERATION_PLUGIN_ID, "image_generate")
    ]


def test_image_generation_plugin_resources_and_dry_run(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.kernel.extensions.builtin_plugins.settings.ENABLE_IMAGE_GENERATION",
        True,
    )
    runtime = PluginRuntime([build_image_generation_plugin_manifest()])

    resource_keys = {
        (resource.resource_type, resource.resource_id)
        for resource in runtime.resource_ledger.list(plugin_id=IMAGE_GENERATION_PLUGIN_ID)
    }
    dry_run = build_uninstall_dry_run(
        plugin_id=IMAGE_GENERATION_PLUGIN_ID,
        ledger=runtime.resource_ledger,
    )

    assert (PluginResourceType.TOOL, "image_generate") in resource_keys
    assert (PluginResourceType.TOOL_RENDERER, "image_generation:image-generate") in resource_keys
    assert (PluginResourceType.SETTING, "image_generation.API_KEY") in resource_keys
    assert (PluginResourceType.SETTING, "image_generation.BASE_URL") in resource_keys
    assert (PluginResourceType.ENV_KEY_DECLARATION, "IMAGE_GENERATION_API_KEY") in resource_keys
    assert (PluginResourceType.FILE, "generated-images/{user_id}") in resource_keys
    assert dry_run.resource_count == 9
    assert dry_run.will_delete == []
    assert dry_run.needs_manual_review == []
    assert dry_run.forbidden_to_delete == []


def test_image_generation_plugin_tool_guard_uses_legacy_tool_name(monkeypatch) -> None:
    monkeypatch.setattr(
        "src.kernel.extensions.builtin_plugins.settings.ENABLE_IMAGE_GENERATION",
        True,
    )
    runtime = PluginRuntime([build_image_generation_plugin_manifest()])

    registration = runtime.ensure_tool_available("image_generate")

    assert registration.plugin_id == IMAGE_GENERATION_PLUGIN_ID
    runtime.disable_plugin(IMAGE_GENERATION_PLUGIN_ID)
    assert runtime.tools() == []
