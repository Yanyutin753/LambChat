/**
 * Version API - 版本信息
 */

import {
  getUpdateChannel,
  type UpdateChannel,
} from "../../utils/updateChannel";
import type { VersionInfo } from "../../types";
import { API_BASE, buildApiUrl } from "./config";
import { authFetch } from "./fetch";

/**
 * 构造 release 资产的同源代理下载 URL。
 *
 * 移动端 WebView 直连 GitHub browser_download_url 会被 CORS 拦截
 * （release 下载端点不带 Access-Control-Allow-Origin），必须经
 * 自托管后端流式转发，进度条（content-length）照常工作。
 */
export function buildReleaseAssetDownloadUrl(
  assetName: string,
  apiBase: string = API_BASE,
  version?: string,
): string {
  return buildApiUrl(
    `/api/version/assets/${encodeURIComponent(assetName)}/download${
      version
        ? `?tag=${encodeURIComponent(`v${version.replace(/^v/, "")}`)}`
        : ""
    }`,
    apiBase,
  );
}

export const versionApi = {
  /**
   * Get application version info
   *
   * client_version 让后端按客户端 App 版本（而非服务端版本）判断 has_update。
   */
  async get(
    clientVersion?: string,
    channel: UpdateChannel = getUpdateChannel(),
  ): Promise<VersionInfo> {
    const query = new URLSearchParams();
    if (channel === "dev") query.set("channel", channel);
    if (clientVersion) {
      query.set("client_version", clientVersion);
    }
    const suffix = query.size > 0 ? `?${query}` : "";
    return authFetch<VersionInfo>(`${API_BASE}/api/version${suffix}`, {
      skipAuth: true,
    });
  },

  /**
   * Check for updates (force refresh from GitHub).
   * client_version 让后端按客户端 App 版本（而非服务端版本）判断 has_update。
   */
  async checkForUpdates(
    clientVersion?: string,
    channel: UpdateChannel = getUpdateChannel(),
  ): Promise<VersionInfo> {
    const query = new URLSearchParams({ force_refresh: "true" });
    if (channel === "dev") query.set("channel", channel);
    if (clientVersion) {
      query.set("client_version", clientVersion);
    }
    return authFetch<VersionInfo>(`${API_BASE}/api/version?${query}`, {
      skipAuth: true,
    });
  },
};
