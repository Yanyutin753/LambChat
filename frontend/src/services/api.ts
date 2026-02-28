/**
 * API service for backend communication
 * 支持JWT认证的API服务
 */

import type {
  User,
  UserCreate,
  UserUpdate,
  Role,
  RoleCreate,
  RoleUpdate,
  LoginRequest,
  TokenResponse,
  SessionEventsResponse,
  RunSummary,
  SettingItem,
  SettingsResponse,
  SettingResetResponse,
  MCPServerResponse,
  MCPServersResponse,
  MCPServerCreate,
  MCPServerUpdate,
  MCPServerToggleResponse,
  MCPImportRequest,
  MCPImportResponse,
  MCPExportResponse,
  PermissionsResponse,
  VersionInfo,
} from "../types";

const API_BASE = import.meta.env.VITE_API_BASE || "";
export { API_BASE };

// ============================================
// Token 管理
// ============================================

const TOKEN_KEY = "access_token";
const REFRESH_TOKEN_KEY = "refresh_token";

/**
 * 获取存储的 access token
 */
export function getAccessToken(): string | null {
  return localStorage.getItem(TOKEN_KEY);
}

/**
 * 获取存储的 refresh token
 */
export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_TOKEN_KEY);
}

/**
 * 保存 tokens
 */
export function setTokens(access_token: string, refresh_token?: string): void {
  localStorage.setItem(TOKEN_KEY, access_token);
  if (refresh_token) {
    localStorage.setItem(REFRESH_TOKEN_KEY, refresh_token);
  }
}

/**
 * 清除 tokens
 */
export function clearTokens(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(REFRESH_TOKEN_KEY);
}

/**
 * 检查是否已登录
 */
export function isAuthenticated(): boolean {
  return !!getAccessToken();
}

/**
 * 解码 JWT token（不验证签名，仅用于读取内容）
 */
export function decodeToken(token: string): Record<string, unknown> | null {
  try {
    const base64Url = token.split(".")[1];
    const base64 = base64Url.replace(/-/g, "+").replace(/_/g, "/");
    const jsonPayload = decodeURIComponent(
      atob(base64)
        .split("")
        .map((c) => "%" + ("00" + c.charCodeAt(0).toString(16)).slice(-2))
        .join(""),
    );
    return JSON.parse(jsonPayload);
  } catch {
    return null;
  }
}

/**
 * 检查 token 是否过期
 */
export function isTokenExpired(token: string): boolean {
  const payload = decodeToken(token);
  if (!payload || !payload.exp) return true;
  return (payload.exp as number) * 1000 < Date.now();
}

// ============================================
// Token 刷新队列管理
// ============================================

// 刷新状态标志
let isRefreshing = false;

// 等待刷新完成的请求队列
// 回调接收 token 参数；如果传入 null 表示刷新失败，订阅者应直接失败
let refreshSubscribers: Array<(token: string | null) => void> = [];

/**
 * 订阅 token 刷新完成事件
 * @param callback - 刷新成功时接收新 token，刷新失败时接收 null
 */
function subscribeTokenRefresh(callback: (token: string | null) => void): void {
  refreshSubscribers.push(callback);
}

/**
 * token 刷新成功，通知所有等待的请求
 */
function onTokenRefreshed(token: string): void {
  refreshSubscribers.forEach((callback) => callback(token));
  refreshSubscribers = [];
}

/**
 * token 刷新失败，通知所有等待的请求并清空队列
 *
 * 注意：虽然刷新失败后通常会触发 redirectToLogin() 导致页面跳转，
 * 但为了代码正确性，我们需要通知所有等待中的 Promise，
 * 否则这些 Promise 会永远处于 pending 状态（内存泄漏）。
 */
function onRefreshFailed(): void {
  // 先通知所有等待的请求刷新失败
  refreshSubscribers.forEach((callback) => callback(null));
  // 再清空队列
  refreshSubscribers = [];
}

/**
 * 跳转到登录页并保存当前路径
 */
function redirectToLogin(): void {
  const currentPath = window.location.pathname + window.location.search;
  // 保存当前路径到 sessionStorage，登录后可返回
  if (currentPath !== "/login" && currentPath !== "/") {
    sessionStorage.setItem("redirect_after_login", currentPath);
  }
  clearTokens();
  window.dispatchEvent(new CustomEvent("auth:logout"));
}

/**
 * 获取登录后重定向路径
 */
export function getRedirectPath(): string | null {
  return sessionStorage.getItem("redirect_after_login");
}

/**
 * 清除重定向路径
 */
export function clearRedirectPath(): void {
  sessionStorage.removeItem("redirect_after_login");
}

// ============================================
// Token 刷新重试逻辑
// ============================================

/**
 * 刷新 token 并重试原请求
 * 处理并发请求：第一个请求触发刷新，其他请求等待
 */
async function refreshTokenAndRetry<T>(
  originalRequest: () => Promise<T>,
): Promise<T> {
  // 如果已经在刷新中，加入等待队列
  if (isRefreshing) {
    return new Promise((resolve, reject) => {
      subscribeTokenRefresh((token) => {
        if (token === null) {
          // 刷新失败，直接拒绝
          reject(new Error("Token refresh failed"));
        } else {
          // 刷新成功，用新 token 重试原请求
          originalRequest().then(resolve).catch(reject);
        }
      });
    });
  }

  // 开始刷新
  isRefreshing = true;

  try {
    const refreshToken = getRefreshToken();
    if (!refreshToken) {
      throw new Error("No refresh token available");
    }

    // 调用刷新接口
    const response = await fetch(`${API_BASE}/api/auth/refresh`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (!response.ok) {
      throw new Error("Token refresh failed");
    }

    const tokenResponse = await response.json();

    // 保存新 token
    setTokens(tokenResponse.access_token, tokenResponse.refresh_token);

    // 通知所有等待的请求
    onTokenRefreshed(tokenResponse.access_token);

    // 重试原请求
    return originalRequest();
  } catch (error) {
    // 刷新失败，清空队列并跳转登录
    onRefreshFailed();
    redirectToLogin();
    throw error;
  } finally {
    isRefreshing = false;
  }
}

// ============================================
// 带认证的 fetch 封装
// ============================================

interface FetchOptions extends RequestInit {
  skipAuth?: boolean;
}

/**
 * 带认证的 fetch 封装
 * 自动添加 Authorization header
 * 处理 401 响应
 */
export async function authFetch<T>(
  url: string,
  options: FetchOptions = {},
): Promise<T> {
  const { skipAuth = false, headers = {}, ...restOptions } = options;

  const finalHeaders: HeadersInit = {
    "Content-Type": "application/json",
    ...headers,
  };

  if (!skipAuth) {
    const token = getAccessToken();
    if (token) {
      (finalHeaders as Record<string, string>)["Authorization"] =
        `Bearer ${token}`;
    }
  }

  const response = await fetch(url, {
    ...restOptions,
    headers: finalHeaders,
  });

  // 检查当前用户是否被修改（需要重新登录）
  if (!skipAuth && response.headers.get("X-Force-Relogin") === "true") {
    // 清除 token 并触发登出事件
    clearTokens();
    window.dispatchEvent(new CustomEvent("auth:logout"));
    throw new Error("用户权限已变更，请重新登录");
  }

  // 处理 401 未授权响应
  if (response.status === 401 && !skipAuth) {
    const refreshToken = getRefreshToken();

    // 有 refresh token，尝试刷新并重试
    if (refreshToken) {
      return refreshTokenAndRetry(() =>
        authFetch<T>(url, { ...options, skipAuth: false }),
      );
    }

    // 没有 refresh token，直接跳转登录
    redirectToLogin();
    throw new Error("Unauthorized");
  }

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(
      errorData.detail || `Request failed: ${response.statusText}`,
    );
  }

  // 处理空响应
  const text = await response.text();
  return text ? JSON.parse(text) : (null as T);
}

// ============================================
// Auth API - 认证相关
// ============================================

export const authApi = {
  /**
   * 用户登录
   */
  async login(credentials: LoginRequest): Promise<TokenResponse> {
    const response = await authFetch<TokenResponse>(
      `${API_BASE}/api/auth/login`,
      {
        method: "POST",
        skipAuth: true,
        body: JSON.stringify(credentials),
      },
    );

    // 保存 tokens
    setTokens(response.access_token, response.refresh_token);

    // 通知登录成功
    window.dispatchEvent(new CustomEvent("auth:login"));

    return response;
  },

  /**
   * 用户注册
   */
  async register(userData: UserCreate): Promise<User> {
    return authFetch<User>(`${API_BASE}/api/auth/register`, {
      method: "POST",
      skipAuth: true,
      body: JSON.stringify(userData),
    });
  },

  /**
   * 刷新 token
   */
  async refreshToken(): Promise<TokenResponse> {
    const refreshToken = getRefreshToken();
    if (!refreshToken) {
      throw new Error("No refresh token available");
    }

    const response = await authFetch<TokenResponse>(
      `${API_BASE}/api/auth/refresh`,
      {
        method: "POST",
        skipAuth: true,
        body: JSON.stringify({ refresh_token: refreshToken }),
      },
    );

    setTokens(response.access_token, response.refresh_token);

    return response;
  },

  /**
   * 获取当前用户信息
   */
  async getCurrentUser(): Promise<User> {
    return authFetch<User>(`${API_BASE}/api/auth/me`);
  },

  /**
   * 登出
   */
  logout(): void {
    clearTokens();
    window.dispatchEvent(new CustomEvent("auth:logout"));
  },

  /**
   * 获取所有可用权限列表
   */
  async getPermissions(): Promise<PermissionsResponse> {
    return authFetch<PermissionsResponse>(`${API_BASE}/api/auth/permissions`, {
      skipAuth: true,
    });
  },

  /**
   * 修改密码
   */
  async changePassword(
    oldPassword: string,
    newPassword: string,
  ): Promise<{ message: string }> {
    return authFetch<{ message: string }>(
      `${API_BASE}/api/auth/change-password`,
      {
        method: "POST",
        body: JSON.stringify({
          old_password: oldPassword,
          new_password: newPassword,
        }),
      },
    );
  },

  /**
   * 更新头像
   */
  async updateAvatar(avatarUrl: string): Promise<User> {
    return authFetch<User>(`${API_BASE}/api/auth/update-avatar`, {
      method: "POST",
      body: JSON.stringify({ avatar_url: avatarUrl }),
    });
  },

  /**
   * 更新用户名
   */
  async updateUsername(username: string): Promise<User> {
    return authFetch<User>(`${API_BASE}/api/auth/update-username`, {
      method: "POST",
      body: JSON.stringify({ username }),
    });
  },

  /**
   * 获取用户个人资料
   */
  async getProfile(): Promise<User> {
    return authFetch<User>(`${API_BASE}/api/auth/profile`);
  },
};

// ============================================
// User API - 用户管理
// ============================================

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

// ============================================
// Role API - 角色管理
// ============================================

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

// ============================================
// Session API - 会话管理
// ============================================

// Backend Session type (matches backend Session schema in src/kernel/schemas/session.py)
export interface BackendSession {
  id: string;
  user_id?: string;
  agent_id: string;
  created_at: string;
  updated_at: string;
  is_active: boolean;
  name?: string;
  metadata: Record<string, unknown>;
}

// Session list response type
export interface SessionListResponse {
  sessions: BackendSession[];
  total: number;
  skip: number;
  limit: number;
  has_more: boolean;
}

export const sessionApi = {
  /**
   * List all sessions with pagination
   */
  async list(params?: {
    status?: string;
    limit?: number;
    skip?: number;
  }): Promise<SessionListResponse | BackendSession[]> {
    const searchParams = new URLSearchParams();
    if (params?.status) searchParams.set("status", params.status);
    if (params?.limit) searchParams.set("limit", params.limit.toString());
    if (params?.skip) searchParams.set("skip", params.skip.toString());

    const url = `${API_BASE}/api/sessions${
      searchParams.toString() ? `?${searchParams}` : ""
    }`;
    return authFetch<SessionListResponse | BackendSession[]>(url);
  },

  /**
   * Get a session
   * Note: Backend returns Session without messages
   */
  async get(sessionId: string): Promise<BackendSession | null> {
    try {
      return await authFetch<BackendSession>(
        `${API_BASE}/api/sessions/${sessionId}`,
      );
    } catch (error) {
      if ((error as Error).message.includes("404")) {
        return null;
      }
      throw error;
    }
  },

  /**
   * Get all session events
   */
  async getEvents(
    sessionId: string,
    options?: {
      event_types?: string[];
      run_id?: string;
      exclude_run_id?: string;
    },
  ): Promise<SessionEventsResponse & { run_id?: string }> {
    const searchParams = new URLSearchParams();
    if (options?.event_types && options.event_types.length > 0) {
      searchParams.set("event_types", options.event_types.join(","));
    }
    if (options?.run_id) {
      searchParams.set("run_id", options.run_id);
    }
    if (options?.exclude_run_id) {
      searchParams.set("exclude_run_id", options.exclude_run_id);
    }

    const url = `${API_BASE}/api/sessions/${sessionId}/events${
      searchParams.toString() ? `?${searchParams}` : ""
    }`;
    return authFetch<SessionEventsResponse & { run_id?: string }>(url);
  },

  /**
   * Get all runs for a session
   */
  async getRuns(
    sessionId: string,
  ): Promise<{ session_id: string; runs: RunSummary[]; count: number }> {
    return authFetch(`${API_BASE}/api/sessions/${sessionId}/runs`);
  },

  /**
   * Delete a session
   */
  async delete(sessionId: string) {
    return authFetch(`${API_BASE}/api/sessions/${sessionId}`, {
      method: "DELETE",
    });
  },

  /**
   * Update session status
   */
  async updateStatus(sessionId: string, status: "active" | "archived") {
    return authFetch(
      `${API_BASE}/api/sessions/${sessionId}/status?status=${status}`,
      {
        method: "PATCH",
      },
    );
  },

  /**
   * Clear messages for a session
   */
  async clearMessages(sessionId: string) {
    return authFetch(`${API_BASE}/api/sessions/${sessionId}/clear-messages`, {
      method: "POST",
    });
  },

  /**
   * Generate title for session using LLM
   */
  async generateTitle(
    sessionId: string,
    message: string,
  ): Promise<{ title: string; session_id: string }> {
    return authFetch(
      `${API_BASE}/api/sessions/${sessionId}/generate-title?message=${encodeURIComponent(
        message,
      )}`,
      {
        method: "POST",
      },
    );
  },

  /**
   * Get session stream URL for SSE
   */
  getStreamUrl(sessionId: string, runId: string) {
    const token = getAccessToken();
    const params = new URLSearchParams();
    params.set("run_id", runId);
    if (token) {
      params.set("token", token);
    }
    return `${API_BASE}/api/chat/sessions/${sessionId}/stream?${params.toString()}`;
  },

  /**
   * Get sandbox init stream URL for SSE
   */
  getSandboxInitUrl(sessionId: string) {
    const token = getAccessToken();
    const params = new URLSearchParams();
    if (token) {
      params.set("token", token);
    }
    return `${API_BASE}/api/sessions/${sessionId}/sandbox/init?${params.toString()}`;
  },

  /**
   * Get session task status
   */
  async getStatus(
    sessionId: string,
    runId?: string,
  ): Promise<{
    session_id: string;
    run_id?: string;
    status: string;
    error?: string;
  }> {
    const params = runId ? `?run_id=${runId}` : "";
    return authFetch(
      `${API_BASE}/api/chat/sessions/${sessionId}/status${params}`,
    );
  },

  /**
   * Cancel running task for a session
   */
  async cancel(sessionId: string): Promise<{
    success: boolean;
    message: string;
  }> {
    return authFetch(`${API_BASE}/api/chat/sessions/${sessionId}/cancel`, {
      method: "POST",
    });
  },

  /**
   * Submit a chat message (returns immediately)
   */
  async submitChat(
    agentId: string,
    message: string,
    sessionId?: string,
    agentOptions?: Record<string, boolean | string | number>,
  ): Promise<{
    session_id: string;
    run_id: string;
    trace_id: string;
    status: string;
  }> {
    return authFetch(`${API_BASE}/api/chat/stream?agent_id=${agentId}`, {
      method: "POST",
      body: JSON.stringify({
        message,
        session_id: sessionId,
        agent_options: agentOptions,
      }),
    });
  },
};

// ============================================
// Agent API - Agent 相关
// ============================================

export const agentApi = {
  /**
   * List all agents
   */
  async list() {
    return authFetch(`${API_BASE}/agents`);
  },

  /**
   * Stream chat endpoint URL
   */
  getStreamUrl(agentId: string) {
    return `${API_BASE}/${agentId}/stream`;
  },

  /**
   * Non-streaming chat
   */
  async chat(agentId: string, message: string, sessionId?: string) {
    return authFetch(`${API_BASE}/${agentId}/chat`, {
      method: "POST",
      body: JSON.stringify({ message, session_id: sessionId }),
    });
  },

  /**
   * 获取带认证的 Stream URL（用于 EventSource）
   */
  getAuthenticatedStreamUrl(agentId: string, sessionId?: string) {
    const token = getAccessToken();
    const params = new URLSearchParams();
    if (token) {
      params.set("token", token);
    }
    if (sessionId) {
      params.set("session_id", sessionId);
    }
    return `${API_BASE}/${agentId}/stream?${params.toString()}`;
  },
};

// ============================================
// Skill API - 技能管理
// ============================================

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
};

// ============================================
// Settings API - 系统设置
// ============================================

export const settingsApi = {
  /**
   * Get all settings grouped by category
   */
  async list(): Promise<SettingsResponse> {
    return authFetch<SettingsResponse>(`${API_BASE}/api/settings/`);
  },

  /**
   * Get single setting
   */
  async get(key: string): Promise<SettingItem> {
    return authFetch<SettingItem>(`${API_BASE}/api/settings/${key}`);
  },

  /**
   * Update a setting
   */
  async update(
    key: string,
    value: string | number | boolean | object,
  ): Promise<SettingItem> {
    return authFetch<SettingItem>(`${API_BASE}/api/settings/${key}`, {
      method: "PUT",
      body: JSON.stringify({ value }),
    });
  },

  /**
   * Reset all settings to defaults
   */
  async resetAll(): Promise<SettingResetResponse> {
    return authFetch<SettingResetResponse>(`${API_BASE}/api/settings/reset`, {
      method: "POST",
    });
  },

  /**
   * Reset single setting to default
   */
  async reset(key: string): Promise<SettingResetResponse> {
    return authFetch<SettingResetResponse>(
      `${API_BASE}/api/settings/reset/${key}`,
      {
        method: "POST",
      },
    );
  },
};

// ============================================
// MCP API - MCP Server Management
// ============================================

export const mcpApi = {
  /**
   * List all visible MCP servers
   */
  async list(): Promise<MCPServersResponse> {
    return authFetch<MCPServersResponse>(`${API_BASE}/api/mcp`);
  },

  /**
   * Get a single MCP server
   */
  async get(name: string): Promise<MCPServerResponse> {
    return authFetch<MCPServerResponse>(
      `${API_BASE}/api/mcp/${encodeURIComponent(name)}`,
    );
  },

  /**
   * Create a new MCP server
   */
  async create(data: MCPServerCreate): Promise<MCPServerResponse> {
    return authFetch<MCPServerResponse>(`${API_BASE}/api/mcp`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  /**
   * Update an MCP server (user server only)
   */
  async update(
    name: string,
    data: MCPServerUpdate,
  ): Promise<MCPServerResponse> {
    return authFetch<MCPServerResponse>(
      `${API_BASE}/api/mcp/${encodeURIComponent(name)}`,
      {
        method: "PUT",
        body: JSON.stringify(data),
      },
    );
  },

  /**
   * Update a system MCP server (admin only)
   */
  async updateSystem(
    name: string,
    data: MCPServerUpdate,
  ): Promise<MCPServerResponse> {
    return authFetch<MCPServerResponse>(
      `${API_BASE}/api/admin/mcp/${encodeURIComponent(name)}`,
      {
        method: "PUT",
        body: JSON.stringify(data),
      },
    );
  },

  /**
   * Delete an MCP server (user server only)
   */
  async delete(name: string): Promise<void> {
    return authFetch<void>(`${API_BASE}/api/mcp/${encodeURIComponent(name)}`, {
      method: "DELETE",
    });
  },

  /**
   * Delete a system MCP server (admin only)
   */
  async deleteSystem(name: string): Promise<void> {
    return authFetch<void>(
      `${API_BASE}/api/admin/mcp/${encodeURIComponent(name)}`,
      {
        method: "DELETE",
      },
    );
  },

  /**
   * Toggle MCP server enabled status
   */
  async toggle(name: string): Promise<MCPServerToggleResponse> {
    return authFetch<MCPServerToggleResponse>(
      `${API_BASE}/api/mcp/${encodeURIComponent(name)}/toggle`,
      {
        method: "PATCH",
      },
    );
  },

  /**
   * Import MCP servers from JSON
   */
  async import(data: MCPImportRequest): Promise<MCPImportResponse> {
    return authFetch<MCPImportResponse>(`${API_BASE}/api/mcp/import`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  /**
   * Export MCP servers
   */
  async export(): Promise<MCPExportResponse> {
    return authFetch<MCPExportResponse>(`${API_BASE}/api/mcp/export`);
  },
};

// ============================================
// Upload API - 文件上传
// ============================================

interface UploadResult {
  key: string;
  url: string;
  size: number;
  content_type: string;
}

interface StorageConfig {
  enabled: boolean;
  provider: string | null;
  max_file_size: number | null;
}

interface SignedUrlItem {
  key: string;
  url: string | null;
  error?: string;
}

export const uploadApi = {
  /**
   * 上传文件
   */
  async uploadFile(
    file: File,
    folder: string = "uploads",
  ): Promise<UploadResult> {
    const formData = new FormData();
    formData.append("file", file);

    const token = getAccessToken();
    const response = await fetch(
      `${API_BASE}/api/upload/upload?folder=${encodeURIComponent(folder)}`,
      {
        method: "POST",
        body: formData,
        headers: token
          ? {
              Authorization: `Bearer ${token}`,
            }
          : {},
        credentials: "include",
      },
    );

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(
        errorData.detail || `Upload failed: ${response.statusText}`,
      );
    }

    return response.json();
  },

  /**
   * 上传头像
   */
  async uploadAvatar(file: File): Promise<UploadResult> {
    const formData = new FormData();
    formData.append("file", file);

    const token = getAccessToken();
    const response = await fetch(`${API_BASE}/api/upload/upload/avatar`, {
      method: "POST",
      body: formData,
      headers: token
        ? {
            Authorization: `Bearer ${token}`,
          }
        : {},
      credentials: "include",
    });

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(
        errorData.detail || `Upload failed: ${response.statusText}`,
      );
    }

    return response.json();
  },

  /**
   * 获取存储配置
   */
  async getConfig(): Promise<StorageConfig> {
    return authFetch<StorageConfig>(`${API_BASE}/api/upload/config`);
  },

  /**
   * 获取 S3 签名 URL（用于访问私有文件）
   */
  async getSignedUrl(key: string): Promise<string> {
    const result = await authFetch<SignedUrlItem>(
      `${API_BASE}/api/upload/signed-url?key=${encodeURIComponent(key)}`,
    );
    if (result.error || !result.url) {
      throw new Error(result.error || "Failed to get signed URL");
    }
    return result.url;
  },

  /**
   * 批量获取 S3 签名 URL
   */
  async getSignedUrls(
    keys: string[],
    expires: number = 3600,
  ): Promise<{ urls: SignedUrlItem[]; expires_in: number }> {
    return authFetch(`${API_BASE}/api/upload/signed-urls`, {
      method: "POST",
      body: JSON.stringify({ keys, expires }),
    });
  },
};

// ============================================
// Version API - 版本信息
// ============================================

export const versionApi = {
  /**
   * Get application version info
   */
  async get(): Promise<VersionInfo> {
    return authFetch<VersionInfo>(`${API_BASE}/api/version`, {
      skipAuth: true,
    });
  },

  /**
   * Check for updates (force refresh from GitHub)
   */
  async checkForUpdates(): Promise<VersionInfo> {
    return authFetch<VersionInfo>(
      `${API_BASE}/api/version?force_refresh=true`,
      {
        skipAuth: true,
      },
    );
  },
};
