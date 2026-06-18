import type { LucideIcon } from "lucide-react";
import {
  BarChart3,
  Bell,
  Brain,
  MessageCircle,
  Server,
  Settings,
  Settings2,
  Shield,
  Sparkles,
  Plug,
  UserRound,
  Users,
} from "lucide-react";
import { Permission } from "../types";
import type { SettingCategory } from "../types/settings";
import type { TabType } from "../components/layout/AppContent/types";
import {
  FEEDBACK_APP_ROUTE_CONTRIBUTION,
  FEEDBACK_FRONTEND_PLUGIN_CONTRIBUTIONS,
  FEEDBACK_MESSAGE_ACTION_CONTRIBUTION,
  FEEDBACK_USER_MENU_CONTRIBUTION,
} from "../plugins/feedback/contributions";

export type CoreContributionArea =
  | "app_route"
  | "panel"
  | "sidebar_more_menu"
  | "user_menu"
  | "settings_section"
  | "tool_renderer"
  | "file_viewer"
  | "skill_importer"
  | "channel_connector"
  | "message_action"
  | "plugin_asset_slot"
  | "i18n_namespace";

export interface CoreAppRouteContribution {
  id: Exclude<TabType, "chat">;
  pluginId?: string;
  insertAfterId?: Exclude<TabType, "chat">;
  path: string;
  seoPath?: string;
  seoTitle: string;
  seoDescription: string;
  tab: Exclude<TabType, "chat">;
  permissions?: Permission[];
  redirectTo?: string;
  showNoPermissionToast?: boolean;
  area: "app_route";
}

export interface CorePanelContribution {
  id: Exclude<TabType, "chat">;
  pluginId?: string;
  tab: Exclude<TabType, "chat">;
  area: "panel";
}

export interface CoreSidebarNavContribution {
  id: string;
  pluginId?: string;
  path: string;
  labelKey: string;
  fallbackLabel?: string;
  icon: LucideIcon;
  requiredAnyPermissions?: Permission[];
  requiresSetting?: "memory";
  area: "sidebar_more_menu";
}

export interface CoreUserMenuContribution {
  id: string;
  pluginId?: string;
  path: string;
  labelKey: string;
  icon: LucideIcon;
  requiredAnyPermissions: Permission[];
  group: "admin" | "system";
  area: "user_menu";
}

export interface CoreSettingsSectionContribution {
  id: SettingCategory;
  category: SettingCategory;
  area: "settings_section";
}

export interface CoreToolRendererContribution {
  id: string;
  toolNames: readonly string[];
  area: "tool_renderer";
}

export interface CoreFileViewerContribution {
  id: string;
  extensions: readonly string[];
  area: "file_viewer";
}

export interface CoreSkillImporterContribution {
  id: string;
  source: "github" | "zip";
  area: "skill_importer";
}

export interface CoreChannelConnectorContribution {
  id: string;
  pluginId: string;
  channelType: string;
  area: "channel_connector";
}

export interface CoreMessageActionContribution {
  id: string;
  pluginId: string;
  action: "feedback";
  area: "message_action";
}

export interface CoreI18nNamespaceContribution {
  id: string;
  pluginId: string;
  namespace: string;
  area: "i18n_namespace";
}

export interface CorePluginAssetSlotContribution {
  id: string;
  pluginId: string;
  slot: string;
  assetSchema: string;
  assets: readonly string[];
  mountPath: string;
  area: "plugin_asset_slot";
}

export interface BuiltinPluginToolRendererContribution
  extends CoreToolRendererContribution {
  pluginId: string;
}

export interface BuiltinPluginFileViewerContribution
  extends CoreFileViewerContribution {
  pluginId: string;
}

export interface BuiltinPluginSkillImporterContribution
  extends CoreSkillImporterContribution {
  pluginId: string;
}

export interface PluginRuntimeContributionState {
  plugin_id: string;
  enabled: boolean;
  executable: boolean;
  status: string;
  tools?: Array<{
    name: string;
    legacy_ids?: string[];
  }>;
  frontend?: {
    routes?: string[];
    panels?: string[];
    nav_items?: string[];
    tool_renderers?: string[];
    file_viewers?: string[];
    skill_importers?: string[];
    channel_connectors?: string[];
    message_actions?: string[];
    i18n_namespaces?: string[];
  };
  package?: {
    frontend_assets?: {
      plugin_id: string;
      asset_schema: string;
      slots: string[];
      assets: string[];
      phase: string;
    } | null;
  };
}

export type PluginRuntimeContributionStates =
  | readonly PluginRuntimeContributionState[]
  | undefined;

export interface PluginContributionSnapshot {
  appRoutes: readonly string[];
  panels: readonly string[];
  sidebarMoreItems: readonly string[];
  userMenuItems: readonly string[];
  toolRenderers: readonly string[];
  fileViewers: readonly string[];
  skillImporters: readonly string[];
  channelConnectors: readonly string[];
  messageActions: readonly string[];
  pluginAssetSlots: readonly string[];
  i18nNamespaces: readonly string[];
}

export interface PluginContributionPreview {
  current: PluginContributionSnapshot;
  simulatedDisabled: PluginContributionSnapshot;
  removedWhenDisabled: PluginContributionSnapshot;
}

export const CORE_APP_ROUTES: readonly CoreAppRouteContribution[] = [
  {
    id: "skills",
    path: "/skills",
    seoTitle: "seo.skills.title",
    seoDescription: "seo.skills.description",
    tab: "skills",
    permissions: [Permission.SKILL_READ, Permission.MARKETPLACE_READ],
    redirectTo: "/chat",
    showNoPermissionToast: true,
    area: "app_route",
  },
  {
    id: "marketplace",
    path: "/marketplace",
    seoTitle: "seo.marketplace.title",
    seoDescription: "seo.marketplace.description",
    tab: "marketplace",
    permissions: [Permission.SKILL_READ, Permission.MARKETPLACE_READ],
    redirectTo: "/chat",
    showNoPermissionToast: true,
    area: "app_route",
  },
  {
    id: "plugins",
    path: "/plugins",
    seoTitle: "seo.plugins.title",
    seoDescription: "seo.plugins.description",
    tab: "plugins",
    permissions: [Permission.MARKETPLACE_READ],
    redirectTo: "/chat",
    showNoPermissionToast: true,
    area: "app_route",
  },
  {
    id: "mcp",
    path: "/mcp",
    seoTitle: "seo.mcp.title",
    seoDescription: "seo.mcp.description",
    tab: "mcp",
    permissions: [Permission.MCP_READ],
    redirectTo: "/chat",
    showNoPermissionToast: true,
    area: "app_route",
  },
  {
    id: "users",
    path: "/users",
    seoTitle: "seo.users.title",
    seoDescription: "seo.users.description",
    tab: "users",
    permissions: [Permission.USER_READ],
    redirectTo: "/chat",
    showNoPermissionToast: true,
    area: "app_route",
  },
  {
    id: "roles",
    path: "/roles",
    seoTitle: "seo.roles.title",
    seoDescription: "seo.roles.description",
    tab: "roles",
    permissions: [Permission.ROLE_MANAGE],
    redirectTo: "/chat",
    showNoPermissionToast: true,
    area: "app_route",
  },
  {
    id: "settings",
    path: "/settings",
    seoTitle: "seo.settings.title",
    seoDescription: "seo.settings.description",
    tab: "settings",
    permissions: [Permission.SETTINGS_MANAGE],
    redirectTo: "/chat",
    showNoPermissionToast: true,
    area: "app_route",
  },
  {
    id: "channels",
    path: "/channels/:channelType?/:instanceId?",
    seoPath: "/channels",
    seoTitle: "seo.channels.title",
    seoDescription: "seo.channels.description",
    tab: "channels",
    permissions: [Permission.CHANNEL_READ],
    redirectTo: "/chat",
    showNoPermissionToast: true,
    area: "app_route",
  },
  {
    id: "agents",
    path: "/agents",
    seoTitle: "seo.agents.title",
    seoDescription: "seo.agents.description",
    tab: "agents",
    area: "app_route",
  },
  {
    id: "persona",
    path: "/persona",
    seoTitle: "seo.persona.title",
    seoDescription: "seo.persona.description",
    tab: "persona",
    area: "app_route",
  },
  {
    id: "files",
    path: "/files",
    seoTitle: "seo.files.title",
    seoDescription: "seo.files.description",
    tab: "files",
    area: "app_route",
  },
  {
    id: "notifications",
    path: "/notifications",
    seoTitle: "seo.notifications.title",
    seoDescription: "seo.notifications.description",
    tab: "notifications",
    permissions: [Permission.NOTIFICATION_MANAGE],
    redirectTo: "/chat",
    showNoPermissionToast: true,
    area: "app_route",
  },
  {
    id: "memory",
    path: "/memory",
    seoTitle: "seo.memory.title",
    seoDescription: "seo.memory.description",
    tab: "memory",
    area: "app_route",
  },
  {
    id: "scheduled-tasks",
    path: "/scheduled-tasks",
    seoTitle: "seo.scheduledTasks.title",
    seoDescription: "seo.scheduledTasks.description",
    tab: "scheduled-tasks",
    permissions: [Permission.SCHEDULED_TASK_READ],
    redirectTo: "/chat",
    showNoPermissionToast: true,
    area: "app_route",
  },
];

export const CORE_PANEL_CONTRIBUTIONS: readonly CorePanelContribution[] =
  CORE_APP_ROUTES.map((route) => ({
    id: route.id,
    tab: route.tab,
    area: "panel" as const,
  }));

export const BUILTIN_PLUGIN_APP_ROUTES: readonly CoreAppRouteContribution[] = [
  FEEDBACK_APP_ROUTE_CONTRIBUTION,
  {
    id: "team",
    pluginId: "agent_team",
    insertAfterId: "agents",
    path: "/team",
    seoTitle: "seo.team.title",
    seoDescription: "seo.team.description",
    tab: "team",
    permissions: [Permission.TEAM_READ],
    area: "app_route",
  },
  {
    id: "usage",
    pluginId: "usage_reports",
    insertAfterId: "scheduled-tasks",
    path: "/usage",
    seoTitle: "seo.usage.title",
    seoDescription: "seo.usage.description",
    tab: "usage",
    permissions: [Permission.USAGE_READ],
    redirectTo: "/chat",
    showNoPermissionToast: true,
    area: "app_route",
  },
];

const BUILTIN_PLUGIN_APP_ROUTE_BY_CONTRIBUTION_ID: Readonly<
  Record<string, CoreAppRouteContribution>
> = {
  "feedback-route": FEEDBACK_APP_ROUTE_CONTRIBUTION,
  "agent_team:team-route": BUILTIN_PLUGIN_APP_ROUTES.find(
    (route) => route.id === "team",
  )!,
  "usage_reports:usage-route": BUILTIN_PLUGIN_APP_ROUTES.find(
    (route) => route.id === "usage",
  )!,
};

export const BUILTIN_PLUGIN_PANEL_CONTRIBUTIONS: readonly CorePanelContribution[] =
  BUILTIN_PLUGIN_APP_ROUTES.map((route) => ({
    id: route.id,
    tab: route.tab,
    area: "panel" as const,
  }));

export const BUILTIN_PLUGIN_MESSAGE_ACTIONS: readonly CoreMessageActionContribution[] = [
  FEEDBACK_MESSAGE_ACTION_CONTRIBUTION,
];

export const APP_ROUTE_CONTRIBUTIONS: readonly CoreAppRouteContribution[] = [
  ...buildAppRouteContributions(),
] as const;

export const PANEL_CONTRIBUTIONS: readonly CorePanelContribution[] =
  buildPanelContributions();

export const CORE_SIDEBAR_MORE_NAV: readonly CoreSidebarNavContribution[] = [
  {
    id: "persona",
    path: "/persona",
    labelKey: "personaPresets.title",
    fallbackLabel: "角色广场",
    icon: UserRound,
    area: "sidebar_more_menu",
  },
  {
    id: "skills",
    path: "/skills",
    labelKey: "nav.skills",
    icon: Sparkles,
    requiredAnyPermissions: [Permission.SKILL_READ],
    area: "sidebar_more_menu",
  },
  {
    id: "plugins",
    path: "/plugins",
    labelKey: "nav.plugins",
    icon: Plug,
    requiredAnyPermissions: [Permission.MARKETPLACE_READ],
    area: "sidebar_more_menu",
  },
  {
    id: "mcp",
    path: "/mcp",
    labelKey: "nav.mcp",
    icon: Server,
    requiredAnyPermissions: [Permission.MCP_READ],
    area: "sidebar_more_menu",
  },
  {
    id: "channels",
    path: "/channels",
    labelKey: "nav.channels",
    icon: MessageCircle,
    requiredAnyPermissions: [Permission.CHANNEL_READ],
    area: "sidebar_more_menu",
  },
  {
    id: "memory",
    path: "/memory",
    labelKey: "nav.memory",
    icon: Brain,
    requiresSetting: "memory",
    area: "sidebar_more_menu",
  },
];

export const BUILTIN_PLUGIN_SIDEBAR_MORE_NAV: readonly CoreSidebarNavContribution[] = [
  {
    id: "team",
    pluginId: "agent_team",
    path: "/team",
    labelKey: "nav.team",
    fallbackLabel: "团队构建",
    icon: Users,
    requiredAnyPermissions: [Permission.TEAM_READ],
    area: "sidebar_more_menu",
  },
];

const BUILTIN_PLUGIN_SIDEBAR_MORE_NAV_BY_CONTRIBUTION_ID: Readonly<
  Record<string, CoreSidebarNavContribution>
> = {
  "agent_team:team-nav": BUILTIN_PLUGIN_SIDEBAR_MORE_NAV[0],
};

export const CORE_USER_MENU_ITEMS: readonly CoreUserMenuContribution[] = [
  {
    id: "users",
    path: "/users",
    labelKey: "nav.users",
    icon: Users,
    requiredAnyPermissions: [Permission.USER_READ, Permission.USER_WRITE],
    group: "admin",
    area: "user_menu",
  },
  {
    id: "roles",
    path: "/roles",
    labelKey: "nav.roles",
    icon: Shield,
    requiredAnyPermissions: [Permission.ROLE_MANAGE],
    group: "admin",
    area: "user_menu",
  },
  {
    id: "agents",
    path: "/agents",
    labelKey: "nav.agents",
    icon: Settings2,
    requiredAnyPermissions: [Permission.AGENT_ADMIN, Permission.MODEL_ADMIN],
    group: "admin",
    area: "user_menu",
  },
  {
    id: "notifications",
    path: "/notifications",
    labelKey: "nav.notifications",
    icon: Bell,
    requiredAnyPermissions: [Permission.NOTIFICATION_MANAGE],
    group: "system",
    area: "user_menu",
  },
  {
    id: "settings",
    path: "/settings",
    labelKey: "nav.systemSettings",
    icon: Settings,
    requiredAnyPermissions: [Permission.SETTINGS_MANAGE],
    group: "system",
    area: "user_menu",
  },
];

export const BUILTIN_PLUGIN_USER_MENU_ITEMS: readonly CoreUserMenuContribution[] = [
  FEEDBACK_USER_MENU_CONTRIBUTION,
  {
    id: "usage",
    pluginId: "usage_reports",
    path: "/usage",
    labelKey: "nav.usage",
    icon: BarChart3,
    requiredAnyPermissions: [Permission.USAGE_READ],
    group: "system",
    area: "user_menu",
  },
];

const BUILTIN_PLUGIN_USER_MENU_BY_CONTRIBUTION_ID: Readonly<
  Record<string, CoreUserMenuContribution>
> = {
  "feedback-nav": FEEDBACK_USER_MENU_CONTRIBUTION,
  "usage_reports:usage-menu": BUILTIN_PLUGIN_USER_MENU_ITEMS.find(
    (item) => item.id === "usage",
  )!,
};

export { FEEDBACK_FRONTEND_PLUGIN_CONTRIBUTIONS };

export const USER_MENU_CONTRIBUTIONS: readonly CoreUserMenuContribution[] = [
  ...buildUserMenuContributions(),
] as const;

function isBuiltinPluginContributionEnabled(
  pluginId: string,
  runtimePlugins: PluginRuntimeContributionStates,
): boolean {
  if (!runtimePlugins) return true;
  const runtimePlugin = runtimePlugins.find((plugin) => plugin.plugin_id === pluginId);
  return Boolean(runtimePlugin?.enabled && runtimePlugin.executable);
}

function filterBuiltinPluginContributions<T extends { id: string }>(
  contributions: readonly T[],
  runtimePlugins: PluginRuntimeContributionStates,
): T[] {
  return contributions.filter((contribution) =>
    isBuiltinPluginContributionEnabled(
      "pluginId" in contribution && typeof contribution.pluginId === "string"
        ? contribution.pluginId
        : contribution.id,
      runtimePlugins,
    ),
  );
}

export function buildAppRouteContributions(
  runtimePlugins?: PluginRuntimeContributionStates,
): readonly CoreAppRouteContribution[] {
  const pluginRoutes = runtimePlugins
    ? runtimePlugins.flatMap((plugin) => {
        if (!plugin.enabled || !plugin.executable) return [];
        return (plugin.frontend?.routes ?? []).flatMap((routeId) => {
          const route = BUILTIN_PLUGIN_APP_ROUTE_BY_CONTRIBUTION_ID[routeId];
          if (!route) return [];
          return [route];
        });
      })
    : filterBuiltinPluginContributions(BUILTIN_PLUGIN_APP_ROUTES, runtimePlugins);
  return CORE_APP_ROUTES.reduce<CoreAppRouteContribution[]>((routes, coreRoute) => {
    routes.push(coreRoute);
    routes.push(
      ...pluginRoutes.filter(
        (pluginRoute) => pluginRoute.insertAfterId === coreRoute.id,
      ),
    );
    return routes;
  }, [
    ...pluginRoutes.filter((pluginRoute) => !pluginRoute.insertAfterId),
  ]);
}

export function buildPanelContributions(
  runtimePlugins?: PluginRuntimeContributionStates,
): readonly CorePanelContribution[] {
  if (runtimePlugins) {
    const declaredPanelIds = new Set(
      runtimePlugins.flatMap((plugin) =>
        plugin.enabled && plugin.executable ? (plugin.frontend?.panels ?? []) : [],
      ),
    );
    return buildAppRouteContributions(runtimePlugins)
      .filter((route) => {
        if (!route.pluginId) return true;
        return declaredPanelIds.has(`${route.pluginId}:${route.id}-panel`) ||
          declaredPanelIds.has(`${route.pluginId}:${route.id}`) ||
          declaredPanelIds.has(`${route.pluginId}:${route.tab}-panel`) ||
          declaredPanelIds.has(`${route.pluginId}:${route.tab}`) ||
          declaredPanelIds.has(route.id) ||
          declaredPanelIds.has(`${route.id}-panel`);
      })
      .map((route) => ({
        id: route.id,
        tab: route.tab,
        area: "panel" as const,
      }));
  }
  return buildAppRouteContributions(runtimePlugins).map((route) => ({
    id: route.id,
    tab: route.tab,
    area: "panel" as const,
  }));
}

export function buildUserMenuContributions(
  runtimePlugins?: PluginRuntimeContributionStates,
): readonly CoreUserMenuContribution[] {
  const pluginMenuItems = runtimePlugins
    ? runtimePlugins.flatMap((plugin) => {
        if (!plugin.enabled || !plugin.executable) return [];
        return (plugin.frontend?.nav_items ?? []).flatMap((itemId) => {
          const item = BUILTIN_PLUGIN_USER_MENU_BY_CONTRIBUTION_ID[itemId];
          if (!item) return [];
          return [item];
        });
      })
    : filterBuiltinPluginContributions(BUILTIN_PLUGIN_USER_MENU_ITEMS, runtimePlugins);
  return [
    ...CORE_USER_MENU_ITEMS.slice(0, 3),
    ...pluginMenuItems,
    ...CORE_USER_MENU_ITEMS.slice(3),
  ];
}

export function buildSidebarMoreNavContributions(
  runtimePlugins?: PluginRuntimeContributionStates,
): readonly CoreSidebarNavContribution[] {
  const pluginNavItems = runtimePlugins
    ? runtimePlugins.flatMap((plugin) => {
        if (!plugin.enabled || !plugin.executable) return [];
        return (plugin.frontend?.nav_items ?? []).flatMap((itemId) => {
          const item = BUILTIN_PLUGIN_SIDEBAR_MORE_NAV_BY_CONTRIBUTION_ID[itemId];
          if (!item) return [];
          return [item];
        });
      })
    : filterBuiltinPluginContributions(BUILTIN_PLUGIN_SIDEBAR_MORE_NAV, runtimePlugins);
  return [
    ...CORE_SIDEBAR_MORE_NAV.slice(0, 1),
    ...pluginNavItems,
    ...CORE_SIDEBAR_MORE_NAV.slice(1),
  ];
}

function snapshotContributions(
  runtimePlugins?: PluginRuntimeContributionStates,
): PluginContributionSnapshot {
  return {
    appRoutes: buildAppRouteContributions(runtimePlugins).map(
      (route) => route.path,
    ),
    panels: buildPanelContributions(runtimePlugins).map((panel) => panel.tab),
    sidebarMoreItems: buildSidebarMoreNavContributions(runtimePlugins).map(
      (item) => item.path,
    ),
    userMenuItems: buildUserMenuContributions(runtimePlugins).map(
      (item) => item.path,
    ),
    toolRenderers: buildToolRendererContributions(runtimePlugins).map(
      (renderer) => renderer.id,
    ),
    fileViewers: buildFileViewerContributions(runtimePlugins).map(
      (viewer) => viewer.id,
    ),
    skillImporters: buildSkillImporterContributions(runtimePlugins).map(
      (importer) => importer.id,
    ),
    channelConnectors: buildChannelConnectorContributions(runtimePlugins).map(
      (connector) => connector.id,
    ),
    messageActions: buildMessageActionContributions(runtimePlugins).map(
      (action) => action.id,
    ),
    pluginAssetSlots: buildPluginAssetSlotContributions(runtimePlugins).map(
      (slot) => slot.id,
    ),
    i18nNamespaces: buildI18nNamespaceContributions(runtimePlugins).map(
      (namespace) => namespace.id,
    ),
  };
}

function removedValues(
  current: readonly string[],
  simulatedDisabled: readonly string[],
): readonly string[] {
  const disabled = new Set(simulatedDisabled);
  return current.filter((item) => !disabled.has(item));
}

export function buildPluginContributionPreview(
  pluginId: string,
  runtimePlugins?: PluginRuntimeContributionStates,
): PluginContributionPreview {
  const current = snapshotContributions(runtimePlugins);
  const states = runtimePlugins ? [...runtimePlugins] : [];
  const existingIndex = states.findIndex((plugin) => plugin.plugin_id === pluginId);
  const disabledState: PluginRuntimeContributionState = {
    plugin_id: pluginId,
    enabled: false,
    executable: false,
    status: "disabled",
  };

  if (existingIndex >= 0) {
    states[existingIndex] = { ...states[existingIndex], ...disabledState };
  } else {
    states.push(disabledState);
  }

  const simulatedDisabled = snapshotContributions(states);
  return {
    current,
    simulatedDisabled,
    removedWhenDisabled: {
      appRoutes: removedValues(current.appRoutes, simulatedDisabled.appRoutes),
      panels: removedValues(current.panels, simulatedDisabled.panels),
      sidebarMoreItems: removedValues(
        current.sidebarMoreItems,
        simulatedDisabled.sidebarMoreItems,
      ),
      userMenuItems: removedValues(
        current.userMenuItems,
        simulatedDisabled.userMenuItems,
      ),
      toolRenderers: removedValues(
        current.toolRenderers,
        simulatedDisabled.toolRenderers,
      ),
      fileViewers: removedValues(current.fileViewers, simulatedDisabled.fileViewers),
      skillImporters: removedValues(
        current.skillImporters,
        simulatedDisabled.skillImporters,
      ),
      channelConnectors: removedValues(
        current.channelConnectors,
        simulatedDisabled.channelConnectors,
      ),
      messageActions: removedValues(
        current.messageActions,
        simulatedDisabled.messageActions,
      ),
      pluginAssetSlots: removedValues(
        current.pluginAssetSlots,
        simulatedDisabled.pluginAssetSlots,
      ),
      i18nNamespaces: removedValues(
        current.i18nNamespaces,
        simulatedDisabled.i18nNamespaces,
      ),
    },
  };
}

const CORE_SETTING_CATEGORIES = [
  "frontend",
  "agent",
  "llm",
  "session",
  "mongodb",
  "redis",
  "checkpoint",
  "long_term_storage",
  "memory",
  "memory_embedding",
  "memory_search",
  "memory_storage",
  "security",
  "email",
  "captcha",
  "s3",
  "file_upload",
  "sandbox",
  "skills",
  "tools",
  "audio_transcription",
  "tracing",
  "user",
  "oauth",
] satisfies readonly SettingCategory[];

export const CORE_SETTINGS_SECTIONS: readonly CoreSettingsSectionContribution[] =
  CORE_SETTING_CATEGORIES.map((category) => ({
    id: category,
    category,
    area: "settings_section" as const,
  }));

export const CORE_TOOL_RENDERERS: readonly CoreToolRendererContribution[] = [
  { id: "read-file", toolNames: ["read_file"], area: "tool_renderer" },
  { id: "reveal-file", toolNames: ["reveal_file"], area: "tool_renderer" },
  { id: "reveal-project", toolNames: ["reveal_project"], area: "tool_renderer" },
  { id: "edit-file", toolNames: ["edit_file"], area: "tool_renderer" },
  { id: "write-file", toolNames: ["write_file"], area: "tool_renderer" },
  { id: "grep", toolNames: ["grep"], area: "tool_renderer" },
  { id: "ls", toolNames: ["ls"], area: "tool_renderer" },
  { id: "glob", toolNames: ["glob"], area: "tool_renderer" },
  { id: "execute", toolNames: ["execute"], area: "tool_renderer" },
  {
    id: "scheduled-task",
    toolNames: [
      "scheduled_task_create",
      "scheduled_task_list",
      "scheduled_task_update",
      "scheduled_task_delete",
    ],
    area: "tool_renderer",
  },
  {
    id: "env-var",
    toolNames: ["env_var_list", "env_var_set", "env_var_delete"],
    area: "tool_renderer",
  },
  { id: "persona", toolNames: ["save_persona_preset"], area: "tool_renderer" },
  {
    id: "sandbox-mcp",
    toolNames: ["sandbox_mcp_add", "sandbox_mcp_update", "sandbox_mcp_remove"],
    area: "tool_renderer",
  },
  { id: "memory-recall", toolNames: ["memory_recall"], area: "tool_renderer" },
  {
    id: "memory-store",
    toolNames: ["memory_retain", "memory_delete"],
    area: "tool_renderer",
  },
  { id: "ask-human", toolNames: ["ask_human"], area: "tool_renderer" },
  { id: "search-tools", toolNames: ["search_tools"], area: "tool_renderer" },
];

export const BUILTIN_PLUGIN_TOOL_RENDERERS: readonly BuiltinPluginToolRendererContribution[] = [
  {
    id: "agent-team",
    pluginId: "agent_team",
    toolNames: ["search_persona_presets", "create_agent_team"],
    area: "tool_renderer",
  },
  {
    id: "image-generate",
    pluginId: "image_generation",
    toolNames: ["image_generate"],
    area: "tool_renderer",
  },
  {
    id: "audio-transcribe",
    pluginId: "audio_transcription",
    toolNames: ["audio_transcribe"],
    area: "tool_renderer",
  },
];

export const BUILTIN_PLUGIN_FILE_VIEWERS: readonly BuiltinPluginFileViewerContribution[] = [
  {
    id: "pdf",
    pluginId: "advanced_file_viewers",
    extensions: ["pdf"],
    area: "file_viewer",
  },
  {
    id: "ppt",
    pluginId: "advanced_file_viewers",
    extensions: ["ppt", "pptx"],
    area: "file_viewer",
  },
  {
    id: "word",
    pluginId: "advanced_file_viewers",
    extensions: ["docx"],
    area: "file_viewer",
  },
  {
    id: "excel",
    pluginId: "advanced_file_viewers",
    extensions: ["xls", "xlsx", "csv"],
    area: "file_viewer",
  },
  {
    id: "cad",
    pluginId: "advanced_file_viewers",
    extensions: ["dxf", "dwg"],
    area: "file_viewer",
  },
  {
    id: "excalidraw",
    pluginId: "advanced_file_viewers",
    extensions: ["excalidraw"],
    area: "file_viewer",
  },
  {
    id: "html",
    pluginId: "advanced_file_viewers",
    extensions: ["html", "htm"],
    area: "file_viewer",
  },
  {
    id: "markdown",
    pluginId: "advanced_file_viewers",
    extensions: ["md", "markdown"],
    area: "file_viewer",
  },
  {
    id: "code",
    pluginId: "advanced_file_viewers",
    extensions: ["*"],
    area: "file_viewer",
  },
];

const BUILTIN_PLUGIN_FILE_VIEWER_EXTENSIONS: Readonly<Record<string, readonly string[]>> = {
  pdf: ["pdf"],
  ppt: ["ppt", "pptx"],
  word: ["docx"],
  excel: ["xls", "xlsx", "csv"],
  cad: ["dxf", "dwg"],
  excalidraw: ["excalidraw"],
  html: ["html", "htm"],
  markdown: ["md", "markdown"],
  code: ["*"],
};

const BUILTIN_PLUGIN_SKILL_IMPORTER_SOURCES: Readonly<
  Record<string, CoreSkillImporterContribution["source"]>
> = {
  "github-import": "github",
};

const BUILTIN_PLUGIN_CHANNEL_CONNECTOR_TYPES: Readonly<Record<string, string>> = {
  feishu: "feishu",
};

const BUILTIN_PLUGIN_MESSAGE_ACTION_BY_ID: Readonly<
  Record<string, CoreMessageActionContribution>
> = {
  "feedback:message-feedback": FEEDBACK_MESSAGE_ACTION_CONTRIBUTION,
};

export const BUILTIN_PLUGIN_SKILL_IMPORTERS: readonly BuiltinPluginSkillImporterContribution[] = [
  {
    id: "github-import",
    pluginId: "github_installer",
    source: "github",
    area: "skill_importer",
  },
];

export const BUILTIN_PLUGIN_CHANNEL_CONNECTORS: readonly CoreChannelConnectorContribution[] = [
  {
    id: "feishu_connector:feishu",
    pluginId: "feishu_connector",
    channelType: "feishu",
    area: "channel_connector",
  },
];

export const BUILTIN_PLUGIN_I18N_NAMESPACES: readonly CoreI18nNamespaceContribution[] = [
  {
    id: "advanced_file_viewers:documents",
    pluginId: "advanced_file_viewers",
    namespace: "advanced_file_viewers:documents",
    area: "i18n_namespace",
  },
  {
    id: "github_installer:skills",
    pluginId: "github_installer",
    namespace: "github_installer:skills",
    area: "i18n_namespace",
  },
  {
    id: "feishu_connector:channels",
    pluginId: "feishu_connector",
    namespace: "feishu_connector:channels",
    area: "i18n_namespace",
  },
];

export function buildToolRendererContributions(
  runtimePlugins?: PluginRuntimeContributionStates,
): readonly CoreToolRendererContribution[] {
  if (runtimePlugins) {
    return [
      ...CORE_TOOL_RENDERERS,
      ...runtimePlugins.flatMap((plugin) => {
        if (!plugin.enabled || !plugin.executable) return [];
        const rendererIds = plugin.frontend?.tool_renderers ?? [];
        const toolNames = plugin.tools?.flatMap((tool) => [
          tool.name,
          ...(tool.legacy_ids ?? []),
        ]) ?? [];
        return rendererIds.map((qualifiedId) => ({
          id: unqualifiedContributionId(qualifiedId, plugin.plugin_id),
          toolNames,
          area: "tool_renderer" as const,
        }));
      }),
    ];
  }
  return [
    ...CORE_TOOL_RENDERERS,
    ...BUILTIN_PLUGIN_TOOL_RENDERERS.filter((renderer) =>
      isBuiltinPluginContributionEnabled(renderer.pluginId, runtimePlugins),
    ),
  ];
}

export function buildFileViewerContributions(
  runtimePlugins?: PluginRuntimeContributionStates,
): readonly CoreFileViewerContribution[] {
  if (runtimePlugins) {
    return runtimePlugins.flatMap((plugin) => {
      if (!plugin.enabled || !plugin.executable) return [];
      return (plugin.frontend?.file_viewers ?? []).flatMap((qualifiedId) => {
        const id = unqualifiedContributionId(qualifiedId, plugin.plugin_id);
        const extensions = BUILTIN_PLUGIN_FILE_VIEWER_EXTENSIONS[id];
        if (!extensions) return [];
        return [
          {
            id,
            extensions,
            area: "file_viewer" as const,
          },
        ];
      });
    });
  }
  return BUILTIN_PLUGIN_FILE_VIEWERS.filter((viewer) =>
    isBuiltinPluginContributionEnabled(viewer.pluginId, runtimePlugins),
  );
}

function unqualifiedContributionId(value: string, pluginId: string): string {
  const prefix = `${pluginId}:`;
  return value.startsWith(prefix) ? value.slice(prefix.length) : value;
}

export function buildSkillImporterContributions(
  runtimePlugins?: PluginRuntimeContributionStates,
): readonly CoreSkillImporterContribution[] {
  if (runtimePlugins) {
    return runtimePlugins.flatMap((plugin) => {
      if (!plugin.enabled || !plugin.executable) return [];
      return (plugin.frontend?.skill_importers ?? []).flatMap((qualifiedId) => {
        const id = unqualifiedContributionId(qualifiedId, plugin.plugin_id);
        const source = BUILTIN_PLUGIN_SKILL_IMPORTER_SOURCES[id];
        if (!source) return [];
        return [
          {
            id,
            source,
            area: "skill_importer" as const,
          },
        ];
      });
    });
  }
  return BUILTIN_PLUGIN_SKILL_IMPORTERS.filter((importer) =>
    isBuiltinPluginContributionEnabled(importer.pluginId, runtimePlugins),
  );
}

export function buildChannelConnectorContributions(
  runtimePlugins?: PluginRuntimeContributionStates,
): readonly CoreChannelConnectorContribution[] {
  if (runtimePlugins) {
    return runtimePlugins.flatMap((plugin) => {
      if (!plugin.enabled || !plugin.executable) return [];
      return (plugin.frontend?.channel_connectors ?? []).flatMap((qualifiedId) => {
        const id = unqualifiedContributionId(qualifiedId, plugin.plugin_id);
        const channelType = BUILTIN_PLUGIN_CHANNEL_CONNECTOR_TYPES[id];
        if (!channelType) return [];
        return [
          {
            id: qualifiedId,
            pluginId: plugin.plugin_id,
            channelType,
            area: "channel_connector" as const,
          },
        ];
      });
    });
  }
  return BUILTIN_PLUGIN_CHANNEL_CONNECTORS.filter((connector) =>
    isBuiltinPluginContributionEnabled(connector.pluginId, runtimePlugins),
  );
}

export function buildMessageActionContributions(
  runtimePlugins?: PluginRuntimeContributionStates,
): readonly CoreMessageActionContribution[] {
  if (runtimePlugins) {
    return runtimePlugins.flatMap((plugin) => {
      if (!plugin.enabled || !plugin.executable) return [];
      return (plugin.frontend?.message_actions ?? []).flatMap((actionId) => {
        const action = BUILTIN_PLUGIN_MESSAGE_ACTION_BY_ID[actionId];
        if (!action) return [];
        return [action];
      });
    });
  }
  return BUILTIN_PLUGIN_MESSAGE_ACTIONS.filter((action) =>
    isBuiltinPluginContributionEnabled(action.pluginId, runtimePlugins),
  );
}

export function buildI18nNamespaceContributions(
  runtimePlugins?: PluginRuntimeContributionStates,
): readonly CoreI18nNamespaceContribution[] {
  if (runtimePlugins) {
    return runtimePlugins.flatMap((plugin) => {
      if (!plugin.enabled || !plugin.executable) return [];
      return (plugin.frontend?.i18n_namespaces ?? []).map((namespace) => ({
        id: namespace,
        pluginId: plugin.plugin_id,
        namespace,
        area: "i18n_namespace" as const,
      }));
    });
  }
  return BUILTIN_PLUGIN_I18N_NAMESPACES.filter((namespace) =>
    isBuiltinPluginContributionEnabled(namespace.pluginId, runtimePlugins),
  );
}

export function buildPluginAssetSlotContributions(
  runtimePlugins?: PluginRuntimeContributionStates,
): readonly CorePluginAssetSlotContribution[] {
  if (!runtimePlugins) return [];
  return runtimePlugins.flatMap((plugin) => {
    const bundle = plugin.package?.frontend_assets;
    if (!plugin.enabled || !plugin.executable || !bundle) return [];
    if (bundle.plugin_id !== plugin.plugin_id) return [];
    return bundle.slots.map((slot) => ({
      id: `${plugin.plugin_id}:${slot}`,
      pluginId: plugin.plugin_id,
      slot,
      assetSchema: bundle.asset_schema,
      assets: bundle.assets,
      mountPath: `/plugin-assets/${plugin.plugin_id}/`,
      area: "plugin_asset_slot" as const,
    }));
  });
}

export function hasChannelConnectorContribution(
  channelType: string,
  runtimePlugins?: PluginRuntimeContributionStates,
): boolean {
  return buildChannelConnectorContributions(runtimePlugins).some(
    (connector) => connector.channelType === channelType,
  );
}

export function hasFileViewerContribution(
  viewerId: string,
  runtimePlugins?: PluginRuntimeContributionStates,
): boolean {
  return buildFileViewerContributions(runtimePlugins).some(
    (viewer) => viewer.id === viewerId,
  );
}

export function hasSkillImporterContribution(
  importerId: string,
  runtimePlugins?: PluginRuntimeContributionStates,
): boolean {
  return buildSkillImporterContributions(runtimePlugins).some(
    (importer) => importer.id === importerId,
  );
}

export function hasMessageActionContribution(
  action: CoreMessageActionContribution["action"],
  runtimePlugins?: PluginRuntimeContributionStates,
): boolean {
  return buildMessageActionContributions(runtimePlugins).some(
    (contribution) => contribution.action === action,
  );
}

export function hasPluginAssetSlotContribution(
  slot: string,
  runtimePlugins?: PluginRuntimeContributionStates,
): boolean {
  return buildPluginAssetSlotContributions(runtimePlugins).some(
    (contribution) => contribution.slot === slot,
  );
}

export function hasI18nNamespaceContribution(
  namespace: string,
  runtimePlugins?: PluginRuntimeContributionStates,
): boolean {
  return buildI18nNamespaceContributions(runtimePlugins).some(
    (contribution) => contribution.namespace === namespace,
  );
}

export function findCoreAppRoute(
  tab: TabType,
): CoreAppRouteContribution | undefined {
  if (tab === "chat") return undefined;
  return CORE_APP_ROUTES.find((route) => route.tab === tab);
}

export function findAppRouteContribution(
  tab: TabType,
): CoreAppRouteContribution | undefined {
  if (tab === "chat") return undefined;
  return APP_ROUTE_CONTRIBUTIONS.find((route) => route.tab === tab);
}

export function findCorePanelContribution(
  tab: TabType,
): CorePanelContribution | undefined {
  if (tab === "chat") return undefined;
  return CORE_PANEL_CONTRIBUTIONS.find((panel) => panel.tab === tab);
}

export function findPanelContribution(
  tab: TabType,
): CorePanelContribution | undefined {
  if (tab === "chat") return undefined;
  return PANEL_CONTRIBUTIONS.find((panel) => panel.tab === tab);
}

export function getCoreToolRenderer(
  toolName: string,
): CoreToolRendererContribution | undefined {
  return CORE_TOOL_RENDERERS.find((renderer) =>
    renderer.toolNames.includes(toolName),
  );
}

export function getToolRenderer(
  toolName: string,
  runtimePlugins?: PluginRuntimeContributionStates,
): CoreToolRendererContribution | undefined {
  return buildToolRendererContributions(runtimePlugins).find((renderer) =>
    renderer.toolNames.includes(toolName),
  );
}

export function getCoreToolRendererId(toolName: string): string | undefined {
  return getCoreToolRenderer(toolName)?.id;
}

export function getToolRendererId(
  toolName: string,
  runtimePlugins?: PluginRuntimeContributionStates,
): string | undefined {
  return getToolRenderer(toolName, runtimePlugins)?.id;
}

export function hasCoreToolRenderer(toolName: string): boolean {
  return getCoreToolRenderer(toolName) !== undefined;
}

export function hasToolRenderer(
  toolName: string,
  runtimePlugins?: PluginRuntimeContributionStates,
): boolean {
  return getToolRenderer(toolName, runtimePlugins) !== undefined;
}
