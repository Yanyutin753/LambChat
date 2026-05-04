import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { personaPresetApi } from "../services/api";
import type {
  PersonaPreset,
  PersonaPresetCreate,
  PersonaPresetListParams,
  PersonaPresetSnapshot,
  PersonaPresetUpdate,
} from "../types";

export function usePersonaPresets(options?: { enabled?: boolean }) {
  const { t } = useTranslation();
  const enabled = options?.enabled !== false;
  const [presets, setPresets] = useState<PersonaPreset[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isMutating, setIsMutating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchPresets = useCallback(
    async (params: PersonaPresetListParams = {}) => {
      if (!enabled) return;
      setIsLoading(true);
      setError(null);
      try {
        const response = await personaPresetApi.list(params);
        setPresets(response.presets);
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
      }
    },
    [enabled, t],
  );

  useEffect(() => {
    fetchPresets();
  }, [fetchPresets]);

  const usePreset = useCallback(
    async (presetId: string): Promise<PersonaPresetSnapshot | null> => {
      setIsMutating(true);
      setError(null);
      try {
        return await personaPresetApi.use(presetId);
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

  const copyPreset = useCallback(
    async (presetId: string): Promise<PersonaPreset | null> => {
      setIsMutating(true);
      setError(null);
      try {
        const copied = await personaPresetApi.copy(presetId);
        await fetchPresets();
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
    [fetchPresets, t],
  );

  const createPreset = useCallback(
    async (data: PersonaPresetCreate): Promise<PersonaPreset | null> => {
      setIsMutating(true);
      setError(null);
      try {
        const created = await personaPresetApi.create(data);
        await fetchPresets();
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
    [fetchPresets, t],
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
        await fetchPresets();
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
    [fetchPresets, t],
  );

  const deletePreset = useCallback(
    async (presetId: string): Promise<boolean> => {
      setIsMutating(true);
      setError(null);
      try {
        await personaPresetApi.delete(presetId);
        await fetchPresets();
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
    [fetchPresets, t],
  );

  return {
    presets,
    isLoading,
    isMutating,
    error,
    fetchPresets,
    usePreset,
    copyPreset,
    createPreset,
    updatePreset,
    deletePreset,
  };
}
