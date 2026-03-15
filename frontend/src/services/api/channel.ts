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
};
