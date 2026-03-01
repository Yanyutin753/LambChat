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
   * Check for updates (force refresh from GitHub)
   */
  async checkForUpdates(): Promise<VersionInfo> {
    return authFetch<VersionInfo>(
      `${API_BASE}/api/version?force_refresh=true`,
      {
        skipAuth: true,
      },
    );
  },
};
