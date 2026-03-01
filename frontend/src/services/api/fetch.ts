/**
 * Authenticated fetch wrapper with token refresh support
 */

import { API_BASE } from "./config";
import {
  getAccessToken,
  getRefreshToken,
  setTokens,
  clearTokens,
} from "./token";

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
 */
function onRefreshFailed(): void {
  refreshSubscribers.forEach((callback) => callback(null));
  refreshSubscribers = [];
}

/**
 * 跳转到登录页并保存当前路径
 */
function redirectToLogin(): void {
  const currentPath = window.location.pathname + window.location.search;
  if (currentPath !== "/login" && currentPath !== "/") {
    sessionStorage.setItem("redirect_after_login", currentPath);
  }
  clearTokens();
  window.dispatchEvent(new CustomEvent("auth:logout"));
}

/**
 * 刷新 token 并重试原请求
 * 处理并发请求：第一个请求触发刷新，其他请求等待
 */
async function refreshTokenAndRetry<T>(
  originalRequest: () => Promise<T>,
): Promise<T> {
  if (isRefreshing) {
    return new Promise((resolve, reject) => {
      subscribeTokenRefresh((token) => {
        if (token === null) {
          reject(new Error("Token refresh failed"));
        } else {
          originalRequest().then(resolve).catch(reject);
        }
      });
    });
  }

  isRefreshing = true;

  try {
    const refreshToken = getRefreshToken();
    if (!refreshToken) {
      throw new Error("No refresh token available");
    }

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
    setTokens(tokenResponse.access_token, tokenResponse.refresh_token);
    onTokenRefreshed(tokenResponse.access_token);

    return originalRequest();
  } catch (error) {
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
    clearTokens();
    window.dispatchEvent(new CustomEvent("auth:logout"));
    throw new Error("用户权限已变更，请重新登录");
  }

  // 处理 401 未授权响应
  if (response.status === 401 && !skipAuth) {
    const refreshToken = getRefreshToken();

    if (refreshToken) {
      return refreshTokenAndRetry(() =>
        authFetch<T>(url, { ...options, skipAuth: false }),
      );
    }

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
