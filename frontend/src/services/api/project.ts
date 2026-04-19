/**
 * Project API - 项目管理
 */

import { API_BASE } from "./config";
import { authFetch } from "./fetch";
import type { Project, ProjectCreate, ProjectUpdate } from "../../types";

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
