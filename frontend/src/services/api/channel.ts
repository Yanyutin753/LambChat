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
   * Get all configured channels for current user
   */
  async list(): Promise<ChannelConfigResponse[]> {
    const response = await authFetch<ChannelListResponse>(
      `${API_BASE}/api/channels/`,
    );
    return response.channels;
  },

  /**
   * Get a specific channel configuration
   */
  async get(channelType: ChannelType): Promise<ChannelConfigResponse | null> {
    return authFetch<ChannelConfigResponse | null>(
      `${API_BASE}/api/channels/${channelType}`,
    );
  },

  /**
   * Create a channel configuration
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
   * Update a channel configuration
   */
  async update(
    channelType: ChannelType,
    data: ChannelConfigUpdate,
  ): Promise<ChannelConfigResponse> {
    return authFetch<ChannelConfigResponse>(
      `${API_BASE}/api/channels/${channelType}`,
      {
        method: "PUT",
        body: JSON.stringify(data),
      },
    );
  },

  /**
   * Delete a channel configuration
   */
  async delete(channelType: ChannelType): Promise<{ message: string }> {
    return authFetch<{ message: string }>(
      `${API_BASE}/api/channels/${channelType}`,
      {
        method: "DELETE",
      },
    );
  },

  /**
   * Get channel connection status
   */
  async getStatus(channelType: ChannelType): Promise<ChannelConfigStatus> {
    return authFetch<ChannelConfigStatus>(
      `${API_BASE}/api/channels/${channelType}/status`,
    );
  },

  /**
   * Test channel connection
   */
  async test(
    channelType: ChannelType,
  ): Promise<{ success: boolean; message: string }> {
    return authFetch<{ success: boolean; message: string }>(
      `${API_BASE}/api/channels/${channelType}/test`,
      {
        method: "POST",
      },
    );
  },
};
