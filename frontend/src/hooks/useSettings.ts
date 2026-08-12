import { useState, useCallback, useEffect, useRef } from "react";
import i18n from "i18next";
import { settingsApi, getAccessToken } from "../services/api";
import type { SettingsResponse } from "../types";

export function useSettings() {
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savingKeys, setSavingKeys] = useState<Set<string>>(new Set());
  const authGenerationRef = useRef(0);
  const inFlightRef = useRef<{
    token: string;
    promise: Promise<void>;
  } | null>(null);

  const fetchSettings = useCallback((force = false): Promise<void> => {
    // 没有 token 时不请求 settings
    const token = getAccessToken();
    if (!token) {
      authGenerationRef.current += 1;
      inFlightRef.current = null;
      setSettings(null);
      setIsLoading(false);
      return Promise.resolve();
    }

    if (!force && inFlightRef.current?.token === token) {
      return inFlightRef.current.promise;
    }

    authGenerationRef.current += 1;
    const generation = authGenerationRef.current;
    setIsLoading(true);
    setError(null);
    const promise = settingsApi
      .list()
      .then((data) => {
        if (
          generation === authGenerationRef.current &&
          getAccessToken() === token
        ) {
          setSettings(data);
        }
      })
      .catch((err) => {
        if (generation === authGenerationRef.current) {
          setError(
            err instanceof Error
              ? err.message
              : i18n.t("settings.loadFailed", "加载设置失败"),
          );
        }
      })
      .finally(() => {
        if (inFlightRef.current?.promise === promise) {
          inFlightRef.current = null;
        }
        if (generation === authGenerationRef.current) {
          setIsLoading(false);
        }
      });
    inFlightRef.current = { token, promise };
    return promise;
  }, []);

  useEffect(() => {
    fetchSettings();
  }, [fetchSettings]);

  // 监听登录成功事件，重新加载 settings
  useEffect(() => {
    const handleLogin = () => {
      void fetchSettings();
    };
    const handleLogout = () => {
      authGenerationRef.current += 1;
      inFlightRef.current = null;
      setSettings(null);
      setIsLoading(false);
    };

    window.addEventListener("auth:login", handleLogin);
    window.addEventListener("auth:logout", handleLogout);

    return () => {
      window.removeEventListener("auth:login", handleLogin);
      window.removeEventListener("auth:logout", handleLogout);
      authGenerationRef.current += 1;
    };
  }, [fetchSettings]);

  const updateSetting = useCallback(
    async (key: string, value: string | number | boolean | object) => {
      setSavingKeys((prev) => new Set(prev).add(key));
      setError(null);
      try {
        await settingsApi.update(key, value);
        // Re-fetch settings from server to ensure UI is in sync
        await fetchSettings(true);
        return true;
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : i18n.t("settings.updateFailed", "更新设置失败"),
        );
        return false;
      } finally {
        setSavingKeys((prev) => {
          const next = new Set(prev);
          next.delete(key);
          return next;
        });
      }
    },
    [fetchSettings],
  );

  const resetSetting = useCallback(
    async (key: string) => {
      setSavingKeys((prev) => new Set(prev).add(key));
      setError(null);
      try {
        await settingsApi.reset(key);
        // Refetch to get updated values
        await fetchSettings(true);
        return true;
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : i18n.t("settings.resetFailed", "重置设置失败"),
        );
        return false;
      } finally {
        setSavingKeys((prev) => {
          const next = new Set(prev);
          next.delete(key);
          return next;
        });
      }
    },
    [fetchSettings],
  );

  const resetAllSettings = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      await settingsApi.resetAll();
      await fetchSettings(true);
      return true;
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : i18n.t("settings.resetAllFailed", "重置所有设置失败"),
      );
      return false;
    } finally {
      setIsLoading(false);
    }
  }, [fetchSettings]);

  const exportSettings = useCallback(() => {
    if (!settings) return;

    const exportData = {
      version: "1.0",
      exported_at: new Date().toISOString(),
      settings: Object.values(settings.settings)
        .flat()
        .reduce(
          (acc, item) => {
            acc[item.key] = item.value;
            return acc;
          },
          {} as Record<string, unknown>,
        ),
    };

    const blob = new Blob([JSON.stringify(exportData, null, 2)], {
      type: "application/json",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    const date = new Date().toISOString().split("T")[0];
    a.href = url;
    a.download = `lambchat-settings-${date}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }, [settings]);

  const importSettings = useCallback(
    async (
      file: File,
    ): Promise<{
      success: boolean;
      updatedCount: number;
      errors: string[];
    }> => {
      const errors: string[] = [];
      let updatedCount = 0;

      try {
        const text = await file.text();
        const data = JSON.parse(text);

        // Validate structure
        if (
          !data.version ||
          !data.settings ||
          typeof data.settings !== "object"
        ) {
          return {
            success: false,
            updatedCount: 0,
            errors: [i18n.t("settings.invalidFormat", "设置文件格式无效")],
          };
        }

        // Get all valid keys from current settings
        const validKeys = new Set(
          Object.values(settings?.settings ?? {})
            .flat()
            .map((item) => item.key),
        );

        // Merge: update each valid key from imported settings
        for (const [key, value] of Object.entries(
          data.settings as Record<string, unknown>,
        )) {
          if (validKeys.has(key)) {
            const success = await updateSetting(
              key,
              value as string | number | boolean | object,
            );
            if (success) {
              updatedCount++;
            } else {
              errors.push(`Failed to update: ${key}`);
            }
          }
        }

        return { success: true, updatedCount, errors };
      } catch (err) {
        return {
          success: false,
          updatedCount: 0,
          errors: [
            err instanceof Error
              ? err.message
              : i18n.t("settings.parseFailed", "解析JSON文件失败"),
          ],
        };
      }
    },
    [settings, updateSetting],
  );

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  // Get a specific setting value by key
  const getSettingValue = useCallback(
    (key: string): boolean | string | number | object | undefined => {
      if (!settings) return undefined;
      const allSettings = Object.values(settings.settings).flat();
      const setting = allSettings.find((s) => s.key === key);
      return setting?.value;
    },
    [settings],
  );

  // Get a boolean setting value (returns false if not found or while loading)
  const getBooleanSetting = useCallback(
    (key: string): boolean => {
      const value = getSettingValue(key);
      return value === true || value === "true";
    },
    [getSettingValue],
  );

  return {
    settings,
    isLoading,
    error,
    savingKeys,
    fetchSettings,
    updateSetting,
    resetSetting,
    resetAllSettings,
    clearError,
    exportSettings,
    importSettings,
    getSettingValue,
    getBooleanSetting,
  };
}
