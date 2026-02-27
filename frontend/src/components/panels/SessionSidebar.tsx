/**
 * Session sidebar component for displaying and managing chat history
 */

import { useEffect, useState, useCallback, useRef } from "react";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { Plus, Trash2, ChevronDown, X, Search, Loader2 } from "lucide-react";
import { useInView } from "react-intersection-observer";
import { sessionApi, type BackendSession } from "../../services/api";
import { useAuth } from "../../hooks/useAuth";
import { ConfirmDialog } from "../common/ConfirmDialog";

const PAGE_SIZE = 20;

interface SessionSidebarProps {
  currentSessionId: string | null;
  onSelectSession: (sessionId: string) => void;
  onNewSession: () => void;
  refreshKey?: number;
  newSession?: BackendSession | null;
  mobileOpen?: boolean;
  onMobileClose?: () => void;
  isCollapsed?: boolean;
  onToggleCollapsed?: (collapsed: boolean) => void;
  onShowProfile?: () => void;
}

export function SessionSidebar({
  currentSessionId,
  onSelectSession,
  onNewSession,
  refreshKey,
  newSession,
  mobileOpen = false,
  onMobileClose,
  isCollapsed: externalCollapsed,
  onToggleCollapsed,
  onShowProfile,
}: SessionSidebarProps) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const [sessions, setSessions] = useState<BackendSession[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [internalCollapsed, setInternalCollapsed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");

  // Use external state if provided, otherwise use internal state
  const isCollapsed = externalCollapsed ?? internalCollapsed;
  const setIsCollapsed = onToggleCollapsed ?? setInternalCollapsed;

  const [pullDistance, setPullDistance] = useState(0);
  const touchStartRef = useRef(0);
  const isPullingRef = useRef(false);
  const scrollContainerRef = useRef<HTMLDivElement | null>(null);

  const [hasMore, setHasMore] = useState(false);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [skip, setSkip] = useState(0);

  // Delete confirmation dialog state
  const [deleteConfirm, setDeleteConfirm] = useState<{
    isOpen: boolean;
    sessionId: string | null;
  }>({ isOpen: false, sessionId: null });

  const { ref: loadMoreRef, inView } = useInView({
    threshold: 0.1,
  });

  const loadSessions = async (reset = false) => {
    console.log("[loadSessions] reset:", reset, "current skip:", skip);
    if (reset) {
      setIsLoading(true);
      setSkip(0);
    } else {
      setIsLoadingMore(true);
    }
    setError(null);

    try {
      const currentSkip = reset ? 0 : skip;
      console.log(
        "[loadSessions] fetching with skip:",
        currentSkip,
        "limit:",
        PAGE_SIZE,
      );
      const response = await sessionApi.list({
        limit: PAGE_SIZE,
        skip: currentSkip,
        status: "active",
      });

      const sessions =
        "sessions" in response
          ? response.sessions
          : Array.isArray(response)
            ? response
            : [];
      const total = "total" in response ? response.total : sessions.length;
      const hasMore = "has_more" in response ? response.has_more : false;

      console.log(
        "[loadSessions] got",
        sessions.length,
        "sessions, total:",
        total,
        "hasMore:",
        hasMore,
      );

      if (reset) {
        setSessions(sessions);
      } else {
        setSessions((prev) => [...prev, ...sessions]);
      }
      const newSkip = currentSkip + sessions.length;
      console.log("[loadSessions] setting skip to:", newSkip);
      setSkip(newSkip);
      setHasMore(hasMore);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load sessions");
    } finally {
      setIsLoading(false);
      setIsLoadingMore(false);
    }
  };

  const loadMoreSessions = useCallback(() => {
    if (hasMore && !isLoadingMore && !isLoading) {
      loadSessions(false);
    }
  }, [hasMore, isLoadingMore, isLoading]);

  useEffect(() => {
    if (inView && hasMore && !isLoadingMore) {
      loadMoreSessions();
    }
  }, [inView, hasMore, isLoadingMore, loadMoreSessions]);

  const handleTouchStart = (e: React.TouchEvent) => {
    touchStartRef.current = e.touches[0].clientY;
    isPullingRef.current = true;
    console.log("[TouchStart] startY:", e.touches[0].clientY);
  };

  const handleTouchMove = (e: React.TouchEvent) => {
    console.log(
      "[TouchMove] isPulling:",
      isPullingRef.current,
      "isLoadingMore:",
      isLoadingMore,
    );
    if (!isPullingRef.current || isLoadingMore) return;
    const distance = e.touches[0].clientY - touchStartRef.current;
    console.log(
      "[TouchMove] distance:",
      distance,
      "currentY:",
      e.touches[0].clientY,
      "startY:",
      touchStartRef.current,
    );
    // 往上拉(distance < 0)才触发
    if (distance < 0) {
      setPullDistance(Math.min(Math.abs(distance), 80));
    } else {
      setPullDistance(0);
    }
  };

  const handleTouchEnd = () => {
    console.log("[TouchEnd] pullDistance:", pullDistance, "hasMore:", hasMore);
    if (pullDistance > 60 && hasMore && !isLoadingMore) {
      loadMoreSessions();
    }
    setPullDistance(0);
    isPullingRef.current = false;
  };

  // Mouse events for DevTools simulation
  const handleMouseDown = (e: React.MouseEvent) => {
    touchStartRef.current = e.clientY;
    isPullingRef.current = true;
    console.log("[MouseDown] startY:", e.clientY);
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    console.log(
      "[MouseMove] buttons:",
      e.buttons,
      "isPulling:",
      isPullingRef.current,
      "isLoadingMore:",
      isLoadingMore,
    );
    if (e.buttons !== 1) return;
    if (!isPullingRef.current || isLoadingMore) return;
    const distance = e.clientY - touchStartRef.current;
    console.log(
      "[MouseMove] distance:",
      distance,
      "currentY:",
      e.clientY,
      "startY:",
      touchStartRef.current,
    );
    // 往上拉(distance < 0)才触发
    if (distance < 0) {
      setPullDistance(Math.min(Math.abs(distance), 80));
    } else {
      setPullDistance(0);
    }
  };

  const handleMouseUp = () => {
    console.log("[MouseUp] pullDistance:", pullDistance, "hasMore:", hasMore);
    if (pullDistance > 60 && hasMore && !isLoadingMore) {
      loadMoreSessions();
    }
    setPullDistance(0);
    isPullingRef.current = false;
  };

  const deleteSession = async (sessionId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setDeleteConfirm({ isOpen: true, sessionId });
  };

  const confirmDeleteSession = async () => {
    const sessionId = deleteConfirm.sessionId;
    if (!sessionId) return;

    try {
      await sessionApi.delete(sessionId);
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
      if (currentSessionId === sessionId) {
        onNewSession();
      }
      toast.success(t("sidebar.sessionDeleted"));
    } catch (err) {
      console.error("Failed to delete session:", err);
      toast.error(t("sidebar.deleteFailed"));
    } finally {
      setDeleteConfirm({ isOpen: false, sessionId: null });
    }
  };

  useEffect(() => {
    loadSessions(true);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey]);

  useEffect(() => {
    if (newSession && newSession.id) {
      setSessions((prev) => {
        const existingIndex = prev.findIndex((s) => s.id === newSession.id);
        if (existingIndex >= 0) {
          // Update existing session (e.g., when title is generated)
          const updated = [...prev];
          updated[existingIndex] = { ...updated[existingIndex], ...newSession };
          return updated;
        }
        // Add new session
        return [newSession, ...prev];
      });
    }
  }, [newSession]);

  const getSessionTitle = (session: BackendSession) => {
    if (session.name) return session.name;
    const meta = session.metadata as Record<string, unknown>;
    if (meta?.title) return meta.title as string;
    return t("sidebar.newChat");
  };

  const filteredSessions = sessions.filter((session) => {
    if (!searchQuery.trim()) return true;
    const title = getSessionTitle(session).toLowerCase();
    return title.includes(searchQuery.toLowerCase());
  });

  const groupSessionsByTime = (sessionList: BackendSession[]) => {
    const groups: { label: string; sessions: BackendSession[] }[] = [];
    const today: BackendSession[] = [];
    const yesterday: BackendSession[] = [];
    const thisWeek: BackendSession[] = [];
    const older: BackendSession[] = [];

    const now = new Date();
    const todayStart = new Date(
      now.getFullYear(),
      now.getMonth(),
      now.getDate(),
    );
    const yesterdayStart = new Date(todayStart.getTime() - 24 * 60 * 60 * 1000);
    const weekStart = new Date(todayStart.getTime() - 7 * 24 * 60 * 60 * 1000);

    sessionList.forEach((session) => {
      const sessionDate = new Date(session.updated_at);
      if (sessionDate >= todayStart) {
        today.push(session);
      } else if (sessionDate >= yesterdayStart) {
        yesterday.push(session);
      } else if (sessionDate >= weekStart) {
        thisWeek.push(session);
      } else {
        older.push(session);
      }
    });

    if (today.length > 0)
      groups.push({ label: t("sidebar.today"), sessions: today });
    if (yesterday.length > 0)
      groups.push({ label: t("sidebar.yesterday"), sessions: yesterday });
    if (thisWeek.length > 0)
      groups.push({ label: t("sidebar.previous7Days"), sessions: thisWeek });
    if (older.length > 0)
      groups.push({ label: t("sidebar.older"), sessions: older });

    return groups;
  };

  const groupedSessions = groupSessionsByTime(filteredSessions);

  if (isCollapsed) {
    return null;
  }

  const sessionListContent = (
    <>
      {/* Header with brand */}
      <div className="flex items-center justify-between px-3 pt-4 pb-2 sm:px-4">
        <div className="flex h-8 items-center gap-2">
          <img
            src="/icons/icon.svg"
            alt="LambChat"
            className="size-6 rounded-full object-cover"
          />
          <span className="text-base font-bold text-gray-700 dark:text-stone-200">
            LambChat
          </span>
        </div>
        <button
          onClick={() => setIsCollapsed(true)}
          className="flex h-8 w-8 items-center justify-center rounded-lg hover:bg-gray-100 dark:hover:bg-stone-800 transition-colors"
          title={t("sidebar.collapseSidebar")}
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            className="w-5 h-5 text-gray-600 dark:text-stone-400"
          >
            <path
              fillRule="evenodd"
              clipRule="evenodd"
              d="M8.85719 3H15.1428C16.2266 2.99999 17.1007 2.99998 17.8086 3.05782C18.5375 3.11737 19.1777 3.24318 19.77 3.54497C20.7108 4.02433 21.4757 4.78924 21.955 5.73005C22.2568 6.32234 22.3826 6.96253 22.4422 7.69138C22.5 8.39925 22.5 9.27339 22.5 10.3572V13.6428C22.5 14.7266 22.5 15.6008 22.4422 16.3086C22.3826 17.0375 22.2568 17.6777 21.955 18.27C21.4757 19.2108 20.7108 19.9757 19.77 20.455C19.1777 20.7568 18.5375 20.8826 17.8086 20.9422C17.1008 21 16.2266 21 15.1428 21H8.85717C7.77339 21 6.89925 21 6.19138 20.9422C5.46253 20.8826 4.82234 20.7568 4.23005 20.455C3.28924 19.9757 2.52433 19.2108 2.04497 18.27C1.74318 17.6777 1.61737 17.0375 1.55782 16.3086C1.49998 15.6007 1.49999 14.7266 1.5 13.6428V10.3572C1.49999 9.27341 1.49998 8.39926 1.55782 7.69138C1.61737 6.96253 1.74318 6.32234 2.04497 5.73005C2.52433 4.78924 3.28924 4.02433 4.23005 3.54497C4.82234 3.24318 5.46253 3.11737 6.19138 3.05782C6.89926 2.99998 7.77341 2.99999 8.85719 3ZM6.35424 5.05118C5.74907 5.10062 5.40138 5.19279 5.13803 5.32698C4.57354 5.6146 4.1146 6.07354 3.82698 6.63803C3.69279 6.90138 3.60062 7.24907 3.55118 7.85424C3.50078 8.47108 3.5 9.26339 3.5 10.4V13.6C3.5 14.7366 3.50078 15.5289 3.55118 16.1458C3.60062 16.7509 3.69279 17.0986 3.82698 17.362C4.1146 17.9265 4.57354 18.3854 5.13803 18.673C5.40138 18.8072 5.74907 18.8994 6.35424 18.9488C6.97108 18.9992 7.76339 19 8.9 19H9.5V5H8.9C7.76339 5 6.97108 5.00078 6.35424 5.05118ZM11.5 5V19H15.1C16.2366 19 17.0289 18.9992 17.6458 18.9488C18.2509 18.8994 18.5986 18.8072 18.862 18.673C19.4265 18.3854 19.8854 17.9265 20.173 17.362C20.3072 17.0986 20.3994 16.7509 20.4488 16.1458C20.4992 15.5289 20.5 14.7366 20.5 13.6V10.4C20.5 9.26339 20.4992 8.47108 20.4488 7.85424C20.3994 7.24907 20.3072 6.90138 20.173 6.63803C19.8854 6.07354 19.4265 5.6146 18.862 5.32698C18.5986 5.19279 18.2509 5.10062 17.6458 5.05118C17.0289 5.00078 16.2366 5 15.1 5H11.5ZM5 8.5C5 7.94772 5.44772 7.5 6 7.5H7C7.55229 7.5 8 7.94772 8 8.5C8 9.05229 7.55229 9.5 7 9.5H6C5.44772 9.5 5 9.05229 5 8.5ZM5 12C5 11.4477 5.44772 11 6 11H7C7.55229 11 8 11.4477 8 12C8 12.5523 7.55229 13 7 13H6C5.44772 13 5 12.5523 5 12Z"
              fill="currentColor"
            />
          </svg>
        </button>
      </div>

      {/* New chat button */}
      <div className="px-2 pb-3">
        <button
          onClick={onNewSession}
          className="w-full flex items-center gap-2 rounded-lg border border-gray-200 dark:border-stone-700 px-3 py-2 text-sm text-gray-700 dark:text-stone-200 hover:bg-gray-50 dark:hover:bg-stone-800 transition-colors"
        >
          <Plus size={18} strokeWidth={2} />
          <span>{t("sidebar.newChat")}</span>
        </button>
      </div>

      {/* Search */}
      <div className="px-2 pb-2">
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-gray-100/80 dark:bg-stone-800/80">
          <Search
            size={14}
            className="flex-shrink-0 text-gray-400 dark:text-stone-500"
          />
          <input
            type="text"
            placeholder={t("common.search") + "..."}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="flex-1 min-w-0 text-sm bg-transparent text-gray-700 dark:text-stone-200 placeholder-gray-400 dark:placeholder-stone-500 focus:outline-none"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="flex-shrink-0 p-0.5 rounded text-gray-400 hover:text-gray-600 dark:text-stone-500 dark:hover:text-stone-300 transition-colors"
            >
              <X size={14} />
            </button>
          )}
        </div>
      </div>

      {/* Session list */}
      <div
        ref={scrollContainerRef}
        className="flex-1 overflow-y-auto px-2"
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      >
        {(pullDistance > 0 || isLoadingMore) && (
          <div
            className="flex items-center justify-center py-2 text-gray-400 dark:text-stone-500 transition-all"
            style={{ height: isLoadingMore ? 40 : pullDistance * 0.5 }}
          >
            {isLoadingMore ? (
              <Loader2 size={20} className="animate-spin" />
            ) : (
              <ChevronDown
                size={20}
                className={`transition-transform ${
                  pullDistance > 60 ? "rotate-180" : ""
                }`}
              />
            )}
          </div>
        )}
        {isLoading ? (
          <div className="flex items-center justify-center py-8">
            <div className="h-5 w-5 animate-spin rounded-full border-2 border-gray-200 dark:border-stone-700 border-t-gray-500 dark:border-t-stone-400" />
          </div>
        ) : error ? (
          <div className="py-6 text-center">
            <p className="text-sm text-gray-400 dark:text-stone-500">{error}</p>
            <button
              onClick={() => loadSessions(true)}
              className="mt-2 text-xs text-gray-500 dark:text-stone-400 hover:text-gray-700 dark:hover:text-stone-200"
            >
              {t("sidebar.retry")}
            </button>
          </div>
        ) : filteredSessions.length === 0 ? (
          <div className="py-8 text-center">
            <p className="text-sm text-gray-400 dark:text-stone-500">
              {searchQuery
                ? t("sidebar.noMatchingSessions")
                : t("sidebar.noSessions")}
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {groupedSessions.map((group) => (
              <div key={group.label}>
                <div className="px-2 py-1.5 text-xs font-medium text-gray-400 dark:text-stone-500">
                  {group.label}
                </div>
                <div className="space-y-0.5">
                  {group.sessions
                    .filter((session) => session.id)
                    .map((session) => (
                      <div
                        key={session.id}
                        onClick={() => {
                          onSelectSession(session.id);
                          onMobileClose?.();
                        }}
                        className={`group relative flex cursor-pointer items-center gap-2 rounded-lg px-2 py-2.5 transition-colors ${
                          currentSessionId === session.id
                            ? "bg-gray-100 dark:bg-stone-800"
                            : "hover:bg-gray-50 dark:hover:bg-stone-800/50"
                        }`}
                      >
                        <div className="min-w-0 flex-1">
                          <div className="truncate text-sm text-gray-700 dark:text-stone-200">
                            {getSessionTitle(session)}
                          </div>
                        </div>
                        <button
                          onClick={(e) => deleteSession(session.id, e)}
                          className="flex-shrink-0 rounded p-1 opacity-0 group-hover:opacity-100 hover:bg-gray-200 dark:hover:bg-stone-700 transition-all"
                          title={t("common.delete")}
                        >
                          <Trash2
                            size={14}
                            className="text-gray-400 hover:text-red-500 dark:text-stone-500 dark:hover:text-red-400"
                          />
                        </button>
                      </div>
                    ))}
                </div>
              </div>
            ))}
            <div ref={loadMoreRef} className="flex justify-center py-2">
              {isLoadingMore && (
                <div className="flex items-center gap-2 text-gray-400 dark:text-stone-500">
                  <Loader2 size={14} className="animate-spin" />
                  <span className="text-xs">{t("common.loading")}</span>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="border-t border-gray-100 dark:border-stone-800 px-2 py-1">
        <div
          onClick={onShowProfile}
          className="flex items-center gap-3 rounded-lg p-3 hover:bg-gray-50 dark:hover:bg-stone-800 transition-colors cursor-pointer"
        >
          {user?.avatar_url ? (
            <img
              src={user.avatar_url}
              alt={user?.username || "User"}
              className="size-6 rounded-full object-cover flex-shrink-0"
            />
          ) : (
            <div className="flex size-6 items-center justify-center rounded-full bg-gradient-to-br from-violet-500 to-purple-600 flex-shrink-0">
              <span className="text-base font-semibold text-white">
                {user?.username?.charAt(0).toUpperCase() || "U"}
              </span>
            </div>
          )}
          <div className="flex-1 min-w-0 space-y-1">
            <div className="text-sm font-semibold text-gray-900 dark:text-stone-100 truncate">
              {user?.username || "User"}
            </div>
          </div>
        </div>
      </div>
    </>
  );

  return (
    <>
      {mobileOpen && (
        <div className="fixed inset-0  sm:hidden" onClick={onMobileClose} />
      )}

      <div
        className={`rounded-r-lg fixed inset-y-0 left-0 z-50 w-64 flex flex-col transform bg-white dark:bg-stone-900 transition-transform duration-300 ease-in-out sm:hidden ${
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {sessionListContent}
      </div>

      <div className="hidden h-full w-64 flex-col rounded-r-lg border-r border-gray-200 dark:border-stone-800 bg-white dark:bg-stone-900 sm:flex">
        {sessionListContent}
      </div>

      {/* Delete Confirmation Dialog */}
      <ConfirmDialog
        isOpen={deleteConfirm.isOpen}
        title={t("sidebar.deleteSession")}
        message={t("sidebar.deleteConfirm")}
        confirmText={t("common.delete")}
        cancelText={t("common.cancel")}
        onConfirm={confirmDeleteSession}
        onCancel={() => setDeleteConfirm({ isOpen: false, sessionId: null })}
        variant="danger"
      />
    </>
  );
}
