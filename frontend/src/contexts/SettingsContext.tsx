import { createContext, useContext, ReactNode } from "react";
import { useSettings } from "../hooks/useSettings";

interface SettingsContextValue {
  enableMcp: boolean;
  enableSkills: boolean;
  isLoading: boolean;
}

const SettingsContext = createContext<SettingsContextValue | undefined>(
  undefined,
);

export function SettingsProvider({ children }: { children: ReactNode }) {
  const { isLoading, getBooleanSetting } = useSettings();

  const value: SettingsContextValue = {
    enableMcp: getBooleanSetting("ENABLE_MCP"),
    enableSkills: getBooleanSetting("ENABLE_SKILLS"),
    isLoading,
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
