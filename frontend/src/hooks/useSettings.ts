import { useState, useCallback, useEffect } from "react";
import { settingsApi } from "../services/api";
import type { SettingsResponse } from "../types";

export function useSettings() {
  const [settings, setSettings] = useState<SettingsResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savingKeys, setSavingKeys] = useState<Set<string>>(new Set());

  const fetchSettings = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await settingsApi.list();
      setSettings(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load settings");
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchSettings();
  }, [fetchSettings]);

  const updateSetting = useCallback(
    async (key: string, value: string | number | boolean | object) => {
      setSavingKeys((prev) => new Set(prev).add(key));
      setError(null);
      try {
        await settingsApi.update(key, value);
        // Re-fetch settings from server to ensure UI is in sync
        await fetchSettings();
        return true;
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to update setting",
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
        await fetchSettings();
        return true;
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to reset setting",
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
      await fetchSettings();
      return true;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to reset settings");
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
    a.download = `lamb-agent-settings-${date}.json`;
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
            errors: ["Invalid settings file format"],
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
            err instanceof Error ? err.message : "Failed to parse JSON file",
          ],
        };
      }
    },
    [settings, updateSetting],
  );

  const clearError = useCallback(() => {
    setError(null);
  }, []);

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
  };
}
