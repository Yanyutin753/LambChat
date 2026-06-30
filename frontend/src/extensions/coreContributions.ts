import type { LucideIcon } from "lucide-react";
import {
  BarChart3,
  Bell,
  Brain,
  Star,
  MessageCircle,
  Server,
  Settings,
  Settings2,
  Shield,
  Sparkles,
  Plug,
  UserRound,
  Workflow,
  Users,
} from "lucide-react";
import { Permission } from "../types";
import type { SettingCategory } from "../types/settings";
import type { TabType } from "../components/layout/AppContent/types";

export type CoreContributionArea =
  | "app_route"
  | "panel"
  | "sidebar_more_menu"
  | "user_menu"
  | "settings_section"
  | "tool_renderer"
  | "file_viewer"
  | "upload_handler"
  | "skill_importer"
  | "channel_connector"
  | "message_action"
  | "chat_input_option"
  | "chat_input_panel"
  | "mention_provider"
  | "welcome_surface"
  | "assistant_identity_resolver"
  | "agent_catalog_entry"
  | "agent_category"
  | "project_option"
  | "session_option"
  | "channel_option"
  | "scheduled_task_option"
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
  renderer?: string;
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

export interface CoreUploadHandlerContribution {
  id: string;
  pluginId: string;
  accept: readonly string[];
  maxBytes?: number | null;
  handler?: string | null;
  area: "upload_handler";
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
  panelRenderer?: string | null;
  area: "channel_connector";
}

export interface CoreMessageActionContribution {
  id: string;
  pluginId: string;
  target: "assistant_message" | "user_message" | "tool_result" | "shared_message" | string;
  renderer: string;
  order: number;
  permissions?: string[];
  visibleWhen?: PluginContributionVisibleWhen | null;
  area: "message_action";
}

export interface PluginContributionVisibilityContext {
  agentId?: string | null;
  route?: string | null;
  scope?: string | null;
  permissions?: readonly string[];
}

export interface PluginMessageActionContext extends PluginContributionVisibilityContext {
  target?: CoreMessageActionContribution["target"];
}

interface PluginContributionVisibleWhen {
  agent_id?: string | null;
  route?: string | null;
  scope?: string | null;
  permissions?: string[];
}

export interface PluginOptionBindingContribution {
  pluginId: string;
  key: string;
  scope: string;
}

interface PluginRuntimeAppTab {
  id: string;
  tab: string;
  path: string;
  label?: string;
  panel?: string | null;
  order: number;
  insert_after?: string | null;
  permissions?: string[];
  seo_title?: string;
  seo_description?: string;
  redirect_to?: string | null;
  show_no_permission_toast?: boolean;
  visible_when?: PluginContributionVisibleWhen | null;
}

interface PluginRuntimeAppPanel {
  id: string;
  tab: string;
  renderer: string;
  visible_when?: PluginContributionVisibleWhen | null;
}

interface PluginRuntimeSidebarItem {
  id: string;
  path: string;
  label: string;
  icon: string;
  order: number;
  permissions?: string[];
  visible_when?: PluginContributionVisibleWhen | null;
}

interface PluginRuntimeUserMenuItem extends PluginRuntimeSidebarItem {
  group: "admin" | "system";
}

interface PluginRuntimeMessageAction {
  id: string;
  target?: string;
  renderer: string;
  order?: number;
  permissions?: string[];
  visible_when?: PluginContributionVisibleWhen | null;
}

interface PluginRuntimeToolRenderer {
  id: string;
  tool_names?: string[];
}

interface PluginRuntimeFileViewer {
  id: string;
  extensions?: string[];
}

interface PluginRuntimeUploadHandler {
  id: string;
  accept?: string[];
  max_bytes?: number | null;
  handler?: string | null;
}

interface PluginRuntimeSkillImporter {
  id: string;
  source: "github" | "zip";
}

interface PluginRuntimeChannelConnector {
  id: string;
  channel_type: string;
  panel_renderer?: string | null;
}

export interface CoreChatInputOptionContribution {
  id: string;
  pluginId: string;
  slot: "enhance" | "settings" | "upload" | string;
  label: string;
  icon: string;
  panel?: string | null;
  selectedRenderer?: string | null;
  suppressesCorePersonaSelector: boolean;
  shortcut?: string | null;
  order: number;
  optionBinding?: PluginOptionBindingContribution | null;
  visibleWhen?: PluginContributionVisibleWhen | null;
  area: "chat_input_option";
}

export interface CoreChatInputPanelContribution {
  id: string;
  pluginId: string;
  renderer: string;
  createPath?: string | null;
  managePath?: string | null;
  optionBinding?: PluginOptionBindingContribution | null;
  visibleWhen?: PluginContributionVisibleWhen | null;
  area: "chat_input_panel";
}

export interface CoreMentionProviderContribution {
  id: string;
  pluginId: string;
  trigger: string;
  mode: string;
  provider: string;
  optionBinding?: PluginOptionBindingContribution | null;
  visibleWhen?: PluginContributionVisibleWhen | null;
  area: "mention_provider";
}

export interface CoreWelcomeSurfaceContribution {
  id: string;
  pluginId: string;
  agentId: string;
  renderer: string;
  order: number;
  optionBinding?: PluginOptionBindingContribution | null;
  visibleWhen?: PluginContributionVisibleWhen | null;
  area: "welcome_surface";
}

export interface CoreAssistantIdentityResolverContribution {
  id: string;
  pluginId: string;
  agentId: string;
  resolver: string;
  order: number;
  optionBinding?: PluginOptionBindingContribution | null;
  visibleWhen?: PluginContributionVisibleWhen | null;
  area: "assistant_identity_resolver";
}

export interface CoreAgentCategoryContribution {
  id: string;
  pluginId: string;
  label: string;
  description: string;
  icon: string;
  order: number;
  visibleWhen?: PluginContributionVisibleWhen | null;
  area: "agent_category";
}

export interface CoreAgentCatalogEntryContribution {
  id: string;
  pluginId: string;
  name: string;
  description: string;
  icon: string;
  category?: string | null;
  order: number;
  sortOrder: number;
  requiredPermissions: readonly string[];
  area: "agent_catalog_entry";
}

interface PluginRuntimeAgent {
  id: string;
  module?: string;
  name?: string;
  description?: string;
  icon?: string;
  sort_order?: number;
  category?: string | null;
  required_permissions?: string[];
}

export interface CoreScopedPluginOptionContribution {
  id: string;
  pluginId: string;
  pluginEnabled: boolean;
  effective: boolean;
  pluginStatus: string;
  key: string;
  type: "string" | "text" | "number" | "boolean" | "select" | "json" | string;
  label: string;
  description: string;
  defaultValue?: unknown;
  group: string;
  order: number;
  options?: string[] | null;
  jsonSchema?: Record<string, unknown> | null;
  renderer?: string | null;
  suppressesCorePersonaSelector: boolean;
  legacyPayloadKeys: readonly string[];
  appliesToSessionKey?: string | null;
  visibleWhen?: PluginContributionVisibleWhen | null;
  area: "project_option" | "session_option" | "channel_option" | "scheduled_task_option";
}

interface PluginRuntimeAgentCategory {
  id: string;
  label: string;
  description?: string;
  icon: string;
  order: number;
  visible_when?: PluginContributionVisibleWhen | null;
}

interface PluginRuntimeAssistantIdentityResolver {
  id: string;
  agent_id: string;
  resolver: string;
  order: number;
  option_binding?: PluginRuntimeOptionBinding | null;
  visible_when?: PluginContributionVisibleWhen | null;
}

interface PluginRuntimeScopedOption {
  key: string;
  type: string;
  label: string;
  description?: string;
  default?: unknown;
  group?: string;
  order: number;
  options?: string[] | null;
  json_schema?: Record<string, unknown> | null;
  renderer?: string | null;
  suppresses_core_persona_selector?: boolean;
  legacy_payload_keys?: string[];
  applies_to_session_key?: string | null;
  visible_when?: PluginContributionVisibleWhen | null;
}

interface PluginRuntimeOptionBinding {
  plugin_id?: string | null;
  key: string;
  scope?: string;
}

function optionBindingFromRuntime(
  pluginId: string,
  binding: PluginRuntimeOptionBinding | null | undefined,
): PluginOptionBindingContribution | null {
  if (!binding?.key) return null;
  return {
    pluginId: binding.plugin_id || pluginId,
    key: binding.key,
    scope: binding.scope || "session",
  };
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

export interface PluginRuntimeContributionState {
  plugin_id: string;
  enabled: boolean;
  executable: boolean;
  status: string;
  agents?: PluginRuntimeAgent[];
  tools?: Array<{
    name: string;
    legacy_ids?: string[];
  }>;
  frontend?: {
    routes?: string[];
    panels?: string[];
    nav_items?: string[];
    app_tabs?: PluginRuntimeAppTab[];
    app_panels?: PluginRuntimeAppPanel[];
    sidebar_items?: PluginRuntimeSidebarItem[];
    user_menu_items?: PluginRuntimeUserMenuItem[];
    tool_renderers?: Array<string | PluginRuntimeToolRenderer>;
    file_viewers?: Array<string | PluginRuntimeFileViewer>;
    upload_handlers?: Array<string | PluginRuntimeUploadHandler>;
    skill_importers?: Array<string | PluginRuntimeSkillImporter>;
    channel_connectors?: Array<string | PluginRuntimeChannelConnector>;
    message_actions?: Array<string | PluginRuntimeMessageAction>;
    chat_input_options?: Array<{
      id: string;
      slot: string;
      label: string;
      icon: string;
      panel?: string | null;
      selected_renderer?: string | null;
      suppresses_core_persona_selector?: boolean;
      shortcut?: string | null;
      order: number;
      option_binding?: PluginRuntimeOptionBinding | null;
      visible_when?: PluginContributionVisibleWhen | null;
    }>;
    chat_input_panels?: Array<{
      id: string;
      renderer: string;
      create_path?: string | null;
      manage_path?: string | null;
      option_binding?: PluginRuntimeOptionBinding | null;
      visible_when?: PluginContributionVisibleWhen | null;
    }>;
    mention_providers?: Array<{
      id: string;
      trigger: string;
      mode: string;
      provider: string;
      option_binding?: PluginRuntimeOptionBinding | null;
      visible_when?: PluginContributionVisibleWhen | null;
    }>;
    welcome_surfaces?: Array<{
      id: string;
      agent_id: string;
      renderer: string;
      order: number;
      option_binding?: PluginRuntimeOptionBinding | null;
      visible_when?: PluginContributionVisibleWhen | null;
    }>;
    assistant_identity_resolvers?: PluginRuntimeAssistantIdentityResolver[];
    agent_categories?: PluginRuntimeAgentCategory[];
    project_options?: PluginRuntimeScopedOption[];
    session_options?: PluginRuntimeScopedOption[];
    channel_options?: PluginRuntimeScopedOption[];
    scheduled_task_options?: PluginRuntimeScopedOption[];
    i18n_namespaces?: string[];
  } | null;
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
  chatInputOptions: readonly string[];
  chatInputPanels: readonly string[];
  mentionProviders: readonly string[];
  welcomeSurfaces: readonly string[];
  assistantIdentityResolvers: readonly string[];
  agentCatalogEntries: readonly string[];
  agentCategories: readonly string[];
  projectOptions: readonly string[];
  sessionOptions: readonly string[];
  channelOptions: readonly string[];
  scheduledTaskOptions: readonly string[];
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

export const USER_MENU_CONTRIBUTIONS: readonly CoreUserMenuContribution[] = [
  ...buildUserMenuContributions(),
] as const;

export function isRuntimePluginExecutable(plugin: PluginRuntimeContributionState): boolean {
  return Boolean(plugin.enabled && plugin.executable);
}

export function isRuntimePluginExecutableById(
  runtimePlugins: PluginRuntimeContributionStates,
  pluginId: string,
): boolean {
  const plugin = runtimePlugins?.find((item) => item.plugin_id === pluginId);
  return plugin ? isRuntimePluginExecutable(plugin) : false;
}

function matchesVisibleWhen(
  visibleWhen: PluginContributionVisibleWhen | null | undefined,
  context?: PluginContributionVisibilityContext,
): boolean {
  if (!visibleWhen) return true;
  if (
    visibleWhen.agent_id &&
    visibleWhen.agent_id !== (context?.agentId ?? null)
  ) {
    return false;
  }
  if (visibleWhen.route && visibleWhen.route !== (context?.route ?? null)) {
    return false;
  }
  if (visibleWhen.scope && visibleWhen.scope !== (context?.scope ?? null)) {
    return false;
  }
  if (visibleWhen.permissions?.length) {
    const available = new Set(context?.permissions ?? []);
    return visibleWhen.permissions.every((permission) => available.has(permission));
  }
  return true;
}

function sortByOrderThenId<T extends { order?: number; id: string }>(items: T[]): T[] {
  return items.sort((a, b) => (a.order ?? 100) - (b.order ?? 100) || a.id.localeCompare(b.id));
}

function asKnownTab(tab: string): Exclude<TabType, "chat"> | null {
  const normalized = tab.trim();
  if (!normalized || normalized === "chat") return null;
  return normalized as Exclude<TabType, "chat">;
}

function asPermissionValues(values: readonly string[] | undefined): Permission[] | undefined {
  if (!values?.length) return undefined;
  return values as Permission[];
}

function iconByName(name: string): LucideIcon {
  const icons: Record<string, LucideIcon> = {
    BarChart3,
    Plug,
    Star,
    Users,
    Workflow,
  };
  return icons[name] ?? Plug;
}

function menuIdFromPath(path: string, fallbackId: string, pluginId: string): string {
  const normalized = path.replace(/^\/+/, "").split(/[/?#]/)[0];
  return normalized || unqualifiedContributionId(fallbackId, pluginId);
}

function routeFromRuntimeAppTab(
  plugin: PluginRuntimeContributionState,
  tab: PluginRuntimeAppTab,
): CoreAppRouteContribution | null {
  const knownTab = asKnownTab(tab.tab);
  if (!knownTab) return null;
  return {
    id: knownTab,
    pluginId: plugin.plugin_id,
    insertAfterId: tab.insert_after ? asKnownTab(tab.insert_after) ?? undefined : undefined,
    path: tab.path,
    seoTitle: tab.seo_title || `seo.${knownTab}.title`,
    seoDescription: tab.seo_description || `seo.${knownTab}.description`,
    tab: knownTab,
    permissions: asPermissionValues(tab.permissions),
    redirectTo: tab.redirect_to ?? undefined,
    showNoPermissionToast: Boolean(tab.show_no_permission_toast),
    area: "app_route",
  };
}

function panelFromRuntimeAppPanel(
  plugin: PluginRuntimeContributionState,
  panel: PluginRuntimeAppPanel,
): CorePanelContribution | null {
  const knownTab = asKnownTab(panel.tab);
  if (!knownTab) return null;
  return {
    id: knownTab,
    pluginId: plugin.plugin_id,
    tab: knownTab,
    renderer: panel.renderer,
    area: "panel",
  };
}

function sidebarItemFromRuntime(
  plugin: PluginRuntimeContributionState,
  item: PluginRuntimeSidebarItem,
): CoreSidebarNavContribution {
  return {
    id: menuIdFromPath(item.path, item.id, plugin.plugin_id),
    pluginId: plugin.plugin_id,
    path: item.path,
    labelKey: item.label,
    icon: iconByName(item.icon),
    requiredAnyPermissions: asPermissionValues(item.permissions),
    area: "sidebar_more_menu",
  };
}

function userMenuItemFromRuntime(
  plugin: PluginRuntimeContributionState,
  item: PluginRuntimeUserMenuItem,
): CoreUserMenuContribution {
  return {
    id: menuIdFromPath(item.path, item.id, plugin.plugin_id),
    pluginId: plugin.plugin_id,
    path: item.path,
    labelKey: item.label,
    icon: iconByName(item.icon),
    requiredAnyPermissions: asPermissionValues(item.permissions) ?? [],
    group: item.group,
    area: "user_menu",
  };
}

function scopedOptionFromRuntime(
  plugin: PluginRuntimeContributionState,
  option: PluginRuntimeScopedOption,
  area: "project_option" | "session_option" | "channel_option" | "scheduled_task_option",
): CoreScopedPluginOptionContribution {
  return {
    id: `${plugin.plugin_id}.${option.key}`,
    pluginId: plugin.plugin_id,
    pluginEnabled: Boolean(plugin.enabled),
    effective: isRuntimePluginExecutable(plugin),
    pluginStatus: plugin.status,
    key: option.key,
    type: option.type,
    label: option.label,
    description: option.description ?? "",
    defaultValue: option.default,
    group: option.group ?? "general",
    order: option.order,
    options: option.options,
    jsonSchema: option.json_schema,
    renderer: option.renderer,
    suppressesCorePersonaSelector: Boolean(option.suppresses_core_persona_selector),
    legacyPayloadKeys: option.legacy_payload_keys ?? [],
    appliesToSessionKey: option.applies_to_session_key,
    visibleWhen: option.visible_when,
    area,
  };
}

export function buildAppRouteContributions(
  runtimePlugins?: PluginRuntimeContributionStates,
): readonly CoreAppRouteContribution[] {
  const pluginRoutes = runtimePlugins
    ? runtimePlugins.flatMap((plugin) => {
        if (!plugin.enabled || !plugin.executable) return [];
        const structuredRoutes = sortByOrderThenId(
          (plugin.frontend?.app_tabs ?? []).flatMap((tab) => {
            const route = routeFromRuntimeAppTab(plugin, tab);
            return route ? [route] : [];
          }),
        );
        return structuredRoutes;
      })
    : [];
  const routes = CORE_APP_ROUTES.reduce<CoreAppRouteContribution[]>((routes, coreRoute) => {
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
  const insertedRouteIds = new Set(routes.map((route) => route.id));
  const pendingRoutes = pluginRoutes.filter(
    (pluginRoute) => pluginRoute.insertAfterId && !insertedRouteIds.has(pluginRoute.id),
  );
  while (pendingRoutes.length > 0) {
    const pendingBefore = pendingRoutes.length;
    for (let index = pendingRoutes.length - 1; index >= 0; index -= 1) {
      const route = pendingRoutes[index];
      const insertIndex = routes.findIndex(
        (candidate) => candidate.id === route.insertAfterId,
      );
      if (insertIndex === -1) continue;
      routes.splice(insertIndex + 1, 0, route);
      insertedRouteIds.add(route.id);
      pendingRoutes.splice(index, 1);
    }
    if (pendingRoutes.length === pendingBefore) break;
  }
  routes.push(...pendingRoutes);
  return routes;
}

export function buildPanelContributions(
  runtimePlugins?: PluginRuntimeContributionStates,
): readonly CorePanelContribution[] {
  if (runtimePlugins) {
    const structuredPanels = runtimePlugins.flatMap((plugin) => {
      if (!plugin.enabled || !plugin.executable) return [];
      return (plugin.frontend?.app_panels ?? []).flatMap((panel) => {
        const contribution = panelFromRuntimeAppPanel(plugin, panel);
        return contribution ? [contribution] : [];
      });
    });
    if (structuredPanels.length) {
      const byTab = new Map(structuredPanels.map((panel) => [panel.tab, panel]));
      return buildAppRouteContributions(runtimePlugins).flatMap((route) => {
        if (!route.pluginId) {
          return [{ id: route.id, tab: route.tab, area: "panel" as const }];
        }
        const panel = byTab.get(route.tab);
        return panel ? [panel] : [];
      });
    }
    return buildAppRouteContributions(runtimePlugins)
      .filter((route) => !route.pluginId)
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
        const structuredItems = sortByOrderThenId(
          (plugin.frontend?.user_menu_items ?? [])
            .filter((item) => matchesVisibleWhen(item.visible_when))
            .map((item) => userMenuItemFromRuntime(plugin, item)),
        );
        return structuredItems;
      })
    : [];
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
        const structuredItems = sortByOrderThenId(
          (plugin.frontend?.sidebar_items ?? [])
            .filter((item) => matchesVisibleWhen(item.visible_when))
            .map((item) => sidebarItemFromRuntime(plugin, item)),
        );
        return structuredItems;
      })
    : [];
  return [
    ...CORE_SIDEBAR_MORE_NAV.slice(0, 1),
    ...pluginNavItems,
    ...CORE_SIDEBAR_MORE_NAV.slice(1),
  ];
}

function snapshotContributions(
  runtimePlugins?: PluginRuntimeContributionStates,
  context?: PluginContributionVisibilityContext,
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
    chatInputOptions: buildChatInputOptionContributions(runtimePlugins, context).map(
      (option) => option.id,
    ),
    chatInputPanels: buildChatInputPanelContributions(runtimePlugins, context).map(
      (panel) => panel.id,
    ),
    mentionProviders: buildMentionProviderContributions(runtimePlugins, context).map(
      (provider) => provider.id,
    ),
    welcomeSurfaces: buildWelcomeSurfaceContributions(runtimePlugins, context).map(
      (surface) => surface.id,
    ),
    assistantIdentityResolvers: buildAssistantIdentityResolverContributions(
      runtimePlugins,
      context,
    ).map((resolver) => resolver.id),
    agentCatalogEntries: buildAgentCatalogEntryContributions(runtimePlugins).map(
      (entry) => entry.id,
    ),
    agentCategories: buildAgentCategoryContributions(runtimePlugins).map(
      (category) => category.id,
    ),
    projectOptions: buildProjectOptionContributions(runtimePlugins, context).map(
      (option) => option.id,
    ),
    sessionOptions: buildSessionOptionContributions(runtimePlugins, context).map(
      (option) => option.id,
    ),
    channelOptions: buildChannelOptionContributions(runtimePlugins, context).map(
      (option) => option.id,
    ),
    scheduledTaskOptions: buildScheduledTaskOptionContributions(runtimePlugins, context).map(
      (option) => option.id,
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
  context?: PluginContributionVisibilityContext,
): PluginContributionPreview {
  const current = snapshotContributions(runtimePlugins, context);
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

  const simulatedDisabled = snapshotContributions(states, context);
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
      chatInputOptions: removedValues(
        current.chatInputOptions,
        simulatedDisabled.chatInputOptions,
      ),
      chatInputPanels: removedValues(
        current.chatInputPanels,
        simulatedDisabled.chatInputPanels,
      ),
      mentionProviders: removedValues(
        current.mentionProviders,
        simulatedDisabled.mentionProviders,
      ),
      welcomeSurfaces: removedValues(
        current.welcomeSurfaces,
        simulatedDisabled.welcomeSurfaces,
      ),
      assistantIdentityResolvers: removedValues(
        current.assistantIdentityResolvers,
        simulatedDisabled.assistantIdentityResolvers,
      ),
      agentCatalogEntries: removedValues(
        current.agentCatalogEntries,
        simulatedDisabled.agentCatalogEntries,
      ),
      agentCategories: removedValues(
        current.agentCategories,
        simulatedDisabled.agentCategories,
      ),
      projectOptions: removedValues(
        current.projectOptions,
        simulatedDisabled.projectOptions,
      ),
      sessionOptions: removedValues(
        current.sessionOptions,
        simulatedDisabled.sessionOptions,
      ),
      channelOptions: removedValues(
        current.channelOptions,
        simulatedDisabled.channelOptions,
      ),
      scheduledTaskOptions: removedValues(
        current.scheduledTaskOptions,
        simulatedDisabled.scheduledTaskOptions,
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

function runtimeMessageActionToContribution(
  plugin: PluginRuntimeContributionState,
  action: string | PluginRuntimeMessageAction,
): CoreMessageActionContribution | null {
  if (typeof action === "string") {
    return null;
  }
  return {
    id: action.id,
    pluginId: plugin.plugin_id,
    target: action.target ?? "assistant_message",
    renderer: action.renderer,
    order: action.order ?? 100,
    permissions: action.permissions,
    visibleWhen: action.visible_when,
    area: "message_action" as const,
  };
}

export function buildToolRendererContributions(
  runtimePlugins?: PluginRuntimeContributionStates,
): readonly CoreToolRendererContribution[] {
  if (runtimePlugins) {
    return [
      ...CORE_TOOL_RENDERERS,
      ...runtimePlugins.flatMap((plugin) => {
        if (!plugin.enabled || !plugin.executable) return [];
        return (plugin.frontend?.tool_renderers ?? []).flatMap((renderer) => {
          if (typeof renderer === "string") return [];
          return {
            id: unqualifiedContributionId(renderer.id, plugin.plugin_id),
            toolNames: renderer.tool_names ?? [],
            area: "tool_renderer" as const,
          };
        });
      }),
    ];
  }
  return CORE_TOOL_RENDERERS;
}

export function buildFileViewerContributions(
  runtimePlugins?: PluginRuntimeContributionStates,
): readonly CoreFileViewerContribution[] {
  if (runtimePlugins) {
    return runtimePlugins.flatMap((plugin) => {
      if (!plugin.enabled || !plugin.executable) return [];
      return (plugin.frontend?.file_viewers ?? []).flatMap((viewer) => {
        if (typeof viewer === "string") return [];
        const extensions = viewer.extensions ?? [];
        if (extensions.length === 0) return [];
        return [
          {
            id: unqualifiedContributionId(viewer.id, plugin.plugin_id),
            extensions,
            area: "file_viewer" as const,
          },
        ];
      });
    });
  }
  return [];
}

export function buildUploadHandlerContributions(
  runtimePlugins?: PluginRuntimeContributionStates,
): readonly CoreUploadHandlerContribution[] {
  if (runtimePlugins) {
    return runtimePlugins.flatMap((plugin) => {
      if (!plugin.enabled || !plugin.executable) return [];
      return (plugin.frontend?.upload_handlers ?? []).flatMap((handler) => {
        if (typeof handler === "string") return [];
        return [
          {
            id: handler.id,
            pluginId: plugin.plugin_id,
            accept: handler.accept ?? [],
            maxBytes: handler.max_bytes ?? null,
            handler: handler.handler ?? null,
            area: "upload_handler" as const,
          },
        ];
      });
    });
  }
  return [];
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
      return (plugin.frontend?.skill_importers ?? []).flatMap((importer) => {
        if (typeof importer === "string") return [];
        return [
          {
            id: unqualifiedContributionId(importer.id, plugin.plugin_id),
            source: importer.source,
            area: "skill_importer" as const,
          },
        ];
      });
    });
  }
  return [];
}

export function buildChannelConnectorContributions(
  runtimePlugins?: PluginRuntimeContributionStates,
): readonly CoreChannelConnectorContribution[] {
  if (runtimePlugins) {
    return runtimePlugins.flatMap((plugin) => {
      if (!plugin.enabled || !plugin.executable) return [];
      return (plugin.frontend?.channel_connectors ?? []).flatMap((connector) => {
        if (typeof connector === "string") return [];
        const channelType = connector.channel_type;
        if (!channelType) return [];
        return [
          {
            id: connector.id,
            pluginId: plugin.plugin_id,
            channelType,
            panelRenderer: connector.panel_renderer ?? null,
            area: "channel_connector" as const,
          },
        ];
      });
    });
  }
  return [];
}

export function buildMessageActionContributions(
  runtimePlugins?: PluginRuntimeContributionStates,
  context?: PluginMessageActionContext,
): readonly CoreMessageActionContribution[] {
  const matchesContext = (action: CoreMessageActionContribution) => {
    if (context?.target && action.target !== context.target) return false;
    return matchesVisibleWhen(action.visibleWhen, context);
  };
  if (runtimePlugins) {
    return sortByOrderThenId(runtimePlugins.flatMap((plugin) => {
      if (!plugin.enabled || !plugin.executable) return [];
      return (plugin.frontend?.message_actions ?? []).flatMap((action) => {
        const contribution = runtimeMessageActionToContribution(plugin, action);
        return contribution && matchesContext(contribution) ? [contribution] : [];
      });
    }));
  }
  return [];
}

export function buildChatInputOptionContributions(
  runtimePlugins?: PluginRuntimeContributionStates,
  context?: PluginContributionVisibilityContext,
): readonly CoreChatInputOptionContribution[] {
  if (!runtimePlugins) return [];
  return sortByOrderThenId(
    runtimePlugins.flatMap((plugin) => {
      if (!isRuntimePluginExecutable(plugin)) return [];
      return (plugin.frontend?.chat_input_options ?? []).flatMap((option) => {
        if (!matchesVisibleWhen(option.visible_when, context)) return [];
        return [
          {
            id: option.id,
            pluginId: plugin.plugin_id,
            slot: option.slot,
            label: option.label,
            icon: option.icon,
            panel: option.panel,
            selectedRenderer: option.selected_renderer,
            suppressesCorePersonaSelector: Boolean(
              option.suppresses_core_persona_selector,
            ),
            shortcut: option.shortcut,
            order: option.order,
            optionBinding: optionBindingFromRuntime(
              plugin.plugin_id,
              option.option_binding,
            ),
            visibleWhen: option.visible_when,
            area: "chat_input_option" as const,
          },
        ];
      });
    }),
  );
}

export function buildChatInputPanelContributions(
  runtimePlugins?: PluginRuntimeContributionStates,
  context?: PluginContributionVisibilityContext,
): readonly CoreChatInputPanelContribution[] {
  if (!runtimePlugins) return [];
  return runtimePlugins.flatMap((plugin) => {
    if (!isRuntimePluginExecutable(plugin)) return [];
    return (plugin.frontend?.chat_input_panels ?? []).flatMap((panel) => {
      if (!matchesVisibleWhen(panel.visible_when, context)) return [];
      return [
          {
            id: panel.id,
            pluginId: plugin.plugin_id,
            renderer: panel.renderer,
            createPath: panel.create_path,
            managePath: panel.manage_path,
            optionBinding: optionBindingFromRuntime(
              plugin.plugin_id,
              panel.option_binding,
            ),
            visibleWhen: panel.visible_when,
            area: "chat_input_panel" as const,
          },
      ];
    });
  });
}

export function buildMentionProviderContributions(
  runtimePlugins?: PluginRuntimeContributionStates,
  context?: PluginContributionVisibilityContext,
): readonly CoreMentionProviderContribution[] {
  if (!runtimePlugins) return [];
  return runtimePlugins.flatMap((plugin) => {
    if (!isRuntimePluginExecutable(plugin)) return [];
    return (plugin.frontend?.mention_providers ?? []).flatMap((provider) => {
      if (!matchesVisibleWhen(provider.visible_when, context)) return [];
      return [
        {
          id: provider.id,
          pluginId: plugin.plugin_id,
          trigger: provider.trigger,
          mode: provider.mode,
          provider: provider.provider,
          optionBinding: optionBindingFromRuntime(
            plugin.plugin_id,
            provider.option_binding,
          ),
          visibleWhen: provider.visible_when,
          area: "mention_provider" as const,
        },
      ];
    });
  });
}

export function buildWelcomeSurfaceContributions(
  runtimePlugins?: PluginRuntimeContributionStates,
  context?: PluginContributionVisibilityContext,
): readonly CoreWelcomeSurfaceContribution[] {
  if (!runtimePlugins) return [];
  return sortByOrderThenId(
    runtimePlugins.flatMap((plugin) => {
      if (!isRuntimePluginExecutable(plugin)) return [];
      return (plugin.frontend?.welcome_surfaces ?? []).flatMap((surface) => {
        if (!matchesVisibleWhen(surface.visible_when, context)) return [];
        return [
          {
            id: surface.id,
            pluginId: plugin.plugin_id,
            agentId: surface.agent_id,
            renderer: surface.renderer,
            order: surface.order,
            optionBinding: optionBindingFromRuntime(
              plugin.plugin_id,
              surface.option_binding,
            ),
            visibleWhen: surface.visible_when,
            area: "welcome_surface" as const,
          },
        ];
      });
    }),
  );
}

export function buildAssistantIdentityResolverContributions(
  runtimePlugins?: PluginRuntimeContributionStates,
  context?: PluginContributionVisibilityContext,
): readonly CoreAssistantIdentityResolverContribution[] {
  if (!runtimePlugins) return [];
  return sortByOrderThenId(
    runtimePlugins.flatMap((plugin) => {
      if (!isRuntimePluginExecutable(plugin)) return [];
      return (plugin.frontend?.assistant_identity_resolvers ?? []).flatMap((resolver) => {
        if (context && !matchesVisibleWhen(resolver.visible_when, context)) return [];
        return [
          {
            id: resolver.id,
            pluginId: plugin.plugin_id,
            agentId: resolver.agent_id,
            resolver: resolver.resolver,
            order: resolver.order,
            optionBinding: optionBindingFromRuntime(
              plugin.plugin_id,
              resolver.option_binding,
            ),
            visibleWhen: resolver.visible_when,
            area: "assistant_identity_resolver" as const,
          },
        ];
      });
    }),
  );
}

export function findAssistantIdentityResolverContribution(
  resolverId: string,
  runtimePlugins?: PluginRuntimeContributionStates,
  context?: PluginContributionVisibilityContext,
): CoreAssistantIdentityResolverContribution | undefined {
  return buildAssistantIdentityResolverContributions(runtimePlugins, context).find(
    (resolver) => resolver.id === resolverId || resolver.resolver === resolverId,
  );
}

export function buildAgentCategoryContributions(
  runtimePlugins?: PluginRuntimeContributionStates,
  context?: PluginContributionVisibilityContext,
): readonly CoreAgentCategoryContribution[] {
  if (!runtimePlugins) return [];
  return sortByOrderThenId(
    runtimePlugins.flatMap((plugin) => {
      if (!isRuntimePluginExecutable(plugin)) return [];
      return (plugin.frontend?.agent_categories ?? []).flatMap((category) => {
        if (!matchesVisibleWhen(category.visible_when, context)) return [];
        return [
          {
            id: category.id,
            pluginId: plugin.plugin_id,
            label: category.label,
            description: category.description ?? "",
            icon: category.icon,
            order: category.order,
            visibleWhen: category.visible_when,
            area: "agent_category" as const,
          },
        ];
      });
    }),
  );
}

export function buildAgentCatalogEntryContributions(
  runtimePlugins?: PluginRuntimeContributionStates,
): readonly CoreAgentCatalogEntryContribution[] {
  if (!runtimePlugins) return [];
  return sortByOrderThenId(
    runtimePlugins.flatMap((plugin) => {
      if (!isRuntimePluginExecutable(plugin)) return [];
      return (plugin.agents ?? []).map((agent) => ({
        id: agent.id,
        pluginId: plugin.plugin_id,
        name: agent.name ?? agent.id,
        description: agent.description ?? "",
        icon: agent.icon ?? "Bot",
        category: agent.category ?? null,
        order: agent.sort_order ?? 100,
        sortOrder: agent.sort_order ?? 100,
        requiredPermissions: agent.required_permissions ?? [],
        area: "agent_catalog_entry" as const,
      }));
    }),
  );
}

export function findAgentCatalogEntryContribution(
  agentId: string,
  runtimePlugins?: PluginRuntimeContributionStates,
): CoreAgentCatalogEntryContribution | undefined {
  return buildAgentCatalogEntryContributions(runtimePlugins).find(
    (entry) => entry.id === agentId,
  );
}

export function hasAgentCatalogEntryContribution(
  agentId: string,
  runtimePlugins?: PluginRuntimeContributionStates,
): boolean {
  return findAgentCatalogEntryContribution(agentId, runtimePlugins) !== undefined;
}

export function buildProjectOptionContributions(
  runtimePlugins?: PluginRuntimeContributionStates,
  context?: PluginContributionVisibilityContext,
  options?: { includeInactive?: boolean },
): readonly CoreScopedPluginOptionContribution[] {
  if (!runtimePlugins) return [];
  return sortByOrderThenId(
    runtimePlugins.flatMap((plugin) => {
      if (!options?.includeInactive && !isRuntimePluginExecutable(plugin)) return [];
      return (plugin.frontend?.project_options ?? []).flatMap((option) => {
        if (!matchesVisibleWhen(option.visible_when, context)) return [];
        return [scopedOptionFromRuntime(plugin, option, "project_option")];
      });
    }),
  );
}

export function buildSessionOptionContributions(
  runtimePlugins?: PluginRuntimeContributionStates,
  context?: PluginContributionVisibilityContext,
): readonly CoreScopedPluginOptionContribution[] {
  if (!runtimePlugins) return [];
  return sortByOrderThenId(
    runtimePlugins.flatMap((plugin) => {
      if (!isRuntimePluginExecutable(plugin)) return [];
      return (plugin.frontend?.session_options ?? []).flatMap((option) => {
        if (!matchesVisibleWhen(option.visible_when, context)) return [];
        return [scopedOptionFromRuntime(plugin, option, "session_option")];
      });
    }),
  );
}

export function buildChannelOptionContributions(
  runtimePlugins?: PluginRuntimeContributionStates,
  context?: PluginContributionVisibilityContext,
  options?: { includeInactive?: boolean },
): readonly CoreScopedPluginOptionContribution[] {
  if (!runtimePlugins) return [];
  return sortByOrderThenId(
    runtimePlugins.flatMap((plugin) => {
      if (!options?.includeInactive && !isRuntimePluginExecutable(plugin)) return [];
      return (plugin.frontend?.channel_options ?? []).flatMap((option) => {
        if (!matchesVisibleWhen(option.visible_when, context)) return [];
        return [scopedOptionFromRuntime(plugin, option, "channel_option")];
      });
    }),
  );
}

export function buildScheduledTaskOptionContributions(
  runtimePlugins?: PluginRuntimeContributionStates,
  context?: PluginContributionVisibilityContext,
  options?: { includeInactive?: boolean },
): readonly CoreScopedPluginOptionContribution[] {
  if (!runtimePlugins) return [];
  return sortByOrderThenId(
    runtimePlugins.flatMap((plugin) => {
      if (!options?.includeInactive && !isRuntimePluginExecutable(plugin)) return [];
      return (plugin.frontend?.scheduled_task_options ?? []).flatMap((option) => {
        if (!matchesVisibleWhen(option.visible_when, context)) return [];
        return [scopedOptionFromRuntime(plugin, option, "scheduled_task_option")];
      });
    }),
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
  return [];
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

export function findChannelConnectorContribution(
  channelType: string,
  runtimePlugins?: PluginRuntimeContributionStates,
): CoreChannelConnectorContribution | undefined {
  return buildChannelConnectorContributions(runtimePlugins).find(
    (connector) => connector.channelType === channelType,
  );
}

export function hasRuntimeManagedChannelConnector(
  channelType: string,
  runtimePlugins?: PluginRuntimeContributionStates,
): boolean {
  return Boolean(
    runtimePlugins?.some((plugin) =>
      (plugin.frontend?.channel_connectors ?? []).some(
        (connector) =>
          typeof connector !== "string" && connector.channel_type === channelType,
      ),
    ),
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
  actionIdOrPluginId: string,
  runtimePlugins?: PluginRuntimeContributionStates,
): boolean {
  return buildMessageActionContributions(runtimePlugins).some(
    (contribution) =>
      contribution.id === actionIdOrPluginId || contribution.pluginId === actionIdOrPluginId,
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
  runtimePlugins?: PluginRuntimeContributionStates,
): CoreAppRouteContribution | undefined {
  if (tab === "chat") return undefined;
  return buildAppRouteContributions(runtimePlugins).find((route) => route.tab === tab);
}

export function findCorePanelContribution(
  tab: TabType,
): CorePanelContribution | undefined {
  if (tab === "chat") return undefined;
  return CORE_PANEL_CONTRIBUTIONS.find((panel) => panel.tab === tab);
}

export function findPanelContribution(
  tab: TabType,
  runtimePlugins?: PluginRuntimeContributionStates,
): CorePanelContribution | undefined {
  if (tab === "chat") return undefined;
  return buildPanelContributions(runtimePlugins).find((panel) => panel.tab === tab);
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
