/**
 * Session management hooks
 */

import { useState, useCallback, useEffect, useRef } from "react";
import { useInView } from "react-intersection-observer";
import { sessionApi, type BackendSession } from "../services/api";

const PAGE_SIZE = 20;

// ─── Paginated session list with auto-fill (sidebar) ─────────────────

interface UseSessionListReturn {
  sessions: BackendSession[];
  isLoading: boolean;
  isLoadingMore: boolean;
  hasMore: boolean;
  error: string | null;
  loadSessions: (reset?: boolean) => Promise<void>;
  loadMoreSessions: () => void;
  setSessions: React.Dispatch<React.SetStateAction<BackendSession[]>>;
  scrollContainerRef: React.RefObject<HTMLDivElement | null>;
  loadMoreRef: React.RefCallback<HTMLElement>;
}

export function useSessionList(
  refreshKey?: number,
  isProjectsCollapsed?: boolean,
  setIsProjectsCollapsed?: (collapsed: boolean) => void,
  sidebarVisible?: boolean,
  isChatsCollapsed?: boolean,
): UseSessionListReturn {
  const [sessions, setSessions] = useState<BackendSession[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [hasMore, setHasMore] = useState(false);
  const [skip, setSkip] = useState(0);
  const [error, setError] = useState<string | null>(null);

  const scrollContainerRef = useRef<HTMLDivElement | null>(null);
  // Track in-flight request's skip to prevent duplicate requests
  const loadingSkipRef = useRef<number | null>(null);

  const { ref: loadMoreRef, inView } = useInView({
    threshold: 0.1,
  });

  const loadSessions = async (reset = false) => {
    if (!reset && (isLoading || isLoadingMore)) return;
    if (!reset && !hasMore) return;
    // Prevent infinite loops when collapsed sections hide all content
    if (!reset && isChatsCollapsed) return;

    const targetSkip = reset ? 0 : skip;
    // Skip if already loading this exact skip value (prevents duplicate requests)
    if (!reset && loadingSkipRef.current === targetSkip) return;
    loadingSkipRef.current = targetSkip;

    if (reset) {
      setIsLoading(true);
      setSkip(0);
    } else {
      setIsLoadingMore(true);
    }
    setError(null);

    try {
      const response = await sessionApi.list({
        limit: PAGE_SIZE,
        skip: targetSkip,
        status: "active",
      });

      const newSessions =
        "sessions" in response
          ? response.sessions
          : Array.isArray(response)
            ? response
            : [];
      const newHasMore = "has_more" in response ? response.has_more : false;

      if (reset) {
        setSessions(newSessions);
        setSkip(newSessions.length);
      } else {
        setSessions((prev) => [...prev, ...newSessions]);
        setSkip(targetSkip + newSessions.length);
      }
      // If no new sessions returned, stop loading even if backend says has_more
      // (e.g. remaining sessions are filtered out by status=active)
      setHasMore(newSessions.length > 0 ? newHasMore : false);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load sessions");
    } finally {
      setIsLoading(false);
      setIsLoadingMore(false);
      // Don't reset loadingSkipRef here - let it be cleared after skip is updated
      // This prevents auto-fill from sending duplicate requests while skip is stale
    }
  };

  const loadMoreSessions = useCallback(() => {
    if (hasMore && !isLoadingMore && !isLoading) {
      loadSessions(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasMore, isLoadingMore, isLoading]);

  // Infinite scroll via sentinel
  useEffect(() => {
    if (inView && hasMore && !isLoadingMore) {
      loadMoreSessions();
    }
  }, [inView, hasMore, isLoadingMore, loadMoreSessions]);

  // Auto-fill sidebar: expand projects first, then load more if still needed
  const loadSessionsRef = useRef(loadSessions);
  loadSessionsRef.current = loadSessions;

  useEffect(() => {
    if (isLoading || isLoadingMore) return;
    // Don't auto-fill when chats are collapsed — content is intentionally hidden,
    // so loading more sessions won't fill visible space and causes infinite loop
    if (isChatsCollapsed) return;

    // sessionListContent renders in both mobile & desktop sidebars.
    // Query DOM to find the scroll container that has actual dimensions.
    const allContainers = document.querySelectorAll<HTMLDivElement>(
      "[data-sidebar-scroll]",
    );
    let container: HTMLDivElement | null = null;
    for (const el of allContainers) {
      const rect = el.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) {
        container = el;
        break;
      }
    }

    if (!container || container.scrollHeight > container.clientHeight) return;

    // First: expand projects to reveal already-loaded sessions (no network request)
    if (isProjectsCollapsed && setIsProjectsCollapsed) {
      const hasProjectSessions = sessions.some((s) => s.metadata?.project_id);
      if (hasProjectSessions) {
        setIsProjectsCollapsed(false);
        return; // re-run after expansion to re-check if container is now full
      }
    }

    // Second: load more sessions only if projects are already expanded
    if (hasMore) {
      loadSessionsRef.current(false);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    sessions,
    hasMore,
    isLoading,
    isLoadingMore,
    isProjectsCollapsed,
    sidebarVisible,
    isChatsCollapsed,
  ]);

  // Initial load on mount / refresh
  useEffect(() => {
    loadSessions(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey]);

  // Clear loadingSkipRef after skip is updated to prevent duplicate requests
  useEffect(() => {
    loadingSkipRef.current = null;
  }, [skip]);

  return {
    sessions,
    isLoading,
    isLoadingMore,
    hasMore,
    error,
    loadSessions,
    loadMoreSessions,
    setSessions,
    scrollContainerRef,
    loadMoreRef,
  };
}

// ─── Single session operations ──────────────────────────────────────

interface UseSessionReturn {
  currentSession: BackendSession | null;
  isLoading: boolean;
  error: string | null;
  loadSession: (sessionId: string) => Promise<BackendSession | null>;
  deleteSession: (sessionId: string) => Promise<void>;
  switchSession: (sessionId: string | null) => void;
  clearError: () => void;
}

export function useSession(): UseSessionReturn {
  const [currentSession, setCurrentSession] = useState<BackendSession | null>(
    null,
  );
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadSession = useCallback(
    async (sessionId: string): Promise<BackendSession | null> => {
      setIsLoading(true);
      setError(null);

      try {
        const session = await sessionApi.get(sessionId);
        if (session) {
          setCurrentSession(session);
        }
        return session;
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load session");
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    [],
  );

  const deleteSession = useCallback(
    async (sessionId: string) => {
      try {
        await sessionApi.delete(sessionId);
        if (currentSession?.id === sessionId) {
          setCurrentSession(null);
        }
      } catch (err) {
        setError(
          err instanceof Error ? err.message : "Failed to delete session",
        );
      }
    },
    [currentSession],
  );

  const switchSession = useCallback(
    (sessionId: string | null) => {
      if (sessionId) {
        loadSession(sessionId);
      } else {
        setCurrentSession(null);
      }
    },
    [loadSession],
  );

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  return {
    currentSession,
    isLoading,
    error,
    loadSession,
    deleteSession,
    switchSession,
    clearError,
  };
}

// ─── Message history loader ─────────────────────────────────────────

interface UseMessageHistoryReturn {
  loadHistory: (sessionId: string) => Promise<void>;
  isLoading: boolean;
  error: string | null;
}

export function useMessageHistory(
  onHistoryLoaded: (session: BackendSession) => void,
): UseMessageHistoryReturn {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadHistory = useCallback(
    async (sessionId: string) => {
      setIsLoading(true);
      setError(null);

      try {
        const session = await sessionApi.get(sessionId);
        if (session) {
          onHistoryLoaded(session);
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Failed to load history");
      } finally {
        setIsLoading(false);
      }
    },
    [onHistoryLoaded],
  );

  return {
    loadHistory,
    isLoading,
    error,
  };
}
