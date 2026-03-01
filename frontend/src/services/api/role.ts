/**
 * Role API - 角色管理
 */

import type { Role, RoleCreate, RoleUpdate } from "../../types";
import { API_BASE } from "./config";
import { authFetch } from "./fetch";

export const roleApi = {
  /**
   * 列出角色
   */
  async list(skip = 0, limit = 100): Promise<Role[]> {
    return authFetch<Role[]>(
      `${API_BASE}/api/roles/?skip=${skip}&limit=${limit}`,
    );
  },

  /**
   * 获取单个角色
   */
  async get(roleId: string): Promise<Role> {
    return authFetch<Role>(`${API_BASE}/api/roles/${roleId}`);
  },

  /**
   * 创建角色
   */
  async create(roleData: RoleCreate): Promise<Role> {
    return authFetch<Role>(`${API_BASE}/api/roles/`, {
      method: "POST",
      body: JSON.stringify(roleData),
    });
  },

  /**
   * 更新角色
   */
  async update(roleId: string, roleData: RoleUpdate): Promise<Role> {
    return authFetch<Role>(`${API_BASE}/api/roles/${roleId}`, {
      method: "PUT",
      body: JSON.stringify(roleData),
    });
  },

  /**
   * 删除角色
   */
  async delete(roleId: string): Promise<{ status: string }> {
    return authFetch<{ status: string }>(`${API_BASE}/api/roles/${roleId}`, {
      method: "DELETE",
    });
  },
};
