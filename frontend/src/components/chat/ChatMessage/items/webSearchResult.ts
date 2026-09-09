/** web_search 工具结果的归一化解析（后端字段 snake_case → 前端 camelCase）。 */

export interface WebSearchResultItem {
  title: string;
  url: string;
  snippet: string;
  score: number | null;
  faviconUrl: string | null;
  publishedDate: string | null;
}

export interface WebSearchImage {
  url: string;
  description: string | null;
}

export interface WebSearchSummary {
  provider: string;
  answer: string | null;
  results: WebSearchResultItem[];
  images: WebSearchImage[];
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function asString(value: unknown): string | null {
  return typeof value === "string" && value.trim() ? value.trim() : null;
}

function asScore(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function parseResultEntry(entry: Record<string, unknown>): WebSearchResultItem | null {
  const url = asString(entry.url);
  if (!url) return null;
  return {
    title: asString(entry.title) ?? "",
    url,
    snippet: asString(entry.snippet) ?? "",
    score: asScore(entry.score),
    faviconUrl: asString(entry.favicon_url) ?? asString(entry.faviconUrl),
    publishedDate: asString(entry.published_date) ?? asString(entry.publishedDate),
  };
}

function parseImageEntry(entry: unknown): WebSearchImage | null {
  if (typeof entry === "string") {
    const url = asString(entry);
    return url ? { url, description: null } : null;
  }
  if (!isRecord(entry)) return null;
  const url = asString(entry.url);
  return url ? { url, description: asString(entry.description) } : null;
}

export function parseWebSearchResult(result: unknown): WebSearchSummary | null {
  let data: unknown = result;
  if (typeof data === "string") {
    try {
      data = JSON.parse(data);
    } catch {
      return null;
    }
  }
  if (!isRecord(data) || data.success === false) return null;
  if (!Array.isArray(data.results)) return null;

  return {
    provider: asString(data.provider) ?? "",
    answer: asString(data.answer),
    results: data.results
      .filter(isRecord)
      .map(parseResultEntry)
      .filter((item): item is WebSearchResultItem => item !== null),
    images: Array.isArray(data.images)
      ? data.images
          .map(parseImageEntry)
          .filter((item): item is WebSearchImage => item !== null)
      : [],
  };
}

/** 从 URL 提取 host（失败时返回空串）。 */
export function hostFromUrl(url: string): string {
  try {
    return new URL(url).host;
  } catch {
    return "";
  }
}

const SECOND_LEVEL_TLDS = new Set([
  "co",
  "com",
  "gov",
  "ac",
  "net",
  "org",
  "edu",
]);

/**
 * 提取短站点名（ChatGPT 引用卡风格）：去 www. 与二级子域，
 * 如 zhuanlan.zhihu.com → zhihu.com、www.bbc.co.uk → bbc.co.uk。
 */
export function siteLabelFromUrl(url: string): string {
  try {
    const parts = new URL(url).host.replace(/^www\./, "").split(".");
    if (parts.length <= 2) return parts.join(".");
    const publicSuffix =
      parts.length >= 3 && SECOND_LEVEL_TLDS.has(parts[parts.length - 2]);
    return publicSuffix
      ? parts.slice(-3).join(".")
      : parts.slice(-2).join(".");
  } catch {
    return "";
  }
}
