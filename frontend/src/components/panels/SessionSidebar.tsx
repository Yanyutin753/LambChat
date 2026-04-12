/**
 * Session sidebar component for displaying and managing chat history.
 * Each project independently loads its sessions with per-project pagination.
 */

import { useState, useEffect, useRef, useCallback } from "react";
import { useNavigate } from "react-router-dom";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { ChevronDown, Search, FolderPlus, FolderOpen } from "lucide-react";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { sessionApi, type BackendSession } from "../../services/api";
import { useAuth } from "../../hooks/useAuth";
import { useProjectSessionList } from "../../hooks/useSession";
import { useProjectManager } from "../../hooks/useProjectManager";
import { APP_NAME, GITHUB_URL } from "../../constants";
import { useTouchDrag } from "../../hooks/useTouchDrag";
import { ConfirmDialog } from "../common/ConfirmDialog";
import { ProjectItem } from "../sidebar/ProjectItem";
import type { ProjectItemHandle } from "../sidebar/ProjectItem";
import { SessionItem } from "../sidebar/SessionItem";
import { getSessionTitle, groupSessionsByTime } from "./sessionHelpers";
import { SearchDialog } from "./SearchDialog";

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
  onSetPendingProjectId,
  autoExpandProjectId,
}: SessionSidebarProps) {
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
  const [scrollEl, setScrollEl] = useState<HTMLDivElement | null>(null);

  // Track mobile breakpoint to avoid ref conflicts — both sidebars render
  // sessionListContent in the DOM, causing shared refs (scrollEl, loadMoreRef)
  // to be called twice. The desktop element wins (last call), breaking the
  // IntersectionObserver on mobile.
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

  // Uncategorized sessions — independent pagination
  const uncategorizedList = useProjectSessionList("none", scrollEl);

  // Project refs for cross-project operations
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

  // Touch drag — sessions array is now distributed, pass empty (touch drag
  // only works on uncategorized sessions in the sidebar)
  const handleMoveSession = useCallback(
    async (sessionId: string, projectId: string | null) => {
      try {
        const response = await sessionApi.moveToProject(sessionId, projectId);
        if (response.session) {
          // Remove from whichever list currently owns this session
          for (const [, handle] of projectRefs.current) {
            if (handle.sessions.some((s) => s.id === sessionId)) {
              handle.removeSession(sessionId);
              break;
            }
          }
          if (uncategorizedList.sessions.some((s) => s.id === sessionId)) {
            uncategorizedList.removeSession(sessionId);
          }
          // Add to target
          if (projectId) {
            getProjectRef(projectId)?.prependSession(response.session);
          } else {
            uncategorizedList.prependSession(response.session);
          }
        }
      } catch (err) {
        console.error("Failed to move session:", err);
        toast.error(t("sidebar.sessionMoveFailed"));
      }
    },
    [getProjectRef, uncategorizedList, t],
  );

  const handleMoveSessionRef = useRef(handleMoveSession);
  handleMoveSessionRef.current = handleMoveSession;

  const touchDrag = useTouchDrag([], (sessionId, projectId) => {
    handleMoveSessionRef.current(sessionId, projectId);
  });

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
      // Remove from all lists
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

  // Auto-expand projects section when a new session is created in a project
  useEffect(() => {
    if (autoExpandProjectId) {
      setIsProjectsCollapsed(false);
    }
  }, [autoExpandProjectId]);

  // Load projects on mount / refresh
  useEffect(() => {
    projectManager.loadProjects();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey]);

  // Handle new session from parent — prepend or update in the correct list
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
        lastAppliedNewSessionKeyRef.current = sessionKey;
      }
    }
  }, [newSession, getProjectRef, projectCount, uncategorizedList]);

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
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [onNewSession]);

  // ─── Select session helper (mobile close) ───────────────────────

  const selectAndClose = (sessionId: string) => {
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
            className="text-xl font-bold leading-none text-stone-800 dark:text-stone-100 hover:text-stone-900 dark:hover:text-stone-50 transition-colors font-serif"
          >
            {APP_NAME}
          </a>
        </div>
        <button
          onClick={() => {
            setIsCollapsed(true);
            onMobileClose?.();
          }}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-stone-600 hover:bg-stone-100 dark:text-stone-300 dark:hover:bg-stone-800 transition-colors"
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

      {/* Action buttons */}
      <div className="flex flex-col gap-px px-2 py-2 space-y-1">
        {/* New chat button */}
        <button
          onClick={onNewSession}
          className="w-full h-9 rounded-[10px] flex items-center gap-3 px-[9px] text-sm font-medium text-stone-600 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-stone-800/60 focus:outline-none transition-colors"
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            strokeWidth="0.1"
            viewBox="0 0 24 24"
            stroke="currentColor"
            className="w-[18px] h-[18px]"
          >
            <path
              d="M15.6729 3.91287C16.8918 2.69392 18.8682 2.69392 20.0871 3.91287C21.3061 5.13182 21.3061 7.10813 20.0871 8.32708L14.1499 14.2643C13.3849 15.0293 12.3925 15.5255 11.3215 15.6785L9.14142 15.9899C8.82983 16.0344 8.51546 15.9297 8.29289 15.7071C8.07033 15.4845 7.96554 15.1701 8.01005 14.8586L8.32149 12.6785C8.47449 11.6075 8.97072 10.615 9.7357 9.85006L15.6729 3.91287ZM18.6729 5.32708C18.235 4.88918 17.525 4.88918 17.0871 5.32708L11.1499 11.2643C10.6909 11.7233 10.3932 12.3187 10.3014 12.9613L10.1785 13.8215L11.0386 13.6986C11.6812 13.6068 12.2767 13.3091 12.7357 12.8501L18.6729 6.91287C19.1108 6.47497 19.1108 5.76499 18.6729 5.32708ZM11 3.99929C11.0004 4.55157 10.5531 4.99963 10.0008 5.00007C9.00227 5.00084 8.29769 5.00827 7.74651 5.06064C7.20685 5.11191 6.88488 5.20117 6.63803 5.32695C6.07354 5.61457 5.6146 6.07351 5.32698 6.63799C5.19279 6.90135 5.10062 7.24904 5.05118 7.8542C5.00078 8.47105 5 9.26336 5 10.4V13.6C5 14.7366 5.00078 15.5289 5.05118 16.1457C5.10062 16.7509 5.19279 17.0986 5.32698 17.3619C5.6146 17.9264 6.07354 18.3854 6.63803 18.673C6.90138 18.8072 7.24907 18.8993 7.85424 18.9488C8.47108 18.9992 9.26339 19 10.4 19H13.6C14.7366 19 15.5289 18.9992 16.1458 18.9488C16.7509 18.8993 17.0986 18.8072 17.362 18.673C17.9265 18.3854 18.3854 17.9264 18.673 17.3619C18.7988 17.1151 18.8881 16.7931 18.9393 16.2535C18.9917 15.7023 18.9991 14.9977 18.9999 13.9992C19.0003 13.4469 19.4484 12.9995 20.0007 13C20.553 13.0004 21.0003 13.4485 20.9999 14.0007C20.9991 14.9789 20.9932 15.7808 20.9304 16.4426C20.8664 17.116 20.7385 17.7136 20.455 18.2699C19.9757 19.2107 19.2108 19.9756 18.27 20.455C17.6777 20.7568 17.0375 20.8826 16.3086 20.9421C15.6008 21 14.7266 21 13.6428 21H10.3572C9.27339 21 8.39925 21 7.69138 20.9421C6.96253 20.8826 6.32234 20.7568 5.73005 20.455C4.78924 19.9756 4.02433 19.2107 3.54497 18.2699C3.24318 17.6776 3.11737 17.0374 3.05782 16.3086C2.99998 15.6007 2.99999 14.7266 3 13.6428V10.3572C2.99999 9.27337 2.99998 8.39922 3.05782 7.69134C3.11737 6.96249 3.24318 6.3223 3.54497 5.73001C4.02433 4.7892 4.78924 4.0243 5.73005 3.54493C6.28633 3.26149 6.88399 3.13358 7.55735 3.06961C8.21919 3.00673 9.02103 3.00083 9.99922 3.00007C10.5515 2.99964 10.9996 3.447 11 3.99929Z"
              fill="currentColor"
            ></path>
          </svg>
          <span>{t("sidebar.newChat")}</span>
        </button>

        {/* Search button */}
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

        {/* File library button */}
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
          setIsScrolled(e.currentTarget.scrollTop > 100);
        }}
      >
        {/* Scroll to top button */}
        {isScrolled && (
          <button
            onClick={() =>
              scrollEl?.scrollTo({
                top: 0,
                behavior: "smooth",
              })
            }
            className="absolute top-16 right-3 z-10 flex items-center justify-center w-7 h-7 rounded-full bg-white dark:bg-stone-800 border border-stone-200/80 dark:border-stone-700/60 shadow-sm hover:bg-stone-50 dark:hover:bg-stone-700 transition-all"
            title={t("common.scrollToTop")}
          >
            <ChevronDown size={14} className="rotate-180 text-stone-500" />
          </button>
        )}

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

          {/* New project button */}
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
                  onRenameProject={projectManager.handleRenameProject}
                  onDeleteProject={(id) => {
                    projectManager.handleDeleteProject(id, () => {
                      uncategorizedList.refresh();
                    });
                  }}
                  onUpdateIcon={projectManager.handleUpdateIcon}
                  scrollRoot={scrollEl}
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
                  onRenameProject={projectManager.handleRenameProject}
                  onDeleteProject={(id) => {
                    projectManager.handleDeleteProject(id, () => {
                      uncategorizedList.refresh();
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
                />
              ))}

          {/* Divider */}
          {!isProjectsCollapsed && (
            <div className="h-px bg-stone-200/60 dark:bg-stone-700/40 mx-2 my-1" />
          )}

          {/* Uncategorized sessions (by time) */}
          {(() => {
            const rawSessions = uncategorizedList.sessions;
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
                {/* Chats section header */}
                <div
                  onClick={() => setIsChatsCollapsed(!isChatsCollapsed)}
                  className="flex items-center justify-between px-[9px] h-9 cursor-pointer select-none group/section"
                >
                  <span className="text-[13px] font-medium text-stone-400 dark:text-stone-500 group-hover/section:text-stone-500 dark:group-hover/section:text-stone-400 transition-colors">
                    {t("sidebar.chats")}
                  </span>
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
                        <LoadingSpinner size="sm" />
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
                                  onSessionUpdate={(s) =>
                                    uncategorizedList.updateSession(s)
                                  }
                                  isFavorite={false}
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
                    {/* Infinite scroll sentinel for uncategorized */}
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
      <div className="h-px bg-stone-200/60 dark:bg-stone-700/40 mx-2 my-1" />
      <div className="px-2 pb-2">
        <div
          onClick={onShowProfile}
          className="flex items-center gap-3 px-[9px] h-9 rounded-[10px] hover:bg-stone-100 dark:hover:bg-stone-800/60 transition-colors cursor-pointer"
        >
          {user?.avatar_url && !imgError ? (
            <img
              src={user.avatar_url}
              alt={user?.username || "User"}
              className="size-5 rounded-full object-cover flex-shrink-0"
              onError={() => setImgError(true)}
            />
          ) : (
            <div className="flex size-5 items-center justify-center bg-gradient-to-br from-stone-500 to-stone-700 rounded-full">
              <span className="text-[10px] font-semibold text-white">
                {user?.username?.charAt(0).toUpperCase() || "U"}
              </span>
            </div>
          )}
          <span className="text-sm text-stone-600 dark:text-stone-400 truncate">
            {user?.username || "User"}
          </span>
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

      {/* Mobile sidebar — only render content on mobile to avoid ref conflicts */}
      <div
        className={`rounded-r-lg fixed inset-y-0 left-0 z-[70] w-64 flex flex-col sm:hidden bg-[var(--theme-bg-sidebar)] ${
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        } transition-transform duration-300 ease-in-out`}
      >
        {isMobile ? sessionListContent : <div className="flex-1" />}
      </div>

      {/* Desktop sidebar — only render content on desktop to avoid ref conflicts */}
      {!isCollapsed && (
        <div className="hidden h-full w-64 flex-col rounded-r-lg border-r border-stone-200/60 dark:border-stone-800/60 sm:flex">
          {!isMobile ? sessionListContent : <div className="flex-1" />}
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

      {/* Search Dialog */}
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
        <div className="fixed inset-0 z-[80] flex items-center justify-center">
          <div
            className="absolute inset-0 bg-black/40"
            onClick={() => projectManager.setShowNewProjectModal(false)}
          />
          <div className="relative bg-white dark:bg-stone-800 rounded-xl shadow-2xl p-5 w-[90vw] max-w-md space-y-3">
            <h3 className="text-sm font-semibold text-stone-800 dark:text-stone-100">
              {t("sidebar.newProject")}
            </h3>
            <p className="text-xs text-stone-400 dark:text-stone-500">
              {t("sidebar.projectHint")}
            </p>

            <div className="flex items-center gap-2 px-3 py-2.5 rounded-lg border border-stone-200 dark:border-stone-600 bg-stone-50 dark:bg-stone-700/50 focus-within:ring-2 focus-within:ring-stone-400/50 focus-within:border-stone-300 dark:focus-within:border-stone-500 transition-all">
              <input
                type="text"
                value={projectManager.newProjectIcon}
                onChange={(e) =>
                  projectManager.setNewProjectIcon(e.target.value)
                }
                placeholder={t("sidebar.projectName")}
                className="w-8 text-sm bg-transparent text-stone-500 dark:text-stone-400 placeholder-stone-400 focus:outline-none"
              />
              <div className="w-px h-5 bg-stone-300 dark:bg-stone-600" />
              <input
                ref={(el) => {
                  if (el) el.focus();
                }}
                type="text"
                value={projectManager.newProjectName}
                onChange={(e) =>
                  projectManager.setNewProjectName(e.target.value)
                }
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
                className="flex-1 text-sm bg-transparent text-stone-700 dark:text-stone-200 placeholder-stone-400 focus:outline-none"
              />
            </div>
            <div className="flex justify-end gap-2 pt-1">
              <button
                onClick={() => {
                  projectManager.setShowNewProjectModal(false);
                  projectManager.setNewProjectName("");
                  projectManager.setNewProjectIcon("📁");
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
