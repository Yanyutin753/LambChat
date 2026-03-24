/**
 * useSkills hook - Simplified Architecture
 *
 * New backend stores skills as individual files. This hook:
 * - Fetches skill list from /api/skills/ (basic info only)
 * - Fetches full skill details (with files) on demand
 * - Composes SkillResponse for frontend components
 */

import { useState, useCallback, useEffect } from "react";
import { skillApi } from "../services/api/skill";
import type {
  SkillResponse,
  SkillSource,
  UserSkill,
  UserSkillDetail,
  SkillCreate,
  PublishToMarketplaceRequest,
} from "../types/skill";

// Map installed_from to SkillSource
function mapInstalledToSource(installed_from: string): SkillSource {
  switch (installed_from) {
    case "builtin":
      return "builtin";
    case "marketplace":
      return "marketplace";
    case "manual":
    default:
      return "manual";
  }
}

// Compose full SkillResponse from UserSkill + files content
function composeSkillResponse(
  userSkill: UserSkill,
  _detail?: UserSkillDetail,
  filesContent?: Record<string, string>,
): SkillResponse {
  // Use description from API directly (extracted from SKILL.md by backend)
  const description = userSkill.description || userSkill.skill_name;

  // If filesContent provided, use it; otherwise files will be fetched on demand
  const files = filesContent || {};

  return {
    name: userSkill.skill_name,
    description,
    enabled: userSkill.enabled,
    source: mapInstalledToSource(userSkill.installed_from),
    content: files["SKILL.md"] || "",
    files,
    file_count: userSkill.file_count,
    installed_from: userSkill.installed_from,
    published_marketplace_name: userSkill.published_marketplace_name,
    created_at: userSkill.created_at,
    updated_at: userSkill.updated_at,
    is_published: userSkill.is_published,
    marketplace_is_active: userSkill.marketplace_is_active,
  };
}

export function useSkills(options?: { enabled?: boolean }) {
  const enabled = options?.enabled !== false; // Default to true
  const [skills, setSkills] = useState<SkillResponse[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch all skills (basic info only)
  const fetchSkills = useCallback(async () => {
    if (!enabled) return;
    setIsLoading(true);
    setError(null);
    try {
      const userSkills: UserSkill[] = await skillApi.list();
      // For list view, we don't fetch full details immediately
      // Components that need details will fetch them on demand
      const composed = userSkills.map((u) => composeSkillResponse(u));
      setSkills(composed);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch skills");
    } finally {
      setIsLoading(false);
    }
  }, [enabled]);

  // Fetch single skill with full details
  const getSkill = useCallback(
    async (name: string): Promise<SkillResponse | null> => {
      try {
        const [userSkill, detail] = await Promise.all([
          skillApi
            .list()
            .then((list) => list.find((s) => s.skill_name === name)),
          skillApi.get(name),
        ]);

        if (!userSkill) return null;

        // Fetch all files content
        const filesContent: Record<string, string> = {};
        if (detail.files) {
          await Promise.all(
            detail.files.map(async (filePath) => {
              try {
                const fileResp = await skillApi.getFile(name, filePath);
                filesContent[filePath] = fileResp.content;
              } catch {
                // File might not be readable
              }
            }),
          );
        }

        return composeSkillResponse(userSkill, detail, filesContent);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to fetch skill");
        return null;
      }
    },
    [],
  );

  // Create skill
  const createSkill = useCallback(
    async (data: SkillCreate): Promise<boolean> => {
      setIsLoading(true);
      setError(null);
      try {
        await skillApi.create(data);
        await fetchSkills();
        return true;
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to create skill");
        return false;
      } finally {
        setIsLoading(false);
      }
    },
    [fetchSkills],
  );

  // Update skill
  const updateSkill = useCallback(
    async (
      name: string,
      updates: { description?: string; content?: string; enabled?: boolean; files?: Record<string, string>; deletedFiles?: string[] },
    ): Promise<boolean> => {
      setIsLoading(true);
      setError(null);
      try {
        await skillApi.update(name, updates);
        await fetchSkills();
        return true;
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to update skill");
        return false;
      } finally {
        setIsLoading(false);
      }
    },
    [fetchSkills],
  );

  // Delete skill
  const deleteSkill = useCallback(
    async (name: string): Promise<boolean> => {
      setIsLoading(true);
      setError(null);
      try {
        await skillApi.delete(name);
        await fetchSkills();
        return true;
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to delete skill");
        return false;
      } finally {
        setIsLoading(false);
      }
    },
    [fetchSkills],
  );

  // Toggle skill
  const toggleSkill = useCallback(async (name: string): Promise<boolean> => {
    // Optimistic update
    setSkills((prev) =>
      prev.map((s) => (s.name === name ? { ...s, enabled: !s.enabled } : s)),
    );

    try {
      await skillApi.toggle(name);
      return true;
    } catch (err) {
      // Rollback on error
      setSkills((prev) =>
        prev.map((s) => (s.name === name ? { ...s, enabled: !s.enabled } : s)),
      );
      setError(err instanceof Error ? err.message : "Failed to toggle skill");
      return false;
    }
  }, []);

  // Toggle skill wrapper (for compatibility)
  const toggleSkillWrapper = useCallback(async (name: string): Promise<void> => {
    await toggleSkill(name);
  }, [toggleSkill]);

  // Toggle category (not applicable in new architecture - just toggle all)
  const toggleCategory = useCallback(
    async (_category: SkillSource, enabled: boolean): Promise<void> => {
      const promises = skills
        .filter((s) => s.source === _category && s.enabled !== enabled)
        .map((s) => toggleSkill(s.name));
      await Promise.all(promises);
    },
    [skills, toggleSkill],
  );

  // Toggle all skills
  const toggleAll = useCallback(
    async (enabled: boolean): Promise<void> => {
      const promises = skills
        .filter((s) => s.enabled !== enabled)
        .map((s) => toggleSkill(s.name));
      await Promise.all(promises);
    },
    [skills, toggleSkill],
  );

  // Get enabled skill names
  const getEnabledSkillNames = useCallback((): string[] => {
    return skills.filter((s) => s.enabled).map((s) => s.name);
  }, [skills]);

  // Get category stats
  const getCategoryStats = useCallback(() => {
    const stats: Record<SkillSource, { enabled: number; total: number }> = {
      builtin: { enabled: 0, total: 0 },
      marketplace: { enabled: 0, total: 0 },
      manual: { enabled: 0, total: 0 },
    };

    skills.forEach((skill) => {
      const cat = skill.source;
      if (stats[cat]) {
        stats[cat].total++;
        if (skill.enabled) {
          stats[cat].enabled++;
        }
      }
    });

    return stats;
  }, [skills]);

  // Upload skill from ZIP file
  const uploadSkill = useCallback(
    async (file: File): Promise<boolean> => {
      setIsLoading(true);
      setError(null);
      try {
        await skillApi.uploadZip(file);
        await fetchSkills();
        return true;
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to upload skill");
        return false;
      } finally {
        setIsLoading(false);
      }
    },
    [fetchSkills],
  );

  // Preview skills from GitHub repository
  const previewGitHubSkills = useCallback(
    async (
      repoUrl: string,
      branch: string = "main",
    ): Promise<{ repo_url: string; branch: string; skills: Array<{ name: string; path: string; description: string }> } | null> => {
      setIsLoading(true);
      setError(null);
      try {
        return await skillApi.previewGitHub(repoUrl, branch);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to preview GitHub skills");
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    [],
  );

  // Install skills from GitHub repository
  const installGitHubSkills = useCallback(
    async (
      repoUrl: string,
      skillNames: string[],
      branch: string = "main",
    ): Promise<{ message: string; installed: string[]; errors: string[] } | null> => {
      setIsLoading(true);
      setError(null);
      try {
        const result = await skillApi.installGitHub(repoUrl, skillNames, branch);
        await fetchSkills();
        return result;
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to install GitHub skills");
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    [fetchSkills],
  );

  // Stats
  const enabledCount = skills.filter((s) => s.enabled).length;
  const totalCount = skills.length;

  // Publish skill to marketplace
  const publishToMarketplace = useCallback(
    async (name: string, data?: PublishToMarketplaceRequest): Promise<boolean> => {
      setIsLoading(true);
      setError(null);
      try {
        await skillApi.publishToMarketplace(name, data);
        await fetchSkills();
        return true;
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to publish skill");
        return false;
      } finally {
        setIsLoading(false);
      }
    },
    [fetchSkills],
  );

  // Initial load
  useEffect(() => {
    fetchSkills();
  }, [fetchSkills]);

  return {
    skills,
    isLoading,
    error,
    fetchSkills,
    getSkill,
    createSkill,
    updateSkill,
    deleteSkill,
    toggleSkill,
    toggleSkillWrapper,
    toggleCategory,
    toggleAll,
    uploadSkill,
    previewGitHubSkills,
    installGitHubSkills,
    publishToMarketplace,
    getEnabledSkillNames,
    getCategoryStats,
    enabledCount,
    totalCount,
    clearError: () => setError(null),
  };
}
