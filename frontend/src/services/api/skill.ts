/**
 * Skill API - 技能管理 (Simplified Architecture)
 *
 * New architecture: skills are stored as individual files in MongoDB.
 * - /api/skills/ - list, get, delete user skills
 * - /api/skills/{name}/files/{path} - read/write individual files
 * - /api/skills/{name}/toggle - enable/disable
 * - /api/marketplace/ - browse and install from marketplace
 */

import { API_BASE } from "./config";
import { authFetch } from "./fetch";
import type {
  UserSkillDetail,
  SkillFileResponse,
  SkillToggleResponse,
  SkillCreate,
  SkillPreferenceResponse,
  SkillPreferenceUpdate,
  MarketplaceSkillResponse,
  PublishToMarketplaceRequest,
  SkillsResponse,
} from "../../types/skill";

const SKILLS_API = `${API_BASE}/api/skills`;

export interface SkillListParams {
  skip?: number;
  limit?: number;
  q?: string;
  tags?: string[];
}

export function buildSkillListUrl(params: SkillListParams = {}): string {
  const searchParams = new URLSearchParams();
  if (params.skip !== undefined) searchParams.set("skip", String(params.skip));
  if (params.limit !== undefined)
    searchParams.set("limit", String(params.limit));
  if (params.q) searchParams.set("q", params.q);
  params.tags?.forEach((tag) => searchParams.append("tags", tag));
  const query = searchParams.toString();
  return `${SKILLS_API}/${query ? `?${query}` : ""}`;
}

export const skillApi = {
  /**
   * List all user skills
   */
  async list(params: SkillListParams = {}): Promise<SkillsResponse> {
    return authFetch(buildSkillListUrl(params));
  },

  /**
   * Get skill detail (with files list)
   */
  async get(skillName: string): Promise<UserSkillDetail> {
    return authFetch(`${SKILLS_API}/${encodeURIComponent(skillName)}`);
  },

  /**
   * Get skill file content
   */
  async getFile(
    skillName: string,
    filePath: string,
  ): Promise<SkillFileResponse> {
    return authFetch(
      `${SKILLS_API}/${encodeURIComponent(
        skillName,
      )}/files/${encodeURIComponent(filePath)}`,
    );
  },

  /**
   * Upload a binary file to skill (stored in S3/local storage)
   */
  async uploadBinaryFile(
    skillName: string,
    filePath: string,
    file: File,
  ): Promise<{
    message: string;
    url: string;
    mime_type: string;
    size: number;
  }> {
    const formData = new FormData();
    formData.append("file", file);
    return authFetch(
      `${SKILLS_API}/${encodeURIComponent(
        skillName,
      )}/binary-files/${encodeURIComponent(filePath)}`,
      {
        method: "PUT",
        body: formData,
      },
    );
  },

  /**
   * Update skill file content
   */
  async updateFile(
    skillName: string,
    filePath: string,
    content: string,
  ): Promise<{ message: string }> {
    return authFetch(
      `${SKILLS_API}/${encodeURIComponent(
        skillName,
      )}/files/${encodeURIComponent(filePath)}`,
      {
        method: "PUT",
        body: JSON.stringify({ content }),
      },
    );
  },

  /**
   * Create skill - writes all files to /api/skills/{name}/files/{path}
   * Files are written sequentially; on failure, already-written files are rolled back.
   */
  async create(data: SkillCreate): Promise<{ message: string }> {
    // Build files dict from content (SKILL.md) or explicit files
    const filesToWrite: Record<string, string> = {};

    if (data.files && Object.keys(data.files).length > 0) {
      // Use explicit files from form
      Object.entries(data.files).forEach(([path, content]) => {
        filesToWrite[path] = content;
      });
    } else {
      // Fallback to content as SKILL.md
      filesToWrite["SKILL.md"] = data.content;
    }

    // Write files sequentially for atomicity
    const writtenPaths: string[] = [];
    try {
      for (const [filePath, content] of Object.entries(filesToWrite)) {
        await authFetch(
          `${SKILLS_API}/${encodeURIComponent(
            data.name,
          )}/files/${encodeURIComponent(filePath)}`,
          {
            method: "PUT",
            body: JSON.stringify({ content }),
          },
        );
        writtenPaths.push(filePath);
      }
    } catch (error) {
      // Rollback: delete already-written files
      await Promise.allSettled(
        writtenPaths.map((filePath) =>
          authFetch(
            `${SKILLS_API}/${encodeURIComponent(
              data.name,
            )}/files/${encodeURIComponent(filePath)}`,
            { method: "DELETE" },
          ),
        ),
      );
      throw error;
    }

    return { message: "Skill created" };
  },

  /**
   * Update skill metadata and content
   * Files are written/deleted sequentially to avoid partial failure leaving inconsistent state.
   */
  async update(
    skillName: string,
    data: {
      description?: string;
      content?: string;
      enabled?: boolean;
      files?: Record<string, string>;
      deletedFiles?: string[];
    },
  ): Promise<{ message: string }> {
    // Update SKILL.md if content changed (legacy single-file mode)
    if (data.content !== undefined && !data.files) {
      await authFetch(
        `${SKILLS_API}/${encodeURIComponent(skillName)}/files/SKILL.md`,
        {
          method: "PUT",
          body: JSON.stringify({ content: data.content }),
        },
      );
    }

    // Write new/updated files sequentially
    if (data.files) {
      for (const [filePath, content] of Object.entries(data.files)) {
        await authFetch(
          `${SKILLS_API}/${encodeURIComponent(
            skillName,
          )}/files/${encodeURIComponent(filePath)}`,
          {
            method: "PUT",
            body: JSON.stringify({ content }),
          },
        );
      }
    }

    // Delete removed files sequentially
    if (data.deletedFiles && data.deletedFiles.length > 0) {
      for (const filePath of data.deletedFiles) {
        await authFetch(
          `${SKILLS_API}/${encodeURIComponent(
            skillName,
          )}/files/${encodeURIComponent(filePath)}`,
          { method: "DELETE" },
        );
      }
    }

    // Toggle if enabled changed
    if (data.enabled !== undefined) {
      await this.toggle(skillName, data.enabled);
    }

    return { message: "Updated" };
  },

  /**
   * Delete (uninstall) user skill
   */
  async delete(skillName: string): Promise<{ message: string }> {
    return authFetch(`${SKILLS_API}/${encodeURIComponent(skillName)}`, {
      method: "DELETE",
    });
  },

  /**
   * Toggle skill enabled state
   */
  async toggle(
    skillName: string,
    enabled?: boolean,
  ): Promise<SkillToggleResponse> {
    const body = enabled !== undefined ? { enabled } : undefined;
    return authFetch(`${SKILLS_API}/${encodeURIComponent(skillName)}/toggle`, {
      method: "PATCH",
      body: body ? JSON.stringify(body) : undefined,
    });
  },

  /**
   * Update current user's pin/favorite presentation preference
   */
  async updatePreference(
    skillName: string,
    data: SkillPreferenceUpdate,
  ): Promise<SkillPreferenceResponse> {
    return authFetch(
      `${SKILLS_API}/${encodeURIComponent(skillName)}/preference`,
      {
        method: "PATCH",
        body: JSON.stringify(data),
      },
    );
  },

  /**
   * Preview skills in a ZIP file (without creating them)
   */
  async previewZip(file: File): Promise<{
    skill_count: number;
    skills: Array<{
      name: string;
      description: string;
      file_count: number;
      files: string[];
      already_exists: boolean;
    }>;
  }> {
    const formData = new FormData();
    formData.append("file", file);
    return authFetch(`${SKILLS_API}/upload/preview`, {
      method: "POST",
      body: formData,
    });
  },

  /**
   * Upload skill(s) from ZIP file (optionally filter by skill names)
   */
  async uploadZip(
    file: File,
    skillNames?: string[],
  ): Promise<{
    message: string;
    created: Array<{ name: string; file_count: number }>;
    errors: Array<{ name: string; reason: string }>;
    skill_count: number;
  }> {
    const formData = new FormData();
    formData.append("file", file);
    if (skillNames && skillNames.length > 0) {
      formData.append("skill_names", skillNames.join(","));
    }
    return authFetch(`${SKILLS_API}/upload`, {
      method: "POST",
      body: formData,
    });
  },

  /**
   * Preview skills from GitHub repository
   */
  async previewGitHub(
    repoUrl: string,
    branch: string = "main",
  ): Promise<{
    repo_url: string;
    branch: string;
    skills: Array<{ name: string; path: string; description: string }>;
  }> {
    return authFetch(`${API_BASE}/api/github/preview`, {
      method: "POST",
      body: JSON.stringify({ repo_url: repoUrl, branch }),
    });
  },

  /**
   * Install skills from GitHub repository
   */
  async installGitHub(
    repoUrl: string,
    skillNames: string[],
    branch: string = "main",
  ): Promise<{
    message: string;
    installed: string[];
    errors: string[];
  }> {
    return authFetch(`${API_BASE}/api/github/install`, {
      method: "POST",
      body: JSON.stringify({
        repo_url: repoUrl,
        branch,
        skill_names: skillNames,
      }),
    });
  },

  /**
   * Batch delete skills
   */
  async batchDelete(names: string[]): Promise<{
    deleted: string[];
    errors: Array<{ name: string; reason: string }>;
  }> {
    return authFetch(`${SKILLS_API}/batch/delete`, {
      method: "POST",
      body: JSON.stringify({ names }),
    });
  },

  /**
   * Batch toggle skills enabled state
   */
  async batchToggle(
    names: string[],
    enabled: boolean,
  ): Promise<{
    updated: string[];
    errors: Array<{ name: string; reason: string }>;
  }> {
    return authFetch(`${SKILLS_API}/batch/toggle`, {
      method: "POST",
      body: JSON.stringify({ names, enabled }),
    });
  },

  /**
   * Publish skill to marketplace
   */
  async publishToMarketplace(
    skillName: string,
    data?: PublishToMarketplaceRequest,
  ): Promise<MarketplaceSkillResponse> {
    return authFetch(`${SKILLS_API}/${encodeURIComponent(skillName)}/publish`, {
      method: "POST",
      body: JSON.stringify(data || {}),
    });
  },
};
