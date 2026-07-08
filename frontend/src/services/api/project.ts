/**
 * Project API - 项目管理
 */

import { API_BASE } from "./config";
import { authFetch } from "./fetch";
import type { Project, ProjectCreate, ProjectUpdate } from "../../types";

export type ProjectPluginOptions = Record<string, Record<string, unknown>>;

export interface ProjectPluginOptionsResponse {
  project_id: string;
  plugin_options: ProjectPluginOptions;
}

export interface ProjectPluginOptionUpdateResponse
  extends ProjectPluginOptionsResponse {
  plugin_id: string;
  key: string;
  qualified_key: string;
  value: unknown;
  plugin_enabled: boolean;
  effective: boolean;
}

export function buildProjectPluginOptionsUrl(projectId: string): string {
  return `${API_BASE}/api/projects/${encodeURIComponent(projectId)}/plugin-options`;
}

export function buildProjectPluginOptionUrl(
  projectId: string,
  pluginId: string,
  key: string,
): string {
  return `${buildProjectPluginOptionsUrl(projectId)}/${encodeURIComponent(
    pluginId,
  )}/${encodeURIComponent(key)}`;
}

export const projectApi = {
  /**
   * List all projects for current user
   */
  async list(): Promise<Project[]> {
    return authFetch<Project[]>(`${API_BASE}/api/projects`);
  },

  /**
   * Create a new project
   */
  async create(data: ProjectCreate): Promise<Project> {
    return authFetch<Project>(`${API_BASE}/api/projects`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  /**
   * Update a project (rename)
   */
  async update(projectId: string, data: ProjectUpdate): Promise<Project> {
    return authFetch<Project>(`${API_BASE}/api/projects/${projectId}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    });
  },

  async getPluginOptions(
    projectId: string,
  ): Promise<ProjectPluginOptionsResponse> {
    return authFetch(buildProjectPluginOptionsUrl(projectId));
  },

  async updatePluginOption(
    projectId: string,
    pluginId: string,
    key: string,
    value: unknown,
  ): Promise<ProjectPluginOptionUpdateResponse> {
    return authFetch(buildProjectPluginOptionUrl(projectId, pluginId, key), {
      method: "PUT",
      body: JSON.stringify({ value }),
    });
  },

  /**
   * Delete a project
   */
  async delete(
    projectId: string,
    options?: { deleteSessions?: boolean },
  ): Promise<{ status: string }> {
    const params = new URLSearchParams();
    if (options?.deleteSessions) params.set("delete_sessions", "true");
    const qs = params.toString();
    return authFetch<{ status: string }>(
      `${API_BASE}/api/projects/${projectId}${qs ? `?${qs}` : ""}`,
      {
        method: "DELETE",
      },
    );
  },
};
