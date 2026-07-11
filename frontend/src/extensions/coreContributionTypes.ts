import type { LucideIcon } from "lucide-react";
import type { Permission } from "../types";
import type { SettingCategory } from "../types/settings";
import type { TabType } from "../components/layout/AppContent/types";

export type CoreContributionArea =
  | "app_route"
  | "panel"
  | "sidebar_more_menu"
  | "user_menu"
  | "settings_section"
  | "tool_renderer"
  | "plugin_message_renderer"
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
  | "scheduled_task_section"
  | "plugin_asset_slot"
  | "i18n_namespace";

export interface CoreAppRouteContribution {
  id: Exclude<TabType, "chat">;
  pluginId?: string;
  insertAfterId?: Exclude<TabType, "chat">;
  path: string;
  seoPath?: string;
  labelKey?: string;
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

export interface CoreScheduledTaskSectionContribution {
  id: string;
  pluginId: string;
  renderer: string;
  order: number;
  area: "scheduled_task_section";
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

export interface CorePluginMessageRendererContribution {
  id: string;
  pluginId: string;
  renderer: string;
  messageTypes: readonly string[];
  area: "plugin_message_renderer";
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

export interface PluginContributionVisibleWhen {
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

export interface PluginRuntimeAppTab {
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

export interface PluginRuntimeAppPanel {
  id: string;
  tab: string;
  renderer: string;
  visible_when?: PluginContributionVisibleWhen | null;
}

export interface PluginRuntimeScheduledTaskSection {
  id: string;
  renderer: string;
  order?: number;
  visible_when?: PluginContributionVisibleWhen | null;
}

export interface PluginRuntimeSidebarItem {
  id: string;
  path: string;
  label: string;
  icon: string;
  order: number;
  permissions?: string[];
  visible_when?: PluginContributionVisibleWhen | null;
}

export interface PluginRuntimeUserMenuItem extends PluginRuntimeSidebarItem {
  group: "admin" | "system";
}

export interface PluginRuntimeMessageAction {
  id: string;
  target?: string;
  renderer: string;
  order?: number;
  permissions?: string[];
  visible_when?: PluginContributionVisibleWhen | null;
}

export interface PluginRuntimeToolRenderer {
  id: string;
  tool_names?: string[];
}

export interface PluginRuntimeMessageRenderer {
  id: string;
  renderer: string;
  message_types?: string[];
}

export interface PluginRuntimeFileViewer {
  id: string;
  extensions?: string[];
}

export interface PluginRuntimeUploadHandler {
  id: string;
  accept?: string[];
  max_bytes?: number | null;
  handler?: string | null;
}

export interface PluginRuntimeSkillImporter {
  id: string;
  source: "github" | "zip";
}

export interface PluginRuntimeChannelConnector {
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

export interface PluginRuntimeAgent {
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

export interface PluginRuntimeAgentCategory {
  id: string;
  label: string;
  description?: string;
  icon: string;
  order: number;
  visible_when?: PluginContributionVisibleWhen | null;
}

export interface PluginRuntimeAssistantIdentityResolver {
  id: string;
  agent_id: string;
  resolver: string;
  order: number;
  option_binding?: PluginRuntimeOptionBinding | null;
  visible_when?: PluginContributionVisibleWhen | null;
}

export interface PluginRuntimeScopedOption {
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

export interface PluginRuntimeOptionBinding {
  plugin_id?: string | null;
  key: string;
  scope?: string;
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
    message_renderers?: PluginRuntimeMessageRenderer[];
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
    scheduled_task_sections?: PluginRuntimeScheduledTaskSection[];
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
  pluginMessageRenderers: readonly string[];
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
  scheduledTaskSections: readonly string[];
  pluginAssetSlots: readonly string[];
  i18nNamespaces: readonly string[];
}

export interface PluginContributionPreview {
  current: PluginContributionSnapshot;
  simulatedDisabled: PluginContributionSnapshot;
  removedWhenDisabled: PluginContributionSnapshot;
}
