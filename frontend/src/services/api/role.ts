/**
 * Role API - 角色管理
 */

import type {
  Role,
  RoleCreate,
  RoleListResponse,
  RoleUpdate,
} from "../../types";
import { API_BASE } from "./config";
import { authFetch } from "./fetch";
import { getAccessToken } from "./token";

const ROLE_LIST_CACHE_TTL_MS = 10_000;

interface RoleListCacheEntry {
  data?: RoleListResponse;
  expiresAt: number;
  authScope: string | null;
  promise?: Promise<RoleListResponse>;
}

const roleListCache = new Map<string, RoleListCacheEntry>();

function clearRoleListCache(): void {
  roleListCache.clear();
}

function getCachedRoleList(url: string): Promise<RoleListResponse> {
  const now = Date.now();
  const authScope = getAccessToken();
  const cached = roleListCache.get(url);

  if (
    cached?.data &&
    cached.expiresAt > now &&
    cached.authScope === authScope
  ) {
    return Promise.resolve(cached.data);
  }

  if (cached?.promise && cached.authScope === authScope) {
    return cached.promise;
  }

  const promise = authFetch<RoleListResponse>(url)
    .then((data) => {
      roleListCache.set(url, {
        data,
        expiresAt: Date.now() + ROLE_LIST_CACHE_TTL_MS,
        authScope,
      });
      return data;
    })
    .catch((error) => {
      roleListCache.delete(url);
      throw error;
    });

  roleListCache.set(url, {
    promise,
    expiresAt: now + ROLE_LIST_CACHE_TTL_MS,
    authScope,
  });

  return promise;
}

export interface RoleListParams {
  skip?: number;
  limit?: number;
  q?: string;
}

export function buildRoleListUrl(params: RoleListParams = {}): string {
  const searchParams = new URLSearchParams();
  if (params.skip !== undefined) searchParams.set("skip", String(params.skip));
  if (params.limit !== undefined)
    searchParams.set("limit", String(params.limit));
  if (params.q) searchParams.set("q", params.q);
  const query = searchParams.toString();
  return `${API_BASE}/api/roles/${query ? `?${query}` : ""}`;
}

export const roleApi = {
  /**
   * 列出角色
   */
  async list(params: RoleListParams = {}): Promise<RoleListResponse> {
    return getCachedRoleList(buildRoleListUrl(params));
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
    const role = await authFetch<Role>(`${API_BASE}/api/roles/`, {
      method: "POST",
      body: JSON.stringify(roleData),
    });
    clearRoleListCache();
    return role;
  },

  /**
   * 更新角色
   */
  async update(roleId: string, roleData: RoleUpdate): Promise<Role> {
    const role = await authFetch<Role>(`${API_BASE}/api/roles/${roleId}`, {
      method: "PUT",
      body: JSON.stringify(roleData),
    });
    clearRoleListCache();
    return role;
  },

  async updateQuota(
    roleId: string,
    limits: {
      five_hour_budget_usd: number | null;
      weekly_budget_usd: number | null;
    },
  ): Promise<Role> {
    const role = await authFetch<Role>(
      `${API_BASE}/api/roles/${roleId}/usage-quota`,
      {
        method: "PATCH",
        body: JSON.stringify(limits),
      },
    );
    clearRoleListCache();
    return role;
  },

  /**
   * 删除角色
   */
  async delete(roleId: string): Promise<{ status: string }> {
    const result = await authFetch<{ status: string }>(
      `${API_BASE}/api/roles/${roleId}`,
      {
        method: "DELETE",
      },
    );
    clearRoleListCache();
    return result;
  },
};
