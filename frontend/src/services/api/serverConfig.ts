/**
 * Server URL configuration and runtime network redirection for the packaged shell.
 */

import { API_BASE, isNativeAppRuntime } from "./config";

const STORAGE_KEY = "lambchat_server_url";

export interface NativeGlobalLike {
  __TAURI__?: unknown;
  __TAURI_INTERNALS__?: unknown;
  Capacitor?: { isNativePlatform?: () => boolean; getPlatform?: () => string };
}

export function isTauriRuntime(globalLike?: NativeGlobalLike | null): boolean {
  const globalObject =
    globalLike ??
    (typeof globalThis !== "undefined" ? (globalThis as NativeGlobalLike) : null);
  return Boolean(globalObject?.__TAURI__ || globalObject?.__TAURI_INTERNALS__);
}

/** 归一化服务器地址：去空白与尾部斜杠；裸域名补 https://。空/非法返回 ""。 */
export function normalizeServerUrl(raw: string): string {
  const trimmed = raw.trim();
  if (!trimmed) return "";
  const withScheme = /^https?:\/\//i.test(trimmed) ? trimmed : `https://${trimmed}`;
  try {
    const parsed = new URL(withScheme);
    if (!parsed.hostname || !parsed.hostname.includes(".")) {
      if (parsed.hostname !== "localhost" && !/^\d+\.\d+\.\d+\.\d+$/.test(parsed.hostname)) {
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

/** 保存服务器地址（归一化后）；返回归一化结果。 */
export function setStoredServerUrl(raw: string): string {
  const normalized = normalizeServerUrl(raw);
  if (normalized) {
    window.localStorage.setItem(STORAGE_KEY, normalized);
  }
  return normalized;
}

export function clearStoredServerUrl(): void {
  if (typeof window === "undefined" || !window.localStorage) return;
  window.localStorage.removeItem(STORAGE_KEY);
}

/** 生效的 API 基址：运行时配置优先，构建期 VITE_API_BASE 兜底，Web 同源空串。 */
export function effectiveApiBase(): string {
  return getStoredServerUrl() || API_BASE;
}

/** 打包客户端是否需要首启服务器配置（桌面 Tauri 壳 + 移动 Capacitor 壳）。 */
export function needsServerSetup(globalLike?: NativeGlobalLike | null): boolean {
  const native = globalLike
    ? isTauriRuntime(globalLike) ||
      Boolean(globalLike.Capacitor?.isNativePlatform?.())
    : isNativeAppRuntime();
  return native && !effectiveApiBase();
}

export function buildAbsoluteUrl(
  path: string,
  base: string = effectiveApiBase(),
): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  if (!base) return normalizedPath;
  return `${base.replace(/\/+$/, "")}${normalizedPath}`;
}

type FetchLike = typeof fetch;

export interface PatchDeps {
  fetchImpl?: FetchLike;
  WebSocketCtor?: new (url: string | URL, protocols?: string | string[]) => WebSocket;
  base?: string;
}

/**
 * 打包壳网络改写：相对 `/api`、`/ws` 请求改写到运行时配置的服务器。
 *
 * 前端 39 处按构建期 `API_BASE` 拼相对路径——打包壳内 webview origin 无意义，
 * 在网络层单点改写（fetch/EventSource 经 fetch、WebSocket 构造器），业务代码
 * 零侵入；静态资源（非 /api、/ws 开头）与绝对 URL 不受影响。
 */
export function installServerUrlNetworkPatch(deps: PatchDeps = {}): boolean {
  if (typeof window === "undefined") return false;
  // 未注入依赖（生产启动）时仅原生端安装：Web 同源部署无需改写
  if (!deps.fetchImpl && !isNativeAppRuntime()) return false;
  const base = deps.base ?? effectiveApiBase();
  if (!base) return false;

  // 相对 /api、/ws，或绝对但指向 webview 自身 origin（tauri.localhost）的
  // /api、/ws 都要改写；其余绝对 URL（外部链接/签名地址）不动
  const shouldRewrite = (url: string): boolean => {
    try {
      const parsed = new URL(url, window.location.origin);
      const isApiPath = parsed.pathname.startsWith("/api") || parsed.pathname.startsWith("/ws");
      if (!isApiPath) return false;
      return !/^https?:\/\//i.test(url) || parsed.origin === window.location.origin;
    } catch {
      return false;
    }
  };

  const rewriteUrl = (url: string): string => {
    const parsed = new URL(url, window.location.origin);
    return `${base.replace(/\/+$/, "")}${parsed.pathname}${parsed.search}`;
  };

  const rawFetch = deps.fetchImpl ?? window.fetch.bind(window);
  const patchedFetch: FetchLike = async (input, init) => {
    const url =
      typeof input === "string"
        ? input
        : input instanceof URL
          ? input.toString()
          : input instanceof Request
            ? input.url
            : "";
    if (url && shouldRewrite(url)) {
      if (typeof input === "string" || input instanceof URL) {
        return rawFetch(rewriteUrl(url), init);
      }
      // Request 不能直接作为 init：显式复制方法/头/体（流式体需 duplex）
      const cloned = new Request(rewriteUrl(url), {
        method: input.method,
        headers: input.headers,
        body: input.body,
        ...(input.body ? ({ duplex: "half" } as RequestInit) : {}),
      });
      return rawFetch(cloned, init);
    }
    return rawFetch(input, init);
  };
  window.fetch = patchedFetch;

  const RawWebSocket =
    deps.WebSocketCtor ??
    (window.WebSocket as unknown as new (
      url: string | URL,
      protocols?: string | string[],
    ) => WebSocket);
  class PatchedWebSocket extends RawWebSocket {
    constructor(url: string | URL, protocols?: string | string[]) {
      const raw = url.toString();
      const target = shouldRewrite(raw) ? rewriteUrl(raw) : raw;
      super(target, protocols);
    }
  }
  window.WebSocket = PatchedWebSocket as unknown as typeof WebSocket;

  return true;
}
