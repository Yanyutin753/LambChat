import { useUpdateChannel } from "../utils/updateChannel";
import { useState, useEffect, useCallback, useRef } from "react";
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
  const { channel } = useUpdateChannel();
  const request = useRef(0);
  const nextRequest = useCallback(() => ++request.current, []);
  const [versionInfo, setVersionInfo] = useState<VersionInfo | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchVersion = useCallback(async () => {
    const id = nextRequest();
    setIsLoading(true);
    setError(null);
    try {
      // 首次拉取也上报客户端版本：has_update 按客户端 App 版本比较，而非
      // 服务端版本（桌面端/移动端两者可能相差多个版本）
      const info = await versionApi.get(APP_VERSION, channel);
      if (id === request.current) setVersionInfo(info);
    } catch (err) {
      if (id === request.current)
        setError(
          err instanceof Error
            ? err.message
            : i18n.t("version.fetchFailed", "获取版本失败"),
        );
    } finally {
      if (id === request.current) setIsLoading(false);
    }
  }, [channel, nextRequest]);

  const checkForUpdates = useCallback(async () => {
    const id = nextRequest();
    setIsLoading(true);
    setError(null);
    try {
      const info = await versionApi.checkForUpdates(APP_VERSION, channel);
      if (id === request.current) setVersionInfo(info);
    } catch (err) {
      if (id === request.current)
        setError(
          err instanceof Error
            ? err.message
            : i18n.t("version.checkFailed", "检查更新失败"),
        );
    } finally {
      if (id === request.current) setIsLoading(false);
    }
  }, [channel, nextRequest]);

  useEffect(() => {
    setVersionInfo(null);
    void fetchVersion();
    return () => {
      nextRequest();
    };
  }, [fetchVersion, nextRequest]);

  return {
    versionInfo,
    isLoading,
    error,
    checkForUpdates,
  };
}
