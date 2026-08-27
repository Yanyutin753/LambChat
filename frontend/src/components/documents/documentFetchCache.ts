const textCache = new Map<string, Promise<string>>();
const arrayBufferCache = new Map<string, Promise<ArrayBuffer>>();

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
  return `${url}${url.includes("?") ? "&" : "?"}proxy=true`;
}

function isAbortError(error: unknown): boolean {
  return error instanceof Error && error.name === "AbortError";
}

async function fetchWithValidation(
  url: string,
  init?: RequestInit,
): Promise<Response> {
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
  const cached = textCache.get(url);
  if (cached) {
    return cached;
  }

  const request = fetchWithValidation(url)
    .then((response) => response.text())
    .catch((error) => {
      textCache.delete(url);
      throw error;
    });

  textCache.set(url, request);
  return request;
}

export function fetchDocumentArrayBuffer(url: string): Promise<ArrayBuffer> {
  const cached = arrayBufferCache.get(url);
  if (cached) {
    return cached;
  }

  const request = fetchWithValidation(url)
    .then((response) => response.arrayBuffer())
    .catch((error) => {
      arrayBufferCache.delete(url);
      throw error;
    });

  arrayBufferCache.set(url, request);
  return request;
}

export function clearDocumentFetchCaches(): void {
  textCache.clear();
  arrayBufferCache.clear();
}
