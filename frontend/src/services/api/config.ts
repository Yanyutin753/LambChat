/**
 * API configuration and URL utilities
 */

const API_BASE = import.meta.env.VITE_API_BASE || "";
export { API_BASE };

// 全局 API Base URL（可从 settings 动态配置）
let _dynamicApiBaseUrl: string | null = null;

/**
 * 设置动态 API Base URL（从 settings 加载）
 */
export function setDynamicApiBaseUrl(url: string | undefined | null) {
  _dynamicApiBaseUrl = url || null;
}

/**
 * 获取当前使用的 API Base URL
 * 优先使用 settings 中配置的，否则使用环境变量
 */
export function getApiBaseUrl(): string {
  if (_dynamicApiBaseUrl) {
    return _dynamicApiBaseUrl;
  }
  return API_BASE;
}

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
  // 如果是相对路径，拼接 API Base URL（优先使用 settings 中的配置）
  return getApiBaseUrl() + url;
}
