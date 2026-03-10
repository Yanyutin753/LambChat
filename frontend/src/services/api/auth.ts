/**
 * Auth API - 认证相关
 */

import type {
  User,
  UserCreate,
  LoginRequest,
  TokenResponse,
  PermissionsResponse,
} from "../../types";
import { API_BASE } from "./config";
import { authFetch } from "./fetch";
import { setTokens, clearTokens, getRefreshToken } from "./token";

export const authApi = {
  /**
   * 用户登录
   */
  async login(credentials: LoginRequest, turnstileToken?: string): Promise<TokenResponse> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (turnstileToken) {
      headers["X-Turnstile-Token"] = turnstileToken;
    }

    const response = await authFetch<TokenResponse>(
      `${API_BASE}/api/auth/login`,
      {
        method: "POST",
        skipAuth: true,
        body: JSON.stringify(credentials),
        headers,
      },
    );

    setTokens(response.access_token, response.refresh_token);
    window.dispatchEvent(new CustomEvent("auth:login"));

    return response;
  },

  /**
   * 用户注册
   */
  async register(userData: UserCreate, turnstileToken?: string): Promise<User> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (turnstileToken) {
      headers["X-Turnstile-Token"] = turnstileToken;
    }

    return authFetch<User>(`${API_BASE}/api/auth/register`, {
      method: "POST",
      skipAuth: true,
      body: JSON.stringify(userData),
      headers,
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
    turnstileToken?: string,
  ): Promise<{ message: string }> {
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (turnstileToken) {
      headers["X-Turnstile-Token"] = turnstileToken;
    }

    return authFetch<{ message: string }>(
      `${API_BASE}/api/auth/change-password`,
      {
        method: "POST",
        body: JSON.stringify({
          old_password: oldPassword,
          new_password: newPassword,
        }),
        headers,
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

  /**
   * 获取可用的 OAuth 提供商列表
   */
  async getOAuthProviders(): Promise<{
    providers: { id: string; name: string }[];
    registration_enabled: boolean;
    turnstile?: {
      enabled: boolean;
      site_key: string;
      require_on_login: boolean;
      require_on_register: boolean;
      require_on_password_change: boolean;
    };
  }> {
    return authFetch<{
      providers: { id: string; name: string }[];
      registration_enabled: boolean;
      turnstile?: {
        enabled: boolean;
        site_key: string;
        require_on_login: boolean;
        require_on_register: boolean;
        require_on_password_change: boolean;
      };
    }>(`${API_BASE}/api/auth/oauth/providers`, { skipAuth: true });
  },

  /**
   * 发起 OAuth 授权
   */
  async getOAuthAuthorizationUrl(
    provider: string,
  ): Promise<{ authorization_url: string; state: string }> {
    return authFetch<{ authorization_url: string; state: string }>(
      `${API_BASE}/api/auth/oauth/${provider}`,
      { skipAuth: true },
    );
  },

  /**
   * 处理 OAuth 回调
   */
  async handleOAuthCallback(
    provider: string,
    code: string,
    state: string,
  ): Promise<TokenResponse> {
    const response = await authFetch<TokenResponse>(
      `${API_BASE}/api/auth/oauth/${provider}/callback`,
      {
        method: "POST",
        skipAuth: true,
        body: JSON.stringify({ code, state }),
      },
    );

    setTokens(response.access_token, response.refresh_token);
    window.dispatchEvent(new CustomEvent("auth:login"));

    return response;
  },
};
