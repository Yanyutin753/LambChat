/**
 * useSkills hook - Simplified Architecture
 *
 * New backend stores skills as individual files. This hook:
 * - Fetches skill list from /api/skills/ (basic info only)
 * - Fetches full skill details (with files) on demand
 * - Composes SkillResponse for frontend components
 */

import { useState, useCallback, useEffect, useRef } from "react";
import i18n from "i18next";
import { skillApi } from "../services/api/skill";
import type { SkillListParams } from "../services/api/skill";
import type {
  SkillResponse,
  SkillSource,
  UserSkill,
  UserSkillDetail,
  SkillCreate,
  PublishToMarketplaceRequest,
  SkillPreferenceUpdate,
  BinaryFileInfo,
} from "../types/skill";

export const DEFAULT_SKILL_LIST_LIMIT = 20;

export function resolveSkillListParams(
  explicitParams?: SkillListParams,
  defaultParams?: SkillListParams,
): SkillListParams {
  return explicitParams ?? defaultParams ?? { limit: DEFAULT_SKILL_LIST_LIMIT };
}

export function resolveSkillListState<T extends { name: string }>({
  currentSkills,
  incomingSkills,
  params,
  appendPages,
}: {
  currentSkills: T[];
  incomingSkills: T[];
  params: SkillListParams;
  appendPages: boolean;
}): T[] {
  if (!appendPages || !params.skip || params.skip <= 0) {
    return incomingSkills;
  }

  const byName = new Map(currentSkills.map((skill) => [skill.name, skill]));
  incomingSkills.forEach((skill) => byName.set(skill.name, skill));
  return Array.from(byName.values());
}

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
    is_favorite: userSkill.is_favorite ?? false,
    is_pinned: userSkill.is_pinned ?? false,
  };
}

export function useSkills(options?: {
  enabled?: boolean;
  listParams?: SkillListParams;
  appendPages?: boolean;
}) {
  const enabled = options?.enabled !== false; // Default to true
  const listParams = options?.listParams;
  const appendPages = options?.appendPages ?? false;
  const [skills, setSkills] = useState<SkillResponse[]>([]);
  const [availableTags, setAvailableTags] = useState<string[]>([]);
  const [totalSkills, setTotalSkills] = useState(0);
  const [totalEnabledCount, setTotalEnabledCount] = useState(0);
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
  const fetchSkills = useCallback(
    async (params?: SkillListParams) => {
      if (!enabled) return;
      setIsLoading(true);
      setError(null);
      try {
        const response = await skillApi.list(
          resolveSkillListParams(params, listParams),
        );
        const resolvedParams = resolveSkillListParams(params, listParams);
        const userSkills: UserSkill[] = response.skills;
        // For list view, we don't fetch full details immediately
        // Components that need details will fetch them on demand
        const composed = userSkills.map((u) => composeSkillResponse(u));
        setTotalSkills(response.total);
        setTotalEnabledCount(response.enabled_count ?? 0);
        setAvailableTags(response.available_tags || []);
        // 保留正在 toggle 中的 skill 的乐观状态，避免竞态覆盖
        const pendingToggles = pendingTogglesRef.current;
        if (pendingToggles.size === 0) {
          setSkills((current) =>
            resolveSkillListState({
              currentSkills: current,
              incomingSkills: composed,
              params: resolvedParams,
              appendPages,
            }),
          );
        } else {
          const nextSkills = composed.map((s) => {
            const pendingEnabled = pendingToggles.get(s.name);
            if (pendingEnabled !== undefined) {
              return { ...s, enabled: pendingEnabled };
            }
            return s;
          });
          setSkills((current) =>
            resolveSkillListState({
              currentSkills: current,
              incomingSkills: nextSkills,
              params: resolvedParams,
              appendPages,
            }),
          );
        }
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : i18n.t("skills.fetchFailed", "获取技能失败"),
        );
      } finally {
        setIsLoading(false);
      }
    },
    [appendPages, enabled, listParams],
  );

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
            is_favorite: cached.is_favorite,
            is_pinned: cached.is_pinned,
          };
        } else {
          userSkill = {
            skill_name: detail.skill_name || name,
            description: detail.description || name,
            tags: detail.tags || [],
            files: detail.files || [],
            enabled: detail.enabled ?? true,
            file_count: detail.files?.length || 0,
            installed_from: "manual",
            created_at: undefined,
            updated_at: undefined,
            is_published: detail.is_published || false,
            marketplace_is_active: detail.marketplace_is_active ?? true,
            is_favorite: detail.is_favorite ?? false,
            is_pinned: detail.is_pinned ?? false,
          };
        }

        const resp = composeSkillResponse(userSkill, detail);
        resp.filePaths = detail.files || [];
        return resp;
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : i18n.t("skills.fetchDetailFailed", "获取技能详情失败"),
        );
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
            is_favorite: cached.is_favorite,
            is_pinned: cached.is_pinned,
          };
        } else {
          userSkill = {
            skill_name: detail.skill_name || name,
            description: detail.description || name,
            tags: detail.tags || [],
            files: detail.files || [],
            enabled: detail.enabled ?? true,
            file_count: detail.files?.length || 0,
            installed_from: "manual",
            created_at: undefined,
            updated_at: undefined,
            is_published: detail.is_published || false,
            marketplace_is_active: detail.marketplace_is_active ?? true,
            is_favorite: detail.is_favorite ?? false,
            is_pinned: detail.is_pinned ?? false,
          };
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
        setError(
          err instanceof Error
            ? err.message
            : i18n.t("skills.fetchDetailFailed", "获取技能详情失败"),
        );
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
        setError(
          err instanceof Error
            ? err.message
            : i18n.t("skills.createFailed", "创建技能失败"),
        );
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
        setError(
          err instanceof Error
            ? err.message
            : i18n.t("skills.updateFailed", "更新技能失败"),
        );
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
        setError(
          err instanceof Error
            ? err.message
            : i18n.t("skills.deleteFailed", "删除技能失败"),
        );
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
        setError(
          err instanceof Error
            ? err.message
            : i18n.t("skills.toggleFailed", "切换技能状态失败"),
        );
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
          err instanceof Error
            ? err.message
            : i18n.t("skills.batchDeleteFailed", "批量删除技能失败"),
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
          err instanceof Error
            ? err.message
            : i18n.t("skills.batchToggleFailed", "批量切换技能状态失败"),
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

  const updateSkillPreference = useCallback(
    async (
      name: string,
      preference: SkillPreferenceUpdate,
    ): Promise<boolean> => {
      setError(null);
      const previous = skills;
      setSkills((current) =>
        current.map((skill) =>
          skill.name === name ? { ...skill, ...preference } : skill,
        ),
      );
      try {
        const updated = await skillApi.updatePreference(name, preference);
        setSkills((current) =>
          current.map((skill) =>
            skill.name === name
              ? {
                  ...skill,
                  is_favorite: updated.is_favorite,
                  is_pinned: updated.is_pinned,
                }
              : skill,
          ),
        );
        await fetchSkills();
        return true;
      } catch (err) {
        setSkills(previous);
        setError(
          err instanceof Error
            ? err.message
            : i18n.t("skills.preferenceUpdateFailed", "技能偏好更新失败"),
        );
        return false;
      }
    },
    [fetchSkills, skills],
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
        setError(
          err instanceof Error
            ? err.message
            : i18n.t("skills.uploadFailed", "上传技能失败"),
        );
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
        setError(
          err instanceof Error
            ? err.message
            : i18n.t("skills.previewZipFailed", "预览ZIP文件失败"),
        );
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
            : i18n.t("skills.previewGitHubFailed", "预览GitHub技能失败"),
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
            : i18n.t("skills.installGitHubFailed", "安装GitHub技能失败"),
        );
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    [fetchSkills],
  );

  // Stats (from backend for accurate counts regardless of pagination)
  const enabledCount = totalEnabledCount;
  const totalCount = totalSkills;
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
          err instanceof Error
            ? err.message
            : i18n.t("skills.publishFailed", "发布技能失败"),
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
    fetchSkills(listParams);
  }, [fetchSkills, listParams]);

  return {
    skills,
    availableTags,
    total: totalSkills,
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
    updateSkillPreference,
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
