/**
 * Marketplace API - Skills 商城
 */

import { API_BASE } from "./config";
import { authFetch } from "./fetch";
import type {
  MarketplaceSkillResponse,
  MarketplaceSkillFilesResponse,
  MarketplaceSkillFileResponse,
  MarketplaceInstallResponse,
  MarketplaceCreateRequest,
  TagsResponse,
} from "../../types";

const MARKETPLACE_API = `${API_BASE}/api/marketplace`;

export const marketplaceApi = {
  /**
   * List all marketplace skills
   */
  async list(params?: {
    tags?: string;
    search?: string;
    skip?: number;
    limit?: number;
  }) {
    const searchParams = new URLSearchParams();
    if (params?.tags) searchParams.set("tags", params.tags);
    if (params?.search) searchParams.set("search", params.search);
    if (params?.skip !== undefined)
      searchParams.set("skip", String(params.skip));
    if (params?.limit !== undefined)
      searchParams.set("limit", String(params.limit));

    const query = searchParams.toString();
    return authFetch<MarketplaceSkillResponse[]>(
      `${MARKETPLACE_API}/${query ? `?${query}` : ""}`,
    );
  },

  /**
   * Get all available tags
   */
  async getTags() {
    return authFetch<TagsResponse>(`${MARKETPLACE_API}/tags`);
  },

  /**
   * Get marketplace skill details
   */
  async get(skillName: string) {
    return authFetch<MarketplaceSkillResponse>(
      `${MARKETPLACE_API}/${encodeURIComponent(skillName)}`,
    );
  },

  /**
   * List marketplace skill files
   */
  async listFiles(skillName: string) {
    return authFetch<MarketplaceSkillFilesResponse>(
      `${MARKETPLACE_API}/${encodeURIComponent(skillName)}/files`,
    );
  },

  /**
   * Get marketplace skill file content
   */
  async getFile(skillName: string, filePath: string) {
    return authFetch<MarketplaceSkillFileResponse>(
      `${MARKETPLACE_API}/${encodeURIComponent(
        skillName,
      )}/files/${encodeURIComponent(filePath)}`,
    );
  },

  /**
   * Install marketplace skill to user's account
   */
  async install(skillName: string) {
    return authFetch<MarketplaceInstallResponse>(
      `${MARKETPLACE_API}/${encodeURIComponent(skillName)}/install`,
      {
        method: "POST",
      },
    );
  },

  /**
   * Update installed skill from marketplace (re-download)
   */
  async update(skillName: string) {
    return authFetch<MarketplaceInstallResponse>(
      `${MARKETPLACE_API}/${encodeURIComponent(skillName)}/update`,
      {
        method: "POST",
      },
    );
  },

  /**
   * Create and publish skill directly in marketplace
   */
  async createAndPublish(data: MarketplaceCreateRequest) {
    return authFetch<MarketplaceSkillResponse>(`${MARKETPLACE_API}/`, {
      method: "POST",
      body: JSON.stringify(data),
    });
  },

  /**
   * Admin: activate or deactivate a marketplace skill
   */
  async activate(skillName: string, isActive: boolean) {
    return authFetch<MarketplaceSkillResponse>(
      `${MARKETPLACE_API}/${encodeURIComponent(skillName)}/activate`,
      {
        method: "PATCH",
        body: JSON.stringify({ is_active: isActive }),
      },
    );
  },

  /**
   * Admin: delete a marketplace skill
   */
  async deleteSkill(skillName: string) {
    return authFetch<{ message: string }>(
      `${MARKETPLACE_API}/${encodeURIComponent(skillName)}`,
      {
        method: "DELETE",
      },
    );
  },
};
