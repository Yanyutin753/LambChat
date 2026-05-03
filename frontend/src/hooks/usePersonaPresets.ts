import { useCallback, useEffect, useState } from "react";
import { personaPresetApi } from "../services/api";
import type {
  PersonaPreset,
  PersonaPresetCreate,
  PersonaPresetListParams,
  PersonaPresetSnapshot,
  PersonaPresetUpdate,
} from "../types";

export function usePersonaPresets(options?: { enabled?: boolean }) {
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
            : "Failed to fetch persona presets",
        );
      } finally {
        setIsLoading(false);
      }
    },
    [enabled],
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
          err instanceof Error ? err.message : "Failed to use persona preset",
        );
        return null;
      } finally {
        setIsMutating(false);
      }
    },
    [],
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
          err instanceof Error ? err.message : "Failed to copy persona preset",
        );
        return null;
      } finally {
        setIsMutating(false);
      }
    },
    [fetchPresets],
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
            : "Failed to create persona preset",
        );
        return null;
      } finally {
        setIsMutating(false);
      }
    },
    [fetchPresets],
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
            : "Failed to update persona preset",
        );
        return null;
      } finally {
        setIsMutating(false);
      }
    },
    [fetchPresets],
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
  };
}
