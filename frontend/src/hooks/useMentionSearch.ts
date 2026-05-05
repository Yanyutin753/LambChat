import { useState, useEffect, useCallback, useRef } from "react";
import { personaPresetApi } from "../services/api";
import type { PersonaPreset } from "../types";

const PAGE_SIZE = 20;

export function useMentionSearch(query: string, isActive: boolean) {
  const [presets, setPresets] = useState<PersonaPreset[]>([]);
  const [total, setTotal] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const skipRef = useRef(0);
  const prevQueryRef = useRef<string | null>(null);
  const prevActiveRef = useRef(false);

  // Fetch first page when query changes or mention activates
  useEffect(() => {
    if (!isActive) {
      if (prevActiveRef.current) {
        setPresets([]);
        setTotal(0);
        skipRef.current = 0;
        prevQueryRef.current = null;
      }
      prevActiveRef.current = false;
      return;
    }

    prevActiveRef.current = true;

    // Only reset if query actually changed
    if (prevQueryRef.current === query) return;
    prevQueryRef.current = query;
    skipRef.current = 0;

    let cancelled = false;
    setIsLoading(true);
    personaPresetApi
      .list({
        q: query || undefined,
        status: "published",
        skip: 0,
        limit: PAGE_SIZE,
      })
      .then((response) => {
        if (cancelled) return;
        setPresets(response.presets);
        setTotal(response.total);
        skipRef.current = response.presets.length;
      })
      .catch(() => {
        if (cancelled) return;
        setPresets([]);
        setTotal(0);
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [query, isActive]);

  const hasMore = skipRef.current < total;

  const loadMore = useCallback(() => {
    if (isLoadingMore || !hasMore || !isActive) return;

    let cancelled = false;
    setIsLoadingMore(true);
    personaPresetApi
      .list({
        q: query || undefined,
        status: "published",
        skip: skipRef.current,
        limit: PAGE_SIZE,
      })
      .then((response) => {
        if (cancelled) return;
        setPresets((prev) => {
          const existingIds = new Set(prev.map((p) => p.id));
          const newItems = response.presets.filter(
            (p) => !existingIds.has(p.id),
          );
          return [...prev, ...newItems];
        });
        skipRef.current += response.presets.length;
        setTotal(response.total);
      })
      .finally(() => {
        if (!cancelled) setIsLoadingMore(false);
      });

    return () => {
      cancelled = true;
    };
  }, [isLoadingMore, hasMore, isActive, query]);

  return { presets, total, isLoading, isLoadingMore, hasMore, loadMore };
}
