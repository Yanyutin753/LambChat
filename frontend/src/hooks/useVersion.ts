import { useState, useEffect, useCallback } from "react";
import i18n from "i18next";
import { versionApi } from "../services/api";
import { APP_VERSION } from "../utils/appVersion";
import type { VersionInfo } from "../types";

interface UseVersionReturn {
  versionInfo: VersionInfo | null;
  isLoading: boolean;
  error: string | null;
  checkForUpdates: () => Promise<void>;
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
      setError(
        err instanceof Error
          ? err.message
          : i18n.t("version.fetchFailed", "获取版本失败"),
      );
    } finally {
      setIsLoading(false);
    }
  }, []);

  const checkForUpdates = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const info = await versionApi.checkForUpdates(APP_VERSION);
      setVersionInfo(info);
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : i18n.t("version.checkFailed", "检查更新失败"),
      );
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
    checkForUpdates,
  };
}
