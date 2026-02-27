import { useState, useEffect, useCallback } from "react";
import { versionApi } from "../services/api";
import type { VersionInfo } from "../types";

interface UseVersionReturn {
  versionInfo: VersionInfo | null;
  isLoading: boolean;
  error: string | null;
  refetch: () => Promise<void>;
}

export function useVersion(): UseVersionReturn {
  const [versionInfo, setVersionInfo] = useState<VersionInfo | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchVersion = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const info = await versionApi.get();
      setVersionInfo(info);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch version");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchVersion();
  }, [fetchVersion]);

  return {
    versionInfo,
    isLoading,
    error,
    refetch: fetchVersion,
  };
}
