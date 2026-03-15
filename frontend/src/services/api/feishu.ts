/**
 * Feishu API - 飞书渠道配置
 */

import { API_BASE } from "./config";
import { authFetch } from "./fetch";

export interface FeishuConfigResponse {
  user_id: string;
  app_id: string;
  has_app_secret: boolean;
  encrypt_key: string;
  verification_token: string;
  react_emoji: string;
  group_policy: "open" | "mention";
  enabled: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface FeishuConfigCreate {
  app_id: string;
  app_secret: string;
  encrypt_key?: string;
  verification_token?: string;
  react_emoji?: string;
  group_policy?: "open" | "mention";
  enabled?: boolean;
}

export interface FeishuConfigUpdate {
  app_id?: string;
  app_secret?: string;
  encrypt_key?: string;
  verification_token?: string;
  react_emoji?: string;
  group_policy?: "open" | "mention";
  enabled?: boolean;
}

export interface FeishuConfigStatus {
  enabled: boolean;
  connected: boolean;
  error_message?: string;
  last_connected_at?: string;
}

export const feishuApi = {
  /**
   * Get current user's Feishu configuration
   */
  async get(): Promise<FeishuConfigResponse | null> {
    return authFetch<FeishuConfigResponse | null>(`${API_BASE}/api/feishu/`);
  },

  /**
   * Create Feishu configuration
   */
  async create(config: FeishuConfigCreate): Promise<FeishuConfigResponse> {
    return authFetch<FeishuConfigResponse>(`${API_BASE}/api/feishu/`, {
      method: "POST",
      body: JSON.stringify(config),
    });
  },

  /**
   * Update Feishu configuration
   */
  async update(config: FeishuConfigUpdate): Promise<FeishuConfigResponse> {
    return authFetch<FeishuConfigResponse>(`${API_BASE}/api/feishu/`, {
      method: "PUT",
      body: JSON.stringify(config),
    });
  },

  /**
   * Delete Feishu configuration
   */
  async delete(): Promise<{ message: string }> {
    return authFetch<{ message: string }>(`${API_BASE}/api/feishu/`, {
      method: "DELETE",
    });
  },

  /**
   * Get Feishu connection status
   */
  async getStatus(): Promise<FeishuConfigStatus> {
    return authFetch<FeishuConfigStatus>(`${API_BASE}/api/feishu/status`);
  },

  /**
   * Test Feishu connection
   */
  async test(): Promise<{ success: boolean; message: string }> {
    return authFetch<{ success: boolean; message: string }>(
      `${API_BASE}/api/feishu/test`,
      {
        method: "POST",
      },
    );
  },
};
