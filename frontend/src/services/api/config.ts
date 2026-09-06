/**
 * API configuration and URL utilities
 */

import { getStoredServerUrl } from "./serverUrlStore";

const configuredApiBase =
  (import.meta as ImportMeta & { env?: Record<string, string | undefined> }).env
    ?.VITE_API_BASE || "";

function normalizeApiBase(apiBase: string): string {
  return apiBase.replace(/\/+$/, "");
}

const API_BASE = normalizeApiBase(configuredApiBase);
export { API_BASE };

export interface BrowserLocationLike {
  protocol: string;
  host: string;
  hostname?: string;
}

interface NativeRuntimeGlobalLike {
  Capacitor?: { isNativePlatform?: () => boolean };
  __TAURI__?: unknown;
  __TAURI_INTERNALS__?: unknown;
}

export function buildApiUrl(path: string, apiBase: string = API_BASE): string {
  if (path.startsWith("http://") || path.startsWith("https://")) {
    return path;
  }

  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const normalizedBase = normalizeApiBase(apiBase);
  return normalizedBase ? `${normalizedBase}${normalizedPath}` : normalizedPath;
}

export function buildWebSocketUrl(
  path: string = "/ws",
  apiBase: string = API_BASE,
  locationLike?: BrowserLocationLike,
): string {
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;
  const normalizedBase = normalizeApiBase(apiBase);

  if (normalizedBase) {
    const url = new URL(normalizedPath, normalizedBase);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    return url.toString();
  }

  const location =
    locationLike || (typeof window !== "undefined" ? window.location : null);
  if (!location) {
    return normalizedPath;
  }

  const protocol = location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${location.host}${normalizedPath}`;
}

/** 原生壳运行时判定参数（getFullUrl 等纯函数注入测试替身用）。 */
export interface RuntimeDetectOptions {
  locationLike?: Partial<BrowserLocationLike> | null;
  globalLike?: NativeRuntimeGlobalLike | null;
}

/** 非 http(s) 的 webview scheme 绝对地址（tauri://localhost/…）剥出路径部分。 */
const WEBVIEW_SCHEME_URL =
  /^[a-zA-Z][a-zA-Z0-9+.-]*:\/\/[^/?#]*(\/[^?#]*)?([?#].*)?$/;

function stripWebviewOrigin(url: string): string | null {
  // http(s) 绝对地址可能是外部资源或真实服务器，不剥 origin
  if (/^https?:\/\//i.test(url)) return null;
  const match = url.match(WEBVIEW_SCHEME_URL);
  if (!match) return null;
  return `${match[1] || "/"}${match[2] || ""}`;
}

/**
 * 获取完整 URL（用于处理后端返回的相对路径）
 * @param url - 可能是相对路径或完整 URL
 * @returns 完整 URL
 */
export function getFullUrl(
  url: string | undefined | null,
  apiBase: string = API_BASE,
  options: RuntimeDetectOptions = {},
): string | undefined {
  if (!url) return undefined;
  if (/^(blob:|data:)/i.test(url)) return url;

  // 原生壳内 webview origin（tauri://localhost 等）不是真实服务器：<img>/<video>/
  // <audio> 等媒体元素不走 installServerUrlNetworkPatch 改写的 fetch，相对 URL
  // 必须在此处直接解析到运行时配置的服务器，否则全部 404。
  if (isNativeAppRuntime(options.locationLike, options.globalLike)) {
    const base = (getStoredServerUrl() || apiBase).replace(/\/+$/, "");
    if (base) {
      const path = stripWebviewOrigin(url);
      const target = path ?? url;
      if (/^https?:\/\//i.test(target)) {
        // 指向 webview 自身 origin 的 http 绝对地址（Android https://localhost）
        // 重定位到真实服务器；其余绝对地址原样返回
        try {
          const parsed = new URL(target);
          const selfOrigin =
            typeof window !== "undefined" ? window.location.origin : "";
          if (selfOrigin && parsed.origin === selfOrigin) {
            return `${base}${parsed.pathname}${parsed.search}${parsed.hash}`;
          }
        } catch {
          // 非法绝对地址原样返回
        }
        return target;
      }
      return buildApiUrl(target, base);
    }
  }

  // Web：同源部署按当前 origin 拼接
  if (url.startsWith("http://") || url.startsWith("https://")) {
    return url;
  }
  if (apiBase) {
    return buildApiUrl(url, apiBase);
  }
  const baseUrl = typeof window !== "undefined" ? window.location.origin : "";
  return baseUrl + url;
}

export function isNativeAppRuntime(
  locationLike?: Partial<BrowserLocationLike> | null,
  globalLike?: NativeRuntimeGlobalLike | null,
): boolean {
  const location =
    locationLike || (typeof window !== "undefined" ? window.location : null);
  const globalObject =
    globalLike ||
    (typeof globalThis !== "undefined"
      ? (globalThis as NativeRuntimeGlobalLike)
      : null);

  if (globalObject?.Capacitor?.isNativePlatform?.()) {
    return true;
  }
  if (globalObject?.__TAURI__ || globalObject?.__TAURI_INTERNALS__) {
    return true;
  }

  const protocol = location?.protocol?.toLowerCase() || "";
  const hostname = location?.hostname?.toLowerCase() || "";
  return (
    protocol === "capacitor:" ||
    protocol === "ionic:" ||
    protocol === "tauri:" ||
    hostname === "tauri.localhost"
  );
}

function encodeUploadObjectKey(key: string): string {
  return key.split("/").map(encodeURIComponent).join("/");
}

export function buildUploadProxyUrl(
  url: string | undefined | null,
  apiBase: string = API_BASE,
  options: {
    force?: boolean;
    locationLike?: Partial<BrowserLocationLike> | null;
    globalLike?: NativeRuntimeGlobalLike | null;
  } = {},
): string | undefined {
  const fullUrl = getFullUrl(url, apiBase, options) || url || undefined;
  if (!fullUrl) return undefined;
  if (
    !options.force &&
    !isNativeAppRuntime(options.locationLike, options.globalLike)
  ) {
    return fullUrl;
  }

  const fallbackBase =
    typeof window !== "undefined" ? window.location.origin : "http://localhost";

  try {
    const parsed = new URL(fullUrl, fallbackBase);
    if (!parsed.pathname.startsWith("/api/upload/file/")) {
      return fullUrl;
    }
    parsed.searchParams.set("proxy", "true");
    return parsed.toString();
  } catch {
    return fullUrl;
  }
}

export function buildUploadProxyUrlFromKey(
  key: string | undefined | null,
  apiBase: string = API_BASE,
  options: Parameters<typeof buildUploadProxyUrl>[2] = {},
): string | undefined {
  if (!key) return undefined;
  const url = buildApiUrl(
    `/api/upload/file/${encodeUploadObjectKey(key)}`,
    apiBase,
  );
  if (options.force) {
    return buildUploadProxyUrl(url, apiBase, options);
  }
  // 原生壳内产出真实服务器的绝对地址：<video>/<audio> 等媒体元素直接消费该
  // URL（不经 fetch 改写），相对路径会落到 webview origin 上 404
  if (isNativeAppRuntime(options.locationLike, options.globalLike)) {
    return getFullUrl(url, apiBase, options) || url;
  }
  return url;
}
