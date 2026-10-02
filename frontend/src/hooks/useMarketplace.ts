import { useState, useCallback, useEffect, useMemo, useRef } from "react";
import i18n from "i18next";
import { marketplaceApi } from "../services/api/marketplace";
import type {
  MarketplaceSkillResponse,
  MarketplaceSkillFilesResponse,
  MarketplaceCreateRequest,
} from "../types";

interface BinaryFileInfo {
  url: string;
  mime_type: string;
  size: number;
}

type ActiveFilter = "all" | "active" | "inactive";

export function useMarketplace() {
  const [skills, setSkills] = useState<MarketplaceSkillResponse[]>([]);
  const [tags, setTags] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [activeFilter, setActiveFilter] = useState<ActiveFilter>("all");

  // Debounced search value for API calls
  const [debouncedSearch, setDebouncedSearch] = useState("");
  useEffect(() => {
    const timer = setTimeout(() => {
      setDebouncedSearch(searchQuery);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchQuery]);

  // Preview state
  const [previewSkill, setPreviewSkill] =
    useState<MarketplaceSkillResponse | null>(null);
  const [previewFiles, setPreviewFiles] =
    useState<MarketplaceSkillFilesResponse | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string>();
  const [previewFileErrors, setPreviewFileErrors] = useState<
    Record<string, string>
  >({});
  const previewSession = useRef<{ name: string } | null>(null);
  const previewRequests = useRef(new Map<string, symbol>());
  const [previewFileContent, setPreviewFileContent] = useState<
    Record<string, string>
  >({});
  const [previewBinaryFiles, setPreviewBinaryFiles] = useState<
    Record<string, BinaryFileInfo>
  >({});
  const [previewFileLoading, setPreviewFileLoading] = useState(
    new Set<string>(),
  );
  useEffect(() => {
    const requests = previewRequests.current;
    return () => {
      previewSession.current = null;
      requests.clear();
    };
  }, []);

  // Fetch marketplace skills
  const fetchSkills = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const tagsParam =
        selectedTags.length > 0 ? selectedTags.join(",") : undefined;
      const data = await marketplaceApi.list({
        tags: tagsParam,
        search: debouncedSearch || undefined,
      });
      setSkills(data ?? []);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : i18n.t("marketplace.fetchFailed", "获取技能市场失败"),
      );
    } finally {
      setIsLoading(false);
    }
  }, [selectedTags, debouncedSearch]);

  // Fetch all tags
  const fetchTags = useCallback(async () => {
    try {
      const data = await marketplaceApi.getTags();
      setTags(data.tags ?? []);
    } catch (err) {
      console.error(
        i18n.t("marketplace.fetchTagsFailed", "获取标签失败:"),
        err,
      );
    }
  }, []);

  // Install a skill
  const installSkill = useCallback(
    async (skillName: string): Promise<boolean> => {
      try {
        await marketplaceApi.install(skillName);
        return true;
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : i18n.t("marketplace.installFailed", "安装技能失败"),
        );
        return false;
      }
    },
    [],
  );

  // Update a skill from marketplace
  const updateSkill = useCallback(
    async (skillName: string): Promise<boolean> => {
      try {
        await marketplaceApi.update(skillName);
        return true;
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : i18n.t("marketplace.updateFailed", "更新技能失败"),
        );
        return false;
      }
    },
    [],
  );

  // Preview skill detail
  const openPreview = useCallback(async (skill: MarketplaceSkillResponse) => {
    const session = { name: skill.skill_name };
    previewSession.current = session;
    previewRequests.current.clear();
    setPreviewFileLoading(new Set());
    setPreviewFileErrors({});
    setPreviewError(undefined);
    setPreviewSkill(skill);
    setPreviewFiles(null);
    setPreviewFileContent({});
    setPreviewBinaryFiles({});
    setPreviewLoading(true);
    try {
      const files = await marketplaceApi.listFiles(skill.skill_name);
      if (previewSession.current !== session) return;
      setPreviewFiles(files);
    } catch {
      if (previewSession.current === session)
        setPreviewError(i18n.t("files.loadFailed"));
    } finally {
      if (previewSession.current === session) setPreviewLoading(false);
    }
  }, []);

  // Read preview file content
  const readPreviewFile = useCallback(
    async (skillName: string, filePath: string) => {
      const session = previewSession.current;
      if (session?.name !== skillName || previewRequests.current.has(filePath))
        return;
      const request = Symbol(filePath);
      previewRequests.current.set(filePath, request);
      setPreviewFileLoading(new Set(previewRequests.current.keys()));
      setPreviewFileErrors((previous) => {
        const next = { ...previous };
        delete next[filePath];
        return next;
      });
      const isCurrent = () =>
        previewSession.current === session &&
        previewRequests.current.get(filePath) === request;
      try {
        const resp = await marketplaceApi.getFile(skillName, filePath);
        if (!isCurrent()) return;
        setPreviewFileContent((prev) => ({
          ...prev,
          [filePath]: resp.content,
        }));
        if (
          resp.is_binary &&
          resp.url &&
          resp.mime_type &&
          resp.size !== undefined
        ) {
          setPreviewBinaryFiles((prev) => ({
            ...prev,
            [filePath]: {
              url: resp.url!,
              mime_type: resp.mime_type!,
              size: resp.size!,
            },
          }));
        }
      } catch {
        if (isCurrent())
          setPreviewFileErrors((previous) => ({
            ...previous,
            [filePath]: i18n.t("files.loadFailed"),
          }));
      } finally {
        if (isCurrent()) {
          previewRequests.current.delete(filePath);
          setPreviewFileLoading(new Set(previewRequests.current.keys()));
        }
      }
    },
    [],
  );

  const closePreview = useCallback(() => {
    previewSession.current = null;
    previewRequests.current.clear();
    setPreviewLoading(false);
    setPreviewFileLoading(new Set());
    setPreviewFileErrors({});
    setPreviewError(undefined);
    setPreviewSkill(null);
    setPreviewFiles(null);
    setPreviewFileContent({});
    setPreviewBinaryFiles({});
  }, []);

  // Toggle tag selection
  const toggleTag = useCallback((tag: string) => {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag],
    );
  }, []);

  // Client-side active/inactive filter on top of server results
  const filteredSkills = useMemo(() => {
    if (activeFilter === "all") return skills;
    return skills.filter((s) =>
      activeFilter === "active" ? s.is_active : !s.is_active,
    );
  }, [skills, activeFilter]);

  // Clear filters
  const clearFilters = useCallback(() => {
    setSelectedTags([]);
    setSearchQuery("");
    setDebouncedSearch("");
    setActiveFilter("all");
  }, []);

  // Create and publish skill directly in marketplace
  const createAndPublish = useCallback(
    async (data: MarketplaceCreateRequest): Promise<boolean> => {
      setIsLoading(true);
      setError(null);
      try {
        await marketplaceApi.createAndPublish(data);
        await fetchSkills();
        await fetchTags();
        return true;
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : i18n.t("marketplace.createFailed", "创建技能失败"),
        );
        return false;
      } finally {
        setIsLoading(false);
      }
    },
    [fetchSkills, fetchTags],
  );

  // Update marketplace skill directly (creator only)
  const updateMarketplaceSkill = useCallback(
    async (
      skillName: string,
      data: MarketplaceCreateRequest,
    ): Promise<boolean> => {
      setIsLoading(true);
      setError(null);
      try {
        await marketplaceApi.updateMarketplaceSkill(skillName, data);
        await fetchSkills();
        return true;
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : i18n.t("marketplace.updateFailed", "更新技能失败"),
        );
        return false;
      } finally {
        setIsLoading(false);
      }
    },
    [fetchSkills],
  );

  // Admin: activate/deactivate skill
  const activateSkill = useCallback(
    async (skillName: string, isActive: boolean): Promise<boolean> => {
      setError(null);
      try {
        await marketplaceApi.activate(skillName, isActive);
        await fetchSkills();
        return true;
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : i18n.t("marketplace.updateFailed", "更新技能失败"),
        );
        return false;
      }
    },
    [fetchSkills],
  );

  // Admin: delete skill from marketplace
  const deleteSkill = useCallback(
    async (skillName: string): Promise<boolean> => {
      setError(null);
      try {
        await marketplaceApi.deleteSkill(skillName);
        await fetchSkills();
        return true;
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : i18n.t("marketplace.deleteFailed", "删除技能失败"),
        );
        return false;
      }
    },
    [fetchSkills],
  );

  // Load marketplace skill for editing (without local copy)
  const loadMarketplaceSkillForEdit = useCallback(async (skillName: string) => {
    try {
      const [filesResp, skillDetail] = await Promise.all([
        marketplaceApi.listFiles(skillName),
        marketplaceApi.get(skillName),
      ]);

      const fileContents: Record<string, string> = {};
      const binaryFiles: Record<string, BinaryFileInfo> = {};
      await Promise.all(
        filesResp.files.map(async (path) => {
          const resp = await marketplaceApi.getFile(skillName, path);
          fileContents[path] = resp.content;
          if (resp.is_binary && resp.url) {
            binaryFiles[path] = {
              url: resp.url,
              mime_type: resp.mime_type || "application/octet-stream",
              size: resp.size || 0,
            };
          }
        }),
      );

      return {
        name: skillName,
        description: skillDetail.description,
        tags: skillDetail.tags,
        content: fileContents["SKILL.md"] || "",
        files: fileContents,
        binaryFiles,
        enabled: true,
        source: "marketplace" as const,
        file_count: filesResp.files.length,
        installed_from: "marketplace" as const,
        is_published: true,
        marketplace_is_active: skillDetail.is_active,
      };
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : i18n.t("marketplace.loadFailed", "加载技能市场失败"),
      );
      return null;
    }
  }, []);

  // Initial load
  useEffect(() => {
    fetchSkills();
  }, [fetchSkills]);

  // Load tags on mount
  useEffect(() => {
    fetchTags();
  }, [fetchTags]);

  return {
    skills,
    filteredSkills,
    tags,
    isLoading,
    error,
    selectedTags,
    searchQuery,
    setSearchQuery,
    activeFilter,
    setActiveFilter,
    toggleTag,
    clearFilters,
    fetchSkills,
    installSkill,
    updateSkill,
    createAndPublish,
    updateMarketplaceSkill,
    activateSkill,
    deleteSkill,
    loadMarketplaceSkillForEdit,
    clearError: () => setError(null),
    // Preview
    previewSkill,
    previewFiles,
    previewLoading,
    previewError,
    previewFileErrors,
    previewFileContent,
    previewBinaryFiles,
    previewFileLoading,
    openPreview,
    readPreviewFile,
    closePreview,
  };
}
