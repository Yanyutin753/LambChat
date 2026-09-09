/** web_fetch 工具结果的归一化解析（后端字段 snake_case → 前端 camelCase）。 */

export interface WebFetchSummary {
  url: string;
  finalUrl: string | null;
  provider: string;
  title: string | null;
  content: string;
  contentChars: number | null;
  truncated: boolean;
  contentType: string | null;
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function asInt(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value)
    ? Math.trunc(value)
    : null;
}

export function hostFromUrl(url: string): string | null {
  try {
    return new URL(url).hostname || null;
  } catch {
    return null;
  }
}

export function parseWebFetchResult(result: unknown): WebFetchSummary | null {
  let data: unknown = result;
  // 字符串结果是 JSON 文本（工具返回值），先解析
  if (typeof data === "string") {
    try {
      data = JSON.parse(data);
    } catch {
      return null;
    }
  }
  if (!isRecord(data)) return null;
  // 失败结果（success=false）不算可渲染摘要
  if (data.success === false) return null;
  const url = asString(data.url);
  const content = asString(data.content);
  if (!url || !content) return null;
  return {
    url,
    finalUrl: asString(data.final_url) ?? asString(data.finalUrl),
    provider: asString(data.provider) ?? "direct",
    title: asString(data.title),
    content,
    contentChars: asInt(data.content_chars) ?? asInt(data.contentChars),
    truncated: data.truncated === true,
    contentType: asString(data.content_type) ?? asString(data.contentType),
  };
}
