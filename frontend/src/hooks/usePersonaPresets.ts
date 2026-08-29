import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { personaPresetApi } from "../services/api";
import { subscribePersonaPresetsChanged } from "./personaPresetEvents";
import type {
  PersonaPreset,
  PersonaPresetCreate,
  PersonaPresetListParams,
  PersonaPresetPreferenceUpdate,
  PersonaPresetSnapshot,
  PersonaPresetUpdate,
} from "../types";

export function usePersonaPresets(options?: {
  enabled?: boolean;
  listParams?: PersonaPresetListParams;
}) {
  const { t } = useTranslation();
  const enabled = options?.enabled !== false;
  const listParams = options?.listParams;
  const [presets, setPresets] = useState<PersonaPreset[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [isMutating, setIsMutating] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [hasLoaded, setHasLoaded] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchPresets = useCallback(
    async (params: PersonaPresetListParams = {}) => {
      if (!enabled) return;
      setIsLoading(true);
      setError(null);
      try {
        const response = await personaPresetApi.list({
          skip: 0,
          limit: 20,
          ...params,
        });
        setPresets(response.presets);
        setTotal(response.total);
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : t(
                "personaPresets.fetchFailed",
                "Failed to fetch persona presets",
              ),
        );
      } finally {
        setIsLoading(false);
        // 首次请求落地后，后续搜索/翻页刷新不再把页面回退成骨架屏（issue #158）
        setHasLoaded(true);
      }
    },
    [enabled, t],
  );

  const loadMore = useCallback(
    async (params: PersonaPresetListParams = {}) => {
      if (!enabled || isLoadingMore) return;
      setIsLoadingMore(true);
      try {
        const response = await personaPresetApi.list({
          ...params,
          skip: presets.length,
          limit: 20,
        });
        setPresets((prev) => {
          const existingIds = new Set(prev.map((p) => p.id));
          const newItems = response.presets.filter(
            (p) => !existingIds.has(p.id),
          );
          return [...prev, ...newItems];
        });
        setTotal(response.total);
      } catch {
        /* silent — use existing list */
      } finally {
        setIsLoadingMore(false);
      }
    },
    [enabled, isLoadingMore, presets.length],
  );

  useEffect(() => {
    fetchPresets(listParams);
  }, [fetchPresets, listParams]);

  useEffect(() => {
    if (!enabled) return;
    return subscribePersonaPresetsChanged(() => {
      void fetchPresets(listParams);
    });
  }, [enabled, fetchPresets, listParams]);

  const usePreset = useCallback(
    async (presetId: string): Promise<PersonaPresetSnapshot | null> => {
      setIsMutating(true);
      setError(null);
      try {
        const snapshot = await personaPresetApi.use(presetId);
        const now = new Date().toISOString();
        setPresets((prev) =>
          prev.map((preset) =>
            preset.id === presetId
              ? {
                  ...preset,
                  usage_count: preset.usage_count + 1,
                  last_used_at: now,
                }
              : preset,
          ),
        );
        return snapshot;
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : t("personaPresets.useFailed", "Failed to use persona preset"),
        );
        return null;
      } finally {
        setIsMutating(false);
      }
    },
    [t],
  );

  const updatePreference = useCallback(
    async (
      presetId: string,
      preference: PersonaPresetPreferenceUpdate,
    ): Promise<PersonaPreset | null> => {
      setIsMutating(true);
      setError(null);
      try {
        const updated = await personaPresetApi.updatePreference(
          presetId,
          preference,
        );
        setPresets((prev) =>
          prev.map((preset) => (preset.id === updated.id ? updated : preset)),
        );
        return updated;
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : t(
                "personaPresets.preferenceFailed",
                "Failed to update persona preference",
              ),
        );
        return null;
      } finally {
        setIsMutating(false);
      }
    },
    [t],
  );

  const copyPreset = useCallback(
    async (presetId: string): Promise<PersonaPreset | null> => {
      setIsMutating(true);
      setError(null);
      try {
        const copied = await personaPresetApi.copy(presetId);
        await fetchPresets(listParams);
        return copied;
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : t("personaPresets.copyFailed", "Failed to copy persona preset"),
        );
        return null;
      } finally {
        setIsMutating(false);
      }
    },
    [fetchPresets, listParams, t],
  );

  const createPreset = useCallback(
    async (data: PersonaPresetCreate): Promise<PersonaPreset | null> => {
      setIsMutating(true);
      setError(null);
      try {
        const created = await personaPresetApi.create(data);
        await fetchPresets(listParams);
        return created;
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : t(
                "personaPresets.createFailed",
                "Failed to create persona preset",
              ),
        );
        return null;
      } finally {
        setIsMutating(false);
      }
    },
    [fetchPresets, listParams, t],
  );

  const updatePreset = useCallback(
    async (
      presetId: string,
      data: PersonaPresetUpdate,
    ): Promise<PersonaPreset | null> => {
      setIsMutating(true);
      setError(null);
      try {
        const updated = await personaPresetApi.update(presetId, data);
        await fetchPresets(listParams);
        return updated;
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : t(
                "personaPresets.updateFailed",
                "Failed to update persona preset",
              ),
        );
        return null;
      } finally {
        setIsMutating(false);
      }
    },
    [fetchPresets, listParams, t],
  );

  const deletePreset = useCallback(
    async (presetId: string): Promise<boolean> => {
      setIsMutating(true);
      setError(null);
      try {
        await personaPresetApi.delete(presetId);
        await fetchPresets(listParams);
        return true;
      } catch (err) {
        setError(
          err instanceof Error
            ? err.message
            : t(
                "personaPresets.deleteFailed",
                "Failed to delete persona preset",
              ),
        );
        return false;
      } finally {
        setIsMutating(false);
      }
    },
    [fetchPresets, listParams, t],
  );

  return {
    presets,
    total,
    isLoading,
    isLoadingMore,
    isMutating,
    hasLoaded,
    error,
    fetchPresets,
    loadMore,
    usePreset,
    updatePreference,
    copyPreset,
    createPreset,
    updatePreset,
    deletePreset,
  };
}
