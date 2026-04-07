import {
  createContext,
  useContext,
  ReactNode,
  useMemo,
  useState,
  useEffect,
} from "react";
import { useSettings } from "../hooks/useSettings";
import { modelConfigApi } from "../services/api/model_config";
import type { SettingsResponse } from "../types";

export interface AvailableModel {
  value: string;
  label: string;
}

interface SettingsContextValue {
  settings: SettingsResponse | null;
  enableSkills: boolean;
  isLoading: boolean;
  error: string | null;
  savingKeys: Set<string>;
  availableModels: AvailableModel[] | null;
  defaultModel: string;
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
    getSettingValue,
    updateSetting,
    resetSetting,
    resetAllSettings,
    clearError,
    exportSettings,
    importSettings,
  } = useSettings();

  // 用户可用的模型 ID 集合（由后端根据角色权限过滤）
  const [allowedModelIds, setAllowedModelIds] = useState<Set<string> | null>(
    null,
  );

  useEffect(() => {
    let cancelled = false;
    const fetchAllowedModels = async () => {
      try {
        const result = await modelConfigApi.getUserAllowedModels();
        if (!cancelled) {
          setAllowedModelIds(new Set(result.models));
        }
      } catch {
        // API 失败时（如无配置），不限制模型
      }
    };
    fetchAllowedModels();
    return () => {
      cancelled = true;
    };
  }, []);

  const availableModels = useMemo(() => {
    const raw = getSettingValue("LLM_AVAILABLE_MODELS");
    if (!Array.isArray(raw) || raw.length === 0) return null;

    const allModels = raw as AvailableModel[];

    // allowedModelIds 为 null 表示未配置权限限制，显示全部模型
    if (allowedModelIds === null) return allModels;

    // 过滤为仅允许的模型
    const filtered = allModels.filter((m) => allowedModelIds.has(m.value));
    return filtered.length > 0 ? filtered : null;
  }, [getSettingValue, allowedModelIds]);

  const defaultModel = useMemo(() => {
    return (
      (getSettingValue("LLM_MODEL") as string) ||
      "anthropic/claude-3-5-sonnet-20241022"
    );
  }, [getSettingValue]);

  const value: SettingsContextValue = {
    settings,
    enableSkills: getBooleanSetting("ENABLE_SKILLS"),
    availableModels,
    defaultModel,
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
