import {
  createContext,
  useContext,
  ReactNode,
  useMemo,
  useState,
  useEffect,
  useCallback,
} from "react";
import { useSettings } from "../hooks/useSettings";
import { useAuth } from "../hooks/useAuth";
import { modelApi } from "../services/api";
import type { SettingsResponse } from "../types";

export interface AvailableModel {
  id: string;
  value: string;
  provider?: string;
  label: string;
  description?: string;
}

interface SettingsContextValue {
  settings: SettingsResponse | null;
  enableSkills: boolean;
  enableMemory: boolean;
  isLoading: boolean;
  error: string | null;
  savingKeys: Set<string>;
  availableModels: AvailableModel[] | null;
  defaultModel: string;
  pinnedModelIds: string[];
  togglePinnedModel: (modelId: string) => void;
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

  const { isAuthenticated } = useAuth();

  // 从 DB 的 model_configs 读取可用模型
  const [dbModels, setDbModels] = useState<AvailableModel[] | null>(null);

  // 置顶模型 ID
  const [pinnedModelIds, setPinnedModelIds] = useState<string[]>([]);

  const fetchModels = useCallback(() => {
    modelApi
      .listAvailable()
      .then((data) => {
        if (data.models && data.models.length > 0) {
          setDbModels(
            data.models.map((m) => ({
              id: m.id || "",
              value: m.value,
              provider: m.provider,
              label: m.label,
              description: m.description,
            })),
          );
        } else {
          setDbModels(null);
        }
      })
      .catch(() => setDbModels(null));
  }, []);

  const fetchPinnedModels = useCallback(() => {
    modelApi
      .getPinnedModelIds()
      .then(setPinnedModelIds)
      .catch(() => {});
  }, []);

  useEffect(() => {
    if (isAuthenticated) {
      fetchModels();
      fetchPinnedModels();
    }
  }, [isAuthenticated, fetchModels, fetchPinnedModels]);

  const togglePinnedModel = useCallback((modelId: string) => {
    setPinnedModelIds((prev) => {
      const next = prev.includes(modelId)
        ? prev.filter((id) => id !== modelId)
        : [...prev, modelId];
      modelApi.updatePinnedModelIds(next).catch(() => {});
      return next;
    });
  }, []);

  // Auto-clean orphaned pinned IDs (models that were deleted)
  const cleanedPinnedIds = useMemo(() => {
    if (!dbModels || pinnedModelIds.length === 0) return pinnedModelIds;
    const validIds = new Set(dbModels.map((m) => m.id));
    const cleaned = pinnedModelIds.filter((id) => validIds.has(id));
    return cleaned;
  }, [dbModels, pinnedModelIds]);

  useEffect(() => {
    if (cleanedPinnedIds.length === pinnedModelIds.length) return;
    setPinnedModelIds(cleanedPinnedIds);
    modelApi.updatePinnedModelIds(cleanedPinnedIds).catch(() => {});
  }, [cleanedPinnedIds, pinnedModelIds.length]);

  // 从 DB 读取模型
  const availableModels = useMemo(() => {
    return dbModels;
  }, [dbModels]);

  const defaultModel = useMemo(() => {
    return availableModels && availableModels.length > 0
      ? availableModels[0].value
      : "";
  }, [availableModels]);

  const value: SettingsContextValue = {
    settings,
    enableSkills: getBooleanSetting("ENABLE_SKILLS"),
    enableMemory: getBooleanSetting("ENABLE_MEMORY"),
    availableModels,
    defaultModel,
    pinnedModelIds: cleanedPinnedIds,
    togglePinnedModel,
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
