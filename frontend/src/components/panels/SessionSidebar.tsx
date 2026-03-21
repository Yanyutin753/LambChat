/**
 * Session sidebar component for displaying and managing chat history
 */

import { useState, useEffect, useRef, useCallback } from "react";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { Plus, ChevronDown, X, Search, FolderPlus } from "lucide-react";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { sessionApi, type BackendSession } from "../../services/api";
import { useAuth } from "../../hooks/useAuth";
import { useSessionList } from "../../hooks/useSession";
import { useProjectManager } from "../../hooks/useProjectManager";
import { APP_NAME } from "../../constants";
import { useTouchDrag } from "../../hooks/useTouchDrag";
import { ConfirmDialog } from "../common/ConfirmDialog";
import { ProjectItem } from "../sidebar/ProjectItem";
import { SessionItem } from "../sidebar/SessionItem";
import { getSessionTitle, groupSessionsByTime } from "./sessionHelpers";

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
  const [searchQuery, setSearchQuery] = useState("");
  const [imgError, setImgError] = useState(false);
  const [internalCollapsed, setInternalCollapsed] = useState(true);
  const [isProjectsCollapsed, setIsProjectsCollapsed] = useState(true);

  const isCollapsed = externalCollapsed ?? internalCollapsed;
  const setIsCollapsed = onToggleCollapsed ?? setInternalCollapsed;

  // ─── Hooks ──────────────────────────────────────────────────────

  const {
    sessions,
    setSessions,
    isLoading,
    isLoadingMore,
    hasMore,
    error,
    loadSessions,
    loadMoreSessions,
    scrollContainerRef,
    loadMoreRef,
  } = useSessionList(
    refreshKey,
    isProjectsCollapsed,
    setIsProjectsCollapsed,
    mobileOpen,
  );

  const projectManager = useProjectManager();

  // Keep a ref to handleMoveSession for the touch drag hook
  const handleMoveSession = useCallback(
    async (sessionId: string, projectId: string | null) => {
      try {
        const response = await sessionApi.moveToProject(sessionId, projectId);
        if (response.session) {
          setSessions((prev) =>
            prev.map((s) => (s.id === sessionId ? response.session : s)),
          );
        }
      } catch (err) {
        console.error("Failed to move session:", err);
        toast.error(t("sidebar.sessionMoveFailed"));
      }
    },
    [setSessions, t],
  );

  const handleMoveSessionRef = useRef(handleMoveSession);
  handleMoveSessionRef.current = handleMoveSession;

  const touchDrag = useTouchDrag(sessions, (sessionId, projectId) => {
    handleMoveSessionRef.current(sessionId, projectId);
  });

  // ─── Pull-to-refresh ────────────────────────────────────────────

  const [pullDistance, setPullDistance] = useState(0);
  const touchStartRef = useRef(0);
  const isPullingRef = useRef(false);

  const handleTouchStart = (e: React.TouchEvent) => {
    if (touchDrag.draggingSessionId) return;
    touchStartRef.current = e.touches[0].clientY;
    isPullingRef.current = true;
  };

  const handleTouchMove = (e: React.TouchEvent) => {
    if (touchDrag.draggingSessionId) return;
    if (!isPullingRef.current || isLoadingMore) return;
    const distance = e.touches[0].clientY - touchStartRef.current;
    if (distance < 0) {
      setPullDistance(Math.min(Math.abs(distance), 80));
    } else {
      setPullDistance(0);
    }
  };

  const handleTouchEnd = () => {
    if (touchDrag.draggingSessionId) return;
    if (pullDistance > 60 && hasMore && !isLoadingMore) {
      loadMoreSessions();
    }
    setPullDistance(0);
    isPullingRef.current = false;
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    touchStartRef.current = e.clientY;
    isPullingRef.current = true;
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (e.buttons !== 1) return;
    if (!isPullingRef.current || isLoadingMore) return;
    const distance = e.clientY - touchStartRef.current;
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

  // ─── Delete confirmation ────────────────────────────────────────

  const [deleteConfirm, setDeleteConfirm] = useState<{
    isOpen: boolean;
    sessionId: string | null;
  }>({ isOpen: false, sessionId: null });

  const confirmDeleteSession = async () => {
    const sessionId = deleteConfirm.sessionId;
    if (!sessionId) return;
    try {
      await sessionApi.delete(sessionId);
      setSessions((prev) => prev.filter((s) => s.id !== sessionId));
      if (currentSessionId === sessionId) onNewSession();
      toast.success(t("sidebar.sessionDeleted"));
    } catch (err) {
      console.error("Failed to delete session:", err);
      toast.error(t("sidebar.deleteFailed"));
    } finally {
      setDeleteConfirm({ isOpen: false, sessionId: null });
    }
  };

  // ─── Effects ────────────────────────────────────────────────────

  // Load projects on mount / refresh
  useEffect(() => {
    projectManager.loadProjects();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey]);

  // Handle new / updated session from parent
  useEffect(() => {
    if (newSession && newSession.id) {
      setSessions((prev) => {
        const existingIndex = prev.findIndex((s) => s.id === newSession.id);
        if (existingIndex >= 0) {
          const updated = [...prev];
          updated[existingIndex] = { ...updated[existingIndex], ...newSession };
          return updated;
        }
        return [newSession, ...prev];
      });
    }
  }, [newSession, setSessions]);

  // ─── Derived data ───────────────────────────────────────────────

  const handleSessionUpdate = (updatedSession: BackendSession) => {
    setSessions((prev) =>
      prev.map((s) => (s.id === updatedSession.id ? updatedSession : s)),
    );
  };

  const filteredSessions = sessions.filter((session) => {
    if (!searchQuery.trim()) return true;
    const title = getSessionTitle(session, t).toLowerCase();
    return title.includes(searchQuery.toLowerCase());
  });

  // ─── Select session helper (mobile close) ───────────────────────

  const selectAndClose = (sessionId: string) => {
    onSelectSession(sessionId);
    onMobileClose?.();
  };

  const { projects } = projectManager;

  // ─── JSX ────────────────────────────────────────────────────────

  const sessionListContent = (
    <>
      {/* Header */}
      <div className="flex items-center justify-between px-3 pt-3 pb-2 sm:px-4">
        <div className="flex h-7 items-center gap-2">
          <img
            src="/icons/icon.svg"
            alt={APP_NAME}
            className="size-6 rounded-full object-cover ring-1 ring-stone-200 dark:ring-stone-700"
          />
          <a
            href="https://github.com/Yanyutin753/LambChat"
            target="_blank"
            rel="noopener noreferrer"
            className="text-md font-semibold leading-none text-stone-800 dark:text-stone-100 hover:text-stone-900 dark:hover:text-stone-50 transition-colors font-serif"
          >
            {APP_NAME}
          </a>
        </div>
        <button
          onClick={() => {
            setIsCollapsed(true);
            onMobileClose?.();
          }}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-stone-500 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-stone-800 hover:text-stone-700 dark:hover:text-stone-300 transition-all duration-150"
          title={t("sidebar.collapseSidebar")}
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            className="w-5 h-5"
          >
            <path
              fillRule="evenodd"
              clipRule="evenodd"
              d="M8.85719 3H15.1428C16.2266 2.99999 17.1007 2.99998 17.8086 3.05782C18.5375 3.11737 19.1777 3.24318 19.77 3.54497C20.7108 4.02433 21.4757 4.78924 21.955 5.73005C22.2568 6.32234 22.3826 6.96253 22.4422 7.69138C22.5 8.39925 22.5 9.27339 22.5 10.3572V13.6428C22.5 14.7266 22.5 15.6008 22.4422 16.3086C22.3826 17.0375 22.2568 17.6777 21.955 18.27C21.4757 19.2108 20.7108 19.9757 19.77 20.455C19.1777 20.7568 18.5375 20.8826 17.8086 20.9422C17.1008 21 16.2266 21 15.1428 21H8.85717C7.77339 21 6.89925 21 6.19138 20.9422C5.46253 20.8826 4.82234 20.7568 4.23005 20.455C3.28924 19.9757 2.52433 19.2108 2.04497 18.27C1.74318 17.6777 1.61737 17.0375 1.55782 16.3086C1.49998 15.6007 1.49999 14.7266 1.5 13.6428V10.3572C1.49999 9.27341 1.49998 8.39926 1.55782 7.69138C1.61737 6.46253 1.74318 6.32234 2.04497 5.73005C2.52433 4.78924 3.28924 4.02433 4.23005 3.54497C4.82234 3.24318 5.46253 3.11737 6.19138 3.05782C6.89926 2.99998 7.77341 2.99999 8.85719 3ZM6.35424 5.05118C5.74907 5.10062 5.40138 5.19279 5.13803 5.32698C4.57354 5.6146 4.1146 6.07354 3.82698 6.63803C3.69279 6.90138 3.60062 7.24907 3.55118 7.85424C3.50078 8.47108 3.5 9.26339 3.5 10.4V13.6C3.5 14.7366 3.50078 15.5289 3.55118 16.1458C3.60062 16.7509 3.69279 17.0986 3.82698 17.362C4.1146 17.9265 4.57354 18.3854 5.13803 18.673C5.40138 18.8072 5.74907 18.8994 6.35424 18.9488C6.97108 18.9992 7.76339 19 8.9 19H9.5V5H8.9C7.76339 5 6.97108 5.00078 6.35424 5.05118ZM11.5 5V19H15.1C16.2366 19 17.0289 18.9992 17.6458 18.9488C18.2509 18.8994 18.5986 18.8072 18.862 18.673C19.4265 18.3854 19.8854 17.9265 20.173 17.362C20.3072 17.0986 20.3994 16.7509 20.4488 16.1458C20.4992 15.5289 20.5 14.7366 20.5 13.6V10.4C20.5 9.26339 20.4992 8.47108 20.4488 7.85424C20.3994 7.24907 20.3072 6.90138 20.173 6.63803C19.8854 6.07354 19.4265 5.6146 18.862 5.32698C18.5986 5.19279 18.2509 5.10062 17.6458 5.05118C17.0289 5.00078 16.2366 5 15.1 5H11.5ZM5 8.5C5 7.94772 5.44772 7.5 6 7.5H7C7.55229 7.5 8 7.94772 8 8.5C8 9.05229 7.55229 9.5 7 9.5H6C5.44772 9.5 5 9.05229 5 8.5ZM5 12C5 11.4477 5.44772 11 6 11H7C7.55229 11 8 11.4477 8 12C8 12.5523 7.55229 13 7 13H6C5.44772 13 5 12.5523 5 12Z"
              fill="currentColor"
            />
          </svg>
        </button>
      </div>

      {/* New chat button */}
      <div className="px-2 pb-2">
        <button
          onClick={onNewSession}
          className="w-full flex items-center gap-2.5 rounded-xl border border-stone-200 dark:border-stone-700/60 bg-stone-50/80 dark:bg-stone-800/40 px-3 py-2.5 text-sm font-medium text-stone-700 dark:text-stone-200 hover:bg-stone-100 dark:hover:bg-stone-700/50 hover:border-stone-300 dark:hover:border-stone-600 transition-all duration-150 active:scale-[0.98]"
        >
          <Plus size={16} strokeWidth={2.5} />
          <span>{t("sidebar.newChat")}</span>
        </button>
      </div>

      {/* Search */}
      <div className="px-2 pb-2">
        <div className="flex items-center gap-2 px-3 py-2 rounded-lg bg-stone-100/60 dark:bg-stone-800/50 border border-transparent focus-within:border-stone-300 dark:focus-within:border-stone-600 transition-colors">
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

      {/* Session list */}
      <div
        ref={scrollContainerRef}
        data-sidebar-scroll
        className="flex-1 overflow-y-auto px-2 scrollbar-thin"
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
        ) : filteredSessions.length === 0 && projects.length === 0 ? (
          <div className="py-8 text-center">
            <p className="text-sm text-gray-400 dark:text-stone-500">
              {searchQuery
                ? t("sidebar.noMatchingSessions")
                : t("sidebar.noSessions")}
            </p>
          </div>
        ) : (
          <div className="space-y-1">
            {/* Project section header */}
            <div
              onClick={() => setIsProjectsCollapsed(!isProjectsCollapsed)}
              className="px-2 py-1.5 mt-1 flex justify-between items-center text-xs font-medium uppercase tracking-wider text-stone-400 dark:text-stone-500 hover:text-stone-500 dark:hover:text-stone-400 cursor-pointer transition-colors select-none"
            >
              <h2>{t("sidebar.projects")}</h2>
              <ChevronDown
                size={12}
                className={`transition-transform duration-200 ${
                  isProjectsCollapsed ? "-rotate-90" : ""
                }`}
              />
            </div>

            {/* New project button */}
            {!isProjectsCollapsed && (
              <button
                onClick={() => projectManager.setShowNewProjectModal(true)}
                className="group flex w-full cursor-pointer items-center gap-2 rounded-lg px-2 py-2 transition-all duration-150 hover:bg-stone-100 dark:hover:bg-stone-800/30"
              >
                <FolderPlus
                  size={15}
                  className="flex-shrink-0 text-stone-400 dark:text-stone-500 group-hover:text-stone-500 dark:group-hover:text-stone-400 transition-colors"
                />
                <span className="text-sm text-stone-500 dark:text-stone-400 group-hover:text-stone-600 dark:group-hover:text-stone-300 transition-colors">
                  {t("sidebar.newProject")}
                </span>
              </button>
            )}

            {/* Favorites project */}
            {!isProjectsCollapsed &&
              (() => {
                const favoritesProject = projects.find(
                  (p) => p.type === "favorites",
                );
                if (!favoritesProject) return null;
                const favoritesSessions = filteredSessions.filter(
                  (s) => s.metadata?.project_id === favoritesProject.id,
                );
                if (favoritesSessions.length === 0) return null;
                return (
                  <ProjectItem
                    project={favoritesProject}
                    sessions={favoritesSessions}
                    currentSessionId={currentSessionId}
                    allProjects={projects}
                    onSelectSession={selectAndClose}
                    onDeleteSession={(sessionId) => {
                      setDeleteConfirm({ isOpen: true, sessionId });
                    }}
                    onMoveSession={handleMoveSession}
                    onSessionUpdate={handleSessionUpdate}
                    onRenameProject={projectManager.handleRenameProject}
                    onDeleteProject={(id) =>
                      projectManager.handleDeleteProject(id, () =>
                        loadSessions(true),
                      )
                    }
                    draggingSessionId={
                      touchDrag.touchDropTarget === favoritesProject.id
                        ? touchDrag.draggingSessionId
                        : null
                    }
                  />
                );
              })()}

            {/* Custom projects */}
            {!isProjectsCollapsed &&
              projects
                .filter((p) => p.type === "custom")
                .sort((a, b) => a.sort_order - b.sort_order)
                .map((project) => {
                  const projectSessions = filteredSessions.filter(
                    (s) => s.metadata?.project_id === project.id,
                  );
                  return (
                    <ProjectItem
                      key={project.id}
                      project={project}
                      sessions={projectSessions}
                      currentSessionId={currentSessionId}
                      allProjects={projects}
                      onSelectSession={selectAndClose}
                      onDeleteSession={(sessionId) => {
                        setDeleteConfirm({ isOpen: true, sessionId });
                      }}
                      onMoveSession={handleMoveSession}
                      onSessionUpdate={handleSessionUpdate}
                      onRenameProject={projectManager.handleRenameProject}
                      onDeleteProject={(id) =>
                        projectManager.handleDeleteProject(id, () =>
                          loadSessions(true),
                        )
                      }
                      draggingSessionId={
                        touchDrag.touchDropTarget === project.id
                          ? touchDrag.draggingSessionId
                          : null
                      }
                    />
                  );
                })}

            {/* Uncategorized sessions (by time) */}
            {(() => {
              const uncategorizedSessions = filteredSessions.filter(
                (s) => !s.metadata?.project_id,
              );
              if (uncategorizedSessions.length === 0) return null;
              const groupedUncategorized = groupSessionsByTime(
                uncategorizedSessions,
                t,
              );
              return groupedUncategorized.map((group) => (
                <div key={group.label}>
                  <div className="px-2 py-1.5 mt-1 text-xs font-medium uppercase tracking-wider text-stone-400 dark:text-stone-500 select-none">
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
                          projects={projects}
                          onSelect={() => selectAndClose(session.id)}
                          onDelete={() =>
                            setDeleteConfirm({
                              isOpen: true,
                              sessionId: session.id,
                            })
                          }
                          onMoveToProject={(projectId) =>
                            handleMoveSession(session.id, projectId)
                          }
                          onSessionUpdate={handleSessionUpdate}
                          isFavorite={false}
                          onDragStartTouch={touchDrag.handleDragStartTouch}
                          isDraggingTouch={
                            touchDrag.draggingSessionId === session.id
                          }
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
      <div className="border-t border-stone-100 dark:border-stone-800/80 px-2 py-1.5">
        <div
          onClick={onShowProfile}
          className="flex items-center gap-2.5 rounded-lg px-2 py-2 hover:bg-stone-100 dark:hover:bg-stone-800/50 transition-colors cursor-pointer"
        >
          {user?.avatar_url && !imgError ? (
            <img
              src={user.avatar_url}
              alt={user?.username || "User"}
              className="size-7 rounded-full object-cover flex-shrink-0 ring-1 ring-stone-200 dark:ring-stone-700"
              onError={() => setImgError(true)}
            />
          ) : (
            <div className="flex size-6 items-center justify-center bg-gradient-to-br from-stone-500 to-stone-700 rounded-full">
              <span className="text-xs font-semibold text-white">
                {user?.username?.charAt(0).toUpperCase() || "U"}
              </span>
            </div>
          )}
          <div className="flex-1 min-w-0">
            <div className="text-sm font-medium text-stone-700 dark:text-stone-200 capitalize truncate">
              {user?.username || "User"}
            </div>
          </div>
        </div>
      </div>
    </>
  );

  return (
    <>
      {/* Mobile backdrop */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-[60] bg-black/40 sm:hidden"
          onClick={onMobileClose}
        />
      )}

      {/* Mobile sidebar */}
      <div
        className={`rounded-r-lg fixed inset-y-0 left-0 z-[70] w-64 flex flex-col bg-white dark:bg-stone-900 sm:hidden ${
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        } transition-transform duration-300 ease-in-out`}
      >
        {sessionListContent}
      </div>

      {/* Desktop sidebar */}
      {!isCollapsed && (
        <div className="hidden h-full w-64 flex-col rounded-r-lg border-r border-stone-200 dark:border-stone-800 bg-white dark:bg-stone-900 sm:flex">
          {sessionListContent}
        </div>
      )}

      {/* Mobile drag indicator */}
      {touchDrag.dragIndicatorPos && (
        <div
          className="fixed z-[100] pointer-events-none px-3 py-1.5 rounded-lg bg-stone-700 dark:bg-stone-200 text-white dark:text-stone-800 text-xs shadow-lg max-w-[200px] truncate"
          style={{
            left: touchDrag.dragIndicatorPos.x - 20,
            top: touchDrag.dragIndicatorPos.y - 40,
          }}
        >
          {touchDrag.dragIndicatorTitle}
        </div>
      )}

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

      {/* New Project Modal */}
      {projectManager.showNewProjectModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          <div
            className="absolute inset-0 bg-black/40 backdrop-blur-sm"
            onClick={() => projectManager.setShowNewProjectModal(false)}
          />
          <div className="relative bg-white dark:bg-stone-800 rounded-xl shadow-2xl p-5 w-[90vw] max-w-md space-y-3">
            <h3 className="text-sm font-semibold text-stone-800 dark:text-stone-100">
              {t("sidebar.newProject")}
            </h3>
            <p className="text-xs text-stone-400 dark:text-stone-500">
              {t("sidebar.projectHint")}
            </p>
            <input
              ref={(el) => {
                if (el) el.focus();
              }}
              type="text"
              value={projectManager.newProjectName}
              onChange={(e) => projectManager.setNewProjectName(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  projectManager.handleCreateProject();
                  projectManager.setShowNewProjectModal(false);
                }
                if (e.key === "Escape") {
                  projectManager.setShowNewProjectModal(false);
                  projectManager.setNewProjectName("");
                }
              }}
              placeholder={t("sidebar.projectName")}
              className="w-full px-3 py-2.5 text-sm rounded-lg border border-stone-200 dark:border-stone-600 bg-stone-50 dark:bg-stone-700/50 text-stone-700 dark:text-stone-200 placeholder-stone-400 focus:outline-none focus:ring-2 focus:ring-stone-400/50 focus:border-stone-300 dark:focus:border-stone-500 transition-all"
            />
            <div className="flex justify-end gap-2 pt-1">
              <button
                onClick={() => {
                  projectManager.setShowNewProjectModal(false);
                  projectManager.setNewProjectName("");
                }}
                className="px-4 py-2 text-sm font-medium text-stone-600 dark:text-stone-400 hover:text-stone-800 dark:hover:text-stone-200 rounded-lg hover:bg-stone-100 dark:hover:bg-stone-700 transition-all"
              >
                {t("common.cancel")}
              </button>
              <button
                onClick={() => {
                  projectManager.handleCreateProject();
                  projectManager.setShowNewProjectModal(false);
                }}
                disabled={!projectManager.newProjectName.trim()}
                className="px-4 py-2 text-sm font-medium bg-stone-700 dark:bg-stone-200 text-white dark:text-stone-900 rounded-lg hover:bg-stone-800 dark:hover:bg-stone-100 disabled:opacity-40 disabled:cursor-not-allowed transition-all"
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
