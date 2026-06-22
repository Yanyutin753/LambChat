"""Host-declared plugin extension slot contract."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class ExtensionHostSlot:
    """One controlled surface where folder plugins may declare contributions."""

    id: str
    manifest_key: str
    area: str
    description: str
    disabled_behavior: str
    supports_visible_when: bool = False
    renderer_registry: str | None = None
    data_scope: str | None = None

    def model_dump(self) -> dict[str, object]:
        return asdict(self)


EXTENSION_HOST_SLOTS: tuple[ExtensionHostSlot, ...] = (
    ExtensionHostSlot(
        id="app.route",
        manifest_key="app_tabs",
        area="app_route",
        description="Top-level plugin application route such as /feedback, /agent-team, or /usage.",
        disabled_behavior="Route and navigation entry are omitted from executable contributions.",
        supports_visible_when=True,
    ),
    ExtensionHostSlot(
        id="app.panel",
        manifest_key="app_panels",
        area="panel",
        description="Renderer for a plugin-owned application panel.",
        disabled_behavior="Panel contribution is omitted; direct route access falls back to host routing guards.",
        supports_visible_when=True,
        renderer_registry="pluginPanelRenderers",
    ),
    ExtensionHostSlot(
        id="nav.sidebar",
        manifest_key="sidebar_items",
        area="sidebar_more_menu",
        description="Sidebar or more-menu navigation item contributed by a plugin.",
        disabled_behavior="Navigation item is omitted.",
        supports_visible_when=True,
    ),
    ExtensionHostSlot(
        id="nav.user_menu",
        manifest_key="user_menu_items",
        area="user_menu",
        description="User or admin menu item contributed by a plugin.",
        disabled_behavior="Menu item is omitted.",
        supports_visible_when=True,
    ),
    ExtensionHostSlot(
        id="message.action",
        manifest_key="message_actions",
        area="message_action",
        description="Message-level action such as Feedback buttons on assistant messages.",
        disabled_behavior="Message action is omitted.",
        supports_visible_when=True,
        renderer_registry="MESSAGE_ACTION_RENDERERS",
    ),
    ExtensionHostSlot(
        id="chat.input_option",
        manifest_key="chat_input_options",
        area="chat_input_option",
        description="Feature-menu button or shortcut contributed to the chat input.",
        disabled_behavior="Input option and shortcut are omitted.",
        supports_visible_when=True,
    ),
    ExtensionHostSlot(
        id="chat.input_panel",
        manifest_key="chat_input_panels",
        area="chat_input_panel",
        description="Panel opened by a plugin chat input option, such as the Agent Team picker.",
        disabled_behavior="Panel renderer is omitted and cannot be opened by contribution id.",
        supports_visible_when=True,
        renderer_registry="CHAT_INPUT_PANEL_RENDERERS",
    ),
    ExtensionHostSlot(
        id="chat.mention_provider",
        manifest_key="mention_providers",
        area="mention_provider",
        description="Mention search provider for chat input triggers.",
        disabled_behavior="Mention provider is omitted.",
        supports_visible_when=True,
        renderer_registry="PLUGIN_MENTION_PROVIDER_RENDERERS",
    ),
    ExtensionHostSlot(
        id="chat.welcome_surface",
        manifest_key="welcome_surfaces",
        area="welcome_surface",
        description="Welcome-page surface rendered for a matching agent context.",
        disabled_behavior="Welcome surface is omitted.",
        supports_visible_when=True,
        renderer_registry="WELCOME_SURFACE_RENDERERS",
    ),
    ExtensionHostSlot(
        id="chat.assistant_identity",
        manifest_key="assistant_identity_resolvers",
        area="assistant_identity_resolver",
        description="Assistant identity resolver for plugin-owned agent contexts.",
        disabled_behavior="Identity resolver is omitted.",
        supports_visible_when=True,
        renderer_registry="ASSISTANT_IDENTITY_RESOLVERS",
    ),
    ExtensionHostSlot(
        id="agent.category",
        manifest_key="agent_categories",
        area="agent_category",
        description="Agent catalog category contributed by a plugin.",
        disabled_behavior="Category is omitted.",
        supports_visible_when=True,
    ),
    ExtensionHostSlot(
        id="backend.route",
        manifest_key="backend.routes",
        area="backend_route",
        description="Plugin-owned backend API route mounted through the runtime route registry.",
        disabled_behavior="Route execution is guarded by runtime state and fails closed.",
    ),
    ExtensionHostSlot(
        id="agent.catalog_entry",
        manifest_key="backend.agents",
        area="agent_catalog_entry",
        description="Plugin-owned agent catalog entry exposed through the runtime agent registry.",
        disabled_behavior="Agent is hidden and backend execution guard fails closed.",
    ),
    ExtensionHostSlot(
        id="tool.internal",
        manifest_key="backend.tools",
        area="tool",
        description="Plugin-owned internal tool exposed to the controlled tool registry.",
        disabled_behavior="Tool is hidden and execution guard fails closed.",
    ),
    ExtensionHostSlot(
        id="tool.result_renderer",
        manifest_key="tool_renderers",
        area="tool_renderer",
        description="Frontend renderer mapping for plugin-owned tool results.",
        disabled_behavior="Renderer is omitted from executable contributions.",
    ),
    ExtensionHostSlot(
        id="file.viewer",
        manifest_key="file_viewers",
        area="file_viewer",
        description="File preview capability declared by a plugin.",
        disabled_behavior="Viewer is omitted and the host falls back to core preview behavior.",
    ),
    ExtensionHostSlot(
        id="upload.handler",
        manifest_key="upload_handlers",
        area="upload_handler",
        description="Upload type or preprocessing capability declared by a plugin; metadata-only in the current phase.",
        disabled_behavior="Upload handler metadata is omitted and core upload behavior remains in effect.",
    ),
    ExtensionHostSlot(
        id="skill.importer",
        manifest_key="skill_importers",
        area="skill_importer",
        description="Skill import source such as GitHub or ZIP.",
        disabled_behavior="Importer entry is omitted.",
    ),
    ExtensionHostSlot(
        id="channel.connector",
        manifest_key="channel_connectors",
        area="channel_connector",
        description="External channel connector type declared by a plugin.",
        disabled_behavior="Connector is hidden and channel runtime guard fails closed.",
        renderer_registry="CHANNEL_CONNECTOR_PANEL_RENDERERS",
    ),
    ExtensionHostSlot(
        id="settings.system",
        manifest_key="settings",
        area="plugin_setting",
        description="System-scoped plugin setting rendered in the plugin page.",
        disabled_behavior="Setting remains editable but is not effective while the plugin is disabled.",
        supports_visible_when=True,
        data_scope="system",
    ),
    ExtensionHostSlot(
        id="settings.project",
        manifest_key="project_options",
        area="project_option",
        description="Project-scoped plugin option rendered by host project UIs.",
        disabled_behavior="Saved value is retained; executable contribution is omitted unless inactive options are requested.",
        supports_visible_when=True,
        data_scope="project",
    ),
    ExtensionHostSlot(
        id="settings.session",
        manifest_key="session_options",
        area="session_option",
        description="Session-scoped plugin option stored in the plugin namespace.",
        disabled_behavior="Saved value is retained; executable contribution is omitted.",
        supports_visible_when=True,
        data_scope="session",
    ),
    ExtensionHostSlot(
        id="settings.channel",
        manifest_key="channel_options",
        area="channel_option",
        description="Channel-scoped plugin option for connector UIs and channel execution.",
        disabled_behavior="Saved value is retained; executable contribution is omitted unless inactive options are requested.",
        supports_visible_when=True,
        data_scope="channel",
    ),
    ExtensionHostSlot(
        id="settings.scheduled_task",
        manifest_key="scheduled_task_options",
        area="scheduled_task_option",
        description="Scheduled-task scoped plugin option for task configuration.",
        disabled_behavior="Saved value is retained; executable contribution is omitted unless inactive options are requested.",
        supports_visible_when=True,
        data_scope="scheduled_task",
    ),
    ExtensionHostSlot(
        id="frontend.legacy_route",
        manifest_key="routes",
        area="frontend_route",
        description="Legacy frontend route marker retained for package compatibility.",
        disabled_behavior="Legacy marker is omitted from executable contributions.",
    ),
    ExtensionHostSlot(
        id="frontend.legacy_panel",
        manifest_key="panels",
        area="panel",
        description="Legacy frontend panel marker retained for package compatibility.",
        disabled_behavior="Legacy marker is omitted from executable contributions.",
    ),
    ExtensionHostSlot(
        id="frontend.legacy_nav_item",
        manifest_key="nav_items",
        area="nav_item",
        description="Legacy frontend nav marker retained for package compatibility.",
        disabled_behavior="Legacy marker is omitted from executable contributions.",
    ),
    ExtensionHostSlot(
        id="settings.section",
        manifest_key="settings_sections",
        area="settings_section",
        description="Settings section marker contributed by a plugin.",
        disabled_behavior="Settings section marker is omitted.",
    ),
    ExtensionHostSlot(
        id="i18n.namespace",
        manifest_key="i18n_namespaces",
        area="i18n_namespace",
        description="Frontend translation namespace required by a plugin.",
        disabled_behavior="Namespace contribution is omitted.",
    ),
    ExtensionHostSlot(
        id="permission.frontend_required",
        manifest_key="required_permissions",
        area="permission",
        description="Frontend permission hints required by plugin-owned UI contributions.",
        disabled_behavior="Permission hint is omitted with the plugin contribution.",
    ),
    ExtensionHostSlot(
        id="resource.ledger",
        manifest_key="resources",
        area="resource",
        description="Plugin-owned resource declaration used for ownership and uninstall dry-run.",
        disabled_behavior="Resource ledger is retained and dry-run remains available.",
    ),
    ExtensionHostSlot(
        id="lifecycle.hook",
        manifest_key="backend.lifespan_hooks",
        area="lifecycle_hook",
        description="Controlled startup or shutdown hook declared by a plugin.",
        disabled_behavior="Hook is not executed for non-executable plugins.",
    ),
    ExtensionHostSlot(
        id="runtime.effect",
        manifest_key="backend.runtime_effects",
        area="runtime_effect",
        description="Controlled enable/disable side effect declared by a plugin.",
        disabled_behavior="Effect is not executed unless the runtime state transition requests it.",
    ),
    ExtensionHostSlot(
        id="scheduler.job",
        manifest_key="backend.scheduler_jobs",
        area="scheduler_job",
        description="Plugin-owned scheduled job declared for guarded scheduler dispatch.",
        disabled_behavior="Scheduler guard skips or rejects the job while the plugin is not executable.",
    ),
    ExtensionHostSlot(
        id="event.listener",
        manifest_key="backend.event_listeners",
        area="listener",
        description="Plugin-owned pub/sub or event listener declared for guarded dispatch.",
        disabled_behavior="Listener guard skips or rejects dispatch while the plugin is not executable.",
    ),
    ExtensionHostSlot(
        id="migration.script",
        manifest_key="backend.migrations",
        area="plugin_migration_script",
        description="Plugin migration script declaration for reviewed local package upgrades.",
        disabled_behavior="Migration declarations remain metadata and are not executed for disabled plugins.",
    ),
    ExtensionHostSlot(
        id="plugin.asset_slot",
        manifest_key="frontend/dist/plugin-assets.json",
        area="plugin_asset_slot",
        description="Static frontend asset bundle mounted from a local plugin package.",
        disabled_behavior="Asset metadata and static serving are guarded by runtime state.",
    ),
)


FRONTEND_MANIFEST_CONTRIBUTION_KEYS: frozenset[str] = frozenset(
    slot.manifest_key
    for slot in EXTENSION_HOST_SLOTS
    if "." not in slot.manifest_key
    and "/" not in slot.manifest_key
    and slot.manifest_key not in {"settings", "resources"}
)


STRUCTURED_FRONTEND_MANIFEST_KEYS: frozenset[str] = frozenset(
    {
        "app_tabs",
        "app_panels",
        "sidebar_items",
        "user_menu_items",
        "chat_input_options",
        "chat_input_panels",
        "mention_providers",
        "welcome_surfaces",
        "assistant_identity_resolvers",
        "agent_categories",
        "project_options",
        "session_options",
        "channel_options",
        "scheduled_task_options",
    }
)


STRUCTURED_OR_LEGACY_STRING_FRONTEND_MANIFEST_KEYS: frozenset[str] = frozenset(
    {
        "tool_renderers",
        "file_viewers",
        "upload_handlers",
        "skill_importers",
        "channel_connectors",
        "message_actions",
    }
)


BACKEND_PLUGIN_MANIFEST_KEYS: frozenset[str] = frozenset(
    slot.manifest_key.removeprefix("backend.")
    for slot in EXTENSION_HOST_SLOTS
    if slot.manifest_key.startswith("backend.")
) | frozenset({"routers"})


CONTROLLED_FRONTEND_REFERENCES: dict[str, frozenset[str]] = {
    "app_panels.renderer": frozenset(
        {
            "agent_team.TeamBuilderPanel",
            "feedback.FeedbackPanel",
            "usage_reports.UsagePanel",
        }
    ),
    "message_actions.renderer": frozenset({"feedback.FeedbackButtons"}),
    "chat_input_options.selected_renderer": frozenset({"agent_team.SelectedTeamChip"}),
    "chat_input_panels.renderer": frozenset({"agent_team.TeamPickerModal"}),
    "mention_providers.provider": frozenset({"agent_team.searchTeams"}),
    "welcome_surfaces.renderer": frozenset({"agent_team.TeamWelcomeSurface"}),
    "assistant_identity_resolvers.resolver": frozenset({"agent_team.TeamAssistantIdentity"}),
    "project_options.renderer": frozenset({"agent_team.TeamSelectOption"}),
    "session_options.renderer": frozenset({"agent_team.TeamSelectOption"}),
    "channel_options.renderer": frozenset({"agent_team.TeamSelectOption"}),
    "scheduled_task_options.renderer": frozenset({"agent_team.TeamSelectOption"}),
    "channel_connectors.panel_renderer": frozenset({"feishu_connector.FeishuPanel"}),
}


CONTROLLED_FRONTEND_REFERENCE_FIELDS: dict[str, tuple[str, ...]] = {
    "app_panels": ("renderer",),
    "message_actions": ("renderer",),
    "chat_input_options": ("selected_renderer",),
    "chat_input_panels": ("renderer",),
    "mention_providers": ("provider",),
    "welcome_surfaces": ("renderer",),
    "assistant_identity_resolvers": ("resolver",),
    "project_options": ("renderer",),
    "session_options": ("renderer",),
    "channel_options": ("renderer",),
    "scheduled_task_options": ("renderer",),
    "channel_connectors": ("panel_renderer",),
}
