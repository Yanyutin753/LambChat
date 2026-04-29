/**
 * Session sidebar component for displaying and managing chat history.
 * Each project independently loads its sessions with per-project pagination.
 */

import {
  useState,
  useEffect,
  useRef,
  useCallback,
  forwardRef,
  useImperativeHandle,
} from "react";
import { useNavigate } from "react-router-dom";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import {
  ChevronDown,
  Search,
  FolderPlus,
  FolderOpen,
  MessageSquarePlus,
  PanelLeftClose,
  PanelLeftOpen,
  Clock,
} from "lucide-react";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { sessionApi, type BackendSession } from "../../services/api";
import { useAuth } from "../../hooks/useAuth";
import { useProjectSessionList } from "../../hooks/useSession";
import { useProjectManager } from "../../hooks/useProjectManager";
import { APP_NAME, GITHUB_URL } from "../../constants";
import { useTouchDrag } from "../../hooks/useTouchDrag";
import { ConfirmDialog } from "../common/ConfirmDialog";
import { DeleteProjectDialog } from "../common/DeleteProjectDialog";
import { ProjectItem } from "../sidebar/ProjectItem";
import type { ProjectItemHandle } from "../sidebar/ProjectItem";
import { SessionItem } from "../sidebar/SessionItem";
import {
  formatUnreadCount,
  getUnreadCountForUncategorized,
  mergeUnreadUpdate,
  type UnreadBySession,
} from "../sidebar/unreadCounts";
import { isSessionFavorite } from "../sidebar/sessionFavorites";
import { getSessionTitle, groupSessionsByTime } from "./sessionHelpers";
import { SearchDialog } from "./SearchDialog";
import { ShareDialog } from "../share/ShareDialog";
import { NewProjectModal } from "./NewProjectModal";

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
  onSetPendingProjectId?: (projectId: string | null) => void;
  /** Project ID to auto-expand after a new session is created in it */
  autoExpandProjectId?: string | null;
  onConsumeAutoExpandProjectId?: (projectId: string) => void;
}

export interface SessionSidebarHandle {
  updateSessionUnread: (
    sessionId: string,
    unreadCount: number,
    projectId?: string | null,
    isFavorite?: boolean,
  ) => void;
}

export const SessionSidebar = forwardRef<
  SessionSidebarHandle,
  SessionSidebarProps
>(function SessionSidebar(
  {
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
    onSetPendingProjectId,
    autoExpandProjectId,
    onConsumeAutoExpandProjectId,
  },
  ref,
) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const navigate = useNavigate();
  const [searchQuery] = useState("");
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [imgError, setImgError] = useState(false);
  const [internalCollapsed, setInternalCollapsed] = useState(true);
  const [isProjectsCollapsed, setIsProjectsCollapsed] = useState(false);
  const [isChatsCollapsed, setIsChatsCollapsed] = useState(false);
  const [isScrolled, setIsScrolled] = useState(false);
  const [isScrolledToBottom, setIsScrolledToBottom] = useState(false);
  const [scrollEl, setScrollEl] = useState<HTMLDivElement | null>(null);
  const [unreadBySession, setUnreadBySession] = useState<UnreadBySession>(
    () => new Map(),
  );
  const [shareDialogSessionId, setShareDialogSessionId] = useState<
    string | null
  >(null);
  const [shareDialogSessionName, setShareDialogSessionName] = useState("");

  const [isMobile, setIsMobile] = useState(
    () => window.matchMedia("(max-width: 639px)").matches,
  );
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 639px)");
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  const handleNewSessionInProject = useCallback(
    (projectId: string) => {
      onSetPendingProjectId?.(projectId);
      onNewSession();
    },
    [onNewSession, onSetPendingProjectId],
  );

  const isCollapsed = externalCollapsed ?? internalCollapsed;
  const setIsCollapsed = onToggleCollapsed ?? setInternalCollapsed;

  // ─── Hooks ──────────────────────────────────────────────────────

  const uncategorizedList = useProjectSessionList("none", scrollEl);

  const handleSessionUnread = useCallback(
    (
      sid: string,
      count: number,
      projectId?: string | null,
      isFavorite?: boolean,
    ) => {
      setUnreadBySession((prev) =>
        mergeUnreadUpdate(prev, {
          sessionId: sid,
          unreadCount: count,
          projectId,
          isFavorite,
        }),
      );
      const session = uncategorizedList.sessions.find((s) => s.id === sid);
      if (session) {
        uncategorizedList.updateSession({ ...session, unread_count: count });
      }
      for (const [, handle] of projectRefs.current) {
        const s = handle.sessions.find((s) => s.id === sid);
        if (s) {
          handle.updateSession({ ...s, unread_count: count });
        }
      }
    },
    [uncategorizedList],
  );

  useImperativeHandle(
    ref,
    () => ({ updateSessionUnread: handleSessionUnread }),
    [handleSessionUnread],
  );

  const projectRefs = useRef<Map<string, ProjectItemHandle>>(new Map());
  const lastAppliedNewSessionKeyRef = useRef<string | null>(null);

  const getProjectRef = useCallback(
    (projectId: string): ProjectItemHandle | null => {
      return projectRefs.current.get(projectId) ?? null;
    },
    [],
  );

  const setProjectRef = useCallback(
    (projectId: string, handle: ProjectItemHandle | null) => {
      if (handle) {
        projectRefs.current.set(projectId, handle);
      } else {
        projectRefs.current.delete(projectId);
      }
    },
    [],
  );

  const projectManager = useProjectManager();
  const { projects } = projectManager;
  const projectCount = projects.length;

  const handleMoveSession = useCallback(
    async (sessionId: string, projectId: string | null) => {
      try {
        const response = await sessionApi.moveToProject(sessionId, projectId);
        if (response.session) {
          const favorite = isSessionFavorite(response.session);

          for (const [, handle] of projectRefs.current) {
            handle.removeSession(sessionId);
          }
          uncategorizedList.removeSession(sessionId);

          if (projectId) {
            getProjectRef(projectId)?.prependSession(response.session);
          } else {
            uncategorizedList.prependSession(response.session);
          }
          if (favorite) {
            const favoritesProject = projects.find(
              (p) => p.type === "favorites",
            );
            if (favoritesProject) {
              getProjectRef(favoritesProject.id)?.prependSession(
                response.session,
              );
            }
          }
          setUnreadBySession((prev) =>
            mergeUnreadUpdate(prev, {
              sessionId,
              unreadCount: response.session.unread_count ?? 0,
              projectId:
                (response.session.metadata?.project_id as
                  | string
                  | null
                  | undefined) ?? null,
              isFavorite: favorite,
            }),
          );
        }
      } catch (err) {
        console.error("Failed to move session:", err);
        toast.error(t("sidebar.sessionMoveFailed"));
      }
    },
    [getProjectRef, projects, uncategorizedList, t],
  );

  const handleMoveSessionRef = useRef(handleMoveSession);
  handleMoveSessionRef.current = handleMoveSession;

  const handleShareSession = useCallback(
    (sessionId: string) => {
      let title = "";
      for (const [, handle] of projectRefs.current) {
        const s = handle.sessions.find((s) => s.id === sessionId);
        if (s) {
          title = getSessionTitle(s, t);
          break;
        }
      }
      if (!title) {
        const s = uncategorizedList.sessions.find((s) => s.id === sessionId);
        if (s) title = getSessionTitle(s, t);
      }
      setShareDialogSessionId(sessionId);
      setShareDialogSessionName(title || t("sidebar.newChat"));
    },
    [uncategorizedList, t],
  );

  const touchDrag = useTouchDrag([], (sessionId, projectId) => {
    handleMoveSessionRef.current(sessionId, projectId);
  });

  const handleToggleFavorite = useCallback(
    async (sessionId: string) => {
      try {
        const response = await sessionApi.toggleFavorite(sessionId);
        const updatedSession = response.session;
        const favoritesProject = projects.find((p) => p.type === "favorites");
        const favoritesRef = favoritesProject
          ? getProjectRef(favoritesProject.id)
          : null;

        if (
          uncategorizedList.sessions.some((session) => session.id === sessionId)
        ) {
          uncategorizedList.updateSession(updatedSession);
        }

        for (const [, handle] of projectRefs.current) {
          const exists = handle.sessions.some(
            (session) => session.id === sessionId,
          );
          if (!exists) continue;
          if (
            favoritesRef &&
            handle === favoritesRef &&
            !response.is_favorite
          ) {
            handle.removeSession(sessionId);
            continue;
          }
          handle.updateSession(updatedSession);
        }

        if (response.is_favorite && favoritesRef) {
          favoritesRef.prependSession(updatedSession);
          favoritesRef.updateSession(updatedSession);
        }
        setUnreadBySession((prev) =>
          mergeUnreadUpdate(prev, {
            sessionId,
            unreadCount: updatedSession.unread_count ?? 0,
            projectId:
              (updatedSession.metadata?.project_id as
                | string
                | null
                | undefined) ?? null,
            isFavorite: response.is_favorite,
          }),
        );
      } catch (err) {
        console.error("Failed to toggle favorite:", err);
        toast.error(t("sidebar.favoriteToggleFailed", "收藏状态更新失败"));
      }
    },
    [getProjectRef, projects, t, uncategorizedList],
  );

  // ─── Delete confirmation ────────────────────────────────────────

  const [deleteConfirm, setDeleteConfirm] = useState<{
    isOpen: boolean;
    sessionId: string | null;
  }>({ isOpen: false, sessionId: null });

  const [deleteProjectConfirm, setDeleteProjectConfirm] = useState<{
    isOpen: boolean;
    projectId: string | null;
    projectName: string;
  }>({ isOpen: false, projectId: null, projectName: "" });

  const confirmDeleteProject = async (deleteSessions: boolean) => {
    const { projectId } = deleteProjectConfirm;
    if (!projectId) return;
    setDeleteProjectConfirm((prev) => ({ ...prev, isOpen: false }));
    await projectManager.handleDeleteProject(projectId, {
      deleteSessions,
      onAfter: () => uncategorizedList.refresh(),
    });
  };

  const confirmDeleteSession = async () => {
    const sessionId = deleteConfirm.sessionId;
    if (!sessionId) return;
    try {
      await sessionApi.delete(sessionId);
      for (const [, handle] of projectRefs.current) {
        handle.removeSession(sessionId);
      }
      uncategorizedList.removeSession(sessionId);
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

  useEffect(() => {
    if (autoExpandProjectId) {
      setIsProjectsCollapsed(false);
    }
  }, [autoExpandProjectId]);

  useEffect(() => {
    projectManager.loadProjects();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey]);

  useEffect(() => {
    if (!currentSessionId) return;
    uncategorizedList.softRefresh();
    projectRefs.current.forEach((ref) => ref?.softRefresh());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentSessionId]);

  useEffect(() => {
    if (newSession && newSession.id) {
      const sessionKey = [
        newSession.id,
        newSession.updated_at,
        newSession.name ?? "",
      ].join(":");
      if (lastAppliedNewSessionKeyRef.current === sessionKey) {
        return;
      }

      const projectId = newSession.metadata?.project_id as string | undefined;
      const list = projectId ? getProjectRef(projectId) : uncategorizedList;
      if (list) {
        list.prependSession(newSession);
        list.updateSession(newSession);
      }
      if (isSessionFavorite(newSession)) {
        const favoritesProject = projects.find((p) => p.type === "favorites");
        if (favoritesProject) {
          const favoritesRef = getProjectRef(favoritesProject.id);
          favoritesRef?.prependSession(newSession);
          favoritesRef?.updateSession(newSession);
        }
      }
      lastAppliedNewSessionKeyRef.current = sessionKey;
    }
  }, [newSession, getProjectRef, projectCount, projects, uncategorizedList]);

  // ─── Keyboard shortcuts ──────────────────────────────────────────

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      const isMac = navigator.platform.toUpperCase().indexOf("MAC") >= 0;
      const modifier = isMac ? e.metaKey : e.ctrlKey;

      if (modifier && e.key === "k") {
        e.preventDefault();
        setIsSearchOpen(true);
      }
      if (modifier && e.key === "n") {
        e.preventDefault();
        onNewSession();
      }
      if (modifier && e.shiftKey && (e.key === "O" || e.key === "o")) {
        e.preventDefault();
        onNewSession();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onNewSession]);

  // ─── Select session helper (mobile close) ───────────────────────

  const selectAndClose = (sessionId: string) => {
    const uncategorizedSession = uncategorizedList.sessions.find(
      (session) => session.id === sessionId,
    );
    const existingSession =
      uncategorizedSession ??
      Array.from(projectRefs.current.values())
        .flatMap((handle) => handle.sessions)
        .find((session) => session.id === sessionId);
    handleSessionUnread(
      sessionId,
      0,
      (existingSession?.metadata?.project_id as string | null | undefined) ??
        null,
      existingSession ? isSessionFavorite(existingSession) : undefined,
    );
    onSelectSession(sessionId);
    onMobileClose?.();
  };

  // ─── JSX ────────────────────────────────────────────────────────

  const sessionListContent = (
    <>
      {/* Header */}
      <div className="flex items-center justify-between px-3 pt-3 pb-1 sm:px-4">
        <div className="flex h-7 items-center gap-2">
          <img
            src="/icons/icon.svg"
            alt={APP_NAME}
            className="size-6 rounded-full object-cover"
          />
          <a
            href={GITHUB_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="text-lg font-bold leading-none text-stone-800 dark:text-stone-100 hover:text-stone-900 dark:hover:text-stone-50 transition-colors font-serif"
          >
            {APP_NAME}
          </a>
        </div>
        <button
          onClick={() => {
            setIsCollapsed(true);
            onMobileClose?.();
          }}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-stone-600 hover:bg-stone-100 dark:text-stone-300 dark:hover:bg-stone-800 transition-colors cursor-w-resize rtl:cursor-e-resize"
          title={t("sidebar.collapseSidebar")}
        >
          <PanelLeftClose size={18} />
        </button>
      </div>

      {/* Action buttons */}
      <div className="flex flex-col gap-px px-2 py-2 space-y-1">
        <button
          onClick={onNewSession}
          className="w-full h-9 rounded-[10px] flex items-center gap-3 px-[9px] text-sm font-medium text-stone-600 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-stone-800/60 focus:outline-none transition-colors group"
        >
          <MessageSquarePlus size={18} />
          <span className="flex-1 text-left">{t("sidebar.newChat")}</span>
          <kbd className="hidden sm:inline-flex items-center gap-0.5 px-1.5 py-0.5 text-[10px] font-medium text-stone-400 dark:text-stone-500 rounded opacity-0 group-hover:opacity-100 transition-opacity">
            {t("sidebar.newChatShortcut")}
          </kbd>
        </button>

        <button
          onClick={() => setIsSearchOpen(true)}
          className="w-full h-9 rounded-[10px] flex items-center gap-3 px-[9px] text-sm text-stone-600 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-stone-800/60 focus:outline-none transition-colors group"
        >
          <Search size={18} />
          <span className="flex-1 text-left">
            {t("sidebar.searchSessions")}
          </span>
          <kbd className="hidden sm:inline-flex items-center gap-0.5 px-1.5 py-0.5 text-[10px] font-medium text-stone-400 dark:text-stone-500 rounded opacity-0 group-hover:opacity-100 transition-opacity">
            ⌘K
          </kbd>
        </button>

        <button
          onClick={() => navigate("/files")}
          className="w-full h-9 rounded-[10px] flex items-center gap-3 px-[9px] text-sm text-stone-600 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-stone-800/60 focus:outline-none transition-colors"
        >
          <FolderOpen size={18} />
          <span>{t("fileLibrary.title")}</span>
        </button>
      </div>

      {/* Session list */}
      <div
        ref={setScrollEl}
        data-sidebar-scroll
        className="flex-1 overflow-y-auto px-2 relative [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
        onScroll={(e) => {
          const el = e.currentTarget;
          setIsScrolled(el.scrollTop > 10);
          setIsScrolledToBottom(
            el.scrollHeight - el.scrollTop - el.clientHeight < 10,
          );
        }}
      >
        {/* Top scroll fade indicator */}
        <div
          className={`sidebar-scroll-fade-top ${
            isScrolled ? "is-scrolled" : ""
          }`}
        />

        {/* Bottom scroll fade indicator */}
        <div
          className={`sidebar-scroll-fade-bottom transition-opacity duration-150 ${
            isScrolledToBottom ? "opacity-0" : "opacity-100"
          }`}
        />

        <div className="flex flex-col gap-px">
          {/* Project section header */}
          <div
            onClick={() => setIsProjectsCollapsed(!isProjectsCollapsed)}
            className="flex items-center justify-between px-[9px] h-9 cursor-pointer select-none group/section"
          >
            <span className="text-[13px] font-medium text-stone-400 dark:text-stone-500 group-hover/section:text-stone-500 dark:group-hover/section:text-stone-400 transition-colors">
              {t("sidebar.projects")}
            </span>
            <ChevronDown
              size={14}
              className={`text-stone-300 dark:text-stone-600 transition-transform duration-200 ${
                isProjectsCollapsed ? "-rotate-90" : ""
              }`}
            />
          </div>

          {!isProjectsCollapsed && (
            <button
              onClick={() => projectManager.setShowNewProjectModal(true)}
              className="w-full h-9 rounded-[10px] flex items-center gap-3 px-[9px] text-sm text-stone-500 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-stone-800/60 transition-colors cursor-pointer"
            >
              <FolderPlus size={18} />
              <span>{t("sidebar.newProject")}</span>
            </button>
          )}

          {/* Favorites project */}
          {!isProjectsCollapsed &&
            (() => {
              const favoritesProject = projects.find(
                (p) => p.type === "favorites",
              );
              if (!favoritesProject) return null;
              return (
                <ProjectItem
                  ref={(el) => setProjectRef(favoritesProject.id, el)}
                  project={favoritesProject}
                  currentSessionId={currentSessionId}
                  allProjects={projects}
                  onSelectSession={selectAndClose}
                  onDeleteSession={(sessionId) => {
                    setDeleteConfirm({ isOpen: true, sessionId });
                  }}
                  onMoveSession={handleMoveSession}
                  onToggleFavorite={handleToggleFavorite}
                  onShareSession={handleShareSession}
                  onRenameProject={projectManager.handleRenameProject}
                  onDeleteProject={(id) => {
                    const proj = projects.find((p) => p.id === id);
                    setDeleteProjectConfirm({
                      isOpen: true,
                      projectId: id,
                      projectName: proj?.name ?? "",
                    });
                  }}
                  onUpdateIcon={projectManager.handleUpdateIcon}
                  scrollRoot={scrollEl}
                  draggingSessionId={
                    touchDrag.touchDropTarget === favoritesProject.id
                      ? touchDrag.draggingSessionId
                      : null
                  }
                  unreadBySession={unreadBySession}
                  favoritesOnly
                />
              );
            })()}

          {/* Custom projects */}
          {!isProjectsCollapsed &&
            projects
              .filter((p) => p.type === "custom")
              .sort((a, b) => a.sort_order - b.sort_order)
              .map((project) => (
                <ProjectItem
                  key={project.id}
                  ref={(el) => setProjectRef(project.id, el)}
                  project={project}
                  currentSessionId={currentSessionId}
                  allProjects={projects}
                  onSelectSession={selectAndClose}
                  onDeleteSession={(sessionId) => {
                    setDeleteConfirm({ isOpen: true, sessionId });
                  }}
                  onMoveSession={handleMoveSession}
                  onToggleFavorite={handleToggleFavorite}
                  onShareSession={handleShareSession}
                  onRenameProject={projectManager.handleRenameProject}
                  onDeleteProject={(id) => {
                    const proj = projects.find((p) => p.id === id);
                    setDeleteProjectConfirm({
                      isOpen: true,
                      projectId: id,
                      projectName: proj?.name ?? "",
                    });
                  }}
                  onUpdateIcon={projectManager.handleUpdateIcon}
                  scrollRoot={scrollEl}
                  draggingSessionId={
                    touchDrag.touchDropTarget === project.id
                      ? touchDrag.draggingSessionId
                      : null
                  }
                  onNewSessionInProject={handleNewSessionInProject}
                  forceExpandProjectId={autoExpandProjectId}
                  onConsumeAutoExpand={onConsumeAutoExpandProjectId}
                  unreadBySession={unreadBySession}
                />
              ))}

          {!isProjectsCollapsed && (
            <div className="h-px bg-stone-200/60 dark:bg-stone-700/40 mx-2 my-1" />
          )}

          {/* Uncategorized sessions (by time) */}
          {(() => {
            const rawSessions = uncategorizedList.sessions;
            const chatsUnreadCount = getUnreadCountForUncategorized({
              loadedSessions: rawSessions,
              unreadBySession,
            });
            const filtered = searchQuery.trim()
              ? rawSessions.filter((s) => {
                  const title = getSessionTitle(s, t).toLowerCase();
                  return title.includes(searchQuery.toLowerCase());
                })
              : rawSessions;

            if (filtered.length === 0 && !uncategorizedList.isLoading)
              return null;

            const groupedUncategorized = groupSessionsByTime(filtered, t);
            return (
              <>
                <div
                  onClick={() => setIsChatsCollapsed(!isChatsCollapsed)}
                  className="flex items-center justify-between px-[9px] h-9 cursor-pointer select-none group/section"
                >
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="text-[13px] font-medium text-stone-400 dark:text-stone-500 group-hover/section:text-stone-500 dark:group-hover/section:text-stone-400 transition-colors">
                      {t("sidebar.chats")}
                    </span>
                    {chatsUnreadCount > 0 && (
                      <span className="inline-flex h-4 min-w-[16px] items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-medium leading-none text-white">
                        {formatUnreadCount(chatsUnreadCount)}
                      </span>
                    )}
                  </div>
                  <ChevronDown
                    size={14}
                    className={`text-stone-300 dark:text-stone-600 transition-transform duration-200 ${
                      isChatsCollapsed ? "-rotate-90" : ""
                    }`}
                  />
                </div>

                {!isChatsCollapsed && (
                  <>
                    {uncategorizedList.isLoading ? (
                      <div className="flex justify-center py-4">
                        <LoadingSpinner
                          size="sm"
                          color="text-[var(--theme-primary)]"
                        />
                      </div>
                    ) : (
                      groupedUncategorized.map((group) => (
                        <div key={group.label}>
                          <div className="px-[9px] h-7 flex items-center text-[13px] font-medium text-stone-400 dark:text-stone-500 select-none">
                            {group.label}
                          </div>
                          <div className="flex flex-col gap-px">
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
                                  currentProjectId={null}
                                  onShare={() => handleShareSession(session.id)}
                                  onToggleFavorite={() =>
                                    handleToggleFavorite(session.id)
                                  }
                                  onSessionUpdate={(s) =>
                                    uncategorizedList.updateSession(s)
                                  }
                                  isFavorite={isSessionFavorite(session)}
                                  onDragStartTouch={
                                    touchDrag.handleDragStartTouch
                                  }
                                  isDraggingTouch={
                                    touchDrag.draggingSessionId === session.id
                                  }
                                />
                              ))}
                          </div>
                        </div>
                      ))
                    )}
                    {uncategorizedList.hasMore && (
                      <div
                        ref={uncategorizedList.loadMoreRef}
                        className="flex justify-center py-2"
                      >
                        {uncategorizedList.isLoadingMore && (
                          <div className="flex items-center gap-2 text-stone-400 dark:text-stone-500">
                            <LoadingSpinner size="xs" />
                            <span className="text-xs">
                              {t("common.loading")}
                            </span>
                          </div>
                        )}
                      </div>
                    )}
                  </>
                )}
              </>
            );
          })()}
        </div>
      </div>

      {/* Footer */}
      <div className="shrink-0 px-2 pt-2 pb-1 border-t border-gray-200/60 dark:border-gray-800">
        <div
          onClick={onShowProfile}
          className="group flex items-center rounded-xl py-2 px-2 w-full hover:bg-gray-100 dark:hover:bg-gray-850 transition cursor-pointer"
        >
          <div className="shrink-0 w-8 h-8 rounded-full overflow-hidden ring-1 ring-gray-200 dark:ring-gray-700 group-hover:ring-[var(--theme-primary)] transition mr-3">
            {user?.avatar_url && !imgError ? (
              <img
                src={user.avatar_url}
                alt={user?.username || "User"}
                className="w-full h-full object-cover rounded-full"
                onError={() => setImgError(true)}
                draggable={false}
              />
            ) : (
              <div className="flex w-full h-full items-center justify-center bg-gradient-to-br from-stone-500 to-stone-700 rounded-full">
                <span className="text-xs font-semibold text-white">
                  {user?.username?.charAt(0).toUpperCase() || "U"}
                </span>
              </div>
            )}
          </div>
          <div className="flex-1 text-left min-w-0 space-y-0.5">
            <div className="text-sm font-medium text-gray-800 dark:text-gray-100 truncate">
              {user?.username || "User"}
            </div>
            <div className="text-xs text-gray-400 dark:text-gray-500 whitespace-nowrap ">
              {(user?.roles[0] || "User").replace(/^./, (c) => c.toUpperCase())}
            </div>
          </div>
          <ChevronDown className="size-4 text-gray-400 shrink-0" />
        </div>
      </div>
    </>
  );

  return (
    <>
      <div
        className={`fixed inset-0 z-[60] bg-black/40 sm:hidden transition-opacity duration-300 ease-in-out ${
          mobileOpen ? "opacity-100" : "opacity-0 pointer-events-none"
        }`}
        onClick={onMobileClose}
      />

      <div
        className={`rounded-r-lg fixed inset-y-0 left-0 z-[70] w-64 flex flex-col sm:hidden bg-[var(--theme-bg-sidebar)] transition-transform duration-300 ease-in-out ${
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        {isMobile ? sessionListContent : <div className="flex-1" />}
      </div>

      {/* Desktop: always render sidebar container */}
      <div
        className="hidden sm:flex h-full relative shrink-0 overflow-hidden transition-[width] duration-150 ease-[steps(1,start)]"
        style={{
          width: isCollapsed
            ? "var(--sidebar-rail-width)"
            : "var(--sidebar-width)",
        }}
      >
        {/* Full sidebar panel */}
        <div
          className={`h-full w-[--sidebar-width] bg-[var(--theme-bg-sidebar)] border-r border-stone-200/60 dark:border-stone-800/60 transition-opacity duration-150 ease-linear overflow-x-clip overflow-y-auto text-clip whitespace-nowrap ${
            isCollapsed ? "opacity-0 pointer-events-none" : "opacity-100"
          }`}
          inert={isCollapsed || undefined}
        >
          {!isMobile ? sessionListContent : <div className="flex-1" />}
        </div>

        {/* Collapsed rail — absolute overlay on top of panel */}
        <nav
          className={`absolute inset-0 flex h-full w-[--sidebar-rail-width] flex-col items-start bg-transparent pb-1.5 select-none transition-opacity duration-150 ease-[steps(1,end)] ${
            isCollapsed
              ? "opacity-100 pointer-events-auto"
              : "pointer-events-none opacity-0"
          }`}
          aria-label={t("sidebarView")}
        >
          {/* Expand button — aligns with header close button position */}
          <div className="h-11 flex items-center justify-center w-full">
            <button
              onClick={() => setIsCollapsed(false)}
              className="flex h-9 w-9 items-center justify-center rounded-lg text-stone-600 hover:bg-stone-100 dark:text-stone-300 dark:hover:bg-stone-800 transition-colors mx-2 cursor-e-resize rtl:cursor-w-resize"
              aria-label={t("sidebar.expandSidebar")}
            >
              <PanelLeftOpen size={20} />
            </button>
          </div>

          {/* Action icons — gap matches expanded sidebar header pb-1 + action py-2 */}
          <div className="mt-3 flex flex-col items-center w-full gap-px">
            <button
              onClick={onNewSession}
              className="flex h-9 w-9 items-center justify-center rounded-lg text-stone-600 hover:bg-stone-100 dark:text-stone-300 dark:hover:bg-stone-800 transition-colors mx-2"
              aria-label={t("sidebar.newChat")}
            >
              <MessageSquarePlus size={18} />
            </button>
            <button
              onClick={() => setIsSearchOpen(true)}
              className="flex h-9 w-9 items-center justify-center rounded-lg text-stone-600 hover:bg-stone-100 dark:text-stone-300 dark:hover:bg-stone-800 transition-colors mx-2"
              aria-label={t("sidebar.searchSessions")}
            >
              <Search size={18} />
            </button>
            <button
              onClick={() => setIsCollapsed(false)}
              className="flex h-9 w-9 items-center justify-center rounded-lg text-stone-600 hover:bg-stone-100 dark:text-stone-300 dark:hover:bg-stone-800 transition-colors mx-2"
              aria-label={t("sidebar.recentChats")}
            >
              <Clock size={18} />
            </button>
          </div>

          <div className="pointer-events-none flex-grow" />

          {/* Profile avatar — aligns with expanded sidebar footer (px-2 + px-2 + mr-3) */}
          <div className="mb-1 w-full px-2">
            <button
              onClick={onShowProfile}
              className="flex h-9 w-full items-center rounded-lg overflow-hidden transition-colors"
              aria-label={t("sidebar.expandSidebar")}
            >
              <div className="shrink-0 w-8 h-8 rounded-full overflow-hidden ring-1 ring-gray-200 dark:ring-gray-700">
                {user?.avatar_url && !imgError ? (
                  <img
                    src={user.avatar_url}
                    alt={user?.username || "User"}
                    className="w-full h-full object-cover rounded-full"
                    onError={() => setImgError(true)}
                    draggable={false}
                  />
                ) : (
                  <div className="flex w-full h-full items-center justify-center bg-gradient-to-br from-stone-500 to-stone-700 rounded-full">
                    <span className="text-xs font-semibold text-white">
                      {user?.username?.charAt(0).toUpperCase() || "U"}
                    </span>
                  </div>
                )}
              </div>
            </button>
          </div>
        </nav>
      </div>

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

      {isSearchOpen && (
        <SearchDialog
          isOpen={isSearchOpen}
          onClose={() => setIsSearchOpen(false)}
          onSelectSession={(sessionId) => {
            selectAndClose(sessionId);
            setIsSearchOpen(false);
          }}
        />
      )}

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

      <DeleteProjectDialog
        isOpen={deleteProjectConfirm.isOpen}
        projectName={deleteProjectConfirm.projectName}
        onConfirm={confirmDeleteProject}
        onCancel={() =>
          setDeleteProjectConfirm({
            isOpen: false,
            projectId: null,
            projectName: "",
          })
        }
      />

      {projectManager.showNewProjectModal && (
        <NewProjectModal
          icon={projectManager.newProjectIcon}
          name={projectManager.newProjectName}
          onIconChange={projectManager.setNewProjectIcon}
          onNameChange={projectManager.setNewProjectName}
          onCreate={projectManager.handleCreateProject}
          onClose={() => {
            projectManager.setShowNewProjectModal(false);
            projectManager.setNewProjectName("");
            projectManager.setNewProjectIcon("📁");
          }}
        />
      )}

      <ShareDialog
        isOpen={shareDialogSessionId !== null}
        onClose={() => setShareDialogSessionId(null)}
        sessionId={shareDialogSessionId ?? ""}
        sessionName={shareDialogSessionName || t("sidebar.newChat")}
      />
    </>
  );
});
