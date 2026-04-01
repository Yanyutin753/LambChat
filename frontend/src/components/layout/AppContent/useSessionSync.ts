import { useRef, useEffect, useCallback } from "react";
import { useNavigate, useParams, useLocation } from "react-router-dom";

interface UseSessionSyncOptions {
  sessionId: string | null;
  loadHistory: (sessionId: string) => Promise<void>;
  clearMessages: () => void;
}

interface UseSessionSyncReturn {
  handleSelectSession: (selectedSessionId: string) => Promise<void>;
  handleNewSession: () => void;
}

export function shouldResetExternalNavigateFlag(
  locationState: { externalNavigate?: boolean } | null | undefined,
): boolean {
  return locationState?.externalNavigate === true;
}

export function useSessionSync({
  sessionId,
  loadHistory,
  clearMessages,
}: UseSessionSyncOptions): UseSessionSyncReturn {
  const { sessionId: urlSessionId } = useParams<{ sessionId?: string }>();
  const location = useLocation();
  const navigate = useNavigate();

  // Session sync state - controlled by single ref to prevent sync loops
  const isSyncingRef = useRef(false);
  // Track if navigation was initiated internally (not from URL)
  const isInternalNavRef = useRef(false);
  const isLoadingRef = useRef(false);
  // Track a single sync delay timeout for cleanup on unmount
  const syncTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Ref to store loadHistory to avoid stale closure in useEffect
  const loadHistoryRef = useRef(loadHistory);
  loadHistoryRef.current = loadHistory;

  // Use ref to store location pathname to avoid triggering on every render
  const locationPathRef = useRef(location.pathname);
  const locationStateRef = useRef(location.state);
  locationPathRef.current = location.pathname;
  locationStateRef.current = location.state;

  // Cleanup tracked timeouts on unmount
  useEffect(() => {
    return () => {
      if (syncTimeoutRef.current) {
        clearTimeout(syncTimeoutRef.current);
        syncTimeoutRef.current = null;
      }
    };
  }, []);

  const scheduleSyncReset = useCallback(() => {
    if (syncTimeoutRef.current) {
      clearTimeout(syncTimeoutRef.current);
    }
    syncTimeoutRef.current = setTimeout(() => {
      isSyncingRef.current = false;
      syncTimeoutRef.current = null;
    }, 100);
  }, []);

  // Sync from URL only on initial mount
  useEffect(() => {
    if (urlSessionId && !isSyncingRef.current) {
      isSyncingRef.current = true;
      loadHistory(urlSessionId).finally(() => {
        scheduleSyncReset();
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []); // Only run on mount

  // Load session when URL changes (e.g., from toast click)
  useEffect(() => {
    // Skip if sessionId is null (new session being created, handled by clearMessages)
    if (!sessionId) return;

    // Skip if urlSessionId is null/undefined (no session in URL)
    if (!urlSessionId) return;

    // Skip if already loading or if sessionId matches URL (no need to reload)
    if (isLoadingRef.current || sessionId === urlSessionId) return;

    // Skip if this was an internal navigation (handled by handleSelectSession)
    if (isInternalNavRef.current) {
      isInternalNavRef.current = false;
      return;
    }

    isLoadingRef.current = true;
    loadHistoryRef.current(urlSessionId).finally(() => {
      isLoadingRef.current = false;
    });
  }, [urlSessionId, sessionId]);

  // Sync URL with sessionId state (when sessionId changes from internal actions)
  useEffect(() => {
    if (isSyncingRef.current) return;

    // Skip sync if this navigation was initiated externally (e.g., from toast click)
    if (
      shouldResetExternalNavigateFlag(
        locationStateRef.current as { externalNavigate?: boolean } | null,
      )
    ) {
      // Clear the externalNavigate flag using router navigation so the UI
      // stays in sync with the browser history state.
      navigate(locationPathRef.current, { replace: true, state: null });
      return;
    }

    // Skip sync if we're not on a chat route (urlSessionId is undefined/null
    // but sessionId exists - means user navigated to another page like /skills)
    if (!urlSessionId && sessionId) return;

    if (sessionId && sessionId !== urlSessionId) {
      // New session created - update URL
      isSyncingRef.current = true;
      navigate(`/chat/${sessionId}`, { replace: true });
      scheduleSyncReset();
    } else if (!sessionId && urlSessionId) {
      // Session cleared - clear URL
      isSyncingRef.current = true;
      navigate("/chat", { replace: true });
      scheduleSyncReset();
    }
  }, [sessionId, urlSessionId, navigate, scheduleSyncReset]);

  // Handle session selection from sidebar
  const handleSelectSession = useCallback(
    async (selectedSessionId: string) => {
      try {
        isInternalNavRef.current = true;
        await loadHistory(selectedSessionId);
        // Update URL
        navigate(`/chat/${selectedSessionId}`);
        // Scroll to top after loading history
        window.scrollTo({ top: 0, behavior: "smooth" });
      } catch (err) {
        console.error("[handleSelectSession] Error:", err);
      }
    },
    [navigate, loadHistory],
  );

  // Handle new session - just clear messages, URL sync is handled by useEffect
  const handleNewSession = useCallback(() => {
    isInternalNavRef.current = false;
    clearMessages();
  }, [clearMessages]);

  return {
    handleSelectSession,
    handleNewSession,
  };
}
