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

  // Always send token if available (even with skipAuth)
  // skipAuth only controls error handling, not token inclusion
  const token = getAccessToken();
  if (token) {
    (finalHeaders as Record<string, string>)["Authorization"] =
      `Bearer ${token}`;
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
    // 处理 detail 为对象或字符串的情况
    let errorMessage: string;
    if (typeof errorData.detail === "object" && errorData.detail !== null) {
      // 如果 detail 是对象，提取 message 字段
      errorMessage = errorData.detail.message || JSON.stringify(errorData.detail);
    } else {
      errorMessage = errorData.detail || `Request failed: ${response.statusText}`;
    }
    throw new Error(errorMessage);
  }

  // 处理空响应
  // 注意：当响应体为空时返回 null，调用者应处理 T | null 的情况
  // 对于必须返回非空值的场景，API 应确保返回空对象 {} 而不是空响应
  const text = await response.text();
  if (!text) {
    return null as T;
  }

  try {
    return JSON.parse(text) as T;
  } catch {
    console.warn("[authFetch] Failed to parse response as JSON:", text);
    return null as T;
  }
}
