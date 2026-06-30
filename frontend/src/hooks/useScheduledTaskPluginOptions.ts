import { useCallback, useEffect, useMemo, useState } from "react";
import { pluginRuntimeApi } from "../services/api/pluginRuntime";
import type { ExtensionScopedOption } from "../types";
import { listenPluginRuntimeUpdated } from "../utils/pluginRuntimeEvents";
import { filterPluginOptionsByVisibleWhen } from "../extensions/pluginOptions";

interface UseScheduledTaskPluginOptionsResult {
  options: ExtensionScopedOption[];
  isLoading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

export function useScheduledTaskPluginOptions(
  agentId: string | null,
  options: { includeInactive?: boolean; enabled?: boolean } = {},
): UseScheduledTaskPluginOptionsResult {
  const enabled = options.enabled ?? true;
  const includeInactive = options.includeInactive ?? false;
  const [allOptions, setAllOptions] = useState<ExtensionScopedOption[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    if (!enabled) {
      setAllOptions([]);
      setError(null);
      setIsLoading(false);
      return;
    }

    setIsLoading(true);
    setError(null);
    try {
      const response = await pluginRuntimeApi.listScheduledTaskOptions({ includeInactive });
      setAllOptions(response.options);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load scheduled task plugin options");
      setAllOptions([]);
    } finally {
      setIsLoading(false);
    }
  }, [enabled, includeInactive]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!enabled) return;
    return listenPluginRuntimeUpdated(() => {
      void refresh();
    });
  }, [enabled, refresh]);

  const scopedOptions = useMemo(
    () =>
      agentId === null
        ? allOptions
        : filterPluginOptionsByVisibleWhen(allOptions, {
            agentId,
            scope: "scheduled_task",
          }),
    [agentId, allOptions],
  );

  return {
    options: scopedOptions,
    isLoading,
    error,
    refresh,
  };
}
