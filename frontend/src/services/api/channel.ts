/**
 * Channel API - Generic channel configuration service
 */

import { API_BASE } from "./config";
import { authFetch } from "./fetch";
import type {
  ChannelType,
  ChannelMetadata,
  ChannelConfigResponse,
  ChannelConfigStatus,
  ChannelConfigCreate,
  ChannelConfigUpdate,
  ChannelTypeListResponse,
  ChannelListResponse,
} from "../../types/channel";

export interface FeishuRegistrationStatus {
  session_id: string;
  status: string;
  qr_url?: string | null;
  expire_in?: number | null;
  app_id?: string | null;
  app_secret?: string | null;
  error?: string | null;
}

export const channelApi = {
  /**
   * Get all available channel types with metadata
   */
  async getTypes(): Promise<ChannelMetadata[]> {
    const response = await authFetch<ChannelTypeListResponse>(
      `${API_BASE}/api/channels/types`,
    );
    return response.types;
  },

  /**
   * Get all configured channel instances for current user
   */
  async list(): Promise<ChannelConfigResponse[]> {
    const response = await authFetch<ChannelListResponse>(
      `${API_BASE}/api/channels/`,
    );
    return response.channels;
  },

  /**
   * Get all instances of a specific channel type
   */
  async listByType(channelType: ChannelType): Promise<ChannelConfigResponse[]> {
    const response = await authFetch<ChannelListResponse>(
      `${API_BASE}/api/channels/${channelType}`,
    );
    return response.channels;
  },

  /**
   * Get a specific channel instance
   */
  async get(
    channelType: ChannelType,
    instanceId: string,
  ): Promise<ChannelConfigResponse | null> {
    return authFetch<ChannelConfigResponse | null>(
      `${API_BASE}/api/channels/${channelType}/${instanceId}`,
    );
  },

  /**
   * Create a channel instance
   */
  async create(data: ChannelConfigCreate): Promise<ChannelConfigResponse> {
    return authFetch<ChannelConfigResponse>(
      `${API_BASE}/api/channels/${data.channel_type}`,
      {
        method: "POST",
        body: JSON.stringify(data),
      },
    );
  },

  /**
   * Update a channel instance
   */
  async update(
    channelType: ChannelType,
    instanceId: string,
    data: ChannelConfigUpdate,
  ): Promise<ChannelConfigResponse> {
    return authFetch<ChannelConfigResponse>(
      `${API_BASE}/api/channels/${channelType}/${instanceId}`,
      {
        method: "PUT",
        body: JSON.stringify(data),
      },
    );
  },

  /**
   * Delete a channel instance
   */
  async delete(
    channelType: ChannelType,
    instanceId: string,
  ): Promise<{ message: string }> {
    return authFetch<{ message: string }>(
      `${API_BASE}/api/channels/${channelType}/${instanceId}`,
      {
        method: "DELETE",
      },
    );
  },

  /**
   * Get channel connection status for an instance
   */
  async getStatus(
    channelType: ChannelType,
    instanceId: string,
  ): Promise<ChannelConfigStatus> {
    return authFetch<ChannelConfigStatus>(
      `${API_BASE}/api/channels/${channelType}/${instanceId}/status`,
    );
  },

  /**
   * Test channel connection for an instance
   */
  async test(
    channelType: ChannelType,
    instanceId: string,
  ): Promise<{ success: boolean; message: string }> {
    return authFetch<{ success: boolean; message: string }>(
      `${API_BASE}/api/channels/${channelType}/${instanceId}/test`,
      {
        method: "POST",
      },
    );
  },

  async startFeishuRegistration(): Promise<FeishuRegistrationStatus> {
    return authFetch<FeishuRegistrationStatus>(
      `${API_BASE}/api/channels/feishu/registrations`,
      {
        method: "POST",
      },
    );
  },

  async getFeishuRegistration(
    sessionId: string,
  ): Promise<FeishuRegistrationStatus> {
    return authFetch<FeishuRegistrationStatus>(
      `${API_BASE}/api/channels/feishu/registrations/${sessionId}`,
    );
  },

  async cancelFeishuRegistration(
    sessionId: string,
  ): Promise<{ cancelled: boolean }> {
    return authFetch<{ cancelled: boolean }>(
      `${API_BASE}/api/channels/feishu/registrations/${sessionId}`,
      {
        method: "DELETE",
      },
    );
  },

  /** 发起微信 iLink 扫码登录，返回二维码 */
  async startWeixinRegistration(): Promise<{
    qr_code: string;
    qr_url: string;
    expires_in: number;
    interval: number;
  }> {
    return authFetch(`${API_BASE}/api/channels/weixin/registrations`, {
      method: "POST",
    });
  },

  /** 轮询微信扫码状态；success 时返回 bot_token */
  async pollWeixinRegistration(
    qrCode: string,
  ): Promise<{
    status: "pending" | "scanned" | "success" | "expired" | "error";
    bot_token?: string;
    message?: string;
    interval?: number;
  }> {
    return authFetch(
      `${API_BASE}/api/channels/weixin/registrations/${encodeURIComponent(qrCode)}`,
    );
  },
};
