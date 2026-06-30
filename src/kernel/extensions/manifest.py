"""Pydantic manifest models for build-time extensions and plugins."""

import re
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _dedupe_non_blank_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        normalized = value.strip()
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return result


def _is_plugin_owned_id(value: str, plugin_id: str) -> bool:
    normalized = value.strip()
    return normalized == plugin_id or normalized.startswith((f"{plugin_id}:", f"{plugin_id}."))


_LLM_TOOL_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


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

    @field_validator("name")
    @classmethod
    def validate_llm_tool_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("plugin tool name cannot be blank")
        if not _LLM_TOOL_NAME_PATTERN.fullmatch(normalized):
            raise ValueError(
                "plugin tool name must match ^[a-zA-Z0-9_-]+$; use legacy_ids for old names"
            )
        return normalized

    @field_validator("required_permissions", "legacy_ids")
    @classmethod
    def dedupe_strings(cls, values: list[str]) -> list[str]:
        return _dedupe_non_blank_strings(values)


class PluginAgentCatalogEntry(BaseModel):
    """Agent catalog entry owned by a plugin manifest."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    module: str = ""
    name: str = ""
    description: str = ""
    icon: str = "Bot"
    sort_order: int = 100
    category: str | None = None
    required_permissions: list[str] = Field(default_factory=list)

    @field_validator("id", "module", "name", "description", "icon", "category")
    @classmethod
    def normalize_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return value.strip()

    @field_validator("required_permissions")
    @classmethod
    def dedupe_permissions(cls, values: list[str]) -> list[str]:
        return _dedupe_non_blank_strings(values)


class PluginLifecycleHook(BaseModel):
    """Startup or shutdown hook declared by a plugin."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1)
    module: str = Field(..., min_length=1)
    phase: Literal["startup", "shutdown"]
    order: int = 100


class PluginRuntimeEffect(BaseModel):
    """Controlled runtime side effect declared by a plugin."""

    model_config = ConfigDict(extra="forbid")

    action: Literal["enable", "disable"]
    effect: Literal["start_feishu_connector", "stop_feishu_connector"]

    @field_validator("effect")
    @classmethod
    def validate_effect(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("plugin runtime effect cannot be blank")
        return normalized


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
    scope: Literal[
        "system",
        "user",
        "role",
        "project",
        "session",
        "channel",
        "scheduled_task",
    ] = "system"
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


class PluginFrontendVisibleWhen(BaseModel):
    """Safe frontend visibility predicates for plugin-declared UI contributions."""

    model_config = ConfigDict(extra="forbid")

    agent_id: str | None = None
    route: str | None = None
    scope: (
        Literal[
            "system",
            "user",
            "role",
            "project",
            "session",
            "channel",
            "scheduled_task",
        ]
        | None
    ) = None
    permissions: list[str] = Field(default_factory=list)

    @field_validator("agent_id", "route")
    @classmethod
    def normalize_optional_string(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("permissions")
    @classmethod
    def dedupe_permissions(cls, values: list[str]) -> list[str]:
        return _dedupe_non_blank_strings(values)


class PluginOptionBinding(BaseModel):
    """Plugin-local option target written by a plugin UI contribution."""

    model_config = ConfigDict(extra="forbid")

    plugin_id: str | None = None
    key: str = Field(..., min_length=1)
    scope: Literal[
        "system",
        "user",
        "role",
        "project",
        "session",
        "channel",
        "scheduled_task",
    ] = "session"

    @field_validator("plugin_id")
    @classmethod
    def normalize_plugin_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("plugin option binding plugin_id cannot be blank")
        return normalized

    @field_validator("key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("plugin option binding key cannot be blank")
        if "." in normalized:
            raise ValueError("plugin option binding key must be plugin-local")
        return normalized


class PluginChatInputOption(BaseModel):
    """Button or menu item contributed to the chat input feature menu."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    slot: Literal["enhance", "settings", "upload"] = "enhance"
    label: str = Field(..., min_length=1)
    icon: str = "Plug"
    panel: str | None = None
    selected_renderer: str | None = None
    suppresses_core_persona_selector: bool = False
    shortcut: str | None = None
    order: int = 100
    option_binding: PluginOptionBinding | None = None
    visible_when: PluginFrontendVisibleWhen | None = None

    @field_validator("id", "label", "icon", "panel", "selected_renderer", "shortcut")
    @classmethod
    def normalize_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("chat input option fields cannot be blank")
        return normalized


class PluginChatInputPanel(BaseModel):
    """Renderer declaration for a plugin-contributed chat input panel."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    renderer: str = Field(..., min_length=1)
    create_path: str | None = None
    manage_path: str | None = None
    option_binding: PluginOptionBinding | None = None
    visible_when: PluginFrontendVisibleWhen | None = None

    @field_validator("id", "renderer", "create_path", "manage_path")
    @classmethod
    def normalize_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("chat input panel fields cannot be blank")
        return normalized


class PluginMentionProvider(BaseModel):
    """Mention search provider declared by a plugin."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    trigger: str = "@"
    mode: str = Field(..., min_length=1)
    provider: str = Field(..., min_length=1)
    option_binding: PluginOptionBinding | None = None
    visible_when: PluginFrontendVisibleWhen | None = None

    @field_validator("id", "trigger", "mode", "provider")
    @classmethod
    def normalize_strings(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("mention provider fields cannot be blank")
        return normalized


class PluginAppTab(BaseModel):
    """Top-level application route contributed by a plugin."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    tab: str = Field(..., min_length=1)
    path: str = Field(..., min_length=1)
    label: str = ""
    panel: str | None = None
    order: int = 100
    insert_after: str | None = None
    permissions: list[str] = Field(default_factory=list)
    seo_title: str = ""
    seo_description: str = ""
    redirect_to: str | None = None
    show_no_permission_toast: bool = False
    visible_when: PluginFrontendVisibleWhen | None = None

    @field_validator(
        "id",
        "tab",
        "path",
        "label",
        "panel",
        "insert_after",
        "seo_title",
        "seo_description",
        "redirect_to",
    )
    @classmethod
    def normalize_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized and value is not None and value != "":
            raise ValueError("app tab fields cannot be blank")
        return normalized

    @field_validator("permissions")
    @classmethod
    def dedupe_permissions(cls, values: list[str]) -> list[str]:
        return _dedupe_non_blank_strings(values)


class PluginAppPanel(BaseModel):
    """Renderer declaration for a plugin-owned application panel."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    tab: str = Field(..., min_length=1)
    renderer: str = Field(..., min_length=1)
    visible_when: PluginFrontendVisibleWhen | None = None

    @field_validator("id", "tab", "renderer")
    @classmethod
    def normalize_strings(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("app panel fields cannot be blank")
        return normalized


class PluginSidebarItem(BaseModel):
    """Navigation item contributed to the sidebar/more-menu surface."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    path: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    icon: str = "Plug"
    order: int = 100
    permissions: list[str] = Field(default_factory=list)
    visible_when: PluginFrontendVisibleWhen | None = None

    @field_validator("id", "path", "label", "icon")
    @classmethod
    def normalize_strings(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("sidebar item fields cannot be blank")
        return normalized

    @field_validator("permissions")
    @classmethod
    def dedupe_permissions(cls, values: list[str]) -> list[str]:
        return _dedupe_non_blank_strings(values)


class PluginUserMenuItem(BaseModel):
    """User/admin menu item contributed by a plugin."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    path: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    icon: str = "Plug"
    group: Literal["admin", "system"] = "system"
    order: int = 100
    permissions: list[str] = Field(default_factory=list)
    visible_when: PluginFrontendVisibleWhen | None = None

    @field_validator("id", "path", "label", "icon")
    @classmethod
    def normalize_strings(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("user menu item fields cannot be blank")
        return normalized

    @field_validator("permissions")
    @classmethod
    def dedupe_permissions(cls, values: list[str]) -> list[str]:
        return _dedupe_non_blank_strings(values)


class PluginScopedOption(BaseModel):
    """Project/session option declared by a plugin and stored in its namespace."""

    model_config = ConfigDict(extra="forbid")

    key: str = Field(..., min_length=1)
    type: Literal["string", "text", "number", "boolean", "select", "json"]
    label: str = Field(..., min_length=1)
    description: str = ""
    default: Any = None
    group: str = "general"
    order: int = 100
    options: list[str] | None = None
    json_schema: dict[str, Any] | None = None
    renderer: str | None = None
    suppresses_core_persona_selector: bool = False
    legacy_payload_keys: list[str] = Field(default_factory=list)
    applies_to_session_key: str | None = None
    visible_when: PluginFrontendVisibleWhen | None = None

    @field_validator("key")
    @classmethod
    def validate_key(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("plugin scoped option key cannot be blank")
        if "." in normalized:
            raise ValueError("plugin scoped option key must be local")
        return normalized

    @field_validator("label", "description", "group")
    @classmethod
    def normalize_strings(cls, value: str) -> str:
        return value.strip()

    @field_validator("legacy_payload_keys")
    @classmethod
    def dedupe_legacy_payload_keys(cls, values: list[str]) -> list[str]:
        return _dedupe_non_blank_strings(values)

    @field_validator("applies_to_session_key")
    @classmethod
    def normalize_applies_to_session_key(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("plugin scoped option applies_to_session_key cannot be blank")
        if "." in normalized:
            raise ValueError("plugin scoped option applies_to_session_key must be plugin-local")
        return normalized

    @field_validator("renderer")
    @classmethod
    def normalize_renderer(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("plugin scoped option renderer cannot be blank")
        return normalized


class PluginMessageAction(BaseModel):
    """Message-level action contributed by a plugin."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    target: Literal["assistant_message", "user_message", "tool_result", "shared_message"] = (
        "assistant_message"
    )
    renderer: str = Field(..., min_length=1)
    order: int = 100
    permissions: list[str] = Field(default_factory=list)
    visible_when: PluginFrontendVisibleWhen | None = None

    @field_validator("id", "target", "renderer")
    @classmethod
    def normalize_strings(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("message action fields cannot be blank")
        return normalized

    @field_validator("permissions")
    @classmethod
    def dedupe_permissions(cls, values: list[str]) -> list[str]:
        return _dedupe_non_blank_strings(values)


class PluginWelcomeSurface(BaseModel):
    """Welcome-page surface contributed by a plugin for an agent context."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    agent_id: str = Field(..., min_length=1)
    renderer: str = Field(..., min_length=1)
    order: int = 100
    option_binding: PluginOptionBinding | None = None
    visible_when: PluginFrontendVisibleWhen | None = None

    @field_validator("id", "agent_id", "renderer")
    @classmethod
    def normalize_strings(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("welcome surface fields cannot be blank")
        return normalized


class PluginAgentCategory(BaseModel):
    """Agent catalog category declared by a plugin."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    label: str = Field(..., min_length=1)
    description: str = ""
    icon: str = "Plug"
    order: int = 100
    visible_when: PluginFrontendVisibleWhen | None = None

    @field_validator("id", "label", "description", "icon")
    @classmethod
    def normalize_strings(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized and value != "":
            raise ValueError("agent category fields cannot be blank")
        return normalized


class PluginAssistantIdentityResolver(BaseModel):
    """Assistant identity resolver declared by a plugin for an agent context."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    agent_id: str = Field(..., min_length=1)
    resolver: str = Field(..., min_length=1)
    order: int = 100
    option_binding: PluginOptionBinding | None = None
    visible_when: PluginFrontendVisibleWhen | None = None

    @field_validator("id", "agent_id", "resolver")
    @classmethod
    def normalize_strings(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("assistant identity resolver fields cannot be blank")
        return normalized


class PluginToolRendererContribution(BaseModel):
    """Tool result renderer declared by a plugin."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    tool_names: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("tool renderer id cannot be blank")
        return normalized

    @field_validator("tool_names")
    @classmethod
    def dedupe_tool_names(cls, values: list[str]) -> list[str]:
        return _dedupe_non_blank_strings(values)


class PluginFileViewerContribution(BaseModel):
    """File viewer declared by a plugin."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    extensions: list[str] = Field(default_factory=list)

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("file viewer id cannot be blank")
        return normalized

    @field_validator("extensions")
    @classmethod
    def dedupe_extensions(cls, values: list[str]) -> list[str]:
        return _dedupe_non_blank_strings(values)


class PluginUploadHandlerContribution(BaseModel):
    """Upload handling capability declared by a plugin.

    This is metadata only in the current runtime phase. The core upload path
    remains core-owned; host UIs and future guards can inspect these declarations
    before any plugin-owned upload execution is introduced.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    accept: list[str] = Field(default_factory=list)
    max_bytes: int | None = None
    handler: str | None = None

    @field_validator("id", "handler")
    @classmethod
    def normalize_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("upload handler fields cannot be blank")
        return normalized

    @field_validator("accept")
    @classmethod
    def dedupe_accept(cls, values: list[str]) -> list[str]:
        return _dedupe_non_blank_strings(values)

    @field_validator("max_bytes")
    @classmethod
    def validate_max_bytes(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("upload handler max_bytes must be positive")
        return value


class PluginSkillImporterContribution(BaseModel):
    """Skill importer declared by a plugin."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    source: Literal["github", "zip"]

    @field_validator("id")
    @classmethod
    def validate_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("skill importer id cannot be blank")
        return normalized


class PluginChannelConnectorContribution(BaseModel):
    """Channel connector declared by a plugin."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1)
    channel_type: str = Field(..., min_length=1)
    panel_renderer: str | None = None

    @field_validator("id", "channel_type", "panel_renderer")
    @classmethod
    def normalize_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("channel connector fields cannot be blank")
        return normalized


class PluginFrontendContribution(BaseModel):
    """Frontend contribution metadata for static build-time plugin manifests."""

    model_config = ConfigDict(extra="forbid")

    routes: list[str] = Field(default_factory=list)
    panels: list[str] = Field(default_factory=list)
    nav_items: list[str] = Field(default_factory=list)
    app_tabs: list[PluginAppTab] = Field(default_factory=list)
    app_panels: list[PluginAppPanel] = Field(default_factory=list)
    sidebar_items: list[PluginSidebarItem] = Field(default_factory=list)
    user_menu_items: list[PluginUserMenuItem] = Field(default_factory=list)
    tool_renderers: list[PluginToolRendererContribution] = Field(default_factory=list)
    file_viewers: list[PluginFileViewerContribution] = Field(default_factory=list)
    upload_handlers: list[PluginUploadHandlerContribution] = Field(default_factory=list)
    skill_importers: list[PluginSkillImporterContribution] = Field(default_factory=list)
    channel_connectors: list[PluginChannelConnectorContribution] = Field(default_factory=list)
    message_actions: list[PluginMessageAction] = Field(default_factory=list)
    chat_input_options: list[PluginChatInputOption] = Field(default_factory=list)
    chat_input_panels: list[PluginChatInputPanel] = Field(default_factory=list)
    mention_providers: list[PluginMentionProvider] = Field(default_factory=list)
    welcome_surfaces: list[PluginWelcomeSurface] = Field(default_factory=list)
    assistant_identity_resolvers: list[PluginAssistantIdentityResolver] = Field(
        default_factory=list
    )
    agent_categories: list[PluginAgentCategory] = Field(default_factory=list)
    project_options: list[PluginScopedOption] = Field(default_factory=list)
    session_options: list[PluginScopedOption] = Field(default_factory=list)
    channel_options: list[PluginScopedOption] = Field(default_factory=list)
    scheduled_task_options: list[PluginScopedOption] = Field(default_factory=list)
    settings_sections: list[str] = Field(default_factory=list)
    i18n_namespaces: list[str] = Field(default_factory=list)
    required_permissions: list[str] = Field(default_factory=list)

    @field_validator(
        "routes",
        "panels",
        "nav_items",
        "settings_sections",
        "i18n_namespaces",
        "required_permissions",
    )
    @classmethod
    def dedupe_strings(cls, values: list[str]) -> list[str]:
        return _dedupe_non_blank_strings(values)

    @field_validator("message_actions", mode="before")
    @classmethod
    def normalize_message_actions(cls, value: Any) -> list[Any]:
        if value is None:
            return []
        if not isinstance(value, list):
            return value
        normalized: list[Any] = []
        for item in value:
            if isinstance(item, str):
                normalized.append({"id": item, "renderer": _default_message_action_renderer(item)})
            else:
                normalized.append(item)
        return normalized

    @field_validator("tool_renderers", mode="before")
    @classmethod
    def normalize_tool_renderers(cls, value: Any) -> list[Any]:
        if value is None:
            return []
        if not isinstance(value, list):
            return value
        return [
            {"id": item, "tool_names": _default_tool_renderer_tool_names(item)}
            if isinstance(item, str)
            else item
            for item in value
        ]

    @field_validator("file_viewers", mode="before")
    @classmethod
    def normalize_file_viewers(cls, value: Any) -> list[Any]:
        if value is None:
            return []
        if not isinstance(value, list):
            return value
        return [
            {"id": item, "extensions": _default_file_viewer_extensions(item)}
            if isinstance(item, str)
            else item
            for item in value
        ]

    @field_validator("upload_handlers", mode="before")
    @classmethod
    def normalize_upload_handlers(cls, value: Any) -> list[Any]:
        if value is None:
            return []
        if not isinstance(value, list):
            return value
        return [{"id": item, "accept": []} if isinstance(item, str) else item for item in value]

    @field_validator("skill_importers", mode="before")
    @classmethod
    def normalize_skill_importers(cls, value: Any) -> list[Any]:
        if value is None:
            return []
        if not isinstance(value, list):
            return value
        return [
            {"id": item, "source": _default_skill_importer_source(item)}
            if isinstance(item, str)
            else item
            for item in value
        ]

    @field_validator("channel_connectors", mode="before")
    @classmethod
    def normalize_channel_connectors(cls, value: Any) -> list[Any]:
        if value is None:
            return []
        if not isinstance(value, list):
            return value
        return [
            {"id": item, "channel_type": _default_channel_connector_type(item)}
            if isinstance(item, str)
            else item
            for item in value
        ]


def _default_message_action_renderer(action_id: str) -> str:
    mapping = {
        "feedback:message-feedback": "feedback.FeedbackButtons",
    }
    return mapping.get(action_id, action_id)


def _default_tool_renderer_tool_names(renderer_id: str) -> list[str]:
    mapping = {
        "agent_team:agent-team": [
            "agent_team.search_persona_presets",
            "agent_team.create_agent_team",
            "search_persona_presets",
            "create_agent_team",
        ],
        "agent-team": ["search_persona_presets", "create_agent_team"],
        "image_generation:image-generate": ["image_generation.image_generate", "image_generate"],
        "image-generate": ["image_generate"],
        "audio_transcription:audio-transcribe": [
            "audio_transcription.audio_transcribe",
            "audio_transcribe",
        ],
        "audio-transcribe": ["audio_transcribe"],
    }
    return mapping.get(renderer_id, [])


def _default_file_viewer_extensions(viewer_id: str) -> list[str]:
    key = viewer_id.rsplit(":", 1)[-1]
    mapping = {
        "pdf": ["pdf"],
        "ppt": ["ppt", "pptx"],
        "word": ["docx"],
        "excel": ["xls", "xlsx", "csv"],
        "cad": ["dxf", "dwg"],
        "excalidraw": ["excalidraw"],
        "html": ["html", "htm"],
        "markdown": ["md", "markdown"],
        "code": ["*"],
    }
    return mapping.get(key, [])


def _default_skill_importer_source(importer_id: str) -> str:
    mapping = {
        "github_installer:github-import": "github",
        "github-import": "github",
    }
    return mapping.get(importer_id, "github")


def _default_channel_connector_type(connector_id: str) -> str:
    mapping = {
        "feishu_connector:feishu": "feishu",
        "feishu": "feishu",
    }
    return mapping.get(connector_id, connector_id.rsplit(":", 1)[-1])


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
        "upload_handler",
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
    description: str = ""
    version: str = Field(..., min_length=1)
    api_version: str = Field(..., min_length=1)
    depends_on: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    settings: list[PluginSettingDefinition] = Field(default_factory=list)
    legacy_system_settings: list[str] = Field(default_factory=list)
    routers: list[PluginRoute] = Field(default_factory=list)
    agents: list[PluginAgentCatalogEntry] = Field(default_factory=list)
    tools: list[PluginTool] = Field(default_factory=list)
    lifespan_hooks: list[PluginLifecycleHook] = Field(default_factory=list)
    runtime_effects: list[PluginRuntimeEffect] = Field(default_factory=list)
    scheduler_jobs: list[str] = Field(default_factory=list)
    event_listeners: list[str] = Field(default_factory=list)
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
    package_data_template: str = "plugin-data-template"
    package_layout: dict[str, Any] = Field(default_factory=dict)
    package_frontend_assets: PluginFrontendAssetBundle | None = None
    package_manifest_authority: Literal["static_manifest", "folder_package"] = "static_manifest"
    package_static_fallback_used: bool = False
    package_static_fallback_fields: list[str] = Field(default_factory=list)

    @property
    def uninstallable(self) -> bool:
        return (
            self.install_type
            in {
                PluginInstallType.PREINSTALLED,
                PluginInstallType.USER_INSTALLED,
            }
            and not self.core
        )

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
        "event_listeners",
        "migrations",
        "legacy_system_settings",
    )
    @classmethod
    def dedupe_strings(cls, values: list[str]) -> list[str]:
        return _dedupe_non_blank_strings(values)

    @model_validator(mode="after")
    def validate_structured_frontend_contribution_ownership(self) -> "PluginManifest":
        invalid_ids: list[str] = []
        invalid_references: list[str] = []
        frontend = self.frontend
        structured_ids = [
            *(item.id for item in frontend.app_tabs),
            *(item.id for item in frontend.app_panels),
            *(item.id for item in frontend.sidebar_items),
            *(item.id for item in frontend.user_menu_items),
            *(item.id for item in frontend.message_actions),
            *(item.id for item in frontend.chat_input_options),
            *(item.id for item in frontend.chat_input_panels),
            *(item.id for item in frontend.mention_providers),
            *(item.id for item in frontend.welcome_surfaces),
            *(item.id for item in frontend.assistant_identity_resolvers),
            *(item.id for item in frontend.agent_categories),
        ]
        for contribution_id in structured_ids:
            if contribution_id and not _is_plugin_owned_id(contribution_id, self.id):
                invalid_ids.append(contribution_id)
        if invalid_ids:
            raise ValueError(
                "structured frontend contribution ids must be owned by plugin "
                f"{self.id}: {', '.join(invalid_ids)}"
            )
        renderer_references = [
            *(item.panel for item in frontend.app_tabs if item.panel),
            *(item.renderer for item in frontend.app_panels),
            *(item.renderer for item in frontend.message_actions),
            *(item.panel for item in frontend.chat_input_options if item.panel),
            *(
                item.selected_renderer
                for item in frontend.chat_input_options
                if item.selected_renderer
            ),
            *(item.renderer for item in frontend.chat_input_panels),
            *(item.provider for item in frontend.mention_providers),
            *(item.renderer for item in frontend.welcome_surfaces),
            *(item.resolver for item in frontend.assistant_identity_resolvers),
            *(item.renderer for item in frontend.project_options if item.renderer),
            *(item.renderer for item in frontend.session_options if item.renderer),
            *(item.renderer for item in frontend.channel_options if item.renderer),
            *(item.renderer for item in frontend.scheduled_task_options if item.renderer),
            *(item.id for item in frontend.tool_renderers),
            *(item.id for item in frontend.file_viewers),
            *(item.id for item in frontend.upload_handlers),
            *(item.id for item in frontend.skill_importers),
            *(item.id for item in frontend.channel_connectors),
        ]
        for upload_handler in frontend.upload_handlers:
            if upload_handler.handler and not _is_plugin_owned_id(
                upload_handler.handler,
                self.id,
            ):
                invalid_references.append(upload_handler.handler)
        for reference in renderer_references:
            if reference and not _is_plugin_owned_id(reference, self.id):
                invalid_references.append(reference)
        for connector in frontend.channel_connectors:
            if connector.panel_renderer and not _is_plugin_owned_id(
                connector.panel_renderer,
                self.id,
            ):
                invalid_references.append(connector.panel_renderer)
        if invalid_references:
            raise ValueError(
                "structured frontend renderers and contribution references must be owned by plugin "
                f"{self.id}: {', '.join(invalid_references)}"
            )
        invalid_bindings: list[str] = []
        option_bindings = [
            *(item.option_binding for item in frontend.mention_providers if item.option_binding),
            *(item.option_binding for item in frontend.welcome_surfaces if item.option_binding),
            *(
                item.option_binding
                for item in frontend.assistant_identity_resolvers
                if item.option_binding
            ),
            *(item.option_binding for item in frontend.chat_input_options if item.option_binding),
            *(item.option_binding for item in frontend.chat_input_panels if item.option_binding),
        ]
        for binding in option_bindings:
            if binding.plugin_id and binding.plugin_id != self.id:
                invalid_bindings.append(f"{binding.plugin_id}.{binding.key}")
        if invalid_bindings:
            raise ValueError(
                "plugin frontend option bindings must target the declaring plugin "
                f"{self.id}: {', '.join(invalid_bindings)}"
            )
        return self

    @model_validator(mode="after")
    def validate_scoped_option_settings_contract(self) -> "PluginManifest":
        settings_by_scope = {(setting.scope, setting.key) for setting in self.settings}
        missing: list[str] = []
        for option in self.frontend.project_options:
            if ("project", option.key) not in settings_by_scope:
                missing.append(f"project:{option.key}")
        for option in self.frontend.session_options:
            if ("session", option.key) not in settings_by_scope:
                missing.append(f"session:{option.key}")
        for option in self.frontend.channel_options:
            if ("channel", option.key) not in settings_by_scope:
                missing.append(f"channel:{option.key}")
        for option in self.frontend.scheduled_task_options:
            if ("scheduled_task", option.key) not in settings_by_scope:
                missing.append(f"scheduled_task:{option.key}")
        invalid_project_mappings: list[str] = []
        session_keys = {option.key for option in self.frontend.session_options}
        session_setting_keys = {
            setting.key for setting in self.settings if setting.scope == "session"
        }
        for option in self.frontend.project_options:
            target_key = option.applies_to_session_key
            if (
                target_key
                and target_key not in session_keys
                and target_key not in session_setting_keys
            ):
                invalid_project_mappings.append(f"project:{option.key}->{target_key}")
        for chat_input_option in self.frontend.chat_input_options:
            binding = chat_input_option.option_binding
            if binding and (binding.scope, binding.key) not in settings_by_scope:
                missing.append(f"{binding.scope}:{binding.key}")
        for panel in self.frontend.chat_input_panels:
            binding = panel.option_binding
            if binding and (binding.scope, binding.key) not in settings_by_scope:
                missing.append(f"{binding.scope}:{binding.key}")
        for provider in self.frontend.mention_providers:
            binding = provider.option_binding
            if binding and (binding.scope, binding.key) not in settings_by_scope:
                missing.append(f"{binding.scope}:{binding.key}")
        for surface in self.frontend.welcome_surfaces:
            binding = surface.option_binding
            if binding and (binding.scope, binding.key) not in settings_by_scope:
                missing.append(f"{binding.scope}:{binding.key}")
        for resolver in self.frontend.assistant_identity_resolvers:
            binding = resolver.option_binding
            if binding and (binding.scope, binding.key) not in settings_by_scope:
                missing.append(f"{binding.scope}:{binding.key}")
        if missing:
            raise ValueError(
                "plugin scoped frontend options must declare matching plugin settings: "
                + ", ".join(missing)
            )
        if invalid_project_mappings:
            raise ValueError(
                "plugin project options can only apply to declared session options: "
                + ", ".join(invalid_project_mappings)
            )
        return self

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
        for agent in self.agents:
            values.extend(agent.required_permissions)
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
            description=self.description,
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
