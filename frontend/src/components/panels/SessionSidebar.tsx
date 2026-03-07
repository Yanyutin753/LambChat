/**
 * Session sidebar component for displaying and managing chat history
 */

import { useEffect, useState, useCallback, useRef } from "react";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { Plus, ChevronDown, X, Search, FolderPlus } from "lucide-react";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { useInView } from "react-intersection-observer";
import { sessionApi, folderApi, type BackendSession } from "../../services/api";
import { useAuth } from "../../hooks/useAuth";
import { ConfirmDialog } from "../common/ConfirmDialog";
import { FolderItem } from "../sidebar/FolderItem";
import { SessionItem } from "../sidebar/SessionItem";
import type { Folder } from "../../types";

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

  // Folder state
  const [folders, setFolders] = useState<Folder[]>([]);
  const [newFolderName, setNewFolderName] = useState("");
  const [showNewFolderModal, setShowNewFolderModal] = useState(false);
  const [isFoldersCollapsed, setIsFoldersCollapsed] = useState(true); // 默认收起

  const { ref: loadMoreRef, inView } = useInView({
    threshold: 0.1,
  });

  const loadSessions = async (reset = false) => {
    console.log("[loadSessions] reset:", reset, "current skip:", skip);
    // 防止在加载中或没有更多数据时重复请求
    if (!reset && (isLoading || isLoadingMore)) {
      console.log("[loadSessions] skipping - already loading or no more data");
      return;
    }
    if (!reset && !hasMore) {
      console.log("[loadSessions] skipping - no more data");
      return;
    }

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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasMore, isLoadingMore, isLoading]);

  // Load folders
  const loadFolders = async () => {
    try {
      const folderList = await folderApi.list();
      setFolders(folderList);
    } catch (err) {
      console.error("Failed to load folders:", err);
    }
  };

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
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (e.buttons !== 1) return;
    if (!isPullingRef.current || isLoadingMore) return;
    const distance = e.clientY - touchStartRef.current;
    // 往上拉(distance < 0)才触发
    if (distance < 0) {
      setPullDistance(Math.min(Math.abs(distance), 80));
    } else {
      setPullDistance(0);
    }
  };

  const handleMouseUp = () => {
    if (pullDistance > 60 && hasMore && !isLoadingMore) {
      loadMoreSessions();
    }
    setPullDistance(0);
    isPullingRef.current = false;
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

  // Folder operations
  const handleCreateFolder = async () => {
    const trimmedName = newFolderName.trim();
    if (!trimmedName) return;

    try {
      const newFolder = await folderApi.create({ name: trimmedName });
      setFolders((prev) => [...prev, newFolder]);
      setNewFolderName("");
      toast.success(t("sidebar.folderCreated"));
    } catch (err) {
      console.error("Failed to create folder:", err);
      toast.error(t("sidebar.folderCreateFailed"));
    }
  };

  const handleRenameFolder = (folderId: string, name: string) => {
    setFolders((prev) =>
      prev.map((f) => (f.id === folderId ? { ...f, name } : f)),
    );
  };

  const handleDeleteFolder = async (folderId: string) => {
    try {
      await folderApi.delete(folderId);
      setFolders((prev) => prev.filter((f) => f.id !== folderId));
      // Sessions in deleted folder become uncategorized (folder_id cleared on backend)
      // Refresh sessions to get updated folder assignments
      loadSessions(true);
      toast.success(t("sidebar.folderDeleted"));
    } catch (err) {
      console.error("Failed to delete folder:", err);
      toast.error(t("sidebar.folderDeleteFailed"));
    }
  };

  const handleMoveSession = async (
    sessionId: string,
    folderId: string | null,
  ) => {
    try {
      const response = await sessionApi.moveToFolder(sessionId, folderId);
      if (response.session) {
        setSessions((prev) =>
          prev.map((s) => (s.id === sessionId ? response.session : s)),
        );
        toast.success(
          folderId ? t("sidebar.sessionMoved") : t("sidebar.sessionRemoved"),
        );
      }
    } catch (err) {
      console.error("Failed to move session:", err);
      toast.error(t("sidebar.sessionMoveFailed"));
    }
  };

  const handleSessionUpdate = (updatedSession: BackendSession) => {
    setSessions((prev) =>
      prev.map((s) => (s.id === updatedSession.id ? updatedSession : s)),
    );
  };

  useEffect(() => {
    loadSessions(true);
    loadFolders();
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

  if (isCollapsed) {
    return null;
  }

  const sessionListContent = (
    <>
      {/* Header with brand */}
      <div className="flex items-center justify-between px-3 pt-4 pb-2 sm:px-4">
        <div className="flex h-6 items-center gap-2">
          <img
            src="/icons/icon.svg"
            alt="LambChat"
            className="size-6 rounded-full object-cover"
          />
          <a
            href="https://github.com/Yanyutin753/LambChat"
            target="_blank"
            rel="noopener noreferrer"
            className="text-base font-semibold leading-none text-gray-700 dark:text-stone-200 hover:text-gray-900 dark:hover:text-stone-400 transition-colors font-serif"
          >
            LambChat
          </a>
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
          className="w-full flex items-center gap-2 rounded-lg border border-stone-200 dark:border-stone-700 px-3 py-2 text-sm text-stone-700 dark:text-stone-200 hover:bg-stone-50 dark:hover:bg-stone-800 transition-colors"
        >
          <Plus size={18} strokeWidth={2} />
          <span>{t("sidebar.newChat")}</span>
        </button>
      </div>

      {/* Search */}
      <div className="px-2 pb-2">
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-stone-100/80 dark:bg-stone-800/80">
          <Search
            size={14}
            className="flex-shrink-0 text-stone-400 dark:text-stone-500"
          />
          <input
            type="text"
            placeholder={t("common.search") + "..."}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="flex-1 min-w-0 text-sm bg-transparent text-stone-700 dark:text-stone-200 placeholder:text-sm placeholder-stone-400 dark:placeholder-stone-500 focus:outline-none"
          />
          {searchQuery && (
            <button
              onClick={() => setSearchQuery("")}
              className="flex-shrink-0 p-0.5 rounded text-stone-400 hover:text-stone-600 dark:text-stone-500 dark:hover:text-stone-300 transition-colors"
            >
              <X size={12} />
            </button>
          )}
        </div>
      </div>

      {/* Session list with folders */}
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
              <LoadingSpinner size="sm" />
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
            <LoadingSpinner size="sm" />
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
        ) : filteredSessions.length === 0 && folders.length === 0 ? (
          <div className="py-8 text-center">
            <p className="text-sm text-gray-400 dark:text-stone-500">
              {searchQuery
                ? t("sidebar.noMatchingSessions")
                : t("sidebar.noSessions")}
            </p>
          </div>
        ) : (
          <div className="space-y-1">
            {/* Folder section header */}
            <div
              onClick={() => setIsFoldersCollapsed(!isFoldersCollapsed)}
              className="px-2 py-1.5 mt-1 flex justify-between items-center text-xs font-normal text-stone-400 dark:text-stone-500"
            >
              <h2>{t("sidebar.folders")}</h2>
              <ChevronDown
                size={12}
                className={`transition-transform duration-200 ${
                  isFoldersCollapsed ? "-rotate-90" : ""
                }`}
              />
            </div>

            {/* New folder button - only show when expanded */}
            {!isFoldersCollapsed && (
              <button
                onClick={() => setShowNewFolderModal(true)}
                className="group flex cursor-pointer items-center gap-2 rounded-md px-2 py-2 transition-all duration-150 hover:bg-stone-50 dark:hover:bg-stone-800/20"
              >
                <FolderPlus
                  size={16}
                  className="flex-shrink-0 text-stone-500 dark:text-stone-400"
                />
                <span className="text-sm text-stone-600 dark:text-stone-400">
                  {t("sidebar.newFolder")}
                </span>
              </button>
            )}

            {/* Favorites folder */}
            {!isFoldersCollapsed &&
              (() => {
                const favoritesFolder = folders.find(
                  (f) => f.type === "favorites",
                );
                if (!favoritesFolder) return null;
                const favoritesSessions = filteredSessions.filter(
                  (s) => s.metadata?.folder_id === favoritesFolder.id,
                );
                if (favoritesSessions.length === 0) return null;
                return (
                  <FolderItem
                    folder={favoritesFolder}
                    sessions={favoritesSessions}
                    currentSessionId={currentSessionId}
                    allFolders={folders}
                    onSelectSession={(sessionId) => {
                      onSelectSession(sessionId);
                      onMobileClose?.();
                    }}
                    onDeleteSession={(sessionId) => {
                      setDeleteConfirm({ isOpen: true, sessionId });
                    }}
                    onMoveSession={handleMoveSession}
                    onSessionUpdate={handleSessionUpdate}
                    onRenameFolder={handleRenameFolder}
                    onDeleteFolder={handleDeleteFolder}
                  />
                );
              })()}

            {/* Custom folders */}
            {!isFoldersCollapsed &&
              folders
                .filter((f) => f.type === "custom")
                .sort((a, b) => a.sort_order - b.sort_order)
                .map((folder) => {
                  const folderSessions = filteredSessions.filter(
                    (s) => s.metadata?.folder_id === folder.id,
                  );
                  return (
                    <FolderItem
                      key={folder.id}
                      folder={folder}
                      sessions={folderSessions}
                      currentSessionId={currentSessionId}
                      allFolders={folders}
                      onSelectSession={(sessionId) => {
                        onSelectSession(sessionId);
                        onMobileClose?.();
                      }}
                      onDeleteSession={(sessionId) => {
                        setDeleteConfirm({ isOpen: true, sessionId });
                      }}
                      onMoveSession={handleMoveSession}
                      onSessionUpdate={handleSessionUpdate}
                      onRenameFolder={handleRenameFolder}
                      onDeleteFolder={handleDeleteFolder}
                    />
                  );
                })}

            {/* Uncategorized sessions (by time) */}
            {(() => {
              const uncategorizedSessions = filteredSessions.filter(
                (s) => !s.metadata?.folder_id,
              );
              if (uncategorizedSessions.length === 0) return null;
              const groupedUncategorized = groupSessionsByTime(
                uncategorizedSessions,
              );
              return groupedUncategorized.map((group) => (
                <div key={group.label}>
                  <div className="px-2 py-1.5 mt-1 text-xs font-normal text-stone-400 dark:text-stone-500">
                    {group.label}
                  </div>
                  <div className="space-y-0.5">
                    {group.sessions
                      .filter((session) => session.id)
                      .map((session) => (
                        <SessionItem
                          key={session.id}
                          session={session}
                          isActive={currentSessionId === session.id}
                          folders={folders}
                          onSelect={() => {
                            onSelectSession(session.id);
                            onMobileClose?.();
                          }}
                          onDelete={() =>
                            setDeleteConfirm({
                              isOpen: true,
                              sessionId: session.id,
                            })
                          }
                          onMoveToFolder={(folderId) =>
                            handleMoveSession(session.id, folderId)
                          }
                          onSessionUpdate={handleSessionUpdate}
                          isFavorite={false}
                        />
                      ))}
                  </div>
                </div>
              ));
            })()}

            <div ref={loadMoreRef} className="flex justify-center py-2">
              {isLoadingMore && (
                <div className="flex items-center gap-2 text-gray-400 dark:text-stone-500">
                  <LoadingSpinner size="xs" />
                  <span className="text-xs">{t("common.loading")}</span>
                </div>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="border-t border-stone-100 dark:border-stone-800 px-2 py-1.5">
        <div
          onClick={onShowProfile}
          className="flex items-center gap-2.5 rounded-lg px-2 py-2 hover:bg-stone-50 dark:hover:bg-stone-800 transition-colors cursor-pointer"
        >
          {user?.avatar_url ? (
            <img
              src={user.avatar_url}
              alt={user?.username || "User"}
              className="size-7 rounded-full object-cover flex-shrink-0"
            />
          ) : (
            <div className="flex size-7 items-center justify-center rounded-full bg-gradient-to-br from-stone-500 to-stone-700 flex-shrink-0">
              <span className="text-xs font-semibold text-white">
                {user?.username?.charAt(0).toUpperCase() || "U"}
              </span>
            </div>
          )}
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium text-stone-700 dark:text-stone-200 truncate">
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

      {/* New Folder Modal */}
      {showNewFolderModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div
            className="absolute inset-0 bg-black/50"
            onClick={() => setShowNewFolderModal(false)}
          />
          <div className="relative bg-white dark:bg-stone-800 rounded-lg shadow-xl p-4 w-80 max-w-[90vw]">
            <h3 className="text-sm font-medium text-stone-700 dark:text-stone-200 mb-1">
              {t("sidebar.newFolder")}
            </h3>
            <p className="text-xs text-stone-400 dark:text-stone-500 mb-3">
              {t("sidebar.folderHint")}
            </p>
            <input
              ref={(el) => {
                if (el) el.focus();
              }}
              type="text"
              value={newFolderName}
              onChange={(e) => setNewFolderName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  handleCreateFolder();
                  setShowNewFolderModal(false);
                }
                if (e.key === "Escape") {
                  setShowNewFolderModal(false);
                  setNewFolderName("");
                }
              }}
              placeholder={t("sidebar.folderName")}
              className="w-full px-3 py-2 text-sm rounded-lg border border-stone-200 dark:border-stone-600 bg-white dark:bg-stone-700 text-stone-700 dark:text-stone-200 placeholder-stone-400 focus:outline-none focus:ring-2 focus:ring-stone-400"
            />
            <div className="flex justify-end gap-2 mt-4">
              <button
                onClick={() => {
                  setShowNewFolderModal(false);
                  setNewFolderName("");
                }}
                className="px-3 py-1.5 text-sm text-stone-600 dark:text-stone-400 hover:text-stone-800 dark:hover:text-stone-200 transition-colors"
              >
                {t("common.cancel")}
              </button>
              <button
                onClick={() => {
                  handleCreateFolder();
                  setShowNewFolderModal(false);
                }}
                disabled={!newFolderName.trim()}
                className="px-3 py-1.5 text-sm bg-stone-600 text-white rounded-lg hover:bg-stone-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                {t("common.create")}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
