/**
 * Admin Marketplace API - 管理员商城管理
 */

import { API_BASE } from "./config";
import { authFetch } from "./fetch";
import type {
  MarketplaceSkillResponse,
  AdminMarketplaceSkillCreate,
  AdminMarketplaceSkillUpdate,
} from "../../types";

const ADMIN_MARKETPLACE_API = `${API_BASE}/api/admin/marketplace`;

export const adminMarketplaceApi = {
  /**
   * List all marketplace skills (admin)
   */
  async list(): Promise<MarketplaceSkillResponse[]> {
    return authFetch<MarketplaceSkillResponse[]>(`${ADMIN_MARKETPLACE_API}/`);
  },

  /**
   * Create marketplace skill metadata
   */
  async create(
    data: AdminMarketplaceSkillCreate,
  ): Promise<MarketplaceSkillResponse> {
    return authFetch<MarketplaceSkillResponse>(`${ADMIN_MARKETPLACE_API}/`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  /**
   * Get marketplace skill detail (admin)
   */
  async get(skillName: string): Promise<MarketplaceSkillResponse> {
    return authFetch<MarketplaceSkillResponse>(
      `${ADMIN_MARKETPLACE_API}/${encodeURIComponent(skillName)}`,
    );
  },

  /**
   * Update marketplace skill metadata
   */
  async update(
    skillName: string,
    data: AdminMarketplaceSkillUpdate,
  ): Promise<MarketplaceSkillResponse> {
    return authFetch<MarketplaceSkillResponse>(
      `${ADMIN_MARKETPLACE_API}/${encodeURIComponent(skillName)}`,
      {
        method: "PUT",
        body: JSON.stringify(data),
      },
    );
  },

  /**
   * Delete marketplace skill
   */
  async delete(skillName: string): Promise<{ message: string }> {
    return authFetch<{ message: string }>(
      `${ADMIN_MARKETPLACE_API}/${encodeURIComponent(skillName)}`,
      {
        method: "DELETE",
      },
    );
  },

  /**
   * Upload skill files (ZIP)
   */
  async uploadZip(
    skillName: string,
    file: File,
  ): Promise<MarketplaceSkillResponse> {
    const formData = new FormData();
    formData.append("file", file);

    return authFetch<MarketplaceSkillResponse>(
      `${ADMIN_MARKETPLACE_API}/${encodeURIComponent(skillName)}/upload`,
      {
        method: "POST",
        body: formData,
      },
    );
  },
};
