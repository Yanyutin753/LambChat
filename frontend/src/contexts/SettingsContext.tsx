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
import type { SettingsResponse, ModelConfig } from "../types";
import { resolveAvailableModelValue } from "../types/model";

export interface AvailableModel {
  value: string;
  label: string;
  description?: string;
  provider?: string;
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

  // 所有模型列表（从 providers API 获取，用于构建 availableModels）
  const [allFlatModels, setAllFlatModels] = useState<AvailableModel[]>([]);

  useEffect(() => {
    let cancelled = false;
    const fetchAllowedModels = async () => {
      try {
        const [allowedResult, providerResult] = await Promise.all([
          modelConfigApi.getUserAllowedModels(),
          modelConfigApi.getProviderConfig().catch(() => null),
        ]);
        if (!cancelled) {
          setAllowedModelIds(new Set(allowedResult.models));
          if (providerResult) {
            setAllFlatModels(
              providerResult.flat_models.map((m: ModelConfig) => ({
                value: m.value || m.id || "",
                label: m.label || m.name || "",
                description: m.description,
                provider: m.provider,
              })),
            );
          } else if (allowedResult.models.length > 0) {
            // Fallback for non-admin users (no /providers permission):
            // still build a usable model list from allowed model IDs.
            setAllFlatModels(
              allowedResult.models.map((value: string) => ({
                value,
                label: value,
                description: "",
              })),
            );
          }
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
    // 如果没有从 providers API 获取到模型，回退到 settings 中的 LLM_AVAILABLE_MODELS
    const rawModels =
      allFlatModels.length > 0
        ? allFlatModels
        : (getSettingValue("LLM_AVAILABLE_MODELS") as AvailableModel[] | null);

    if (!rawModels || (Array.isArray(rawModels) && rawModels.length === 0)) {
      return null;
    }

    const models = Array.isArray(rawModels) ? rawModels : [];
    // allowedModelIds 为 null 表示未配置权限限制，显示全部模型
    if (allowedModelIds === null) return models;

    // 过滤为仅允许的模型
    const filtered = models.filter((m) => allowedModelIds.has(m.value));
    return filtered.length > 0 ? filtered : null;
  }, [allFlatModels, getSettingValue, allowedModelIds]);

  const defaultModel = useMemo(() => {
    const configuredModel = (getSettingValue("LLM_MODEL") as string) || "";
    return resolveAvailableModelValue(
      configuredModel,
      availableModels,
      configuredModel,
    );
  }, [getSettingValue, availableModels]);

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
