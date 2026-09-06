/**
 * Version API - 版本信息
 */

import type { VersionInfo } from "../../types";
import { API_BASE } from "./config";
import { authFetch } from "./fetch";

export const versionApi = {
  /**
   * Get application version info
   */
  async get(): Promise<VersionInfo> {
    return authFetch<VersionInfo>(`${API_BASE}/api/version`, {
      skipAuth: true,
    });
  },

  /**
   * Check for updates (force refresh from GitHub).
   * client_version 让后端按客户端 App 版本（而非服务端版本）判断 has_update。
   */
  async checkForUpdates(clientVersion?: string): Promise<VersionInfo> {
    const query = new URLSearchParams({ force_refresh: "true" });
    if (clientVersion) {
      query.set("client_version", clientVersion);
    }
    return authFetch<VersionInfo>(`${API_BASE}/api/version?${query}`, {
      skipAuth: true,
    });
  },
};
