import type { PluginRuntimePlugin } from "../../types";

export function formatToolLabel(tool: PluginRuntimePlugin["tools"][number]): string {
  if (tool.legacy_ids.length === 0) return tool.name;
  return `${tool.name} (${tool.legacy_ids.join(" / ")})`;
}

export function formatChatInputOptionLabel(
  option: PluginRuntimePlugin["frontend"]["chat_input_options"][number],
  prefix: string,
): string {
  const effects = option.suppresses_core_persona_selector
    ? " suppresses core persona selector"
    : "";
  return `${prefix} ${option.id}${effects}`;
}

function contributionId(value: string | { id: string }): string {
  return typeof value === "string" ? value : value.id;
}

export function formatToolRendererContribution(
  value: PluginRuntimePlugin["frontend"]["tool_renderers"][number],
): string {
  const tools = typeof value === "string" ? [] : value.tool_names ?? [];
  return tools.length > 0
    ? `${contributionId(value)} (${tools.join(" / ")})`
    : contributionId(value);
}

export function formatFileViewerContribution(
  value: PluginRuntimePlugin["frontend"]["file_viewers"][number],
): string {
  const extensions = typeof value === "string" ? [] : value.extensions ?? [];
  return extensions.length > 0
    ? `${contributionId(value)} (${extensions.join(" / ")})`
    : contributionId(value);
}

export function formatSkillImporterContribution(
  value: PluginRuntimePlugin["frontend"]["skill_importers"][number],
): string {
  return typeof value === "string" ? value : `${value.id} (${value.source})`;
}

export function formatChannelConnectorContribution(
  value: PluginRuntimePlugin["frontend"]["channel_connectors"][number],
): string {
  return typeof value === "string" ? value : `${value.id} (${value.channel_type})`;
}

export function uniqueValues(values: readonly string[]): string[] {
  return Array.from(new Set(values.filter(Boolean)));
}

function legacyFrontendDeclarationLabels(plugin: PluginRuntimePlugin): string[] {
  return uniqueValues([
    ...plugin.frontend.routes.map((value) => `frontend route ${value}`),
    ...plugin.frontend.panels.map((value) => `panel ${value}`),
    ...plugin.frontend.nav_items.map((value) => `nav ${value}`),
  ]);
}

function structuredFrontendDeclarationLabels(plugin: PluginRuntimePlugin): string[] {
  const assetSlots = plugin.package?.frontend_assets?.slots ?? [];
  return uniqueValues([
    ...plugin.frontend.app_tabs.map((value) => `app tab ${value.path || value.tab}`),
    ...plugin.frontend.app_panels.map((value) => `app panel ${value.renderer}`),
    ...plugin.frontend.sidebar_items.map((value) => `sidebar ${value.path}`),
    ...plugin.frontend.user_menu_items.map((value) => `user menu ${value.path}`),
    ...plugin.frontend.chat_input_options.map((value) =>
      formatChatInputOptionLabel(value, "chat option"),
    ),
    ...plugin.frontend.chat_input_panels.map((value) => `chat panel ${value.renderer}`),
    ...plugin.frontend.mention_providers.map((value) => `mention ${value.mode}`),
    ...plugin.frontend.welcome_surfaces.map((value) => `welcome surface ${value.renderer}`),
    ...plugin.frontend.project_options.map((value) => `project option ${plugin.plugin_id}.${value.key}`),
    ...plugin.frontend.session_options.map((value) => `session option ${plugin.plugin_id}.${value.key}`),
    ...(plugin.frontend.channel_options ?? []).map((value) => `channel option ${plugin.plugin_id}.${value.key}`),
    ...plugin.frontend.tool_renderers.map((value) => `renderer ${formatToolRendererContribution(value)}`),
    ...plugin.frontend.file_viewers.map((value) => `viewer ${formatFileViewerContribution(value)}`),
    ...plugin.frontend.skill_importers.map((value) => `importer ${formatSkillImporterContribution(value)}`),
    ...plugin.frontend.channel_connectors.map((value) => `connector ${formatChannelConnectorContribution(value)}`),
    ...plugin.frontend.message_actions.map((value) => `message action ${value.id}`),
    ...plugin.frontend.assistant_identity_resolvers.map((value) => `assistant identity ${value.resolver}`),
    ...plugin.frontend.agent_categories.map((value) => `agent category ${value.id}`),
    ...plugin.frontend.scheduled_task_options.map((value) => `scheduled task option ${plugin.plugin_id}.${value.key}`),
    ...plugin.frontend.settings_sections.map((value) => `settings ${value}`),
    ...plugin.frontend.i18n_namespaces.map((value) => `i18n ${value}`),
    ...assetSlots.map((value) => `asset slot ${value}`),
  ]);
}

function frontendDeclarationLabels(plugin: PluginRuntimePlugin): string[] {
  return uniqueValues([
    ...structuredFrontendDeclarationLabels(plugin),
    ...legacyFrontendDeclarationLabels(plugin),
  ]);
}

export function structuredFrontendContributionCount(plugin: PluginRuntimePlugin): number {
  return (
    plugin.frontend.app_tabs.length +
    plugin.frontend.app_panels.length +
    plugin.frontend.sidebar_items.length +
    plugin.frontend.user_menu_items.length +
    plugin.frontend.chat_input_options.length +
    plugin.frontend.chat_input_panels.length +
    plugin.frontend.mention_providers.length +
    plugin.frontend.welcome_surfaces.length +
    plugin.frontend.project_options.length +
    plugin.frontend.session_options.length +
    (plugin.frontend.channel_options ?? []).length +
    plugin.frontend.scheduled_task_options.length +
    plugin.frontend.tool_renderers.length +
    plugin.frontend.file_viewers.length +
    plugin.frontend.skill_importers.length +
    plugin.frontend.channel_connectors.length +
    plugin.frontend.message_actions.length +
    plugin.frontend.assistant_identity_resolvers.length +
    plugin.frontend.agent_categories.length +
    plugin.frontend.settings_sections.length +
    plugin.frontend.i18n_namespaces.length +
    (plugin.package?.frontend_assets?.slots.length ?? 0)
  );
}

export function legacyFrontendContributionCount(plugin: PluginRuntimePlugin): number {
  return (
    plugin.frontend.routes.length +
    plugin.frontend.panels.length +
    plugin.frontend.nav_items.length
  );
}

export function declaredRuntimeEntryLabels(plugin: PluginRuntimePlugin): string[] {
  return uniqueValues([
    ...plugin.routes.map((route) => `route ${route.prefix}`),
    ...plugin.agents.map((agent) => `agent ${agent.id}`),
    ...plugin.tools.map((tool) => `tool ${formatToolLabel(tool)}`),
    ...frontendDeclarationLabels(plugin),
  ]);
}

export function resourceActionLabels(values: Record<string, number>): string[] {
  return Object.entries(values).map(([action, count]) => `${action}: ${count}`);
}

export function pluginContributionLabels(plugin: PluginRuntimePlugin): string[] {
  return uniqueValues([
    ...plugin.routes.map((route) => `API ${route.prefix}`),
    ...plugin.agents.map((agent) => `Agent ${agent.id}`),
    ...plugin.tools.map((tool) => `Tool ${formatToolLabel(tool)}`),
    ...legacyFrontendDeclarationLabels(plugin).map((label) => `Legacy ${label}`),
    ...plugin.frontend.app_tabs.map((value) => `App Tab ${value.path || value.tab}`),
    ...plugin.frontend.app_panels.map((value) => `App Panel ${value.renderer}`),
    ...plugin.frontend.sidebar_items.map((value) => `Sidebar ${value.path}`),
    ...plugin.frontend.user_menu_items.map((value) => `User Menu ${value.path}`),
    ...plugin.frontend.chat_input_options.map((value) =>
      formatChatInputOptionLabel(value, "Chat Option"),
    ),
    ...plugin.frontend.chat_input_panels.map((value) => `Chat Panel ${value.renderer}`),
    ...plugin.frontend.message_actions.map((value) => `Message Action ${value.id}`),
    ...plugin.frontend.mention_providers.map((value) => `Mention ${value.mode}`),
    ...plugin.frontend.welcome_surfaces.map((value) => `Welcome Surface ${value.renderer}`),
    ...plugin.frontend.assistant_identity_resolvers.map((value) => `Assistant Identity ${value.resolver}`),
    ...plugin.frontend.agent_categories.map((value) => `Agent Category ${value.id}`),
    ...plugin.frontend.project_options.map((value) => `Project Option ${plugin.plugin_id}.${value.key}`),
    ...plugin.frontend.session_options.map((value) => `Session Option ${plugin.plugin_id}.${value.key}`),
    ...(plugin.frontend.channel_options ?? []).map((value) => `Channel Option ${plugin.plugin_id}.${value.key}`),
    ...plugin.frontend.scheduled_task_options.map((value) => `Scheduled Task Option ${plugin.plugin_id}.${value.key}`),
    ...plugin.frontend.tool_renderers.map((value) => `Renderer ${formatToolRendererContribution(value)}`),
    ...plugin.frontend.file_viewers.map((value) => `Viewer ${formatFileViewerContribution(value)}`),
    ...plugin.frontend.skill_importers.map((value) => `Importer ${formatSkillImporterContribution(value)}`),
    ...plugin.frontend.channel_connectors.map((value) => `Connector ${formatChannelConnectorContribution(value)}`),
    ...plugin.frontend.settings_sections.map((value) => `Settings ${value}`),
    ...plugin.frontend.i18n_namespaces.map((value) => `I18n ${value}`),
    ...(plugin.package?.frontend_assets?.slots ?? []).map((value) => `Asset Slot ${value}`),
  ]);
}

export interface PluginContributionGroup {
  id: string;
  title: string;
  entries: string[];
}

export function pluginContributionGroups(plugin: PluginRuntimePlugin): PluginContributionGroup[] {
  const assetSlots = plugin.package?.frontend_assets?.slots ?? [];
  const groups: PluginContributionGroup[] = [
    {
      id: "backend",
      title: "Backend",
      entries: uniqueValues([
        ...plugin.routes.map((route) => `API ${route.prefix} -> ${route.module}`),
        ...plugin.tools.map((tool) => `Tool ${formatToolLabel(tool)} -> ${tool.module}`),
        ...plugin.permissions.map((permission) => `Permission ${permission}`),
      ]),
    },
    {
      id: "app-ui",
      title: "App UI",
      entries: uniqueValues([
        ...plugin.frontend.app_tabs.map((value) => `Tab ${value.path || value.tab}`),
        ...plugin.frontend.app_panels.map((value) => `Panel ${value.renderer}`),
        ...plugin.frontend.sidebar_items.map((value) => `Sidebar ${value.path}`),
        ...plugin.frontend.user_menu_items.map((value) => `User Menu ${value.path}`),
        ...plugin.frontend.message_actions.map((value) => `Message Action ${value.id}`),
      ]),
    },
    {
      id: "chat-ui",
      title: "Chat UI",
      entries: uniqueValues([
        ...plugin.frontend.chat_input_options.map((value) =>
          formatChatInputOptionLabel(value, "Chat Option"),
        ),
        ...plugin.frontend.chat_input_panels.map((value) => `Chat Panel ${value.renderer}`),
        ...plugin.frontend.mention_providers.map((value) => `Mention ${value.mode} -> ${value.provider}`),
        ...plugin.frontend.welcome_surfaces.map((value) => `Welcome ${value.agent_id} -> ${value.renderer}`),
        ...plugin.frontend.assistant_identity_resolvers.map((value) => `Assistant Identity ${value.agent_id} -> ${value.resolver}`),
      ]),
    },
    {
      id: "agent",
      title: "Agent",
      entries: uniqueValues([
        ...plugin.agents.map((agent) => `Agent ${agent.id} -> ${agent.module}`),
        ...plugin.frontend.agent_categories.map((value) => `Category ${value.id}`),
      ]),
    },
    {
      id: "scoped-options",
      title: "Scoped Options",
      entries: uniqueValues([
        ...plugin.frontend.project_options.map((value) => `Project ${plugin.plugin_id}.${value.key}`),
        ...plugin.frontend.session_options.map((value) => `Session ${plugin.plugin_id}.${value.key}`),
        ...(plugin.frontend.channel_options ?? []).map((value) => `Channel ${plugin.plugin_id}.${value.key}`),
        ...plugin.frontend.scheduled_task_options.map((value) => `Scheduled Task ${plugin.plugin_id}.${value.key}`),
      ]),
    },
    {
      id: "integrations",
      title: "Integrations",
      entries: uniqueValues([
        ...plugin.frontend.tool_renderers.map((value) => `Tool Renderer ${formatToolRendererContribution(value)}`),
        ...plugin.frontend.file_viewers.map((value) => `File Viewer ${formatFileViewerContribution(value)}`),
        ...plugin.frontend.skill_importers.map((value) => `Skill Importer ${formatSkillImporterContribution(value)}`),
        ...plugin.frontend.channel_connectors.map((value) => `Channel Connector ${formatChannelConnectorContribution(value)}`),
      ]),
    },
    {
      id: "assets-config",
      title: "Assets And Config",
      entries: uniqueValues([
        ...plugin.frontend.settings_sections.map((value) => `Settings Section ${value}`),
        ...plugin.frontend.i18n_namespaces.map((value) => `I18n ${value}`),
        ...assetSlots.map((value) => `Asset Slot ${value}`),
        ...(plugin.package?.data_template.exists
          ? [plugin.package.layout.data_template || plugin.package.data_template.template || "plugin-data-template"]
          : []),
        ...(plugin.package?.layout.has_config_schema ? ["config/schema.json"] : []),
        ...(plugin.package?.layout.has_config_defaults ? ["config/defaults.json"] : []),
        ...(plugin.package?.layout.has_resources ? ["resources/resources.yaml"] : []),
      ]),
    },
    {
      id: "legacy",
      title: "Legacy Compatibility",
      entries: legacyFrontendDeclarationLabels(plugin),
    },
  ];
  return groups.filter((group) => group.entries.length > 0);
}
