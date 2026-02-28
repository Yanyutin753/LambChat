import { createContext, useContext, ReactNode } from "react";
import { useSettings } from "../hooks/useSettings";
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
}

const SettingsContext = createContext<SettingsContextValue | undefined>(
  undefined,
);

export function SettingsProvider({ children }: { children: ReactNode }) {
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

  const value: SettingsContextValue = {
    settings,
    enableMcp: getBooleanSetting("ENABLE_MCP"),
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
