import { useState, useCallback, useEffect } from "react";
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

export function useMarketplace() {
  const [skills, setSkills] = useState<MarketplaceSkillResponse[]>([]);
  const [tags, setTags] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [searchQuery, setSearchQuery] = useState("");

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
  const [previewFileContent, setPreviewFileContent] = useState<
    Record<string, string>
  >({});
  const [previewBinaryFiles, setPreviewBinaryFiles] = useState<
    Record<string, BinaryFileInfo>
  >({});
  const [previewFileLoading, setPreviewFileLoading] = useState<string | null>(
    null,
  );

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
          : "Failed to fetch marketplace skills",
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
      console.error("Failed to fetch tags:", err);
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
          err instanceof Error ? err.message : "Failed to install skill",
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
        setError(err instanceof Error ? err.message : "Failed to update skill");
        return false;
      }
    },
    [],
  );

  // Preview skill detail
  const openPreview = useCallback(async (skill: MarketplaceSkillResponse) => {
    setPreviewSkill(skill);
    setPreviewFiles(null);
    setPreviewFileContent({});
    setPreviewBinaryFiles({});
    setPreviewLoading(true);
    try {
      const files = await marketplaceApi.listFiles(skill.skill_name);
      setPreviewFiles(files);
    } catch (err) {
      console.error("Failed to fetch skill files:", err);
    } finally {
      setPreviewLoading(false);
    }
  }, []);

  // Read preview file content
  const readPreviewFile = useCallback(
    async (skillName: string, filePath: string) => {
      setPreviewFileLoading(filePath);
      try {
        const resp = await marketplaceApi.getFile(skillName, filePath);
        setPreviewFileContent((prev) => ({
          ...prev,
          [filePath]: resp.content,
        }));
        if (resp.is_binary && resp.url && resp.mime_type && resp.size !== undefined) {
          setPreviewBinaryFiles((prev) => ({
            ...prev,
            [filePath]: {
              url: resp.url!,
              mime_type: resp.mime_type!,
              size: resp.size!,
            },
          }));
        }
      } catch (err) {
        console.error("Failed to fetch file content:", err);
      } finally {
        setPreviewFileLoading(null);
      }
    },
    [],
  );

  const closePreview = useCallback(() => {
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

  // Clear filters
  const clearFilters = useCallback(() => {
    setSelectedTags([]);
    setSearchQuery("");
    setDebouncedSearch("");
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
        setError(err instanceof Error ? err.message : "Failed to create skill");
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
        setError(err instanceof Error ? err.message : "Failed to update skill");
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
        setError(err instanceof Error ? err.message : "Failed to update skill");
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
        setError(err instanceof Error ? err.message : "Failed to delete skill");
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
      await Promise.all(
        filesResp.files.map(async (path) => {
          const resp = await marketplaceApi.getFile(skillName, path);
          fileContents[path] = resp.content;
        }),
      );

      return {
        name: skillName,
        description: skillDetail.description,
        tags: skillDetail.tags,
        content: fileContents["SKILL.md"] || "",
        files: fileContents,
        enabled: true,
        source: "marketplace" as const,
        file_count: filesResp.files.length,
        installed_from: "marketplace" as const,
        is_published: true,
        marketplace_is_active: skillDetail.is_active,
      };
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Failed to load marketplace skill",
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
    tags,
    isLoading,
    error,
    selectedTags,
    searchQuery,
    setSearchQuery,
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
    previewFileContent,
    previewBinaryFiles,
    previewFileLoading,
    openPreview,
    readPreviewFile,
    closePreview,
    setPreviewFileContent,
  };
}
