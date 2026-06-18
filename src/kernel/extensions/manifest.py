"""Pydantic manifest models for build-time extensions and plugins."""

from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _dedupe_non_blank_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


class ExtensionType(str, Enum):
    """Known extension types, including future reserved types."""

    SKILL = "skill"
    PLUGIN = "plugin"
    MCP = "mcp"
    AGENT_TEAM = "agent_team"
    USER_AGENT = "user_agent"
    AGENT = "agent"
    THEME = "theme"
    WORKFLOW = "workflow"
    PROVIDER = "provider"
    FILE_VIEWER = "file_viewer"
    NOTIFICATION_CHANNEL = "notification_channel"


class InstallState(str, Enum):
    """Installation state tracked by the core extension center."""

    BUILTIN = "builtin"
    INSTALLED = "installed"
    NOT_INSTALLED = "not_installed"


class PluginInstallType(str, Enum):
    """Operational install class used by Plugin Runtime controls."""

    SYSTEM_BUILTIN = "system_builtin"
    PREINSTALLED = "preinstalled"
    USER_INSTALLED = "user_installed"


class ExtensionCompatibility(BaseModel):
    """Version compatibility declaration for an extension."""

    model_config = ConfigDict(extra="forbid")

    min_app_version: str | None = None
    max_app_version: str | None = None
    api_version: str | None = None


class ExtensionManifest(BaseModel):
    """Common manifest shared by skills, plugins, MCP profiles, and reserved types."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    type: ExtensionType
    name: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1)
    publisher: str = Field(..., min_length=1)
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    settings_schema: dict[str, Any] = Field(default_factory=dict)
    install_state: InstallState = InstallState.BUILTIN
    enabled: bool = True
    compatibility: ExtensionCompatibility = Field(default_factory=ExtensionCompatibility)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("extension id cannot be blank")
        return normalized

    @field_validator("permissions", "capabilities", "tags")
    @classmethod
    def dedupe_strings(cls, values: list[str]) -> list[str]:
        return _dedupe_non_blank_strings(values)


class PluginRoute(BaseModel):
    """Backend route contributed by a plugin manifest."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1)
    prefix: str = Field(..., min_length=1)
    module: str = Field(..., min_length=1)
    required_permissions: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)

    @field_validator("required_permissions", "tags")
    @classmethod
    def dedupe_strings(cls, values: list[str]) -> list[str]:
        return _dedupe_non_blank_strings(values)


class PluginTool(BaseModel):
    """Tool contributed to the internal MCP/tool registry."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1)
    module: str = Field(..., min_length=1)
    required_permissions: list[str] = Field(default_factory=list)
    legacy_ids: list[str] = Field(default_factory=list)

    @field_validator("required_permissions", "legacy_ids")
    @classmethod
    def dedupe_strings(cls, values: list[str]) -> list[str]:
        return _dedupe_non_blank_strings(values)


class PluginLifecycleHook(BaseModel):
    """Startup or shutdown hook declared by a plugin."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1)
    module: str = Field(..., min_length=1)
    phase: Literal["startup", "shutdown"]
    order: int = 100


class PluginSettingVisibility(BaseModel):
    """Visibility dependency for a plugin-local setting."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(..., min_length=1)
    value: Any = True

    @field_validator("key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("plugin setting dependency key cannot be blank")
        if "." in normalized:
            raise ValueError("plugin setting visibility must reference a plugin-local key")
        return normalized


class PluginSettingDefinition(BaseModel):
    """Structured setting owned by a plugin manifest."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(..., min_length=1)
    type: Literal["string", "text", "number", "boolean", "select", "json"]
    label: str = ""
    description: str = ""
    default: Any = None
    sensitive: bool = False
    required: bool = False
    scope: Literal["system", "user", "role"] = "system"
    group: str = "general"
    order: int = 100
    options: list[str] | None = None
    json_schema: dict[str, Any] | None = None
    requires_restart: bool = False
    env_fallback: str | None = None
    legacy_system_setting_keys: list[str] = Field(default_factory=list)
    visible_when: PluginSettingVisibility | None = None

    @field_validator("key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("plugin setting key cannot be blank")
        if "." in normalized:
            raise ValueError("plugin setting key must be local; use plugin_id.key externally")
        if normalized.startswith("ENABLE_"):
            raise ValueError("plugin runtime enablement must not be modeled as a plugin setting")
        return normalized

    @field_validator("legacy_system_setting_keys")
    @classmethod
    def dedupe_legacy_keys(cls, values: list[str]) -> list[str]:
        return _dedupe_non_blank_strings(values)

    @property
    def legacy_primary_key(self) -> str | None:
        return self.legacy_system_setting_keys[0] if self.legacy_system_setting_keys else None


class PluginFrontendContribution(BaseModel):
    """Frontend contribution metadata for static build-time plugin manifests."""

    model_config = ConfigDict(extra="forbid")

    routes: list[str] = Field(default_factory=list)
    panels: list[str] = Field(default_factory=list)
    nav_items: list[str] = Field(default_factory=list)
    tool_renderers: list[str] = Field(default_factory=list)
    file_viewers: list[str] = Field(default_factory=list)
    skill_importers: list[str] = Field(default_factory=list)
    channel_connectors: list[str] = Field(default_factory=list)
    message_actions: list[str] = Field(default_factory=list)
    settings_sections: list[str] = Field(default_factory=list)
    i18n_namespaces: list[str] = Field(default_factory=list)
    required_permissions: list[str] = Field(default_factory=list)

    @field_validator(
        "routes",
        "panels",
        "nav_items",
        "tool_renderers",
        "file_viewers",
        "skill_importers",
        "channel_connectors",
        "message_actions",
        "settings_sections",
        "i18n_namespaces",
        "required_permissions",
    )
    @classmethod
    def dedupe_strings(cls, values: list[str]) -> list[str]:
        return _dedupe_non_blank_strings(values)


class PluginFrontendAssetBundle(BaseModel):
    """Built frontend asset metadata declared by a folder plugin."""

    model_config = ConfigDict(extra="forbid")

    plugin_id: str = Field(..., min_length=1)
    asset_schema: Literal["lambchat.plugin.frontend-assets.v1"]
    slots: list[str] = Field(default_factory=list)
    assets: list[str] = Field(default_factory=list)
    phase: str = "static_asset_mount_placeholder"

    @field_validator("plugin_id")
    @classmethod
    def validate_plugin_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("frontend asset plugin_id cannot be blank")
        return normalized

    @field_validator("slots", "assets")
    @classmethod
    def dedupe_asset_strings(cls, values: list[str]) -> list[str]:
        return _dedupe_non_blank_strings(values)


class PluginResourceDeclaration(BaseModel):
    """Non-executable resource owned or declared by a plugin."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    type: Literal[
        "db_collection",
        "db_index",
        "db_document",
        "file",
        "cache_key",
        "env_key_declaration",
        "listener",
        "notification_channel",
        "approval_scenario",
        "usage_report",
        "share_target",
        "channel_connector",
        "message_action",
        "plugin_package_folder",
        "plugin_data_folder",
        "plugin_data_config",
        "plugin_data_storage",
        "plugin_frontend_asset",
        "plugin_migration_script",
    ]
    scope: Literal["global", "user", "role", "project", "session", "system"] = "global"
    retention_policy: Literal[
        "delete_on_uninstall",
        "keep_user_data",
        "archive_metadata",
        "manual_review_required",
        "core_owned_do_not_delete",
    ] = "keep_user_data"
    cleanup_strategy: Literal[
        "delete",
        "keep",
        "archive",
        "manual_review",
        "forbid_delete",
    ] = "keep"
    metadata: dict[str, str] = Field(default_factory=dict)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("plugin resource id cannot be blank")
        return normalized


class PluginManifest(BaseModel):
    """Plugin-specific manifest used by the plugin registry."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    version: str = Field(..., min_length=1)
    api_version: str = Field(..., min_length=1)
    depends_on: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    settings: list[PluginSettingDefinition] = Field(default_factory=list)
    legacy_system_settings: list[str] = Field(default_factory=list)
    routers: list[PluginRoute] = Field(default_factory=list)
    tools: list[PluginTool] = Field(default_factory=list)
    lifespan_hooks: list[PluginLifecycleHook] = Field(default_factory=list)
    scheduler_jobs: list[str] = Field(default_factory=list)
    migrations: list[str] = Field(default_factory=list)
    resources: list[PluginResourceDeclaration] = Field(default_factory=list)
    frontend: PluginFrontendContribution = Field(default_factory=PluginFrontendContribution)
    enabled_by_default: bool = True
    core: bool = False
    install_type: PluginInstallType = PluginInstallType.PREINSTALLED
    package_source_type: Literal[
        "static_manifest",
        "system",
        "preinstalled",
        "installed",
        "staged",
    ] = "static_manifest"
    package_source_path: str | None = None
    package_manifest_path: str | None = None
    package_data_dir: str | None = None
    package_validated_at: str | None = None
    package_errors: list[str] = Field(default_factory=list)
    package_config_defaults: dict[str, Any] = Field(default_factory=dict)
    package_layout: dict[str, Any] = Field(default_factory=dict)
    package_frontend_assets: PluginFrontendAssetBundle | None = None
    package_manifest_authority: Literal["static_manifest", "folder_package"] = "static_manifest"
    package_static_fallback_used: bool = False
    package_static_fallback_fields: list[str] = Field(default_factory=list)

    @property
    def uninstallable(self) -> bool:
        return self.install_type in {
            PluginInstallType.PREINSTALLED,
            PluginInstallType.USER_INSTALLED,
        } and not self.core

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("plugin id cannot be blank")
        return normalized

    @field_validator("settings", mode="before")
    @classmethod
    def normalize_settings(cls, value: Any) -> list[Any]:
        if value is None:
            return []
        if isinstance(value, dict):
            normalized: list[dict[str, Any]] = []
            for key, definition in value.items():
                if isinstance(definition, dict):
                    setting_type = definition.get("type", "string")
                    default = definition.get("default")
                else:
                    setting_type = "string"
                    default = None
                normalized.append(
                    {
                        "key": key,
                        "type": "number" if setting_type == "integer" else setting_type,
                        "default": default,
                        "legacy_system_setting_keys": [key],
                    }
                )
            return normalized
        return value

    @field_validator(
        "depends_on",
        "permissions",
        "scheduler_jobs",
        "migrations",
        "legacy_system_settings",
    )
    @classmethod
    def dedupe_strings(cls, values: list[str]) -> list[str]:
        return _dedupe_non_blank_strings(values)

    def setting_keys(self, *, qualified: bool = False) -> list[str]:
        """Return plugin setting keys, optionally qualified with plugin id."""
        keys = [setting.key for setting in self.settings]
        if qualified:
            return [f"{self.id}.{key}" for key in keys]
        return keys

    def legacy_setting_keys(self) -> list[str]:
        """Return global setting keys superseded by this plugin settings contract."""
        values: list[str] = []
        values.extend(self.legacy_system_settings)
        for setting in self.settings:
            values.extend(setting.legacy_system_setting_keys)
        return _dedupe_non_blank_strings(values)

    def declared_permissions(self) -> list[str]:
        """Return all string permissions declared by this plugin manifest."""
        values: list[str] = []
        values.extend(self.permissions)
        for router in self.routers:
            values.extend(router.required_permissions)
        for tool in self.tools:
            values.extend(tool.required_permissions)
        values.extend(self.frontend.required_permissions)
        return _dedupe_non_blank_strings(values)

    def as_extension_manifest(self, *, publisher: str = "core") -> ExtensionManifest:
        """Expose a plugin through the common extension manifest shape."""
        return ExtensionManifest(
            id=self.id,
            type=ExtensionType.PLUGIN,
            name=self.name,
            version=self.version,
            publisher=publisher,
            capabilities=["plugin"],
            permissions=self.declared_permissions(),
            install_state=(
                InstallState.BUILTIN
                if self.install_type is PluginInstallType.SYSTEM_BUILTIN
                else InstallState.INSTALLED
            ),
            enabled=self.enabled_by_default,
            compatibility=ExtensionCompatibility(api_version=self.api_version),
        )
