/**
 * User API - 用户管理
 */

import type {
  User,
  UserCreate,
  UserUpdate,
  UserListResponse,
} from "../../types";
import { API_BASE } from "./config";
import { authFetch } from "./fetch";

export const userApi = {
  /**
   * List users with pagination and search
   */
  async list(params?: {
    skip?: number;
    limit?: number;
    search?: string;
  }): Promise<UserListResponse> {
    const searchParams = new URLSearchParams();
    if (params?.skip !== undefined) {
      searchParams.set("skip", params.skip.toString());
    }
    if (params?.limit !== undefined) {
      searchParams.set("limit", params.limit.toString());
    }
    if (params?.search) {
      searchParams.set("search", params.search);
    }

    const query = searchParams.toString() ? `?${searchParams}` : "";
    return authFetch<UserListResponse>(`${API_BASE}/api/users/${query}`);
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
