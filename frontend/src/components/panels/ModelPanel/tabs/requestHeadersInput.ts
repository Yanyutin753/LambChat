/** Parsing helpers for the per-model request-headers JSON textarea. */

export type ParsedRequestHeaders =
  | { ok: true; headers: Record<string, string> | undefined }
  | { ok: false; error: "invalidJson" | "notObject" };

/** Parse the request-headers JSON textarea; undefined headers = clear override. */
export function parseRequestHeadersInput(raw: string): ParsedRequestHeaders {
  const trimmed = raw.trim();
  if (!trimmed) return { ok: true, headers: undefined };
  let parsed: unknown;
  try {
    parsed = JSON.parse(trimmed);
  } catch {
    return { ok: false, error: "invalidJson" };
  }
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    return { ok: false, error: "notObject" };
  }
  const headers: Record<string, string> = {};
  for (const [key, value] of Object.entries(parsed)) {
    headers[key] = String(value);
  }
  return { ok: true, headers };
}

export function formatRequestHeaders(
  headers: Record<string, string> | null | undefined,
): string {
  if (!headers || Object.keys(headers).length === 0) return "";
  return JSON.stringify(headers, null, 2);
}
