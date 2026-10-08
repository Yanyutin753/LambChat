/**
 * 运行时服务器地址存储（打包壳）。
 *
 * 独立成无依赖小模块：config.ts（URL 拼接）与 serverConfig.ts（壳网络改写）
 * 都要读它，放在任何一方都会形成环依赖。构建期 VITE_API_BASE 不参与这里。
 */

import { clearTokens } from "./token";

const STORAGE_KEY = "lambchat_server_url";

/** 归一化服务器地址：去空白与尾部斜杠；裸域名补 https://。空/非法返回 ""。 */
export function normalizeServerUrl(raw: string): string {
  const trimmed = raw.trim();
  if (!trimmed) return "";
  const withScheme = /^https?:\/\//i.test(trimmed)
    ? trimmed
    : `https://${trimmed}`;
  try {
    const parsed = new URL(withScheme);
    const loopback =
      parsed.hostname === "localhost" ||
      parsed.hostname === "[::1]" ||
      /^127(?:\.\d{1,3}){3}$/.test(parsed.hostname);
    if (
      !["http:", "https:"].includes(parsed.protocol) ||
      (parsed.protocol === "http:" && !loopback) ||
      parsed.username ||
      parsed.password ||
      withScheme.includes("?") ||
      withScheme.includes("#")
    )
      return "";
    if (!parsed.hostname || !parsed.hostname.includes(".")) {
      if (!loopback && !/^\d+\.\d+\.\d+\.\d+$/.test(parsed.hostname)) {
        return "";
      }
    }
    return withScheme.replace(/\/+$/, "");
  } catch {
    return "";
  }
}

export function getStoredServerUrl(): string | null {
  if (typeof window === "undefined" || !window.localStorage) return null;
  const raw = window.localStorage.getItem(STORAGE_KEY);
  const normalized = raw ? normalizeServerUrl(raw) : "";
  return normalized || null;
}

export function hasUnsafeStoredServerUrl(): boolean {
  if (typeof window === "undefined" || !window.localStorage) return false;
  const raw = window.localStorage.getItem(STORAGE_KEY);
  return Boolean(raw && !normalizeServerUrl(raw));
}

/** 保存服务器地址（归一化后）；返回归一化结果。 */
export function setStoredServerUrl(raw: string): string {
  const normalized = normalizeServerUrl(raw);
  if (normalized) {
    if (normalized !== getStoredServerUrl()) clearTokens();
    window.localStorage.setItem(STORAGE_KEY, normalized);
  }
  return normalized;
}

export function clearStoredServerUrl(): void {
  if (typeof window === "undefined" || !window.localStorage) return;
  if (window.localStorage.getItem(STORAGE_KEY)) clearTokens();
  window.localStorage.removeItem(STORAGE_KEY);
}
