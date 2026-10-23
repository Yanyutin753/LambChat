import {
  getOwnUploadFileUrl,
  isCurrentFileAccount,
  resolveUploadFileUrl,
} from "../../services/api/uploadFileUrl";
import { getAccessToken } from "../../services/api/token";

const textCache = new Map<
  string,
  { request: Promise<string>; expiresAt: number }
>();
const arrayBufferCache = new Map<
  string,
  { request: Promise<ArrayBuffer>; expiresAt: number }
>();
let cacheAccount: string | null | undefined;

function syncCacheAccount(): string | null {
  const account = typeof localStorage === "undefined" ? null : getAccessToken();
  if (account !== cacheAccount) {
    clearDocumentFetchCaches();
    cacheAccount = account;
  }
  return account;
}

/**
 * Build the app-proxy variant (?proxy=true) of an upload file URL.
 *
 * The proxy endpoint streams the file through the backend instead of 302
 * redirecting to object storage; clients that cannot reach the storage
 * endpoint directly (e.g. mainland networks vs overseas buckets) can still
 * download through the app origin. Returns null when the URL is not an
 * upload proxy URL or already requests the proxy.
 */
export function buildProxyFallbackUrl(url: string): string | null {
  let parsed: URL;
  try {
    parsed = new URL(url, "https://placeholder.invalid");
  } catch {
    return null;
  }
  if (!parsed.pathname.startsWith("/api/upload/file/")) {
    return null;
  }
  if (parsed.searchParams.get("proxy") === "true") {
    return null;
  }
  parsed.searchParams.set("proxy", "true");
  if (/^https?:\/\//i.test(url)) return parsed.toString();
  const path = `${parsed.pathname}${parsed.search}${parsed.hash}`;
  return url.startsWith("//") ? `//${parsed.host}${path}` : path;
}

function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

async function fetchWithValidation(
  url: string,
  init?: RequestInit,
): Promise<Response> {
  const ownUrl = getOwnUploadFileUrl(url);
  const legacyTool =
    !!ownUrl?.pathname.startsWith("/api/upload/file/tool_binaries/") &&
    !ownUrl.searchParams.has("file_token");
  if (
    ownUrl &&
    (ownUrl.pathname.startsWith("/api/upload/file/cua_screenshots/") ||
      legacyTool)
  ) {
    if (legacyTool) ownUrl.searchParams.set("proxy", "true");
    const { authenticatedRequest } = await import(
      "../../services/api/authenticatedRequest"
    );
    const response = await authenticatedRequest(ownUrl.toString(), {
      ...init,
      cache: "no-store",
      redirect: "error",
    });
    if (!response.ok) throw new Error(`File unavailable: ${response.status}`);
    return response;
  }
  url = await resolveUploadFileUrl(url);
  let response: Response | null = null;
  let networkError: unknown = null;
  try {
    response = await fetch(url, init);
  } catch (error) {
    // 主动取消（如导出 ZIP 的超时 abort）不是网络故障，直接透传，不做代理重试
    if (isAbortError(error)) {
      throw error;
    }
    networkError = error;
  }

  if (response?.ok) {
    return response;
  }

  const fallbackUrl = buildProxyFallbackUrl(url);
  if (fallbackUrl) {
    void response?.body?.cancel().catch(() => {});
    const retried = await fetch(fallbackUrl, init);
    if (retried.ok) {
      return retried;
    }
    throw new Error(`Failed to fetch file: ${retried.status}`);
  }

  if (networkError !== null) {
    throw networkError;
  }
  throw new Error(`Failed to fetch file: ${response?.status}`);
}

/** Fetch an upload file URL with automatic ?proxy=true fallback (no caching). */
export async function fetchUploadFile(
  url: string,
  init?: RequestInit,
): Promise<Response> {
  return fetchWithValidation(url, init);
}

/**
 * One-shot proxy retry src for media elements (<img>/<video>/<audio>) whose
 * direct load failed (e.g. the 302 storage target is unreachable). Returns
 * the ?proxy=true src to assign once, or null when no retry applies.
 */
export function mediaProxyFallbackSrc(el: {
  src: string;
  dataset: Record<string, string | undefined>;
}): string | null {
  if (el.dataset.proxyFallback === "1") {
    return null;
  }
  const fallback = buildProxyFallbackUrl(el.src);
  if (!fallback) {
    return null;
  }
  el.dataset.proxyFallback = "1";
  return fallback;
}

export function fetchDocumentText(url: string): Promise<string> {
  const previewUrl = getOwnUploadFileUrl(url);
  if (previewUrl) {
    previewUrl.searchParams.set("resolve_resources", "true");
    url =
      url.startsWith("/") && !url.startsWith("//")
        ? `${previewUrl.pathname}${previewUrl.search}${previewUrl.hash}`
        : previewUrl.toString();
  }
  const account = syncCacheAccount();
  const key = `${account}\n${url}`;
  const cached = textCache.get(key);
  if (cached && cached.expiresAt > Date.now()) {
    return cached.request;
  }

  const request = fetchWithValidation(url)
    .then(async (response) => {
      const value = await response.text();
      syncCacheAccount();
      if (!isCurrentFileAccount(account))
        throw new Error("File account changed");
      return value;
    })
    .catch((error) => {
      if (textCache.get(key)?.request === request) textCache.delete(key);
      throw error;
    });

  textCache.set(key, { request, expiresAt: Date.now() + 5 * 60_000 });
  while (textCache.size > 64) textCache.delete(textCache.keys().next().value!);
  return request;
}

export function fetchDocumentArrayBuffer(url: string): Promise<ArrayBuffer> {
  const account = syncCacheAccount();
  const key = `${account}\n${url}`;
  const cached = arrayBufferCache.get(key);
  if (cached && cached.expiresAt > Date.now()) {
    return cached.request;
  }

  const request = fetchWithValidation(url)
    .then(async (response) => {
      const value = await response.arrayBuffer();
      syncCacheAccount();
      if (!isCurrentFileAccount(account))
        throw new Error("File account changed");
      return value;
    })
    .catch((error) => {
      if (arrayBufferCache.get(key)?.request === request)
        arrayBufferCache.delete(key);
      throw error;
    });

  arrayBufferCache.set(key, { request, expiresAt: Date.now() + 5 * 60_000 });
  while (arrayBufferCache.size > 64)
    arrayBufferCache.delete(arrayBufferCache.keys().next().value!);
  return request;
}

export function clearDocumentFetchCaches(): void {
  textCache.clear();
  arrayBufferCache.clear();
}
