import { createContext, useContext, ReactNode, useCallback } from "react";
import { useSettings } from "../hooks/useSettings";
import { useAuth } from "../hooks/useAuth";
import { authApi } from "../services/api";
import type { SettingsResponse } from "../types";

interface SettingsContextValue {
  settings: SettingsResponse | null;
  enableMcp: boolean;
  enableSkills: boolean;
  isLoading: boolean;
  error: string | null;
  savingKeys: Set<string>;
  updateSetting: (
    key: string,
    value: string | number | boolean | object,
  ) => Promise<boolean>;
  resetSetting: (key: string) => Promise<boolean>;
  resetAllSettings: () => Promise<boolean>;
  clearError: () => void;
  exportSettings: () => void;
  importSettings: (
    file: File,
  ) => Promise<{ success: boolean; updatedCount: number; errors: string[] }>;
  updateMcpEnabled: (enabled: boolean) => Promise<boolean>;
}

const SettingsContext = createContext<SettingsContextValue | undefined>(
  undefined,
);

export function SettingsProvider({ children }: { children: ReactNode }) {
  const { user, refreshUser } = useAuth();
  const {
    settings,
    isLoading,
    error,
    savingKeys,
    getBooleanSetting,
    updateSetting,
    resetSetting,
    resetAllSettings,
    clearError,
    exportSettings,
    importSettings,
  } = useSettings();

  // Get mcp_enabled from user metadata (stored in database, not settings)
  const enableMcp = user?.metadata?.mcp_enabled ?? false;

  const updateMcpEnabled = useCallback(
    async (enabled: boolean): Promise<boolean> => {
      try {
        await authApi.updateMetadata({ mcp_enabled: enabled });
        await refreshUser();
        return true;
      } catch (err) {
        console.error("Failed to update mcp_enabled:", err);
        return false;
      }
    },
    [refreshUser],
  );

  const value: SettingsContextValue = {
    settings,
    enableMcp,
    enableSkills: getBooleanSetting("ENABLE_SKILLS"),
    isLoading,
    error,
    savingKeys,
    updateSetting,
    resetSetting,
    resetAllSettings,
    clearError,
    exportSettings,
    importSettings,
    updateMcpEnabled,
  };

  return (
    <SettingsContext.Provider value={value}>
      {children}
    </SettingsContext.Provider>
  );
}

// Fast refresh only works when a file only exports components.
// Use a new file to share constants or functions between components
// eslint-disable-next-line react-refresh/only-export-components
export function useSettingsContext() {
  const context = useContext(SettingsContext);
  if (context === undefined) {
    throw new Error(
      "useSettingsContext must be used within a SettingsProvider",
    );
  }
  return context;
}
