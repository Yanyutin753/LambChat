import { useState, useCallback, useEffect } from "react";
import { marketplaceApi } from "../services/api/marketplace";
import type {
  MarketplaceSkillResponse,
  MarketplaceSkillFilesResponse,
} from "../types";

export function useMarketplace() {
  const [skills, setSkills] = useState<MarketplaceSkillResponse[]>([]);
  const [tags, setTags] = useState<string[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [searchQuery, setSearchQuery] = useState("");

  // Preview state
  const [previewSkill, setPreviewSkill] =
    useState<MarketplaceSkillResponse | null>(null);
  const [previewFiles, setPreviewFiles] =
    useState<MarketplaceSkillFilesResponse | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewFileContent, setPreviewFileContent] = useState<
    Record<string, string>
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
        search: searchQuery || undefined,
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
  }, [selectedTags, searchQuery]);

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
    clearError: () => setError(null),
    // Preview
    previewSkill,
    previewFiles,
    previewLoading,
    previewFileContent,
    previewFileLoading,
    openPreview,
    readPreviewFile,
    closePreview,
  };
}
