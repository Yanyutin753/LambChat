/**
 * Session sidebar component for displaying and managing chat history.
 * Each project independently loads its sessions with per-project pagination.
 */

import {
  useState,
  useEffect,
  useRef,
  useCallback,
  useMemo,
  forwardRef,
  useImperativeHandle,
} from "react";
import { useLocation } from "react-router-dom";
import toast from "react-hot-toast";
import { useTranslation } from "react-i18next";
import { Users, Shield, Bot, Cpu, Star, Bell, Settings } from "lucide-react";
import { sessionApi, type BackendSession } from "../../services/api";
import { useAuth } from "../../hooks/useAuth";
import { Permission } from "../../types";
import { useProjectSessionList } from "../../hooks/useSession";
import { useProjectManager } from "../../hooks/useProjectManager";
import { useTouchDrag } from "../../hooks/useTouchDrag";
import { useSwipeToClose } from "../../hooks/useSwipeToClose";
import { ConfirmDialog } from "../common/ConfirmDialog";
import { DeleteProjectDialog } from "../common/DeleteProjectDialog";
import type { ProjectItemHandle } from "../sidebar/ProjectItem";
import { RecentChatsDialog } from "../sidebar/RecentChatsDialog";
import {
  mergeUnreadUpdate,
  type UnreadBySession,
} from "../sidebar/unreadCounts";
import { isSessionFavorite } from "../sidebar/sessionFavorites";
import { getSessionTitle } from "./sessionHelpers";
import { SearchDialog } from "./SearchDialog";
import { ShareDialog } from "../share/ShareDialog";
import { NewProjectModal } from "./NewProjectModal";
import {
  SessionListContent,
  SidebarRail,
  MobileMoreMenuSheet,
  DesktopMoreMenu,
} from "./SidebarParts";
import type { SessionActions, ProjectActions } from "./SidebarParts";

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
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [imgError, setImgError] = useState(false);
  const [internalCollapsed, setInternalCollapsed] = useState(true);
  const [isProjectsCollapsed, setIsProjectsCollapsed] = useState(false);
  const [isChatsCollapsed, setIsChatsCollapsed] = useState(false);
  const [scrollEl, setScrollEl] = useState<HTMLDivElement | null>(null);
  const [unreadBySession, setUnreadBySession] = useState<UnreadBySession>(
    () => new Map(),
  );
  const [shareDialogSessionId, setShareDialogSessionId] = useState<
    string | null
  >(null);
  const [shareDialogSessionName, setShareDialogSessionName] = useState("");
  const [isRecentChatsOpen, setIsRecentChatsOpen] = useState(false);
  const [isMoreMenuOpen, setIsMoreMenuOpen] = useState(false);
  const [moreMenuPosition, setMoreMenuPosition] = useState({ top: 0, left: 0 });
  const { hasAnyPermission } = useAuth();

  const canManageUsers = hasAnyPermission([
    Permission.USER_READ,
    Permission.USER_WRITE,
  ]);
  const canManageRoles = hasAnyPermission([Permission.ROLE_MANAGE]);
  const canManageAgents = hasAnyPermission([Permission.AGENT_READ]);
  const canManageModels = hasAnyPermission([Permission.MODEL_ADMIN]);
  const canViewFeedback = hasAnyPermission([Permission.FEEDBACK_READ]);
  const canManageNotifications = hasAnyPermission([
    Permission.NOTIFICATION_MANAGE,
  ]);
  const canManageSettings = hasAnyPermission([Permission.SETTINGS_MANAGE]);

  const moreMenuUserItems = [
    {
      path: "/users",
      label: t("nav.users"),
      icon: Users,
      show: canManageUsers,
    },
    {
      path: "/roles",
      label: t("nav.roles"),
      icon: Shield,
      show: canManageRoles,
    },
    {
      path: "/agents",
      label: t("nav.agents"),
      icon: Bot,
      show: canManageAgents,
    },
    {
      path: "/models",
      label: t("nav.models"),
      icon: Cpu,
      show: canManageModels,
    },
  ];

  const moreMenuSysItems = [
    {
      path: "/feedback",
      label: t("nav.feedback"),
      icon: Star,
      show: canViewFeedback,
    },
    {
      path: "/notifications",
      label: t("nav.notifications"),
      icon: Bell,
      show: canManageNotifications,
    },
    {
      path: "/settings",
      label: t("nav.systemSettings"),
      icon: Settings,
      show: canManageSettings,
    },
  ];

  const hasMoreMenuItems =
    moreMenuUserItems.some((i) => i.show) ||
    moreMenuSysItems.some((i) => i.show);

  const [isMobile, setIsMobile] = useState(
    () => window.matchMedia("(max-width: 639px)").matches,
  );

  const moreMenuRef = useRef<HTMLDivElement>(null);
  const moreMenuBtnRef = useRef<HTMLButtonElement>(null);
  const expandedMoreMenuBtnRef = useRef<HTMLButtonElement>(null);
  const moreMenuSwipeRef = useSwipeToClose({
    onClose: () => setIsMoreMenuOpen(false),
    enabled: isMoreMenuOpen && isMobile,
  });
  const location = useLocation();

  useEffect(() => {
    const mq = window.matchMedia("(max-width: 639px)");
    const handler = (e: MediaQueryListEvent) => setIsMobile(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, []);

  useEffect(() => {
    if (!isMoreMenuOpen) return;
    const handleClickOutside = (e: MouseEvent) => {
      if (activeMoreMenuBtnRef.current?.contains(e.target as Node)) return;
      if (moreMenuRef.current?.contains(e.target as Node)) return;
      setIsMoreMenuOpen(false);
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isMoreMenuOpen]);

  useEffect(() => {
    if (isMoreMenuOpen) setIsMoreMenuOpen(false);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);

  const handleNewSessionInProject = useCallback(
    (projectId: string) => {
      onSetPendingProjectId?.(projectId);
      onNewSession();
    },
    [onNewSession, onSetPendingProjectId],
  );

  const isCollapsed = externalCollapsed ?? internalCollapsed;
  const setIsCollapsed = onToggleCollapsed ?? setInternalCollapsed;
  const activeMoreMenuBtnRef = isCollapsed
    ? moreMenuBtnRef
    : expandedMoreMenuBtnRef;

  useEffect(() => {
    if (!isMoreMenuOpen || !activeMoreMenuBtnRef.current) return;
    const rect = activeMoreMenuBtnRef.current.getBoundingClientRect();
    const panelWidth = 208;
    const panelMaxHeight = 480;
    let top = rect.top;
    let left = rect.right + 2;
    if (left + panelWidth > window.innerWidth)
      left = window.innerWidth - panelWidth - 8;
    if (left < 8) left = 8;
    if (top + panelMaxHeight > window.innerHeight)
      top = window.innerHeight - panelMaxHeight - 8;
    if (top < 8) top = 8;
    setMoreMenuPosition({ top, left });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isMoreMenuOpen, isCollapsed]);

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
            const fp = projects.find((p) => p.type === "favorites");
            if (fp) getProjectRef(fp.id)?.prependSession(response.session);
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

        if (uncategorizedList.sessions.some((s) => s.id === sessionId)) {
          uncategorizedList.updateSession(updatedSession);
        }
        for (const [, handle] of projectRefs.current) {
          const exists = handle.sessions.some((s) => s.id === sessionId);
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
    if (autoExpandProjectId) setIsProjectsCollapsed(false);
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
      if (lastAppliedNewSessionKeyRef.current === sessionKey) return;
      const projectId = newSession.metadata?.project_id as string | undefined;
      const list = projectId ? getProjectRef(projectId) : uncategorizedList;
      if (list) {
        list.prependSession(newSession);
        list.updateSession(newSession);
      }
      if (isSessionFavorite(newSession)) {
        const fp = projects.find((p) => p.type === "favorites");
        if (fp) {
          const favRef = getProjectRef(fp.id);
          favRef?.prependSession(newSession);
          favRef?.updateSession(newSession);
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

  const selectAndClose = useCallback(
    (sessionId: string) => {
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
    },
    [uncategorizedList, handleSessionUnread, onSelectSession, onMobileClose],
  );

  // ─── Aggregated action objects for SessionListContent ────────────

  const sessionActions: SessionActions = useMemo(
    () => ({
      onDeleteSession: (id) =>
        setDeleteConfirm({ isOpen: true, sessionId: id }),
      onMoveSession: handleMoveSession,
      onToggleFavorite: handleToggleFavorite,
      onShareSession: handleShareSession,
      onSelectSession: selectAndClose,
      onDragStartTouch: touchDrag.handleDragStartTouch,
      draggingSessionId: touchDrag.draggingSessionId,
      touchDropTarget: touchDrag.touchDropTarget,
    }),
    [
      handleMoveSession,
      handleToggleFavorite,
      handleShareSession,
      selectAndClose,
      touchDrag,
    ],
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
      onOpenNewProjectModal: () => projectManager.setShowNewProjectModal(true),
      onNewSessionInProject: handleNewSessionInProject,
      onSetProjectRef: setProjectRef,
    }),
    [projectManager, projects, handleNewSessionInProject, setProjectRef],
  );

  const favoritesProject = useMemo(
    () => projects.find((p) => p.type === "favorites"),
    [projects],
  );

  // ─── JSX ────────────────────────────────────────────────────────

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
        {isMobile ? (
          <SessionListContent
            user={user}
            imgError={imgError}
            onImgError={() => setImgError(true)}
            onCollapse={() => {
              setIsCollapsed(true);
              onMobileClose?.();
            }}
            onNewSession={onNewSession}
            onOpenSearch={() => setIsSearchOpen(true)}
            onShowProfile={onShowProfile!}
            hasMoreMenuItems={hasMoreMenuItems}
            onToggleMoreMenu={() => setIsMoreMenuOpen((prev) => !prev)}
            expandedMoreMenuBtnRef={expandedMoreMenuBtnRef}
            scrollEl={scrollEl}
            onSetScrollEl={setScrollEl}
            uncategorizedSessions={uncategorizedList.sessions}
            isUncategorizedLoading={uncategorizedList.isLoading}
            hasMoreUncategorized={uncategorizedList.hasMore}
            isLoadingMoreUncategorized={uncategorizedList.isLoadingMore}
            loadMoreRef={uncategorizedList.loadMoreRef}
            onSoftRefreshUncategorized={uncategorizedList.softRefresh}
            onUpdateUncategorizedSession={uncategorizedList.updateSession}
            projects={projects}
            favoritesProject={favoritesProject}
            currentSessionId={currentSessionId}
            unreadBySession={unreadBySession}
            sessionActions={sessionActions}
            projectActions={projectActions}
            isProjectsCollapsed={isProjectsCollapsed}
            onToggleProjectsCollapsed={() => setIsProjectsCollapsed((v) => !v)}
            isChatsCollapsed={isChatsCollapsed}
            onToggleChatsCollapsed={() => setIsChatsCollapsed((v) => !v)}
            autoExpandProjectId={autoExpandProjectId ?? null}
            onConsumeAutoExpandProjectId={onConsumeAutoExpandProjectId!}
          />
        ) : (
          <div className="flex-1" />
        )}

        <MobileMoreMenuSheet
          userItems={moreMenuUserItems}
          sysItems={moreMenuSysItems}
          isOpen={isMoreMenuOpen}
          onClose={() => setIsMoreMenuOpen(false)}
          menuRef={moreMenuRef}
          swipeRef={moreMenuSwipeRef}
        />
      </div>

      {/* Desktop: always render sidebar container */}
      <div
        className="hidden sm:flex h-full relative shrink-0 overflow-hidden"
        style={{
          width: isCollapsed
            ? "var(--sidebar-rail-width)"
            : "var(--sidebar-width)",
        }}
      >
        <div
          className={`h-full w-full flex flex-col bg-[var(--theme-bg-sidebar)] border-r border-stone-200/60 dark:border-stone-800/60 ${
            isCollapsed ? "hidden" : ""
          }`}
        >
          {!isMobile ? (
            <SessionListContent
              user={user}
              imgError={imgError}
              onImgError={() => setImgError(true)}
              onCollapse={() => setIsCollapsed(true)}
              onNewSession={onNewSession}
              onOpenSearch={() => setIsSearchOpen(true)}
              onShowProfile={onShowProfile!}
              hasMoreMenuItems={hasMoreMenuItems}
              onToggleMoreMenu={() => setIsMoreMenuOpen((prev) => !prev)}
              expandedMoreMenuBtnRef={expandedMoreMenuBtnRef}
              scrollEl={scrollEl}
              onSetScrollEl={setScrollEl}
              uncategorizedSessions={uncategorizedList.sessions}
              isUncategorizedLoading={uncategorizedList.isLoading}
              hasMoreUncategorized={uncategorizedList.hasMore}
              isLoadingMoreUncategorized={uncategorizedList.isLoadingMore}
              loadMoreRef={uncategorizedList.loadMoreRef}
              onSoftRefreshUncategorized={uncategorizedList.softRefresh}
              onUpdateUncategorizedSession={uncategorizedList.updateSession}
              projects={projects}
              favoritesProject={favoritesProject}
              currentSessionId={currentSessionId}
              unreadBySession={unreadBySession}
              sessionActions={sessionActions}
              projectActions={projectActions}
              isProjectsCollapsed={isProjectsCollapsed}
              onToggleProjectsCollapsed={() =>
                setIsProjectsCollapsed((v) => !v)
              }
              isChatsCollapsed={isChatsCollapsed}
              onToggleChatsCollapsed={() => setIsChatsCollapsed((v) => !v)}
              autoExpandProjectId={autoExpandProjectId ?? null}
              onConsumeAutoExpandProjectId={onConsumeAutoExpandProjectId!}
            />
          ) : (
            <div className="flex-1" />
          )}
        </div>

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
            onNewSession={onNewSession}
            onOpenSearch={() => setIsSearchOpen(true)}
            onOpenRecentChats={() => setIsRecentChatsOpen(true)}
            hasMoreMenuItems={hasMoreMenuItems}
            onToggleMoreMenu={() => setIsMoreMenuOpen((prev) => !prev)}
            moreMenuBtnRef={moreMenuBtnRef}
            recentChatsBtnRef={recentChatsBtnRef}
            onShowProfile={onShowProfile!}
          />
        </div>
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

      <RecentChatsDialog
        isOpen={isRecentChatsOpen}
        onClose={() => setIsRecentChatsOpen(false)}
        onSelectSession={(id) => selectAndClose(id)}
        currentSessionId={currentSessionId}
        anchorEl={recentChatsBtnRef.current}
      />

      <DesktopMoreMenu
        userItems={moreMenuUserItems}
        sysItems={moreMenuSysItems}
        isOpen={isMoreMenuOpen}
        onClose={() => setIsMoreMenuOpen(false)}
        menuRef={moreMenuRef}
        position={moreMenuPosition}
      />
    </>
  );
});
