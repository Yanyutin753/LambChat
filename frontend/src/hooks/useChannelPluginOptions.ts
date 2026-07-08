import { useCallback, useEffect, useMemo, useState } from "react";
import { pluginRuntimeApi } from "../services/api/pluginRuntime";
import type { ExtensionScopedOption } from "../types";
import { listenPluginRuntimeUpdated } from "../utils/pluginRuntimeEvents";

interface UseChannelPluginOptionsResult {
  options: ExtensionScopedOption[];
  isLoading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

function routeForChannel(channelType: string): string {
  return `/channels/${channelType}`;
}

function matchesChannelRoute(option: ExtensionScopedOption, channelType: string): boolean {
  const route = option.visible_when?.route;
  return !route || route === routeForChannel(channelType);
}

export function useChannelPluginOptions(
  channelType: string,
  options: { includeInactive?: boolean; enabled?: boolean } = {},
): UseChannelPluginOptionsResult {
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
      const response = await pluginRuntimeApi.listChannelOptions({ includeInactive });
      setAllOptions(response.options);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load channel plugin options");
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
    () => allOptions.filter((option) => matchesChannelRoute(option, channelType)),
    [allOptions, channelType],
  );

  return {
    options: scopedOptions,
    isLoading,
    error,
    refresh,
  };
}
