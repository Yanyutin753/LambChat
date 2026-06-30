import pytest
from pydantic import ValidationError

from src.kernel.extensions import (
    ExtensionManifest,
    ExtensionMarketplaceEntry,
    ExtensionRegistry,
    ExtensionType,
    InstallState,
    PluginManifest,
    PluginRegistry,
    build_skill_marketplace_entry,
    extension_uses_plugin_runtime,
)
from src.kernel.extensions.registry import RegistryDuplicateError


def test_extension_manifest_accepts_reserved_future_types():
    manifest = ExtensionManifest(
        id="pdf-viewer",
        type=ExtensionType.FILE_VIEWER,
        name="PDF Viewer",
        version="1.0.0",
        publisher="LambChat",
        permissions=["file:upload", "file:upload", ""],
        tags=["viewer", "viewer"],
    )

    assert manifest.type is ExtensionType.FILE_VIEWER
    assert manifest.permissions == ["file:upload"]
    assert manifest.tags == ["viewer"]
    assert manifest.install_state is InstallState.BUILTIN


def test_extension_marketplace_entry_accepts_unknown_future_types_without_manifest():
    entry = ExtensionMarketplaceEntry(
        id="remote.experimental",
        type="unknown_future_type",
        name="Experimental Extension",
        version="0.1.0",
        publisher="remote-source",
        tags=["future", "future", ""],
    )

    assert entry.type == "unknown_future_type"
    assert entry.tags == ["future"]
    assert entry.known_type is None
    assert entry.as_manifest() is None


def test_skill_marketplace_entry_converts_to_extension_manifest():
    entry = build_skill_marketplace_entry(
        skill_name="planner",
        description="Plan work",
        tags=["planning", "planning"],
        version="2.0.0",
        publisher="tester",
        file_count=3,
    )

    manifest = entry.as_manifest()

    assert entry.id == "skill:planner"
    assert entry.type == "skill"
    assert entry.capabilities == ["skill"]
    assert entry.install_state is InstallState.NOT_INSTALLED
    assert entry.legacy == {
        "kind": "marketplace_skill",
        "skill_name": "planner",
        "file_count": 3,
    }
    assert manifest is not None
    assert manifest.id == "skill:planner"
    assert manifest.type is ExtensionType.SKILL
    assert manifest.name == "planner"
    assert manifest.tags == ["planning"]


@pytest.mark.parametrize(
    ("extension_type", "capability"),
    [("plugin", "plugin"), ("mcp", "mcp")],
)
def test_extension_marketplace_entry_models_plugin_and_mcp_types(
    extension_type: str,
    capability: str,
) -> None:
    entry = ExtensionMarketplaceEntry(
        id=f"{extension_type}:sample",
        type=extension_type,
        name="Sample Extension",
        version="1.0.0",
        publisher="LambChat",
        capabilities=[capability],
        permissions=["sample:read"],
        legacy={"source": "test"},
    )

    manifest = entry.as_manifest()

    assert entry.known_type is ExtensionType(extension_type)
    assert manifest is not None
    assert manifest.id == f"{extension_type}:sample"
    assert manifest.type is ExtensionType(extension_type)
    assert manifest.capabilities == [capability]
    assert manifest.permissions == ["sample:read"]


def test_extension_center_plugin_runtime_boundary_only_allows_plugin_type():
    plugin_entry = ExtensionMarketplaceEntry(
        id="feedback",
        type="plugin",
        name="Feedback",
        version="1.0.0",
        publisher="LambChat",
    )
    skill_entry = build_skill_marketplace_entry(skill_name="planner")
    mcp_entry = ExtensionMarketplaceEntry(
        id="mcp:github",
        type="mcp",
        name="GitHub MCP",
        version="1.0.0",
        publisher="LambChat",
    )
    future_entry = ExtensionMarketplaceEntry(
        id="future:theme",
        type="future_theme",
        name="Future Theme",
        version="1.0.0",
        publisher="remote",
    )

    assert plugin_entry.uses_plugin_runtime is True
    assert extension_uses_plugin_runtime(plugin_entry) is True
    assert extension_uses_plugin_runtime(plugin_entry.as_manifest()) is True
    assert skill_entry.uses_plugin_runtime is False
    assert extension_uses_plugin_runtime(skill_entry.as_manifest()) is False
    assert mcp_entry.uses_plugin_runtime is False
    assert extension_uses_plugin_runtime(mcp_entry.as_manifest()) is False
    assert future_entry.uses_plugin_runtime is False
    assert future_entry.as_manifest() is None


def test_extension_manifest_rejects_unknown_type():
    with pytest.raises(ValidationError):
        ExtensionManifest(
            id="unknown",
            type="not-a-type",
            name="Unknown",
            version="1.0.0",
            publisher="LambChat",
        )


def test_extension_registry_registers_filters_and_dedupes_permissions():
    registry = ExtensionRegistry()
    registry.register(
        ExtensionManifest(
            id="skills",
            type="skill",
            name="Skills",
            version="1.0.0",
            publisher="core",
            permissions=["skill:read", "skill:write"],
        )
    )
    registry.register(
        ExtensionManifest(
            id="feedback",
            type="plugin",
            name="Feedback",
            version="1.0.0",
            publisher="core",
            permissions=["feedback:read", "skill:read"],
            enabled=False,
        )
    )

    assert [item.id for item in registry.list(extension_type="skill")] == ["skills"]
    assert [item.id for item in registry.list(enabled=False)] == ["feedback"]
    assert registry.permissions() == ["skill:read", "skill:write"]
    assert registry.permissions(enabled_only=False) == [
        "skill:read",
        "skill:write",
        "feedback:read",
    ]


def test_extension_registry_rejects_duplicate_ids():
    manifest = ExtensionManifest(
        id="skills",
        type="skill",
        name="Skills",
        version="1.0.0",
        publisher="core",
    )
    registry = ExtensionRegistry([manifest])

    with pytest.raises(RegistryDuplicateError):
        registry.register(manifest)


def test_plugin_manifest_converts_to_extension_manifest():
    plugin = PluginManifest(
        id="agent-team",
        name="Agent Team",
        version="1.0.0",
        api_version="v1",
        permissions=["team:read", "team:read", "team:write"],
        enabled_by_default=False,
        frontend={"nav_items": ["agent_team"], "required_permissions": ["team:read"]},
    )

    extension = plugin.as_extension_manifest(publisher="LambChat")

    assert plugin.permissions == ["team:read", "team:write"]
    assert plugin.frontend.nav_items == ["agent_team"]
    assert extension.id == "agent-team"
    assert extension.type is ExtensionType.PLUGIN
    assert extension.publisher == "LambChat"
    assert extension.enabled is False
    assert extension.install_state is InstallState.INSTALLED
    assert extension.compatibility.api_version == "v1"


def test_plugin_registry_filters_and_exports_extensions():
    registry = PluginRegistry(
        [
            PluginManifest(
                id="feedback",
                name="Feedback",
                version="1.0.0",
                api_version="v1",
                permissions=["feedback:read"],
            ),
            PluginManifest(
                id="audio-transcription",
                name="Audio Transcription",
                version="1.0.0",
                api_version="v1",
                permissions=["audio:transcribe"],
                enabled_by_default=False,
            ),
        ]
    )

    assert [item.id for item in registry.list(enabled_by_default=True)] == ["feedback"]
    assert registry.permissions() == ["feedback:read"]
    assert registry.permissions(enabled_only=False) == ["feedback:read", "audio:transcribe"]

    extension_registry = registry.as_extension_registry(publisher="LambChat")
    assert [item.id for item in extension_registry.list(extension_type="plugin")] == [
        "feedback",
        "audio-transcription",
    ]


def test_plugin_registry_rejects_duplicate_ids():
    plugin = PluginManifest(
        id="feedback",
        name="Feedback",
        version="1.0.0",
        api_version="v1",
    )
    registry = PluginRegistry([plugin])

    with pytest.raises(RegistryDuplicateError):
        registry.register(plugin)


def test_plugin_manifest_declared_permissions_collects_nested_permission_strings():
    plugin = PluginManifest(
        id="feedback",
        name="Feedback",
        version="1.0.0",
        api_version="v1",
        permissions=["feedback:read", "feedback:read"],
        routers=[
            {
                "name": "feedback-api",
                "prefix": "/api/feedback",
                "module": "plugins.feedback.routes",
                "required_permissions": ["feedback:write", "feedback:read"],
            }
        ],
        tools=[
            {
                "name": "feedback_summary",
                "module": "plugins.feedback.tools",
                "required_permissions": ["feedback:admin", ""],
            }
        ],
        frontend={"required_permissions": ["feedback:read", "feedback:admin"]},
    )

    assert plugin.declared_permissions() == [
        "feedback:read",
        "feedback:write",
        "feedback:admin",
    ]
    assert plugin.as_extension_manifest().permissions == [
        "feedback:read",
        "feedback:write",
        "feedback:admin",
    ]


def test_plugin_manifest_rejects_llm_unsafe_tool_names():
    with pytest.raises(ValidationError, match="plugin tool name must match"):
        PluginManifest(
            id="feedback",
            name="Feedback",
            version="1.0.0",
            api_version="v1",
            tools=[
                {
                    "name": "feedback.summary",
                    "module": "plugins.feedback.tools",
                }
            ],
        )


def test_plugin_registry_permissions_include_nested_declarations_and_respect_enabled_filter():
    registry = PluginRegistry(
        [
            PluginManifest(
                id="feedback",
                name="Feedback",
                version="1.0.0",
                api_version="v1",
                permissions=["feedback:read"],
                routers=[
                    {
                        "name": "feedback-api",
                        "prefix": "/api/feedback",
                        "module": "plugins.feedback.routes",
                        "required_permissions": ["feedback:write"],
                    }
                ],
            ),
            PluginManifest(
                id="audio",
                name="Audio",
                version="1.0.0",
                api_version="v1",
                tools=[
                    {
                        "name": "transcribe",
                        "module": "plugins.audio.tools",
                        "required_permissions": ["audio:transcribe"],
                    }
                ],
                enabled_by_default=False,
            ),
        ]
    )

    assert registry.permissions() == ["feedback:read", "feedback:write"]
    assert registry.permissions(enabled_only=False) == [
        "feedback:read",
        "feedback:write",
        "audio:transcribe",
    ]


def test_plugin_registry_collects_route_and_tool_declarations_by_enabled_state():
    registry = PluginRegistry(
        [
            PluginManifest(
                id="feedback",
                name="Feedback",
                version="1.0.0",
                api_version="v1",
                routers=[
                    {
                        "name": "feedback-api",
                        "prefix": "/api/plugins/feedback",
                        "module": "plugins.feedback.routes",
                    }
                ],
                tools=[
                    {
                        "name": "feedback_summary",
                        "module": "plugins.feedback.tools",
                        "legacy_ids": ["feedback.summary"],
                    }
                ],
            ),
            PluginManifest(
                id="audio",
                name="Audio",
                version="1.0.0",
                api_version="v1",
                enabled_by_default=False,
                routers=[
                    {
                        "name": "audio-api",
                        "prefix": "/api/plugins/audio",
                        "module": "plugins.audio.routes",
                    }
                ],
                tools=[
                    {
                        "name": "audio_transcribe",
                        "module": "plugins.audio.tools",
                    }
                ],
            ),
        ]
    )

    assert [(route.plugin_id, route.name, route.prefix) for route in registry.routes()] == [
        ("feedback", "feedback-api", "/api/plugins/feedback")
    ]
    assert [(tool.plugin_id, tool.name, tool.module) for tool in registry.tools()] == [
        ("feedback", "feedback_summary", "plugins.feedback.tools")
    ]
    assert [(route.plugin_id, route.name) for route in registry.routes(enabled_only=False)] == [
        ("feedback", "feedback-api"),
        ("audio", "audio-api"),
    ]
    assert [(tool.plugin_id, tool.name) for tool in registry.tools(enabled_only=False)] == [
        ("feedback", "feedback_summary"),
        ("audio", "audio_transcribe"),
    ]
    assert registry.tools()[0].legacy_ids == ["feedback.summary"]


def test_plugin_registry_lifecycle_hooks_are_stably_ordered_by_phase_and_manifest_order():
    registry = PluginRegistry(
        [
            PluginManifest(
                id="first",
                name="First",
                version="1.0.0",
                api_version="v1",
                lifespan_hooks=[
                    {
                        "name": "first-late",
                        "module": "plugins.first.hooks:late",
                        "phase": "startup",
                        "order": 20,
                    },
                    {
                        "name": "first-early",
                        "module": "plugins.first.hooks:early",
                        "phase": "startup",
                        "order": 10,
                    },
                    {
                        "name": "first-stop",
                        "module": "plugins.first.hooks:stop",
                        "phase": "shutdown",
                        "order": 10,
                    },
                ],
            ),
            PluginManifest(
                id="second",
                name="Second",
                version="1.0.0",
                api_version="v1",
                lifespan_hooks=[
                    {
                        "name": "second-early",
                        "module": "plugins.second.hooks:early",
                        "phase": "startup",
                        "order": 10,
                    }
                ],
            ),
        ]
    )

    startup_hooks = registry.lifecycle_hooks(phase="startup")

    assert [(hook.plugin_id, hook.name, hook.order) for hook in startup_hooks] == [
        ("first", "first-early", 10),
        ("second", "second-early", 10),
        ("first", "first-late", 20),
    ]
    assert [(hook.plugin_id, hook.name) for hook in registry.lifecycle_hooks(phase="shutdown")] == [
        ("first", "first-stop")
    ]


def test_plugin_registry_lifecycle_hooks_respect_enabled_filter_and_do_not_import_modules():
    registry = PluginRegistry(
        [
            PluginManifest(
                id="enabled",
                name="Enabled",
                version="1.0.0",
                api_version="v1",
                lifespan_hooks=[
                    {
                        "name": "enabled-start",
                        "module": "plugins.missing.enabled:start",
                        "phase": "startup",
                    }
                ],
            ),
            PluginManifest(
                id="disabled",
                name="Disabled",
                version="1.0.0",
                api_version="v1",
                enabled_by_default=False,
                lifespan_hooks=[
                    {
                        "name": "disabled-start",
                        "module": "plugins.missing.disabled:start",
                        "phase": "startup",
                    }
                ],
            ),
        ]
    )

    assert [(hook.plugin_id, hook.module) for hook in registry.lifecycle_hooks()] == [
        ("enabled", "plugins.missing.enabled:start")
    ]
    assert [hook.plugin_id for hook in registry.lifecycle_hooks(enabled_only=False)] == [
        "enabled",
        "disabled",
    ]
