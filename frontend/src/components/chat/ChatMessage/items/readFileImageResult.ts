import { getFullUrl } from "../../../../services/api/config";

export interface ReadFileImageResult {
  url: string;
  name: string;
  contentType?: string;
  size?: number;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isImageUploadEntry(entry: Record<string, unknown>): boolean {
  const contentType =
    typeof entry.mime_type === "string"
      ? entry.mime_type
      : typeof entry.content_type === "string"
        ? entry.content_type
        : "";

  if (contentType.toLowerCase().startsWith("image/")) return true;

  const url = typeof entry.url === "string" ? entry.url : "";
  return /\.(png|jpe?g|webp|gif|avif|bmp|svg)(?:$|[?#])/i.test(url);
}

/**
 * 识别 read_file 二进制拦截结果（ToolResultBinaryMiddleware 直传 S3 后
 * 返回的 `{url, name, mime_type, _meta.source: "read_file_binary_upload"}`），
 * 供前端直接渲染图片预览；非图片或不属于该链路时返回 null。
 */
export function extractReadFileImageResult(
  result: unknown,
  apiBase?: string,
): ReadFileImageResult | null {
  let parsed: unknown = result;
  if (typeof result === "string") {
    try {
      parsed = JSON.parse(result);
    } catch {
      return null;
    }
  }
  if (!isRecord(parsed)) return null;

  const meta = isRecord(parsed._meta) ? parsed._meta : undefined;
  if (meta?.source !== "read_file_binary_upload") return null;
  if (typeof parsed.url !== "string" || !parsed.url) return null;
  if (!isImageUploadEntry(parsed)) return null;

  const url = getFullUrl(parsed.url, apiBase) || parsed.url;
  return {
    url,
    name:
      typeof parsed.name === "string" && parsed.name
        ? parsed.name
        : url.split("/").pop() || url,
    contentType:
      typeof parsed.mime_type === "string" ? parsed.mime_type : undefined,
    size: typeof parsed.size === "number" ? parsed.size : undefined,
  };
}
