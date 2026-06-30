export type ExtensionType =
  | "skill"
  | "plugin"
  | "mcp"
  | "agent_team"
  | "user_agent"
  | "agent"
  | "theme"
  | "workflow"
  | "provider"
  | "file_viewer"
  | "notification_channel";

export type ExtensionInstallState = "builtin" | "installed" | "not_installed";

export interface ExtensionCompatibility {
  minAppVersion?: string;
  maxAppVersion?: string;
  apiVersion?: string;
}

export interface ExtensionManifest {
  id: string;
  type: ExtensionType;
  name: string;
  version: string;
  publisher: string;
  description?: string;
  tags?: string[];
  capabilities?: string[];
  permissions?: string[];
  settingsSchema?: Record<string, unknown>;
  installState?: ExtensionInstallState;
  enabled?: boolean;
  compatibility?: ExtensionCompatibility;
}

export interface CoreRoute {
  id: string;
  path: string;
  label?: string;
  requiredPermissions?: string[];
  core: true;
}

export interface PluginRoute {
  id: string;
  path: string;
  pluginId: string;
  requiredPermissions?: string[];
  enabled?: boolean;
}

export interface PluginPanel {
  id: string;
  pluginId: string;
  slot: string;
  requiredPermissions?: string[];
  enabled?: boolean;
}

export interface PluginNavItem {
  id: string;
  pluginId: string;
  label: string;
  path: string;
  order?: number;
  requiredPermissions?: string[];
  enabled?: boolean;
}

export interface PluginManifest {
  id: string;
  name: string;
  version: string;
  apiVersion: string;
  dependsOn?: string[];
  permissions?: string[];
  routes?: PluginRoute[];
  panels?: PluginPanel[];
  navItems?: PluginNavItem[];
  toolRenderers?: string[];
  settingsSections?: string[];
  i18nNamespaces?: string[];
  enabledByDefault?: boolean;
  core?: boolean;
}

export interface ExtensionRegistryListOptions {
  type?: ExtensionType;
  enabled?: boolean;
}

export interface PluginRegistryListOptions {
  enabled?: boolean;
}
