/**
 * useSkills hook - Simplified Architecture
 *
 * New backend stores skills as individual files. This hook:
 * - Fetches skill list from /api/skills/ (basic info only)
 * - Fetches full skill details (with files) on demand
 * - Composes SkillResponse for frontend components
 */

import { useState, useCallback, useEffect, useRef } from "react";
import { skillApi } from "../services/api/skill";
import type {
  SkillResponse,
  SkillSource,
  UserSkill,
  UserSkillDetail,
  SkillCreate,
  PublishToMarketplaceRequest,
  BinaryFileInfo,
} from "../types/skill";

// Map installed_from to SkillSource
function mapInstalledToSource(installed_from: string): SkillSource {
  switch (installed_from) {
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
  detail?: UserSkillDetail,
  filesContent?: Record<string, string>,
  binaryFiles?: Record<string, BinaryFileInfo>,
): SkillResponse {
  // Use description from API directly (extracted from SKILL.md by backend)
  const description =
    detail?.description || userSkill.description || userSkill.skill_name;

  // If filesContent provided, use it; otherwise files will be fetched on demand
  const files = filesContent || {};

  // Prefer detail tags (from GET /{name}) over list tags (from GET /)
  const tags = detail?.tags ?? userSkill.tags ?? [];

  return {
    name: userSkill.skill_name,
    description,
    tags,
    enabled: userSkill.enabled,
    source: mapInstalledToSource(userSkill.installed_from),
    content: files["SKILL.md"] || "",
    files,
    binaryFiles: binaryFiles || {},
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

  // Per-operation loading states for better UX
  const [isCreating, setIsCreating] = useState(false);
  const [isUpdating, setIsUpdating] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [isPublishing, setIsPublishing] = useState(false);

  // 跟踪正在 toggle 中的 skill，防止 fetchSkills 覆盖乐观更新
  const pendingTogglesRef = useRef<Map<string, boolean>>(new Map());

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
      // 保留正在 toggle 中的 skill 的乐观状态，避免竞态覆盖
      const pendingToggles = pendingTogglesRef.current;
      if (pendingToggles.size === 0) {
        setSkills(composed);
      } else {
        setSkills(
          composed.map((s) => {
            const pendingEnabled = pendingToggles.get(s.name);
            if (pendingEnabled !== undefined) {
              return { ...s, enabled: pendingEnabled };
            }
            return s;
          }),
        );
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch skills");
    } finally {
      setIsLoading(false);
    }
  }, [enabled]);

  // Fetch single skill — metadata + file paths only (lazy: content loaded on demand)
  const getSkill = useCallback(
    async (name: string): Promise<SkillResponse | null> => {
      try {
        // Use cached skills list first, then fetch detail
        const cached = skills.find((s) => s.name === name);
        const detail = await skillApi.get(name);

        // Build UserSkill from cached list or fetch it
        let userSkill: UserSkill | null = null;
        if (cached) {
          userSkill = {
            skill_name: cached.name,
            description: cached.description,
            tags: cached.tags,
            files: cached.filePaths || [],
            enabled: cached.enabled,
            file_count: cached.file_count,
            installed_from: cached.installed_from,
            published_marketplace_name: cached.published_marketplace_name,
            created_at: cached.created_at,
            updated_at: cached.updated_at,
            is_published: cached.is_published,
            marketplace_is_active: cached.marketplace_is_active,
          };
        } else {
          // Fallback: fetch list to find the skill
          const list = await skillApi.list();
          const found = list.find((s) => s.skill_name === name);
          if (!found) return null;
          userSkill = found;
        }

        const resp = composeSkillResponse(userSkill, detail);
        resp.filePaths = detail.files || [];
        return resp;
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to fetch skill");
        return null;
      }
    },
    [skills],
  );

  // Fetch single skill with ALL file contents (for export etc.)
  const getFullSkill = useCallback(
    async (name: string): Promise<SkillResponse | null> => {
      try {
        // Use cached skills list first
        const cached = skills.find((s) => s.name === name);
        const detail = await skillApi.get(name);

        let userSkill: UserSkill | null = null;
        if (cached) {
          userSkill = {
            skill_name: cached.name,
            description: cached.description,
            tags: cached.tags,
            files: cached.filePaths || [],
            enabled: cached.enabled,
            file_count: cached.file_count,
            installed_from: cached.installed_from,
            published_marketplace_name: cached.published_marketplace_name,
            created_at: cached.created_at,
            updated_at: cached.updated_at,
            is_published: cached.is_published,
            marketplace_is_active: cached.marketplace_is_active,
          };
        } else {
          const list = await skillApi.list();
          const found = list.find((s) => s.skill_name === name);
          if (!found) return null;
          userSkill = found;
        }

        const filesContent: Record<string, string> = {};
        const binaryFiles: Record<string, BinaryFileInfo> = {};
        if (detail.files) {
          await Promise.all(
            detail.files.map(async (filePath) => {
              try {
                const fileResp = await skillApi.getFile(name, filePath);
                if (fileResp.is_binary && fileResp.url) {
                  filesContent[filePath] = `[Binary: ${fileResp.mime_type}, ${(
                    (fileResp.size ?? 0) / 1024
                  ).toFixed(1)}KB]`;
                  binaryFiles[filePath] = {
                    url: fileResp.url,
                    mime_type: fileResp.mime_type || "application/octet-stream",
                    size: fileResp.size || 0,
                  };
                } else {
                  filesContent[filePath] = fileResp.content;
                }
              } catch {
                // File might not be readable
              }
            }),
          );
        }

        return composeSkillResponse(
          userSkill,
          detail,
          filesContent,
          binaryFiles,
        );
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to fetch skill");
        return null;
      }
    },
    [skills],
  );

  // Create skill
  const createSkill = useCallback(
    async (data: SkillCreate): Promise<boolean> => {
      setIsCreating(true);
      setError(null);
      try {
        await skillApi.create(data);
        await fetchSkills();
        return true;
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to create skill");
        return false;
      } finally {
        setIsCreating(false);
      }
    },
    [fetchSkills],
  );

  // Update skill
  const updateSkill = useCallback(
    async (
      name: string,
      updates: {
        description?: string;
        content?: string;
        enabled?: boolean;
        files?: Record<string, string>;
        deletedFiles?: string[];
      },
    ): Promise<boolean> => {
      setIsUpdating(true);
      setError(null);
      try {
        await skillApi.update(name, updates);
        await fetchSkills();
        return true;
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to update skill");
        return false;
      } finally {
        setIsUpdating(false);
      }
    },
    [fetchSkills],
  );

  // Delete skill
  const deleteSkill = useCallback(
    async (name: string): Promise<boolean> => {
      setIsDeleting(true);
      setError(null);
      try {
        await skillApi.delete(name);
        await fetchSkills();
        return true;
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to delete skill");
        return false;
      } finally {
        setIsDeleting(false);
      }
    },
    [fetchSkills],
  );

  // Toggle skill
  const toggleSkill = useCallback(
    async (name: string): Promise<boolean> => {
      // 记录期望的 toggle 状态
      const currentSkill = skills.find((s) => s.name === name);
      if (!currentSkill) {
        return false;
      }
      const newEnabled = currentSkill ? !currentSkill.enabled : true;
      pendingTogglesRef.current.set(name, newEnabled);

      // Optimistic update
      setSkills((prev) =>
        prev.map((s) => (s.name === name ? { ...s, enabled: newEnabled } : s)),
      );

      try {
        const result = await skillApi.toggle(name, newEnabled);
        setSkills((prev) =>
          prev.map((s) =>
            s.name === name ? { ...s, enabled: result.enabled } : s,
          ),
        );
        return true;
      } catch (err) {
        // Rollback on error
        pendingTogglesRef.current.delete(name);
        setSkills((prev) =>
          prev.map((s) =>
            s.name === name ? { ...s, enabled: !newEnabled } : s,
          ),
        );
        setError(err instanceof Error ? err.message : "Failed to toggle skill");
        return false;
      } finally {
        // toggle 完成后清除 pending 状态
        pendingTogglesRef.current.delete(name);
      }
    },
    [skills],
  );

  // Batch delete skills
  const batchDeleteSkills = useCallback(
    async (names: string[]): Promise<boolean> => {
      setError(null);
      try {
        const result = await skillApi.batchDelete(names);
        // Optimistic remove already-deleted skills from state
        if (result.deleted.length > 0) {
          setSkills((prev) =>
            prev.filter((s) => !result.deleted.includes(s.name)),
          );
        }
        // Full refresh for consistency
        await fetchSkills();
        return result.errors.length === 0;
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to delete skills",
        );
        await fetchSkills(); // rollback
        return false;
      }
    },
    [fetchSkills],
  );

  // Batch toggle skills
  const batchToggleSkills = useCallback(
    async (names: string[], enabled: boolean): Promise<boolean> => {
      // Optimistic update
      names.forEach((name) => pendingTogglesRef.current.set(name, enabled));
      setSkills((prev) =>
        prev.map((s) => (names.includes(s.name) ? { ...s, enabled } : s)),
      );

      try {
        const result = await skillApi.batchToggle(names, enabled);
        // Clear pending for successful ones
        result.updated.forEach((name) =>
          pendingTogglesRef.current.delete(name),
        );
        // Refresh for consistency
        await fetchSkills();
        return result.errors.length === 0;
      } catch (err) {
        // Rollback on error
        names.forEach((name) => pendingTogglesRef.current.delete(name));
        setSkills((prev) =>
          prev.map((s) =>
            names.includes(s.name) ? { ...s, enabled: !enabled } : s,
          ),
        );
        setError(
          err instanceof Error ? err.message : "Failed to toggle skills",
        );
        return false;
      }
    },
    [fetchSkills],
  );

  // Toggle category (not applicable in new architecture - just toggle all)
  const toggleCategory = useCallback(
    async (_category: SkillSource, enabled: boolean): Promise<boolean> => {
      const names = skills
        .filter((s) => s.source === _category && s.enabled !== enabled)
        .map((s) => s.name);
      if (names.length === 0) {
        return true;
      }
      return await batchToggleSkills(names, enabled);
    },
    [batchToggleSkills, skills],
  );

  // Toggle all skills
  const toggleAll = useCallback(
    async (enabled: boolean): Promise<boolean> => {
      const names = skills
        .filter((s) => s.enabled !== enabled)
        .map((s) => s.name);
      if (names.length === 0) {
        return true;
      }
      return await batchToggleSkills(names, enabled);
    },
    [batchToggleSkills, skills],
  );

  // Get enabled skill names
  const getEnabledSkillNames = useCallback((): string[] => {
    return skills.filter((s) => s.enabled).map((s) => s.name);
  }, [skills]);

  // Get category stats
  const getCategoryStats = useCallback(() => {
    const stats: Record<SkillSource, { enabled: number; total: number }> = {
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

  // Upload skill(s) from ZIP file
  const uploadSkill = useCallback(
    async (
      file: File,
      skillNames?: string[],
    ): Promise<{
      created: Array<{ name: string; file_count: number }>;
      errors: Array<{ name: string; reason: string }>;
    } | null> => {
      setIsUploading(true);
      setError(null);
      try {
        const result = await skillApi.uploadZip(file, skillNames);
        await fetchSkills();
        return result;
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to upload skill");
        return null;
      } finally {
        setIsUploading(false);
      }
    },
    [fetchSkills],
  );

  // Preview skills from ZIP file
  const previewZipSkills = useCallback(
    async (
      file: File,
    ): Promise<{
      skill_count: number;
      skills: Array<{
        name: string;
        description: string;
        file_count: number;
        files: string[];
        already_exists: boolean;
      }>;
    } | null> => {
      setIsLoading(true);
      setError(null);
      try {
        return await skillApi.previewZip(file);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to preview ZIP");
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    [],
  );

  // Preview skills from GitHub repository
  const previewGitHubSkills = useCallback(
    async (
      repoUrl: string,
      branch: string = "main",
    ): Promise<{
      repo_url: string;
      branch: string;
      skills: Array<{ name: string; path: string; description: string }>;
    } | null> => {
      setIsLoading(true);
      setError(null);
      try {
        return await skillApi.previewGitHub(repoUrl, branch);
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Failed to preview GitHub skills",
        );
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
    ): Promise<{
      message: string;
      installed: string[];
      errors: string[];
    } | null> => {
      setIsLoading(true);
      setError(null);
      try {
        const result = await skillApi.installGitHub(
          repoUrl,
          skillNames,
          branch,
        );
        await fetchSkills();
        return result;
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : "Failed to install GitHub skills",
        );
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
  const pendingSkillNames = Array.from(pendingTogglesRef.current.keys());
  const isMutating = pendingSkillNames.length > 0;

  // Publish skill to marketplace
  const publishToMarketplace = useCallback(
    async (
      name: string,
      data?: PublishToMarketplaceRequest,
    ): Promise<boolean> => {
      setIsPublishing(true);
      setError(null);
      try {
        await skillApi.publishToMarketplace(name, data);
        await fetchSkills();
        return true;
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to publish skill",
        );
        return false;
      } finally {
        setIsPublishing(false);
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
    getFullSkill,
    createSkill,
    updateSkill,
    deleteSkill,
    batchDeleteSkills,
    batchToggleSkills,
    toggleSkill,
    toggleCategory,
    toggleAll,
    uploadSkill,
    previewZipSkills,
    previewGitHubSkills,
    installGitHubSkills,
    publishToMarketplace,
    pendingSkillNames,
    isMutating,
    isCreating,
    isUpdating,
    isDeleting,
    isUploading,
    isPublishing,
    getEnabledSkillNames,
    getCategoryStats,
    enabledCount,
    totalCount,
    clearError: () => setError(null),
  };
}
