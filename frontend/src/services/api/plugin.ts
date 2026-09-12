/**
 * Plugin API - 插件中心
 */

import { API_BASE } from "./config";
import { authFetch } from "./fetch";
import type {
  PluginResponse,
  PluginListResponse,
  PluginInstallResponse,
  PluginInstalledListResponse,
  PluginTagsResponse,
  PluginCreateRequest,
  PluginUpdateRequest,
  PluginSkillFilesResponse,
  PluginFileContentResponse,
} from "../../types";

const PLUGIN_API = `${API_BASE}/api/plugins`;

export const pluginApi = {
  /**
   * List platform plugins (active + own drafts)
   */
  async list(params?: {
    tags?: string;
    search?: string;
    skip?: number;
    limit?: number;
  }) {
    const searchParams = new URLSearchParams();
    if (params?.tags) searchParams.set("tags", params.tags);
    if (params?.search) searchParams.set("search", params.search);
    if (params?.skip !== undefined)
      searchParams.set("skip", String(params.skip));
    if (params?.limit !== undefined)
      searchParams.set("limit", String(params.limit));
    const query = searchParams.toString();
    return authFetch<PluginListResponse>(
      `${PLUGIN_API}/${query ? `?${query}` : ""}`,
    );
  },

  /**
   * Get all available plugin tags
   */
  async getTags() {
    return authFetch<PluginTagsResponse>(`${PLUGIN_API}/tags`);
  },

  /**
   * List plugins installed by the current user
   */
  async listInstalled() {
    return authFetch<PluginInstalledListResponse>(`${PLUGIN_API}/installed`);
  },

  /**
   * Get plugin details
   */
  async get(name: string) {
    return authFetch<PluginResponse>(
      `${PLUGIN_API}/${encodeURIComponent(name)}`,
    );
  },

  /**
   * List skill payload file paths of a plugin
   */
  async listSkillFiles(name: string, skillName: string) {
    return authFetch<PluginSkillFilesResponse>(
      `${PLUGIN_API}/${encodeURIComponent(name)}/skills/${encodeURIComponent(
        skillName,
      )}/files`,
    );
  },

  /**
   * Read one skill payload file of a plugin
   */
  async readSkillFile(name: string, skillName: string, filePath: string) {
    return authFetch<PluginFileContentResponse>(
      `${PLUGIN_API}/${encodeURIComponent(
        name,
      )}/skills/${encodeURIComponent(skillName)}/files/${encodeURIComponent(
        filePath,
      )}`,
    );
  },

  /**
   * Install a plugin (skills → user library, persona → private draft)
   */
  async install(name: string) {
    return authFetch<PluginInstallResponse>(
      `${PLUGIN_API}/${encodeURIComponent(name)}/install`,
      { method: "POST" },
    );
  },

  /**
   * Re-sync installed plugin skills from the platform
   */
  async update(name: string) {
    return authFetch<PluginInstallResponse>(
      `${PLUGIN_API}/${encodeURIComponent(name)}/update`,
      { method: "POST" },
    );
  },

  /**
   * Uninstall a plugin (removes install record only)
   */
  async uninstall(name: string) {
    return authFetch<{ message: string; plugin_name: string }>(
      `${PLUGIN_API}/${encodeURIComponent(name)}/uninstall`,
      { method: "POST" },
    );
  },

  /**
   * Create/submit a plugin (admin may activate directly)
   */
  async create(data: PluginCreateRequest) {
    return authFetch<PluginResponse>(`${PLUGIN_API}/`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  /**
   * Update a plugin (creator or admin)
   */
  async updatePlugin(name: string, data: PluginUpdateRequest) {
    return authFetch<PluginResponse>(
      `${PLUGIN_API}/${encodeURIComponent(name)}`,
      { method: "PUT", body: JSON.stringify(data) },
    );
  },

  /**
   * Write skill payload files of a plugin
   */
  async writeSkillFiles(name: string, skillName: string, files: Record<string, string>) {
    return authFetch<{ message: string }>(
      `${PLUGIN_API}/${encodeURIComponent(name)}/skills/${encodeURIComponent(
        skillName,
      )}/files`,
      { method: "PUT", body: JSON.stringify({ files }) },
    );
  },

  /**
   * Admin: activate or deactivate a plugin
   */
  async activate(name: string, isActive: boolean) {
    return authFetch<PluginResponse>(
      `${PLUGIN_API}/${encodeURIComponent(name)}/activate`,
      { method: "PATCH", body: JSON.stringify({ is_active: isActive }) },
    );
  },

  /**
   * Admin: delete a plugin (removes materialized MCP servers)
   */
  async deletePlugin(name: string) {
    return authFetch<{ message: string; plugin_name: string }>(
      `${PLUGIN_API}/${encodeURIComponent(name)}`,
      { method: "DELETE" },
    );
  },
};
