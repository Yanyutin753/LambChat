/**
 * Settings API - 系统设置
 */

import type {
  SettingItem,
  SettingsResponse,
  SettingResetResponse,
} from "../../types";
import { API_BASE } from "./config";
import { authFetch } from "./fetch";

export const settingsApi = {
  /**
   * Get all settings grouped by category
   */
  async list(): Promise<SettingsResponse> {
    return authFetch<SettingsResponse>(`${API_BASE}/api/settings/`);
  },

  /**
   * Get single setting
   */
  async get(key: string): Promise<SettingItem> {
    return authFetch<SettingItem>(`${API_BASE}/api/settings/${key}`);
  },

  /**
   * Update a setting
   */
  async update(
    key: string,
    value: string | number | boolean | object,
  ): Promise<SettingItem> {
    return authFetch<SettingItem>(`${API_BASE}/api/settings/${key}`, {
      method: "PUT",
      body: JSON.stringify({ value }),
    });
  },

  /**
   * Reset all settings to defaults
   */
  async resetAll(): Promise<SettingResetResponse> {
    return authFetch<SettingResetResponse>(`${API_BASE}/api/settings/reset`, {
      method: "POST",
    });
  },

  /**
   * Reset single setting to default
   */
  async reset(key: string): Promise<SettingResetResponse> {
    return authFetch<SettingResetResponse>(
      `${API_BASE}/api/settings/reset/${key}`,
      {
        method: "POST",
      },
    );
  },
};
