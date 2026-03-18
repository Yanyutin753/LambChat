/**
 * Skill API - 技能管理
 */

import { API_BASE } from "./config";
import { authFetch } from "./fetch";

export const skillApi = {
  /**
   * 列出技能
   */
  async list() {
    return authFetch(`${API_BASE}/api/skills`);
  },

  /**
   * 获取技能详情
   */
  async get(skillPath: string) {
    return authFetch(`${API_BASE}/api/skills/${encodeURIComponent(skillPath)}`);
  },

  /**
   * 创建技能
   */
  async create(data: {
    name: string;
    description: string;
    content: string;
    enabled?: boolean;
  }) {
    return authFetch(`${API_BASE}/api/skills`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  /**
   * 更新技能
   */
  async update(
    skillPath: string,
    data: {
      name?: string;
      description?: string;
      content?: string;
      enabled?: boolean;
      is_system?: boolean;
      files?: Record<string, string>;
    },
  ) {
    return authFetch(
      `${API_BASE}/api/skills/${encodeURIComponent(skillPath)}`,
      {
        method: "PUT",
        body: JSON.stringify(data),
      },
    );
  },

  /**
   * 删除技能
   */
  async delete(skillPath: string) {
    return authFetch(
      `${API_BASE}/api/skills/${encodeURIComponent(skillPath)}`,
      {
        method: "DELETE",
      },
    );
  },

  /**
   * 切换技能启用状态
   */
  async toggle(skillPath: string, enabled: boolean) {
    return authFetch(
      `${API_BASE}/api/skills/${encodeURIComponent(skillPath)}/toggle`,
      {
        method: "PATCH",
        body: JSON.stringify({ enabled }),
      },
    );
  },

  /**
   * Upload skill from ZIP file
   */
  async upload(file: File) {
    const formData = new FormData();
    formData.append("file", file);
    return authFetch(`${API_BASE}/api/skills/upload`, {
      method: "POST",
      body: formData,
    });
  },

  /**
   * Upload skill from ZIP file as admin (system skill)
   */
  async uploadAdmin(file: File) {
    const formData = new FormData();
    formData.append("file", file);
    return authFetch(`${API_BASE}/api/admin/skills/upload`, {
      method: "POST",
      body: formData,
    });
  },
};
