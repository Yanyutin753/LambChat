import { useRef, useEffect, useCallback } from "react";
import { useNavigate, useParams, useLocation } from "react-router-dom";
import type { TabType } from "./types";
import { shouldBlockSessionSelection } from "../../../utils/sessionSelectionGuard";

interface UseSessionSyncOptions {
  activeTab: TabType;
  sessionId: string | null;
  loadHistory: (sessionId: string) => Promise<void>;
  clearMessages: () => void;
}

interface UseSessionSyncReturn {
  handleSelectSession: (selectedSessionId: string) => Promise<void>;
  handleNewSession: () => void;
}

interface SessionRouteSyncActionInput {
  activeTab: TabType;
  pathname: string;
  browserPathname?: string;
  sessionId: string | null;
  urlSessionId: string | undefined;
  externalNavigate: boolean;
}

interface SessionRouteSyncAction {
  type: "clear-external-state" | "replace-url";
  path: string;
}

export function shouldResetExternalNavigateFlag(
  locationState: { externalNavigate?: boolean } | null | undefined,
): boolean {
  return locationState?.externalNavigate === true;
}

export function isChatPath(pathname: string): boolean {
  return pathname === "/chat" || pathname.startsWith("/chat/");
}

export function getSessionRouteSyncAction({
  activeTab,
  pathname,
  browserPathname,
  sessionId,
  urlSessionId,
  externalNavigate,
}: SessionRouteSyncActionInput): SessionRouteSyncAction | null {
  const effectivePathname = browserPathname ?? pathname;

  if (activeTab !== "chat") {
    return externalNavigate
      ? { type: "clear-external-state", path: effectivePathname }
      : null;
  }

  if (externalNavigate) {
    return { type: "clear-external-state", path: effectivePathname };
  }

  // Guard against route transitions: if the current pathname is no longer a
  // chat route, never write a chat URL back into history from stale state.
  if (!isChatPath(effectivePathname)) {
    return null;
  }

  if (sessionId && sessionId !== urlSessionId) {
    return { type: "replace-url", path: `/chat/${sessionId}` };
  }

  if (!sessionId && urlSessionId) {
    return { type: "replace-url", path: "/chat" };
  }

  return null;
}

export function useSessionSync({
  activeTab,
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
  const selectSessionRequestIdRef = useRef(0);
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
    if (activeTab !== "chat") return;

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
    if (activeTab !== "chat") return;

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

    const action = getSessionRouteSyncAction({
      activeTab,
      pathname: locationPathRef.current,
      browserPathname:
        typeof window !== "undefined" ? window.location.pathname : undefined,
      sessionId,
      urlSessionId,
      externalNavigate: shouldResetExternalNavigateFlag(
        locationStateRef.current as { externalNavigate?: boolean } | null,
      ),
    });

    if (!action) {
      return;
    }

    if (action.type === "clear-external-state") {
      // Clear the externalNavigate flag using router navigation so the UI
      // stays in sync with the browser history state.
      navigate(action.path, { replace: true, state: null });
      return;
    }

    if (action.type === "replace-url") {
      isSyncingRef.current = true;
      navigate(action.path, { replace: true });
      scheduleSyncReset();
    }
  }, [activeTab, sessionId, urlSessionId, navigate, scheduleSyncReset]);

  // Handle session selection from sidebar
  const handleSelectSession = useCallback(
    async (selectedSessionId: string) => {
      const currentPathname =
        typeof window !== "undefined" ? window.location.pathname : "";

      if (shouldBlockSessionSelection(currentPathname)) {
        return;
      }

      try {
        const requestId = ++selectSessionRequestIdRef.current;
        isInternalNavRef.current = true;
        await loadHistory(selectedSessionId);

        const latestPathname =
          typeof window !== "undefined" ? window.location.pathname : "";

        if (
          requestId !== selectSessionRequestIdRef.current ||
          !isChatPath(latestPathname)
        ) {
          return;
        }

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
