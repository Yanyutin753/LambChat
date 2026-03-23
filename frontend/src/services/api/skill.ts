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
  UserSkill,
  UserSkillDetail,
  SkillFileResponse,
  SkillToggleResponse,
  SkillCreate,
  MarketplaceInstallResponse,
} from "../../types/skill";

const SKILLS_API = `${API_BASE}/api/skills`;

export const skillApi = {
  /**
   * List all user skills
   */
  async list(): Promise<UserSkill[]> {
    return authFetch(`${SKILLS_API}/`);
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
   * For new architecture, we write files individually
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

    // Write all files
    await Promise.all(
      Object.entries(filesToWrite).map(([filePath, content]) =>
        authFetch(
          `${SKILLS_API}/${encodeURIComponent(
            data.name,
          )}/files/${encodeURIComponent(filePath)}`,
          {
            method: "PUT",
            body: JSON.stringify({ content }),
          },
        ),
      ),
    );

    return { message: "Skill created" };
  },

  /**
   * Update skill metadata and content
   */
  async update(
    skillName: string,
    data: { description?: string; content?: string; enabled?: boolean },
  ): Promise<{ message: string }> {
    // Update SKILL.md if content changed
    if (data.content !== undefined) {
      await authFetch(
        `${SKILLS_API}/${encodeURIComponent(skillName)}/files/SKILL.md`,
        {
          method: "PUT",
          body: JSON.stringify({ content: data.content }),
        },
      );
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
    if (enabled !== undefined) {
      // If we know the desired state, we need to check current state
      // The toggle endpoint just flips, so we need to be careful
      const current = await this.get(skillName);
      if (current.enabled !== enabled) {
        return authFetch(
          `${SKILLS_API}/${encodeURIComponent(skillName)}/toggle`,
          { method: "PATCH" },
        );
      }
      return {
        skill_name: skillName,
        enabled: current.enabled,
        message: `Skill '${skillName}' is already ${
          enabled ? "enabled" : "disabled"
        }`,
      };
    }
    // Toggle (flip current state)
    return authFetch(`${SKILLS_API}/${encodeURIComponent(skillName)}/toggle`, {
      method: "PATCH",
    });
  },

  /**
   * Install skill from marketplace
   */
  async installFromMarketplace(
    skillName: string,
  ): Promise<MarketplaceInstallResponse> {
    const marketplaceApi = `${API_BASE}/api/marketplace`;
    return authFetch(
      `${marketplaceApi}/${encodeURIComponent(skillName)}/install`,
      {
        method: "POST",
      },
    );
  },
};
