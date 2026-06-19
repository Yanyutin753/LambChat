/**
 * Session sidebar component for displaying and managing chat history.
 * Each project independently loads its sessions with per-project pagination.
 *
 * Business logic is split into:
 *  - useSessionSidebarActions  — CRUD handlers (move, share, favorite, delete, mark-read)
 *  - useMoreMenu              — "More" menu state, items, positioning, effects
 *  - useSessionSidebarEffects  — auto-expand, refresh, keyboard shortcuts, mobile query
 */

import {
  useState,
  useRef,
  useCallback,
  useMemo,
  useEffect,
  forwardRef,
  useImperativeHandle,
} from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import type { BackendSession } from "../../services/api";
import { authApi } from "../../services/api/auth";
import { useAuth } from "../../hooks/useAuth";
import { useProjectSessionList } from "../../hooks/useSession";
import { useProjectManager } from "../../hooks/useProjectManager";
import { useTouchDrag } from "../../hooks/useTouchDrag";
import { useSessionSidebarActions } from "../../hooks/useSessionSidebarActions";
import { useMoreMenu } from "../../hooks/useMoreMenu";
import { useSessionSidebarEffects } from "../../hooks/useSessionSidebarEffects";
import {
  PROJECTS_COLLAPSED_STORAGE_KEY,
  CHATS_COLLAPSED_STORAGE_KEY,
  SCHEDULED_TASKS_COLLAPSED_STORAGE_KEY,
} from "../../hooks/userMetadataPreferences";
import { ConfirmDialog } from "../common/ConfirmDialog";
import { DeleteProjectDialog } from "../common/DeleteProjectDialog";
import { RecentChatsDialog } from "../sidebar/RecentChatsDialog";
import type { ProjectItemHandle } from "../sidebar/ProjectItem";
import { ProjectPluginOptionsModal } from "../sidebar/ProjectPluginOptionsModal";
import type { ScheduledTaskItemHandle } from "../sidebar/ScheduledTaskSidebarItem";
import { type UnreadBySession } from "../sidebar/unreadCounts";
import { SearchDialog } from "./SearchDialog";
import { ShareDialog } from "../share/ShareDialog";
import { NewProjectModal } from "./NewProjectModal";
import {
  SessionListContent,
  SidebarRail,
  MobileMoreMenuSheet,
  DesktopMoreMenu,
} from "./SidebarParts";
import type {
  SessionActions,
  ProjectActions,
  ScheduledTaskActions,
} from "./SidebarParts";
import type { PluginRuntimeContributionStates } from "../../extensions/coreContributions";
import type { Project } from "../../types";

// ─── Public interfaces ─────────────────────────────────────────────

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
  runtimePlugins?: PluginRuntimeContributionStates;
}

export interface SessionSidebarHandle {
  updateSessionUnread: (
    sessionId: string,
    unreadCount: number,
    projectId?: string | null,
    isFavorite?: boolean,
    scheduledTaskId?: string | null,
  ) => void;
}

// ─── Component ─────────────────────────────────────────────────────

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
    runtimePlugins,
  },
  ref,
) {
  const { t } = useTranslation();
  const { user } = useAuth();
  const navigate = useNavigate();

  // ─── Core state ──────────────────────────────────────────────────

  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [isRecentChatsOpen, setIsRecentChatsOpen] = useState(false);
  const [imgError, setImgError] = useState(false);
  const [internalCollapsed, setInternalCollapsed] = useState(true);
  const [isProjectsCollapsed, setIsProjectsCollapsed] = useState(() => {
    const saved = localStorage.getItem(PROJECTS_COLLAPSED_STORAGE_KEY);
    return saved === "true";
  });
  const [isScheduledTasksCollapsed, setIsScheduledTasksCollapsed] = useState(
    () => {
      const saved = localStorage.getItem(SCHEDULED_TASKS_COLLAPSED_STORAGE_KEY);
      return saved === "true";
    },
  );
  const [isNavCollapsed, setIsNavCollapsed] = useState(false);
  const [isChatsCollapsed, setIsChatsCollapsed] = useState(() => {
    const saved = localStorage.getItem(CHATS_COLLAPSED_STORAGE_KEY);
    return saved === "true";
  });
  const [scrollEl, setScrollEl] = useState<HTMLDivElement | null>(null);
  const [unreadBySession, setUnreadBySession] = useState<UnreadBySession>(
    () => new Map(),
  );
  const [isMobile, setIsMobile] = useState(
    () => window.matchMedia("(max-width: 639px)").matches,
  );
  const [isSelectionMode, setIsSelectionMode] = useState(false);
  const [selectedSessionIds, setSelectedSessionIds] = useState<Set<string>>(
    () => new Set(),
  );
  const [projectOptionsProject, setProjectOptionsProject] = useState<Project | null>(null);

  // Sync scheduledTasksCollapsed from other tabs / metadata sync on login
  useEffect(() => {
    const handler = (e: Event) => {
      setIsScheduledTasksCollapsed((e as CustomEvent).detail);
    };
    window.addEventListener("scheduled-tasks-collapsed-changed", handler);
    return () =>
      window.removeEventListener("scheduled-tasks-collapsed-changed", handler);
  }, []);

  // Sync projectsCollapsed from other tabs / metadata sync on login
  useEffect(() => {
    const handler = (e: Event) => {
      setIsProjectsCollapsed((e as CustomEvent).detail);
    };
    window.addEventListener("projects-collapsed-changed", handler);
    return () =>
      window.removeEventListener("projects-collapsed-changed", handler);
  }, []);

  // Sync chatsCollapsed from other tabs / metadata sync on login
  useEffect(() => {
    const handler = (e: Event) => {
      setIsChatsCollapsed((e as CustomEvent).detail);
    };
    window.addEventListener("chats-collapsed-changed", handler);
    return () => window.removeEventListener("chats-collapsed-changed", handler);
  }, []);

  // Delete project confirmation (uses projectManager, stays here)
  const [deleteProjectConfirm, setDeleteProjectConfirm] = useState<{
    isOpen: boolean;
    projectId: string | null;
    projectName: string;
  }>({ isOpen: false, projectId: null, projectName: "" });

  const isCollapsed = externalCollapsed ?? internalCollapsed;
  const setIsCollapsed = onToggleCollapsed ?? setInternalCollapsed;

  // ─── Refs ────────────────────────────────────────────────────────

  const projectRefs = useRef<Map<string, ProjectItemHandle>>(new Map());
  const scheduledTaskRefs = useRef<Map<string, ScheduledTaskItemHandle>>(
    new Map(),
  );
  const recentChatsBtnRef = useRef<HTMLButtonElement>(null);

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

  const setScheduledTaskRef = useCallback(
    (taskId: string, handle: ScheduledTaskItemHandle | null) => {
      if (handle) {
        scheduledTaskRefs.current.set(taskId, handle);
      } else {
        scheduledTaskRefs.current.delete(taskId);
      }
    },
    [],
  );

  // ─── Data hooks ──────────────────────────────────────────────────

  const uncategorizedList = useProjectSessionList("none", scrollEl);
  const projectManager = useProjectManager();
  const { projects } = projectManager;

  // ─── Extracted hooks ─────────────────────────────────────────────

  const actions = useSessionSidebarActions({
    uncategorizedList,
    projectRefs,
    scheduledTaskRefs,
    projects,
    currentSessionId,
    setUnreadBySession,
    onNewSession,
    onSelectSession,
    onMobileClose,
    getProjectRef,
  });

  const moreMenu = useMoreMenu({ isCollapsed, isMobile, runtimePlugins });

  useSessionSidebarEffects({
    currentSessionId,
    refreshKey,
    newSession,
    autoExpandProjectId,
    onNewSession,
    setIsSearchOpen,
    setIsProjectsCollapsed,
    setIsMobile,
    loadProjects: projectManager.loadProjects,
    uncategorizedList,
    projectRefs,
    scheduledTaskRefs,
    getProjectRef,
    projects,
  });

  // ─── Imperative handle ────────────────────────────────────────────

  useImperativeHandle(
    ref,
    () => ({ updateSessionUnread: actions.handleSessionUnread }),
    [actions.handleSessionUnread],
  );

  // ─── Total unread count ────────────────────────────────────────────

  const totalUnreadCount = useMemo(() => {
    const realtimeIds = new Set(unreadBySession.keys());
    let total = 0;
    for (const entry of unreadBySession.values()) {
      total += entry.count;
    }
    const addSessions = (sessions: BackendSession[]) => {
      for (const s of sessions) {
        if (!realtimeIds.has(s.id) && (s.unread_count ?? 0) > 0) {
          total += s.unread_count ?? 0;
        }
      }
    };
    addSessions(uncategorizedList.sessions);
    for (const [, handle] of projectRefs.current) {
      addSessions(handle.sessions);
    }
    for (const [, handle] of scheduledTaskRefs.current) {
      addSessions(handle.sessions);
    }
    return total;
  }, [unreadBySession, uncategorizedList.sessions]);

  // ─── Project delete handler ──────────────────────────────────────

  const confirmDeleteProject = async (deleteSessions: boolean) => {
    const { projectId } = deleteProjectConfirm;
    if (!projectId) return;
    setDeleteProjectConfirm((prev) => ({ ...prev, isOpen: false }));
    await projectManager.handleDeleteProject(projectId, {
      deleteSessions,
      onAfter: () => uncategorizedList.refresh(),
    });
  };

  // ─── New session in project ──────────────────────────────────────

  const handleNewSessionInProject = useCallback(
    (projectId: string) => {
      onSetPendingProjectId?.(projectId);
      onNewSession();
    },
    [onNewSession, onSetPendingProjectId],
  );

  // ─── Touch drag ───────────────────────────────────────────────────

  const touchDrag = useTouchDrag([], (sessionId, projectId) => {
    actions.handleMoveSessionRef.current(sessionId, projectId);
  });

  // ─── Favorites project ───────────────────────────────────────────

  const favoritesProject = useMemo(
    () => projects.find((p) => p.type === "favorites"),
    [projects],
  );

  const clearSelection = useCallback(() => {
    setSelectedSessionIds(new Set());
    setIsSelectionMode(false);
  }, []);

  // ─── Aggregated action objects ────────────────────────────────────

  const sessionActions: SessionActions = useMemo(
    () => ({
      onDeleteSession: (id) =>
        actions.setDeleteConfirm({ isOpen: true, sessionId: id }),
      onMoveSession: actions.handleMoveSession,
      onToggleFavorite: actions.handleToggleFavorite,
      onShareSession: actions.handleShareSession,
      onRequestBatchMoveSessions: (ids, projectId) =>
        actions.setBatchMoveConfirm({
          isOpen: true,
          sessionIds: ids,
          projectId,
        }),
      onRequestBatchDeleteSessions: (ids) =>
        actions.setBatchDeleteConfirm({ isOpen: true, sessionIds: ids }),
      onSelectSession: actions.selectAndClose,
      onDragStartTouch: touchDrag.handleDragStartTouch,
      draggingSessionId: touchDrag.draggingSessionId,
      touchDropTarget: touchDrag.touchDropTarget,
    }),
    [actions, touchDrag],
  );

  const projectActions: ProjectActions = useMemo(
    () => ({
      onRenameProject: projectManager.handleRenameProject,
      onDeleteProject: (id) => {
        const proj = projects.find((p) => p.id === id);
        setDeleteProjectConfirm({
          isOpen: true,
          projectId: id,
          projectName: proj?.name ?? "",
        });
      },
      onUpdateIcon: projectManager.handleUpdateIcon,
      onOpenProjectPluginOptions: setProjectOptionsProject,
      onOpenNewProjectModal: () => projectManager.setShowNewProjectModal(true),
      onNewSessionInProject: handleNewSessionInProject,
      onSetProjectRef: setProjectRef,
    }),
    [projectManager, projects, handleNewSessionInProject, setProjectRef],
  );

  const scheduledTaskActions: ScheduledTaskActions = useMemo(
    () => ({
      onSetScheduledTaskRef: setScheduledTaskRef,
    }),
    [setScheduledTaskRef],
  );

  // ─── Stable handlers (avoid new refs on every render) ─────────

  const handleImgError = useCallback(() => setImgError(true), []);
  const handleOpenSearch = useCallback(() => setIsSearchOpen(true), []);
  const handleToggleMoreMenu = useCallback(
    () => moreMenu.setIsMoreMenuOpen((prev) => !prev),
    [moreMenu],
  );
  const handleToggleProjectsCollapsed = useCallback(() => {
    setIsProjectsCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem(PROJECTS_COLLAPSED_STORAGE_KEY, String(next));
      authApi
        .updateMetadata({ projectsCollapsed: String(next) })
        .catch(() => {});
      return next;
    });
  }, []);
  const handleToggleScheduledTasksCollapsed = useCallback(() => {
    setIsScheduledTasksCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem(SCHEDULED_TASKS_COLLAPSED_STORAGE_KEY, String(next));
      authApi
        .updateMetadata({ scheduledTasksCollapsed: String(next) })
        .catch(() => {});
      return next;
    });
  }, []);
  const handleToggleChatsCollapsed = useCallback(() => {
    setIsChatsCollapsed((prev) => {
      const next = !prev;
      localStorage.setItem(CHATS_COLLAPSED_STORAGE_KEY, String(next));
      authApi.updateMetadata({ chatsCollapsed: String(next) }).catch(() => {});
      return next;
    });
  }, []);
  const handleToggleNavCollapsed = useCallback(
    () => setIsNavCollapsed((v) => !v),
    [],
  );

  // ─── Common SessionListContent props (memoized) ──────────────────

  const sessionListProps = useMemo(
    () => ({
      user,
      imgError,
      onImgError: handleImgError,
      onNewSession,
      onOpenSearch: handleOpenSearch,
      onShowProfile: onShowProfile!,
      hasMoreMenuItems: moreMenu.hasMoreMenuItems,
      onToggleMoreMenu: handleToggleMoreMenu,
      expandedMoreMenuBtnRef: moreMenu.expandedMoreMenuBtnRef,
      scrollEl,
      onSetScrollEl: setScrollEl,
      uncategorizedSessions: uncategorizedList.sessions,
      isUncategorizedLoading: uncategorizedList.isLoading,
      hasMoreUncategorized: uncategorizedList.hasMore,
      isLoadingMoreUncategorized: uncategorizedList.isLoadingMore,
      loadMoreRef: uncategorizedList.loadMoreRef,
      onSoftRefreshUncategorized: uncategorizedList.softRefresh,
      onUpdateUncategorizedSession: uncategorizedList.updateSession,
      projects,
      favoritesProject,
      currentSessionId,
      unreadBySession,
      sessionActions,
      projectActions,
      scheduledTaskActions,
      isProjectsCollapsed,
      onToggleProjectsCollapsed: handleToggleProjectsCollapsed,
      isScheduledTasksCollapsed,
      onToggleScheduledTasksCollapsed: handleToggleScheduledTasksCollapsed,
      isChatsCollapsed,
      onToggleChatsCollapsed: handleToggleChatsCollapsed,
      isNavCollapsed,
      onToggleNavCollapsed: handleToggleNavCollapsed,
      autoExpandProjectId: autoExpandProjectId ?? null,
      onConsumeAutoExpandProjectId: onConsumeAutoExpandProjectId!,
      onMarkAllRead: actions.handleMarkAllRead,
      markingReadId: actions.markingReadId,
      isSelectionMode,
      selectedSessionIds,
      onSetSelectionMode: setIsSelectionMode,
      onSetSelectedSessionIds: setSelectedSessionIds,
      onClearSelection: clearSelection,
    }),
    [
      user,
      imgError,
      handleImgError,
      onNewSession,
      handleOpenSearch,
      onShowProfile,
      moreMenu.hasMoreMenuItems,
      handleToggleMoreMenu,
      moreMenu.expandedMoreMenuBtnRef,
      scrollEl,
      setScrollEl,
      uncategorizedList.sessions,
      uncategorizedList.isLoading,
      uncategorizedList.hasMore,
      uncategorizedList.isLoadingMore,
      uncategorizedList.loadMoreRef,
      uncategorizedList.softRefresh,
      uncategorizedList.updateSession,
      projects,
      favoritesProject,
      currentSessionId,
      unreadBySession,
      sessionActions,
      projectActions,
      scheduledTaskActions,
      isProjectsCollapsed,
      handleToggleProjectsCollapsed,
      isScheduledTasksCollapsed,
      handleToggleScheduledTasksCollapsed,
      isChatsCollapsed,
      handleToggleChatsCollapsed,
      isNavCollapsed,
      handleToggleNavCollapsed,
      autoExpandProjectId,
      onConsumeAutoExpandProjectId,
      actions.handleMarkAllRead,
      actions.markingReadId,
      isSelectionMode,
      selectedSessionIds,
      setIsSelectionMode,
      setSelectedSessionIds,
      clearSelection,
    ],
  );

  // ─── JSX ──────────────────────────────────────────────────────────

  return (
    <>
      {/* Mobile overlay */}
      <div
        className={`fixed left-0 right-0 z-[60] bg-black/40 sm:hidden transition-opacity duration-300 ease-in-out ${
          mobileOpen ? "opacity-100" : "opacity-0 pointer-events-none"
        }`}
        style={{
          top: "var(--app-safe-area-top-active, var(--app-safe-area-top, 0px))",
          height:
            "calc(var(--app-viewport-height, 100dvh) - var(--app-safe-area-top-active, var(--app-safe-area-top, 0px)) - var(--app-safe-area-bottom-active, var(--app-safe-area-bottom, 0px)))",
        }}
        onClick={onMobileClose}
      />

      {/* Mobile drawer */}
      <div
        className={`rounded-r-lg fixed left-0 z-[70] w-64 flex flex-col sm:hidden bg-[var(--theme-bg-sidebar)] transition-transform duration-300 ease-in-out ${
          mobileOpen ? "translate-x-0" : "-translate-x-full"
        }`}
        style={{
          top: "var(--app-safe-area-top-active, var(--app-safe-area-top, 0px))",
          height:
            "calc(var(--app-viewport-height, 100dvh) - var(--app-safe-area-top-active, var(--app-safe-area-top, 0px)) - var(--app-safe-area-bottom-active, var(--app-safe-area-bottom, 0px)))",
          paddingBottom:
            "var(--app-safe-area-bottom-active, var(--app-safe-area-bottom, 0px))",
        }}
      >
        {isMobile ? (
          <SessionListContent
            {...sessionListProps}
            onCollapse={() => {
              setIsCollapsed(true);
              onMobileClose?.();
            }}
          />
        ) : (
          <div className="flex-1" />
        )}

        <MobileMoreMenuSheet
          featureItems={moreMenu.moreMenuFeatureItems}
          isOpen={moreMenu.isMoreMenuOpen}
          onClose={() => moreMenu.setIsMoreMenuOpen(false)}
          menuRef={moreMenu.moreMenuRef}
          swipeRef={moreMenu.moreMenuSwipeRef}
          dragHandleRef={moreMenu.moreMenuDragHandleRef}
        />
      </div>

      {/* Desktop sidebar */}
      <div
        className="hidden sm:flex h-full relative shrink-0 overflow-hidden"
        style={{
          width: isCollapsed
            ? "var(--sidebar-rail-width)"
            : "var(--sidebar-width)",
        }}
      >
        <div
          className={`h-full w-full flex flex-col bg-[var(--theme-bg-sidebar)] border-r border-stone-300/70 dark:border-stone-800/60 ${
            isCollapsed ? "hidden" : ""
          }`}
        >
          {!isMobile ? (
            <SessionListContent
              {...sessionListProps}
              onCollapse={() => setIsCollapsed(true)}
            />
          ) : (
            <div className="flex-1" />
          )}
        </div>

        {/* Collapsed rail */}
        <div
          className={`absolute inset-0 ${
            isCollapsed
              ? "opacity-100 pointer-events-auto"
              : "pointer-events-none opacity-0"
          }`}
        >
          <SidebarRail
            user={user}
            imgError={imgError}
            onImgError={() => setImgError(true)}
            onExpand={() => setIsCollapsed(false)}
            onNewSession={() => {
              onNewSession();
              // close recent chats if open (handled by state below)
            }}
            onOpenSearch={() => setIsSearchOpen(true)}
            onOpenRecentChats={() => setIsRecentChatsOpen(true)}
            onOpenFileLibrary={() => navigate("/files")}
            onOpenScheduledTasks={() => navigate("/scheduled-tasks")}
            hasMoreMenuItems={moreMenu.hasMoreMenuItems}
            onToggleMoreMenu={() => moreMenu.setIsMoreMenuOpen((prev) => !prev)}
            moreMenuBtnRef={moreMenu.moreMenuBtnRef}
            recentChatsBtnRef={recentChatsBtnRef}
            onShowProfile={onShowProfile!}
            unreadCount={totalUnreadCount}
          />
        </div>
      </div>

      {/* Touch drag indicator */}
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

      {/* Search dialog */}
      {isSearchOpen && (
        <SearchDialog
          isOpen={isSearchOpen}
          onClose={() => setIsSearchOpen(false)}
          onSelectSession={(sessionId) => {
            actions.selectAndClose(sessionId);
            setIsSearchOpen(false);
          }}
        />
      )}

      {/* Recent chats popover */}
      <RecentChatsDialog
        isOpen={isRecentChatsOpen}
        onClose={() => setIsRecentChatsOpen(false)}
        onSelectSession={(sessionId) => {
          onSelectSession(sessionId);
          setIsRecentChatsOpen(false);
        }}
        currentSessionId={currentSessionId}
        anchorEl={recentChatsBtnRef.current}
        unreadCount={totalUnreadCount}
        onMarkAllRead={actions.handleMarkAllRead}
        markingReadId={actions.markingReadId}
      />

      {/* Delete session confirmation */}
      <ConfirmDialog
        isOpen={actions.deleteConfirm.isOpen}
        title={t("sidebar.deleteSession")}
        message={t("sidebar.deleteConfirm")}
        confirmText={t("common.delete")}
        cancelText={t("common.cancel")}
        onConfirm={actions.confirmDeleteSession}
        onCancel={() =>
          actions.setDeleteConfirm({ isOpen: false, sessionId: null })
        }
        variant="danger"
      />

      {/* Batch move session confirmation */}
      <ConfirmDialog
        isOpen={actions.batchMoveConfirm.isOpen}
        title={t("sidebar.moveSelectedSessions")}
        message={t("sidebar.batchMoveConfirm", {
          count: actions.batchMoveConfirm.sessionIds.length,
          project:
            actions.batchMoveConfirm.projectId === null
              ? t("sidebar.uncategorized")
              : projects.find(
                  (p) => p.id === actions.batchMoveConfirm.projectId,
                )?.name || t("sidebar.projects"),
        })}
        confirmText={t("sidebar.moveToProject")}
        cancelText={t("common.cancel")}
        onConfirm={async () => {
          await actions.confirmBatchMoveSessions();
          clearSelection();
        }}
        onCancel={() =>
          actions.setBatchMoveConfirm({
            isOpen: false,
            sessionIds: [],
            projectId: null,
          })
        }
      />

      {/* Batch delete session confirmation */}
      <ConfirmDialog
        isOpen={actions.batchDeleteConfirm.isOpen}
        title={t("sidebar.deleteSelectedSessions")}
        message={t("sidebar.batchDeleteConfirm", {
          count: actions.batchDeleteConfirm.sessionIds.length,
        })}
        confirmText={t("common.delete")}
        cancelText={t("common.cancel")}
        onConfirm={async () => {
          await actions.confirmBatchDeleteSessions();
          clearSelection();
        }}
        onCancel={() =>
          actions.setBatchDeleteConfirm({ isOpen: false, sessionIds: [] })
        }
        variant="danger"
      />

      {/* Delete project confirmation */}
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

      {/* New project modal */}
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

      <ProjectPluginOptionsModal
        project={projectOptionsProject}
        onClose={() => setProjectOptionsProject(null)}
      />

      {/* Share dialog */}
      <ShareDialog
        isOpen={actions.shareDialogSessionId !== null}
        onClose={() => actions.setShareDialogSessionId(null)}
        sessionId={actions.shareDialogSessionId ?? ""}
        sessionName={actions.shareDialogSessionName || t("sidebar.newChat")}
      />

      {/* Desktop more menu */}
      {!isMobile && (
        <DesktopMoreMenu
          featureItems={moreMenu.moreMenuFeatureItems}
          isOpen={moreMenu.isMoreMenuOpen && moreMenu.moreMenuPosition !== null}
          onClose={() => moreMenu.setIsMoreMenuOpen(false)}
          menuRef={moreMenu.moreMenuRef}
          position={moreMenu.moreMenuPosition}
        />
      )}
    </>
  );
});
