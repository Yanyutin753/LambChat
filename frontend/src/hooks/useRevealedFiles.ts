import { useState, useCallback, useEffect, useRef, useMemo } from "react";
import { useInView } from "react-intersection-observer";
import {
  revealedFileApi,
  type RevealedFileItem,
  type RevealedFileListParams,
  type RevealedFileGroupedListParams,
  type SessionGroupItem,
} from "../services/api";

const PAGE_SIZE = 20;

export interface UseRevealedFilesReturn {
  files: RevealedFileItem[];
  total: number;
  stats: Record<string, number>;
  isLoading: boolean;
  isLoadingMore: boolean;
  hasMore: boolean;
  error: string | null;
  loadMoreRef: React.RefCallback<HTMLElement>;
  refresh: () => void;
  toggleFavorite: (fileId: string) => Promise<void>;
}

export function useRevealedFiles(
  params?: Omit<RevealedFileListParams, "page" | "page_size">,
): UseRevealedFilesReturn {
  const [files, setFiles] = useState<RevealedFileItem[]>([]);
  const [total, setTotal] = useState(0);
  const [stats, setStats] = useState<Record<string, number>>({});
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const { ref: loadMoreRef, inView } = useInView({ threshold: 0.1 });

  // Stabilize params reference to prevent infinite re-fetch loops
  const paramsRef = useRef(params);
  paramsRef.current = params;
  const stableParams = useMemo(() => JSON.stringify(params), [params]);

  const fetchFiles = useCallback(
    async (pageNum: number, append: boolean) => {
      try {
        if (append) {
          setIsLoadingMore(true);
        } else {
          setIsLoading(true);
        }
        setError(null);
        const currentParams = paramsRef.current ?? {};
        const result = await revealedFileApi.list({
          ...currentParams,
          page: pageNum,
          page_size: PAGE_SIZE,
        });
        setFiles((prev) =>
          append ? [...prev, ...result.items] : result.items,
        );
        setTotal(result.total);
        setHasMore(
          result.items.length === PAGE_SIZE &&
            result.total > pageNum * PAGE_SIZE,
        );
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load files");
      } finally {
        setIsLoading(false);
        setIsLoadingMore(false);
      }
    },
    [], // intentionally empty — reads from paramsRef
  );

  const fetchStats = useCallback(async () => {
    try {
      const s = await revealedFileApi.getStats();
      setStats(s);
    } catch {
      // stats are non-critical
    }
  }, []);

  // Re-fetch when stable params change
  useEffect(() => {
    setPage(1);
    setFiles([]);
    fetchFiles(1, false);
    fetchStats();
  }, [stableParams, fetchFiles, fetchStats]);

  useEffect(() => {
    if (inView && hasMore && !isLoading && !isLoadingMore) {
      const nextPage = page + 1;
      setPage(nextPage);
      fetchFiles(nextPage, true);
    }
  }, [inView, hasMore, isLoading, isLoadingMore, page, fetchFiles]);

  const refresh = useCallback(() => {
    setPage(1);
    setFiles([]);
    fetchFiles(1, false);
    fetchStats();
  }, [fetchFiles, fetchStats]);

  const toggleFavorite = useCallback(async (fileId: string) => {
    try {
      const result = await revealedFileApi.toggleFavorite(fileId);
      setFiles((prev) =>
        prev.map((f) =>
          f.id === fileId ? { ...f, is_favorite: result.is_favorite } : f,
        ),
      );
    } catch {
      // non-critical
    }
  }, []);

  return {
    files,
    total,
    stats,
    isLoading,
    isLoadingMore,
    hasMore,
    error,
    loadMoreRef,
    refresh,
    toggleFavorite,
  };
}

/* ── Session-grouped variant ───────────────────────────── */

const SESSION_PAGE_SIZE = 20;

export interface UseRevealedFilesGroupedReturn {
  sessionGroups: SessionGroupItem[];
  totalSessions: number;
  stats: Record<string, number>;
  isLoading: boolean;
  isLoadingMore: boolean;
  hasMore: boolean;
  error: string | null;
  loadMoreRef: React.RefCallback<HTMLElement>;
  refresh: () => void;
  toggleFavorite: (fileId: string) => void;
}

export function useRevealedFilesGrouped(
  params?: Omit<RevealedFileGroupedListParams, "page" | "page_size">,
): UseRevealedFilesGroupedReturn {
  const [sessionGroups, setSessionGroups] = useState<SessionGroupItem[]>([]);
  const [totalSessions, setTotalSessions] = useState(0);
  const [stats, setStats] = useState<Record<string, number>>({});
  const [page, setPage] = useState(1);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const { ref: loadMoreRef, inView } = useInView({ threshold: 0.1 });

  const paramsRef = useRef(params);
  paramsRef.current = params;
  const stableParams = useMemo(() => JSON.stringify(params), [params]);

  const fetchSessions = useCallback(
    async (pageNum: number, append: boolean) => {
      try {
        if (append) setIsLoadingMore(true);
        else setIsLoading(true);
        setError(null);
        const currentParams = paramsRef.current ?? {};
        const result = await revealedFileApi.listGrouped({
          ...currentParams,
          page: pageNum,
          page_size: SESSION_PAGE_SIZE,
        });
        setSessionGroups((prev) =>
          append ? [...prev, ...result.sessions] : result.sessions,
        );
        setTotalSessions(result.total_sessions);
        setHasMore(
          result.sessions.length === SESSION_PAGE_SIZE &&
            result.total_sessions > pageNum * SESSION_PAGE_SIZE,
        );
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load files");
      } finally {
        setIsLoading(false);
        setIsLoadingMore(false);
      }
    },
    [],
  );

  const fetchStats = useCallback(async () => {
    try {
      const s = await revealedFileApi.getStats();
      setStats(s);
    } catch {
      // non-critical
    }
  }, []);

  useEffect(() => {
    setPage(1);
    setSessionGroups([]);
    fetchSessions(1, false);
    fetchStats();
  }, [stableParams, fetchSessions, fetchStats]);

  useEffect(() => {
    if (inView && hasMore && !isLoading && !isLoadingMore) {
      const nextPage = page + 1;
      setPage(nextPage);
      fetchSessions(nextPage, true);
    }
  }, [inView, hasMore, isLoading, isLoadingMore, page, fetchSessions]);

  const refresh = useCallback(() => {
    setPage(1);
    setSessionGroups([]);
    fetchSessions(1, false);
    fetchStats();
  }, [fetchSessions, fetchStats]);

  const toggleFavorite = useCallback((fileId: string) => {
    revealedFileApi
      .toggleFavorite(fileId)
      .then((result) => {
        setSessionGroups((prev) =>
          prev.map((group) => ({
            ...group,
            files: group.files.map((f) =>
              f.id === fileId ? { ...f, is_favorite: result.is_favorite } : f,
            ),
          })),
        );
      })
      .catch(() => {});
  }, []);

  return {
    sessionGroups,
    totalSessions,
    stats,
    isLoading,
    isLoadingMore,
    hasMore,
    error,
    loadMoreRef,
    refresh,
    toggleFavorite,
  };
}
