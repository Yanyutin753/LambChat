import { useState, useCallback, useEffect } from "react";
import { adminMarketplaceApi } from "../services/api/admin-marketplace";
import type { MarketplaceSkillResponse } from "../types";

export function useAdminMarketplace() {
  const [skills, setSkills] = useState<MarketplaceSkillResponse[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Fetch all marketplace skills
  const fetchSkills = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await adminMarketplaceApi.list();
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
  }, []);

  // Create marketplace skill
  const createSkill = useCallback(
    async (data: {
      skill_name: string;
      description?: string;
      tags?: string[];
      version?: string;
    }): Promise<boolean> => {
      setIsLoading(true);
      setError(null);
      try {
        await adminMarketplaceApi.create(data);
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

  // Update marketplace skill
  const updateSkill = useCallback(
    async (
      skillName: string,
      data: { description?: string; tags?: string[]; version?: string },
    ): Promise<boolean> => {
      setIsLoading(true);
      setError(null);
      try {
        await adminMarketplaceApi.update(skillName, data);
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

  // Delete marketplace skill
  const deleteSkill = useCallback(
    async (skillName: string): Promise<boolean> => {
      setIsLoading(true);
      setError(null);
      try {
        await adminMarketplaceApi.delete(skillName);
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

  // Upload ZIP files
  const uploadZip = useCallback(
    async (skillName: string, file: File): Promise<boolean> => {
      setIsLoading(true);
      setError(null);
      try {
        await adminMarketplaceApi.uploadZip(skillName, file);
        await fetchSkills();
        return true;
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to upload skill files",
        );
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
    createSkill,
    updateSkill,
    deleteSkill,
    uploadZip,
    clearError: () => setError(null),
  };
}
