/**
 * Plugin Hub types - 插件中心（技能/MCP/角色统一插件体系）
 */

export type PluginStatus = "draft" | "active" | "deactivated";

export interface PluginSkillPayload {
  skill_name: string;
  description: string;
  tags: string[];
}

export interface PluginMcpServerPayload {
  name: string;
  transport: "sse" | "streamable_http";
  url: string | null;
  headers: Record<string, string> | null;
  ref: boolean;
  enabled: boolean;
}

export interface PluginStarterPromptPayload {
  icon: string | null;
  text: string | Record<string, string>;
}

export interface PluginPersonaPayload {
  name: string;
  description: string;
  avatar: string | null;
  tags: string[];
  system_prompt: string;
  starter_prompts: PluginStarterPromptPayload[];
}

export interface PluginResponse {
  name: string;
  display_name: string;
  description: string;
  version: string;
  author_name: string;
  tags: string[];
  skills: PluginSkillPayload[];
  mcp_servers: PluginMcpServerPayload[];
  persona: PluginPersonaPayload | null;
  status: PluginStatus;
  created_by: string | null;
  created_by_username: string | null;
  install_count: number;
  is_owner: boolean;
  installed: boolean;
  installed_version: string | null;
  migrated_from: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface PluginListResponse {
  plugins: PluginResponse[];
  total: number;
  skip: number;
  limit: number;
}

export interface PluginInstallResponse {
  message: string;
  plugin_name: string;
  version: string;
  installed_skills: string[];
  persona_created: boolean;
}

export interface PluginInstallRecord {
  plugin_name: string;
  version: string;
  installed_at: string;
}

export interface PluginInstalledListResponse {
  installs: PluginInstallRecord[];
  total: number;
}

export interface PluginTagsResponse {
  tags: string[];
}

export interface PluginCreateRequest {
  name: string;
  display_name?: string;
  description?: string;
  version?: string;
  author_name?: string;
  tags?: string[];
  skills?: PluginSkillPayload[];
  mcp_servers?: PluginMcpServerPayload[];
  persona?: PluginPersonaPayload | null;
  activate?: boolean;
}

export interface PluginUpdateRequest {
  display_name?: string;
  description?: string;
  version?: string;
  author_name?: string;
  tags?: string[];
  skills?: PluginSkillPayload[];
  mcp_servers?: PluginMcpServerPayload[];
  persona?: PluginPersonaPayload | null;
}

export interface PluginSkillFilesResponse {
  plugin_name: string;
  skill_name: string;
  file_paths: string[];
}

export interface PluginFileContentResponse {
  content: string;
}
