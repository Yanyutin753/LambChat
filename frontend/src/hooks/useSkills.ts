import { useState, useCallback, useEffect } from "react";
import { getAccessToken } from "../services/api";
import type {
  SkillResponse,
  SkillsResponse,
  SkillCreate,
  SkillUpdate,
  SkillToggleResponse,
  SkillImportRequest,
  SkillImportResponse,
  SkillExportResponse,
  SkillMoveResponse,
  GitHubPreviewResponse,
  GitHubInstallRequest,
  SkillSource,
} from "../types";

// Skill category for grouping (based on source)
export type SkillCategory = SkillSource;

const API_BASE = "/api/skills";
const ADMIN_API_BASE = "/api/admin/skills";

async function authFetch<T>(
  url: string,
  options: RequestInit = {},
): Promise<T> {
  const token = getAccessToken();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options.headers as Record<string, string>),
  };

  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }

  const response = await fetch(url, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(
      errorData.detail || `Request failed: ${response.statusText}`,
    );
  }

  const text = await response.text();
  return text ? JSON.parse(text) : (null as T);
}

export function useSkills() {
  const [skills, setSkills] = useState<SkillResponse[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch all skills
  const fetchSkills = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data: SkillsResponse = await authFetch(`${API_BASE}/`);
      setSkills(data.skills ?? []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch skills");
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Get single skill
  const getSkill = useCallback(
    async (name: string): Promise<SkillResponse | null> => {
      try {
        return await authFetch<SkillResponse>(
          `${API_BASE}/${encodeURIComponent(name)}`,
        );
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to fetch skill");
        return null;
      }
    },
    [],
  );

  // Create skill (auto-selects admin API for system skills)
  const createSkill = useCallback(
    async (
      skill: SkillCreate,
      isSystem: boolean = false,
    ): Promise<SkillResponse | null> => {
      setIsLoading(true);
      setError(null);
      try {
        const baseUrl = isSystem ? ADMIN_API_BASE : API_BASE;
        const data: SkillResponse = await authFetch(`${baseUrl}/`, {
          method: "POST",
          body: JSON.stringify(skill),
        });
        await fetchSkills();
        return data;
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to create skill");
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    [fetchSkills],
  );

  // Update skill (auto-selects admin API for system skills)
  const updateSkill = useCallback(
    async (
      name: string,
      updates: SkillUpdate,
      isSystem: boolean = false,
    ): Promise<SkillResponse | null> => {
      setIsLoading(true);
      setError(null);
      try {
        const baseUrl = isSystem ? ADMIN_API_BASE : API_BASE;
        const data: SkillResponse = await authFetch(
          `${baseUrl}/${encodeURIComponent(name)}`,
          {
            method: "PUT",
            body: JSON.stringify(updates),
          },
        );
        await fetchSkills();
        return data;
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to update skill");
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    [fetchSkills],
  );

  // Delete skill (auto-selects admin API for system skills)
  const deleteSkill = useCallback(
    async (name: string, isSystem: boolean = false): Promise<boolean> => {
      setIsLoading(true);
      setError(null);
      try {
        const baseUrl = isSystem ? ADMIN_API_BASE : API_BASE;
        await authFetch(`${baseUrl}/${encodeURIComponent(name)}`, {
          method: "DELETE",
        });
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

  // Toggle skill enabled status (optimistic update - no global loading)
  const toggleSkill = useCallback(
    async (name: string): Promise<SkillResponse | null> => {
      // Optimistic update - immediately update local state
      setSkills((prev) =>
        prev.map((s) => (s.name === name ? { ...s, enabled: !s.enabled } : s)),
      );

      setError(null);
      try {
        const data: SkillToggleResponse = await authFetch(
          `${API_BASE}/${encodeURIComponent(name)}/toggle`,
          {
            method: "PATCH",
          },
        );
        // Update with server response
        setSkills((prev) =>
          prev.map((s) =>
            s.name === name ? { ...s, enabled: data.skill.enabled } : s,
          ),
        );
        return data.skill;
      } catch (err) {
        // Rollback on error
        setSkills((prev) =>
          prev.map((s) =>
            s.name === name ? { ...s, enabled: !s.enabled } : s,
          ),
        );
        setError(err instanceof Error ? err.message : "Failed to toggle skill");
        return null;
      }
    },
    [],
  );

  // Import skills from JSON
  const importSkills = useCallback(
    async (
      request: SkillImportRequest,
      asSystem: boolean = false,
    ): Promise<SkillImportResponse | null> => {
      setIsLoading(true);
      setError(null);
      try {
        const baseUrl = asSystem ? ADMIN_API_BASE : API_BASE;
        const data: SkillImportResponse = await authFetch(`${baseUrl}/import`, {
          method: "POST",
          body: JSON.stringify(request),
        });
        await fetchSkills();
        return data;
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to import skills",
        );
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    [fetchSkills],
  );

  // Export skills to JSON
  const exportSkills = useCallback(
    async (asSystem: boolean = false): Promise<SkillExportResponse | null> => {
      setIsLoading(true);
      setError(null);
      try {
        const baseUrl = asSystem ? ADMIN_API_BASE : API_BASE;
        return await authFetch<SkillExportResponse>(`${baseUrl}/export`);
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to export skills",
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
      request: GitHubInstallRequest,
    ): Promise<GitHubPreviewResponse | null> => {
      setIsLoading(true);
      setError(null);
      try {
        return await authFetch<GitHubPreviewResponse>(
          `${API_BASE}/github/preview`,
          {
            method: "POST",
            body: JSON.stringify(request),
          },
        );
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
      request: GitHubInstallRequest,
      asSystem: boolean = false,
    ): Promise<SkillImportResponse | null> => {
      setIsLoading(true);
      setError(null);
      try {
        const baseUrl = asSystem ? ADMIN_API_BASE : API_BASE;
        const data: SkillImportResponse = await authFetch(
          `${baseUrl}/github/install`,
          {
            method: "POST",
            body: JSON.stringify(request),
          },
        );
        await fetchSkills();
        return data;
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

  // Promote user skill to system skill (admin only)
  const promoteSkill = useCallback(
    async (
      name: string,
      ownerUserId: string,
    ): Promise<SkillMoveResponse | null> => {
      setIsLoading(true);
      setError(null);
      try {
        const data: SkillMoveResponse = await authFetch(
          `${ADMIN_API_BASE}/${encodeURIComponent(name)}/promote`,
          {
            method: "POST",
            body: JSON.stringify({ target_user_id: ownerUserId }),
          },
        );
        await fetchSkills();
        return data;
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to promote skill",
        );
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    [fetchSkills],
  );

  // Demote system skill to user skill (admin only)
  const demoteSkill = useCallback(
    async (
      name: string,
      targetUserId: string,
    ): Promise<SkillMoveResponse | null> => {
      setIsLoading(true);
      setError(null);
      try {
        const data: SkillMoveResponse = await authFetch(
          `${ADMIN_API_BASE}/${encodeURIComponent(name)}/demote`,
          {
            method: "POST",
            body: JSON.stringify({ target_user_id: targetUserId }),
          },
        );
        await fetchSkills();
        return data;
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to demote skill");
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    [fetchSkills],
  );

  // Toggle all skills in a category
  const toggleCategory = useCallback(
    async (category: SkillCategory, enabled: boolean): Promise<void> => {
      const skillsInCategory = skills.filter((s) => s.source === category);
      for (const skill of skillsInCategory) {
        if (skill.enabled !== enabled) {
          await toggleSkill(skill.name);
        }
      }
    },
    [skills, toggleSkill],
  );

  // Toggle all skills
  const toggleAll = useCallback(
    async (enabled: boolean): Promise<void> => {
      for (const skill of skills) {
        if (skill.enabled !== enabled) {
          await toggleSkill(skill.name);
        }
      }
    },
    [skills, toggleSkill],
  );

  // Toggle skill wrapper that returns void for SkillSelector compatibility
  const toggleSkillWrapper = useCallback(
    async (name: string): Promise<void> => {
      await toggleSkill(name);
    },
    [toggleSkill],
  );

  // Get enabled skill names
  const getEnabledSkillNames = useCallback((): string[] => {
    return skills.filter((s) => s.enabled).map((s) => s.name);
  }, [skills]);

  // Get category stats
  const getCategoryStats = useCallback(() => {
    const stats: Record<SkillCategory, { enabled: number; total: number }> = {
      builtin: { enabled: 0, total: 0 },
      github: { enabled: 0, total: 0 },
      manual: { enabled: 0, total: 0 },
    };

    skills.forEach((skill) => {
      const cat = skill.source as SkillCategory;
      if (stats[cat]) {
        stats[cat].total++;
        if (skill.enabled) {
          stats[cat].enabled++;
        }
      }
    });

    return stats;
  }, [skills]);

  // Enabled count
  const enabledCount = skills.filter((s) => s.enabled).length;

  // Total count
  const totalCount = skills.length;

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
    getEnabledSkillNames,
    getCategoryStats,
    enabledCount,
    totalCount,
    importSkills,
    exportSkills,
    previewGitHubSkills,
    installGitHubSkills,
    promoteSkill,
    demoteSkill,
    clearError: () => setError(null),
  };
}
