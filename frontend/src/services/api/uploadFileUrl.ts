import { getFullUrl } from "./config";
import { decodeToken, getAccessToken } from "./token";

const FILE_PREFIX = "/api/upload/file/";
const CAPABILITY_SECONDS = 3600;
const MAX_ENTRIES = 128;
const capabilities = new Map<string, { url: string; expiresAt: number }>();
const inflight = new Map<string, Promise<string>>();
let cacheAccount: string | null | undefined;

export function getOwnUploadFileUrl(source?: string): URL | null {
  if (!source) return null;
  try {
    const base =
      typeof window === "undefined" ? "http://localhost" : window.location.href;
    const endpoint = new URL(getFullUrl(FILE_PREFIX) || FILE_PREFIX, base);
    const url = new URL(
      source.startsWith("//") ? source : getFullUrl(source) || source,
      endpoint,
    );
    return url.origin === endpoint.origin &&
      url.pathname.startsWith(FILE_PREFIX)
      ? url
      : null;
  } catch {
    return null;
  }
}

export function needsUploadFileCapability(source?: string): boolean {
  const url = getOwnUploadFileUrl(source);
  if (!url || url.searchParams.has("file_token")) return false;
  try {
    const key = decodeURIComponent(url.pathname.slice(FILE_PREFIX.length));
    return !/^(avatars|cua_screenshots)\//.test(key);
  } catch {
    return false;
  }
}

/** Token renewal keeps the owner; logout and different subjects invalidate late reads. */
export function isCurrentFileAccount(account: string | null): boolean {
  const current = typeof localStorage === "undefined" ? null : getAccessToken();
  if (current === account) return true;
  const subject = account ? decodeToken(account)?.sub : undefined;
  return (
    typeof subject === "string" &&
    !!subject &&
    !!current &&
    decodeToken(current)?.sub === subject
  );
}

function trimCache<T>(cache: Map<string, T>) {
  while (cache.size > MAX_ENTRIES) cache.delete(cache.keys().next().value!);
}

/** Only our upload endpoint receives account auth; media uses a key-bound capability. */
export async function resolveUploadFileUrl(source: string): Promise<string> {
  if (!needsUploadFileCapability(source)) return source;
  const url = getOwnUploadFileUrl(source)!;
  const key = decodeURIComponent(url.pathname.slice(FILE_PREFIX.length));
  const account = typeof localStorage === "undefined" ? null : getAccessToken();
  if (cacheAccount !== account) {
    capabilities.clear();
    inflight.clear();
    cacheAccount = account;
  }
  const cacheKey = `${url.origin}/${key}`;
  const cached = capabilities.get(cacheKey);
  let signedUrl: string;
  if (cached && cached.expiresAt > Date.now()) {
    signedUrl = cached.url;
  } else {
    let pending = inflight.get(cacheKey);
    if (!pending) {
      const requestedAt = Date.now();
      pending = (async () => {
        const endpoint = getFullUrl(
          `/api/upload/signed-url?key=${encodeURIComponent(
            key,
          )}&expires=${CAPABILITY_SECONDS}&app_url=true`,
        )!;
        const { authenticatedRequest } = await import("./authenticatedRequest");
        const response = await authenticatedRequest(endpoint, {
          cache: "no-store",
        });
        if (!response.ok)
          throw new Error(`File unavailable: ${response.status}`);
        const result = (await response.json()) as {
          url?: string;
          error?: string;
        };
        if (!result.url || result.error) throw new Error("File unavailable");
        if (!isCurrentFileAccount(account)) {
          throw new Error("File account changed");
        }
        const signed = getOwnUploadFileUrl(result.url);
        if (
          !signed ||
          signed.pathname !== url.pathname ||
          !signed.searchParams.get("file_token")
        )
          throw new Error("Invalid file capability");
        if (cacheAccount === account) {
          capabilities.set(cacheKey, {
            url: signed.toString(),
            expiresAt: requestedAt + (CAPABILITY_SECONDS - 60) * 1000,
          });
          trimCache(capabilities);
        }
        return signed.toString();
      })();
      inflight.set(cacheKey, pending);
      trimCache(inflight);
      void pending
        .finally(() => {
          if (inflight.get(cacheKey) === pending) inflight.delete(cacheKey);
        })
        .catch(() => {});
    }
    signedUrl = await pending;
  }
  const resolved = new URL(signedUrl);
  url.searchParams.forEach((value, name) => {
    if (name !== "file_token") resolved.searchParams.set(name, value);
  });
  resolved.hash = url.hash;
  return resolved.toString();
}
