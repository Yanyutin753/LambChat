export const PWA_BACKEND_PREFIXES = [
  "/api",
  "/ws",
  "/health",
  "/tools",
  "/human",
  "/services",
  "/default",
  "/data_pipeline",
] as const;

const STATIC_ASSET_PATTERN =
  /\.(?:css|js|mjs|png|jpg|jpeg|svg|webp|avif|ico|woff|woff2|ttf|otf|json|wasm)$/i;

export type PwaRequestKind = "bypass" | "navigation" | "static-asset";

interface PwaRequestInput {
  method: string;
  mode?: RequestMode | string | null;
  url: string;
  scopeOrigin: string;
  accept?: string | null;
}

export function isBackendPath(pathname: string): boolean {
  return PWA_BACKEND_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  );
}

export function isEventStreamRequest({
  accept,
  pathname,
}: {
  accept?: string | null;
  pathname: string;
}): boolean {
  return (
    Boolean(accept?.includes("text/event-stream")) ||
    pathname.includes("stream")
  );
}

export function isNavigationRequest({
  accept,
  mode,
}: {
  accept?: string | null;
  mode?: RequestMode | string | null;
}): boolean {
  return mode === "navigate" || Boolean(accept?.includes("text/html"));
}

export function isStaticAssetPath(pathname: string): boolean {
  return STATIC_ASSET_PATTERN.test(pathname);
}

export function getPwaRequestKind({
  method,
  mode,
  url,
  scopeOrigin,
  accept,
}: PwaRequestInput): PwaRequestKind {
  let parsedUrl: URL;
  try {
    parsedUrl = new URL(url);
  } catch {
    return "bypass";
  }

  if (
    method.toUpperCase() !== "GET" ||
    parsedUrl.origin !== scopeOrigin ||
    isBackendPath(parsedUrl.pathname) ||
    isEventStreamRequest({ accept, pathname: parsedUrl.pathname })
  ) {
    return "bypass";
  }

  if (isNavigationRequest({ accept, mode })) {
    return "navigation";
  }

  if (isStaticAssetPath(parsedUrl.pathname)) {
    return "static-asset";
  }

  return "bypass";
}
