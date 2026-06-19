import { useCallback, useEffect, useState } from "react";
import { pluginRuntimeApi } from "../services/api/pluginRuntime";
import type { PluginRuntimeContributionStatesResponse } from "../types";
import { listenPluginRuntimeUpdated } from "../utils/pluginRuntimeEvents";

interface UseExtensionContributionsOptions {
  enabled?: boolean;
}

export function useExtensionContributions(
  options: UseExtensionContributionsOptions = {},
) {
  const enabled = options.enabled ?? true;
  const [data, setData] =
    useState<PluginRuntimeContributionStatesResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchContributions = useCallback(async () => {
    if (!enabled) {
      setData(null);
      setError(null);
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setError(null);
    try {
      setData(await pluginRuntimeApi.listContributions());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load extensions");
      setData(null);
    } finally {
      setIsLoading(false);
    }
  }, [enabled]);

  useEffect(() => {
    void fetchContributions();
  }, [fetchContributions]);

  useEffect(() => {
    if (!enabled) return;
    return listenPluginRuntimeUpdated(() => {
      void fetchContributions();
    });
  }, [enabled, fetchContributions]);

  return {
    data,
    plugins: data?.plugins ?? [],
    isLoading,
    error,
    fetchContributions,
    clearError: () => setError(null),
  };
}
