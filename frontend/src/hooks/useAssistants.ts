import { useCallback, useEffect, useMemo, useState } from "react";

import { assistantApi } from "../services/api/assistant";
import type {
  Assistant,
  AssistantCreate,
  AssistantListScope,
  AssistantUpdate,
} from "../types";

interface UseAssistantsOptions {
  scope?: AssistantListScope;
  search?: string;
  tags?: string[];
  category?: string;
  enabled?: boolean;
}

export const EMPTY_ASSISTANT_TAGS: string[] = [];

export function coerceAssistantList(value: unknown): Assistant[] {
  return Array.isArray(value) ? value : [];
}

export function getAssistantTagsKey(tags?: string[]): string {
  return Array.isArray(tags) && tags.length > 0 ? tags.join(",") : "";
}

export function normalizeAssistantTags(tags?: string[]): string[] {
  return Array.isArray(tags) && tags.length > 0 ? tags : EMPTY_ASSISTANT_TAGS;
}

export function useAssistants(options: UseAssistantsOptions = {}) {
  const {
    scope = "all",
    search = "",
    tags,
    category,
    enabled = true,
  } = options;
  const [assistants, setAssistants] = useState<Assistant[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isMutating, setIsMutating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const tagsKey = getAssistantTagsKey(tags);
  const stableTags = useMemo(() => normalizeAssistantTags(tags), [tagsKey]);

  const refresh = useCallback(async (): Promise<Assistant[]> => {
    if (!enabled) {
      setAssistants([]);
      return [];
    }

    setIsLoading(true);
    try {
      const items = coerceAssistantList(
        await assistantApi.list({ scope, search, tags: stableTags, category }),
      );
      setAssistants(items);
      setError(null);
      return items;
    } catch (err) {
      const message =
        err instanceof Error ? err.message : "Failed to load assistants";
      setError(message);
      setAssistants([]);
      return [];
    } finally {
      setIsLoading(false);
    }
  }, [enabled, scope, search, stableTags, category]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const withMutation = useCallback(
    async <T>(action: () => Promise<T>): Promise<T> => {
      setIsMutating(true);
      try {
        const result = await action();
        setError(null);
        return result;
      } catch (err) {
        const message =
          err instanceof Error ? err.message : "Assistant request failed";
        setError(message);
        throw err;
      } finally {
        setIsMutating(false);
      }
    },
    [],
  );

  const createAssistant = useCallback(
    async (data: AssistantCreate): Promise<Assistant> =>
      withMutation(async () => {
        const created = await assistantApi.create(data);
        await refresh();
        return created;
      }),
    [refresh, withMutation],
  );

  const updateAssistant = useCallback(
    async (assistantId: string, data: AssistantUpdate): Promise<Assistant> =>
      withMutation(async () => {
        const updated = await assistantApi.update(assistantId, data);
        await refresh();
        return updated;
      }),
    [refresh, withMutation],
  );

  const deleteAssistant = useCallback(
    async (assistantId: string): Promise<void> =>
      withMutation(async () => {
        await assistantApi.delete(assistantId);
        await refresh();
      }),
    [refresh, withMutation],
  );

  const cloneAssistant = useCallback(
    async (assistantId: string): Promise<Assistant> =>
      withMutation(async () => {
        const cloned = await assistantApi.clone(assistantId);
        await refresh();
        return cloned;
      }),
    [refresh, withMutation],
  );

  return {
    assistants,
    isLoading,
    isMutating,
    error,
    refresh,
    createAssistant,
    updateAssistant,
    deleteAssistant,
    cloneAssistant,
  };
}
