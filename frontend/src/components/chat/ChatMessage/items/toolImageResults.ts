import { getFullUrl } from "../../../../services/api/config";

export interface GeneratedImageResult {
  url: string;
  name: string;
  contentType?: string;
  size?: number;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function getGeneratedImageModel(
  result: unknown,
  requestedModel: unknown,
): string {
  let parsed = result;
  if (typeof parsed === "string") {
    try {
      parsed = JSON.parse(parsed);
    } catch {
      parsed = null;
    }
  }
  if (isRecord(parsed) && typeof parsed.model === "string" && parsed.model) {
    return parsed.model;
  }
  return typeof requestedModel === "string" ? requestedModel : "";
}

export function fileNameFromUrl(url: string): string {
  try {
    const baseUrl =
      typeof window === "undefined"
        ? "http://localhost"
        : window.location.origin;
    const pathname = new URL(url, baseUrl).pathname;
    const lastSegment = pathname.split("/").filter(Boolean).pop();
    return lastSegment ? decodeURIComponent(lastSegment) : url;
  } catch {
    const lastSegment = url.split("?")[0]?.split("/").filter(Boolean).pop();
    return lastSegment ? decodeURIComponent(lastSegment) : url;
  }
}

function isImageEntry(entry: Record<string, unknown>): boolean {
  const contentType =
    typeof entry.content_type === "string"
      ? entry.content_type
      : typeof entry.contentType === "string"
        ? entry.contentType
        : "";

  if (contentType.toLowerCase().startsWith("image/")) return true;

  const url = typeof entry.url === "string" ? entry.url : "";
  return /\.(png|jpe?g|webp|gif|avif|bmp|svg)(?:$|[?#])/i.test(url);
}

export function extractGeneratedImageResults(
  result: unknown,
  apiBase?: string,
): GeneratedImageResult[] {
  if (!isRecord(result) || !Array.isArray(result.images)) return [];

  return result.images
    .filter(isRecord)
    .filter((entry) => typeof entry.url === "string" && isImageEntry(entry))
    .map((entry) => {
      const url = entry.url as string;
      const resolvedUrl = getFullUrl(url, apiBase) || url;
      const contentType =
        typeof entry.content_type === "string"
          ? entry.content_type
          : typeof entry.contentType === "string"
            ? entry.contentType
            : undefined;

      return {
        url: resolvedUrl,
        name: fileNameFromUrl(url),
        contentType,
        ...(typeof entry.size === "number" &&
        Number.isFinite(entry.size) &&
        entry.size >= 0
          ? { size: entry.size }
          : {}),
      };
    });
}

/**
 * 识别「单个图片负载」形态的工具结果（如 `{url, mime_type, size}`），
 * 供通用工具结果渲染直接出图而不是裸 JSON。要求 url 扩展名或
 * mime/content_type 明确是图片，普通链接对象不会被误判。
 */
export function extractSingleImageResult(
  result: unknown,
  apiBase?: string,
): GeneratedImageResult | null {
  let parsed: unknown = result;
  if (typeof result === "string") {
    try {
      parsed = JSON.parse(result);
    } catch {
      return null;
    }
  }
  if (!isRecord(parsed)) return null;
  if (typeof parsed.url !== "string" || !parsed.url) return null;
  if (!isImageEntry(parsed)) return null;

  const url = getFullUrl(parsed.url, apiBase) || parsed.url;
  return { url, name: fileNameFromUrl(parsed.url) };
}
