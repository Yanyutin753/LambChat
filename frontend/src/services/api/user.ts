/**
 * User API - 用户管理
 */

import type { User, UserCreate, UserUpdate } from "../../types";
import { API_BASE } from "./config";
import { authFetch } from "./fetch";

export const userApi = {
  /**
   * 列出用户
   */
  async list(skip = 0, limit = 100): Promise<User[]> {
    return authFetch<User[]>(
      `${API_BASE}/api/users/?skip=${skip}&limit=${limit}`,
    );
  },

  /**
   * 获取单个用户
   */
  async get(userId: string): Promise<User> {
    return authFetch<User>(`${API_BASE}/api/users/${userId}`);
  },

  /**
   * 创建用户
   */
  async create(userData: UserCreate): Promise<User> {
    return authFetch<User>(`${API_BASE}/api/users/`, {
      method: "POST",
      body: JSON.stringify(userData),
    });
  },

  /**
   * 更新用户
   */
  async update(userId: string, userData: UserUpdate): Promise<User> {
    return authFetch<User>(`${API_BASE}/api/users/${userId}`, {
      method: "PUT",
      body: JSON.stringify(userData),
    });
  },

  /**
   * 删除用户
   */
  async delete(userId: string): Promise<{ status: string }> {
    return authFetch<{ status: string }>(`${API_BASE}/api/users/${userId}`, {
      method: "DELETE",
    });
  },
};
