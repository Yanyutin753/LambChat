/**
 * API configuration and URL utilities
 */

const API_BASE = import.meta.env.VITE_API_BASE || "";
export { API_BASE };

/**
 * 获取完整 URL（用于处理后端返回的相对路径）
 * @param url - 可能是相对路径或完整 URL
 * @returns 完整 URL
 */
export function getFullUrl(url: string | undefined | null): string | undefined {
  if (!url) return undefined;
  // 如果已经是完整 URL（http:// 或 https://），直接返回
  if (url.startsWith("http://") || url.startsWith("https://")) {
    return url;
  }
  // 如果是相对路径，拼接 API Base URL
  return API_BASE + url;
}
