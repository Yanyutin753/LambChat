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

  // Ref to store loadHistory to avoid stale closure in useEffect
  const loadHistoryRef = useRef(loadHistory);
  loadHistoryRef.current = loadHistory;

  // Use ref to store location pathname to avoid triggering on every render
  const locationPathRef = useRef(location.pathname);
  const locationStateRef = useRef(location.state);
  locationPathRef.current = location.pathname;
  locationStateRef.current = location.state;

  // Sync from URL only on initial mount
  useEffect(() => {
    if (urlSessionId && !isSyncingRef.current) {
      isSyncingRef.current = true;
      loadHistory(urlSessionId).finally(() => {
        // Delay reset to allow state to settle
        setTimeout(() => {
          isSyncingRef.current = false;
        }, 100);
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
    const externalNavigate = (
      locationStateRef.current as { externalNavigate?: boolean }
    )?.externalNavigate;
    if (externalNavigate) {
      // Clear the externalNavigate flag without triggering another navigation
      window.history.replaceState({}, "", locationPathRef.current);
      return;
    }

    if (sessionId && sessionId !== urlSessionId) {
      // New session created - update URL
      isSyncingRef.current = true;
      navigate(`/chat/${sessionId}`, { replace: true });
      setTimeout(() => {
        isSyncingRef.current = false;
      }, 100);
    } else if (!sessionId && urlSessionId) {
      // Session cleared - clear URL
      isSyncingRef.current = true;
      navigate("/chat", { replace: true });
      setTimeout(() => {
        isSyncingRef.current = false;
      }, 100);
    }
  }, [sessionId, urlSessionId, navigate]);

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
