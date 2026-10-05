import { SidebarToggleIcon } from "../../common/SidebarToggleIcon";
import { useCallback, useMemo, useState } from "react";
import {
  Search,
  FolderOpen,
  SquarePen,
  MoreHorizontal,
  CalendarClock,
  FolderInput,
  ListChecks,
  Tag,
  Trash2,
  X,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../../../hooks/useAuth";
import { Permission } from "../../../types/auth";
import { LoadingSpinner } from "../../common/LoadingSpinner";
import { Tooltip } from "../../common/Tooltip";
import { SkeletonList } from "../../skeletons";
import { BrandWordmark } from "../../common/BrandWordmark";
import { BrandLogo } from "../../common/BrandLogo";
import { SidebarSectionHeader } from "./SidebarSectionHeader";
import { sectionActionClass, sectionRevealClass } from "./SidebarSectionHeader";
import { SidebarUserRow } from "./SidebarUserRow";
import type { BackendSession } from "../../../services/api";
import type { ProjectItemHandle } from "../../sidebar/ProjectItem";
import {
  getUnreadCountForUncategorized,
  type UnreadBySession,
} from "../../sidebar/unreadCounts";
import { MarkAllReadBadge } from "../../sidebar/MarkAllReadBadge";
import { ProjectItem } from "../../sidebar/ProjectItem";
import { SessionItem } from "../../sidebar/SessionItem";
import { APP_NAME, GITHUB_URL } from "../../../constants";
import { isSessionFavorite } from "../../sidebar/sessionFavorites";
import { isSessionPinned } from "../../sidebar/sessionPin";
import type { Project } from "../../../types";
import { isSidebarProject } from "./projectFilters";
import {
  isEveryVisibleSessionSelected,
  toggleAllVisibleSessions,
  toggleSessionSelection,
} from "../../sidebar/sessionSelection";

export interface SessionActions {
  onDeleteSession: (id: string) => void;
  onMoveSession: (id: string, projectId: string | null) => void;
  onToggleFavorite: (id: string) => void;
  onTogglePin: (id: string) => void;
  onPinSession: (id: string) => void;
  onShareSession: (id: string) => void;
  onRequestBatchMoveSessions: (ids: string[], projectId: string | null) => void;
  onRequestBatchDeleteSessions: (ids: string[]) => void;
  onSelectSession: (id: string) => void;
  onDragStartTouch: (
    sessionId: string,
    clientX: number,
    clientY: number,
  ) => void;
  draggingSessionId: string | null;
  touchDropTarget: string | null;
}

export interface ProjectActions {
  onRenameProject: (id: string, name: string) => void;
  onDeleteProject: (id: string) => void;
  onShareProject?: (id: string) => void;
  onUpdateIcon: (id: string, icon: string) => void;
  onUpdateWorkspace?: (
    id: string,
    workspace: Project["workspace"],
  ) => Promise<void>;
  onOpenNewProjectModal: () => void;
  onNewSessionInProject: (projectId: string) => void;
  onSetProjectRef: (id: string, handle: ProjectItemHandle | null) => void;
}

interface SessionListContentProps {
  user: { username?: string; avatar_url?: string; roles?: string[] } | null;
  imgError: boolean;
  onImgError: () => void;
  onCollapse: () => void;
  /**
   * 桌面双栏（DesktopSidebarShell）模式：隐藏品牌头部与操作行——入口已由
   * ActivityRail 承接，二级面板只保留列表主体（列表区顶部补回 padding）。
   */
  compactChrome?: boolean;
  onNewSession: () => void;
  onOpenSearch: () => void;
  onShowProfile: () => void;
  hasMoreMenuItems: boolean;
  singleMoreMenuItem?: { label: string; icon: typeof MoreHorizontal };
  onToggleMoreMenu: () => void;
  expandedMoreMenuBtnRef: React.RefObject<HTMLButtonElement | null>;
  scrollEl: HTMLDivElement | null;
  onSetScrollEl: (el: HTMLDivElement | null) => void;
  uncategorizedSessions: BackendSession[];
  isUncategorizedLoading: boolean;
  hasMoreUncategorized: boolean;
  isLoadingMoreUncategorized: boolean;
  loadMoreRef: React.RefCallback<HTMLElement>;
  onSoftRefreshUncategorized: () => void;
  onUpdateUncategorizedSession: (s: BackendSession) => void;
  /** 「置顶」分类：跨项目聚合的置顶会话 */
  pinnedSessions: BackendSession[];
  isPinnedLoading: boolean;
  hasMorePinned: boolean;
  isLoadingMorePinned: boolean;
  pinnedLoadMoreRef: React.RefCallback<HTMLElement>;
  onUpdatePinnedSession: (s: BackendSession) => void;
  isPinnedCollapsed: boolean;
  onTogglePinnedCollapsed: () => void;
  projects: Project[];
  favoritesProject: Project | undefined;
  currentSessionId: string | null;
  unreadBySession: UnreadBySession;
  sessionActions: SessionActions;
  projectActions: ProjectActions;
  isProjectsCollapsed: boolean;
  onToggleProjectsCollapsed: () => void;
  isNavCollapsed: boolean;
  onToggleNavCollapsed: () => void;
  isChatsCollapsed: boolean;
  onToggleChatsCollapsed: () => void;
  autoExpandProjectId: string | null | undefined;
  onConsumeAutoExpandProjectId: (id: string) => void;
  onMarkAllRead: (opts?: {
    projectId?: string;
    scheduledTaskId?: string;
  }) => Promise<void> | void;
  markingReadId: string | null;
  isSelectionMode: boolean;
  selectedSessionIds: Set<string>;
  onSetSelectionMode: (enabled: boolean) => void;
  onSetSelectedSessionIds: React.Dispatch<React.SetStateAction<Set<string>>>;
  onClearSelection: () => void;
}

export function SessionListContent({
  user,
  imgError,
  onImgError: _onImgError,
  onCollapse,
  compactChrome = false,
  onNewSession,
  onOpenSearch,
  onShowProfile,
  hasMoreMenuItems,
  singleMoreMenuItem,
  onToggleMoreMenu,
  expandedMoreMenuBtnRef,
  scrollEl,
  onSetScrollEl,
  uncategorizedSessions,
  isUncategorizedLoading,
  hasMoreUncategorized,
  isLoadingMoreUncategorized,
  loadMoreRef,
  onUpdateUncategorizedSession,
  pinnedSessions,
  isPinnedLoading,
  hasMorePinned,
  isLoadingMorePinned,
  pinnedLoadMoreRef,
  onUpdatePinnedSession,
  isPinnedCollapsed,
  onTogglePinnedCollapsed,
  projects,
  favoritesProject,
  currentSessionId,
  unreadBySession,
  sessionActions,
  projectActions,
  isProjectsCollapsed,
  onToggleProjectsCollapsed,
  isChatsCollapsed,
  onToggleChatsCollapsed,
  autoExpandProjectId,
  onConsumeAutoExpandProjectId,
  onMarkAllRead,
  markingReadId,
  isSelectionMode,
  selectedSessionIds,
  onSetSelectionMode,
  onSetSelectedSessionIds,
  onClearSelection,
}: SessionListContentProps) {
  const { t } = useTranslation();
  const MoreIcon = singleMoreMenuItem?.icon ?? MoreHorizontal;
  const moreLabel = singleMoreMenuItem?.label ?? t("nav.more", "更多");
  const navigate = useNavigate();
  const { hasPermission } = useAuth();
  const canReadScheduledTasks = hasPermission(Permission.SCHEDULED_TASK_READ);
  const [isPinnedDragOver, setIsPinnedDragOver] = useState(false);
  const [isProjectPickerOpen, setIsProjectPickerOpen] = useState(false);

  const visibleUncategorizedSessions = useMemo(
    () =>
      uncategorizedSessions.filter(
        (session) =>
          !session.metadata?.scheduled_task_id && !isSessionPinned(session),
      ),
    [uncategorizedSessions],
  );
  const chatsUnreadCount = getUnreadCountForUncategorized({
    loadedSessions: visibleUncategorizedSessions,
    unreadBySession,
  });
  const visibleUncategorizedIds = useMemo(
    () =>
      visibleUncategorizedSessions
        .filter((session) => session.id && !isSessionPinned(session))
        .map((session) => session.id),
    [visibleUncategorizedSessions],
  );
  const allVisibleSelected = isEveryVisibleSessionSelected(
    selectedSessionIds,
    visibleUncategorizedIds,
  );
  const selectedCount = selectedSessionIds.size;
  const selectedIds = useMemo(
    () => Array.from(selectedSessionIds),
    [selectedSessionIds],
  );
  const customProjects = useMemo(
    () =>
      projects
        .filter(isSidebarProject)
        .sort((a, b) => a.sort_order - b.sort_order),
    [projects],
  );
  const handleToggleSelectionMode = useCallback(() => {
    if (isSelectionMode) {
      onClearSelection();
    } else {
      onSetSelectionMode(true);
    }
  }, [isSelectionMode, onClearSelection, onSetSelectionMode]);

  const handleToggleAllVisible = useCallback(() => {
    onSetSelectedSessionIds((prev) =>
      toggleAllVisibleSessions(prev, visibleUncategorizedIds),
    );
  }, [onSetSelectedSessionIds, visibleUncategorizedIds]);

  const handleToggleSessionSelected = useCallback(
    (sessionId: string) => {
      onSetSelectedSessionIds((prev) =>
        toggleSessionSelection(prev, sessionId),
      );
    },
    [onSetSelectedSessionIds],
  );

  const handleMoveSelected = useCallback(
    (projectId: string | null) => {
      if (selectedIds.length === 0) return;
      setIsProjectPickerOpen(false);
      sessionActions.onRequestBatchMoveSessions(selectedIds, projectId);
    },
    [selectedIds, sessionActions],
  );

  const handleRequestDeleteSelected = useCallback(() => {
    if (selectedIds.length === 0) return;
    setIsProjectPickerOpen(false);
    sessionActions.onRequestBatchDeleteSessions(selectedIds);
  }, [selectedIds, sessionActions]);

  const selectModeButton = !isSelectionMode && (
    <Tooltip content={t("sidebar.selectMode")}>
      <button
        type="button"
        onClick={handleToggleSelectionMode}
        aria-label={t("sidebar.selectMode")}
        className={`${sectionActionClass} ${sectionRevealClass}`}
      >
        <ListChecks size={14} />
      </button>
    </Tooltip>
  );

  return (
    <>
      {/* Header（桌面双栏模式下品牌与折叠由 ActivityRail 承接，不渲染） */}
      {!compactChrome && (
        <div
          data-sidebar-brand=""
          className="flex h-12 shrink-0 items-center justify-between px-3"
        >
          <div className="flex size-7 items-center gap-1.5">
            <BrandLogo alt={APP_NAME} className="size-7 mb-1" />
            <a
              aria-label={APP_NAME}
              href={GITHUB_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="text-theme-text dark:text-stone-100 hover:text-theme-text dark:hover:text-stone-50 transition-colors"
            >
              <BrandWordmark decorative className="size-7 w-auto" />
            </a>
          </div>
          <Tooltip content={t("sidebar.collapseSidebar")}>
            <button
              type="button"
              onClick={onCollapse}
              className="flex size-8 items-center justify-center rounded-lg text-theme-text-secondary dark:text-stone-400 transition-colors cursor-w-resize rtl:cursor-e-resize"
              aria-label={t("sidebar.collapseSidebar")}
            >
              <SidebarToggleIcon mobileFilled className="size-5 text-theme-text-secondary dark:text-stone-300" />
            </button>
          </Tooltip>
        </div>
      )}
      {/* 桌面壳仅保留新建对话，其余入口由顶栏和最左侧导航承接。 */}
      <div
        className={
          compactChrome
            ? "flex flex-col gap-0 sm:gap-px px-1 pt-1 mb-2 space-y-0 sm:space-y-1"
            : "flex flex-col gap-0 sm:gap-px px-1 mb-2 space-y-0 sm:space-y-1"
        }
      >
        <button
          onClick={onNewSession}
          className="sidebar-nav-btn w-full h-8 rounded-[10px] flex items-center gap-3 px-[9px] focus:outline-none transition-colors group"
        >
          <SquarePen size={compactChrome ? 19 : 20} />
          <span className="flex-1 text-left">{t("sidebar.newChat")}</span>
          <kbd className="hidden sm:inline-flex items-center gap-0.5 px-1.5 py-0.5 text-10 font-medium text-theme-text-tertiary dark:text-stone-500 rounded opacity-0 group-hover:opacity-100 transition-opacity">
            {t("sidebar.newChatShortcut")}
          </kbd>
        </button>

        {!compactChrome && (
          <button
            onClick={onOpenSearch}
            className="sidebar-nav-btn w-full h-8 rounded-[10px] flex items-center gap-3 px-[9px] focus:outline-none transition-colors group"
          >
            <Search size={20} />
            <span className="flex-1 text-left">
              {t("sidebar.searchSessions")}
            </span>
            <kbd
              className="hidden sm:inline-flex items-center gap-0.5 px-1.5 py-0.5 text-10 font-medium rounded opacity-0 group-hover:opacity-100 transition-opacity"
              style={{ color: "var(--theme-text-tertiary)" }}
            >
              ⌘K
            </kbd>
          </button>
        )}

        {!compactChrome && canReadScheduledTasks && (
          <button
            onClick={() => navigate("/scheduled-tasks")}
            className="sidebar-nav-btn w-full h-8 rounded-[10px] flex items-center gap-3 px-[9px] focus:outline-none transition-colors"
          >
            <CalendarClock size={20} />
            <span>{t("nav.scheduled-tasks")}</span>
          </button>
        )}

        {!compactChrome && (
          <button
            onClick={() => navigate("/files")}
            className="sidebar-nav-btn w-full h-8 rounded-[10px] flex items-center gap-3 px-[9px] focus:outline-none transition-colors"
          >
            <FolderOpen size={20} />
            <span>{t("fileLibrary.title")}</span>
          </button>
        )}

        {!compactChrome && hasMoreMenuItems && (
          <div className="relative">
            <button
              ref={expandedMoreMenuBtnRef}
              onClick={onToggleMoreMenu}
              className="sidebar-nav-btn w-full h-8 rounded-[10px] flex items-center gap-3 px-[9px] focus:outline-none transition-colors"
            >
              <MoreIcon size={20} />
              <span className="flex-1 text-left">{moreLabel}</span>
            </button>
          </div>
        )}
      </div>

      {/* Session list */}
      <div
        ref={onSetScrollEl}
        data-sidebar-scroll
        className="flex-1 overflow-y-auto px-1 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        <div className="flex flex-col gap-px">
          {/* Pinned sessions (aggregated across projects) */}
          <div
            data-pinned-drop
            onDragOver={(event) => {
              if (
                !event.dataTransfer.types.includes(
                  "application/x-lambchat-session",
                )
              )
                return;
              event.preventDefault();
              event.dataTransfer.dropEffect = "move";
              setIsPinnedDragOver(true);
            }}
            onDragLeave={(event) => {
              if (!event.currentTarget.contains(event.relatedTarget as Node))
                setIsPinnedDragOver(false);
            }}
            onDrop={(event) => {
              event.preventDefault();
              setIsPinnedDragOver(false);
              const sessionId = event.dataTransfer.getData(
                "application/x-lambchat-session",
              );
              if (sessionId) sessionActions.onPinSession(sessionId);
            }}
            className={
              isPinnedDragOver || sessionActions.touchDropTarget === "pinned"
                ? "rounded-[10px] bg-theme-border/60 dark:bg-stone-700/40 ring-1 ring-inset ring-theme-border-hover dark:ring-stone-600"
                : undefined
            }
          >
            <SidebarSectionHeader
              label={t("sidebar.pinnedChats")}
              collapsed={isPinnedCollapsed}
              onToggle={onTogglePinnedCollapsed}
              createLabel={t("sidebar.newChat")}
            >
              {selectModeButton}
            </SidebarSectionHeader>
            {!isPinnedCollapsed && (
              <>
                {isPinnedLoading ? (
                  <SkeletonList count={3} compact />
                ) : (
                  <div className="flex flex-col gap-px">
                    {pinnedSessions
                      .filter((session) => session.id)
                      .map((session) => (
                        <SessionItem
                          key={session.id}
                          session={session}
                          isActive={currentSessionId === session.id}
                          projects={projects}
                          onSelect={() =>
                            sessionActions.onSelectSession(session.id)
                          }
                          onDelete={() =>
                            sessionActions.onDeleteSession(session.id)
                          }
                          onMoveToProject={(projectId) =>
                            sessionActions.onMoveSession(session.id, projectId)
                          }
                          currentProjectId={
                            (session.metadata?.project_id as
                              string | null | undefined) ?? null
                          }
                          onShare={() =>
                            sessionActions.onShareSession(session.id)
                          }
                          onToggleFavorite={() =>
                            sessionActions.onToggleFavorite(session.id)
                          }
                          onDragStartTouch={sessionActions.onDragStartTouch}
                          isDraggingTouch={
                            sessionActions.draggingSessionId === session.id
                          }
                          onSessionUpdate={onUpdatePinnedSession}
                          isFavorite={isSessionFavorite(session)}
                          onTogglePin={() =>
                            sessionActions.onTogglePin(session.id)
                          }
                          isPinned={isSessionPinned(session)}
                          selectionMode={isSelectionMode}
                          isSelected={selectedSessionIds.has(session.id)}
                          onToggleSelected={() =>
                            handleToggleSessionSelected(session.id)
                          }
                        />
                      ))}
                  </div>
                )}
                {hasMorePinned && (
                  <div
                    ref={pinnedLoadMoreRef}
                    className="flex justify-center py-2"
                  >
                    {isLoadingMorePinned && (
                      <div className="flex items-center gap-2 text-theme-text-tertiary dark:text-stone-500">
                        <LoadingSpinner size="xs" />
                        <span className="text-12">{t("common.loading")}</span>
                      </div>
                    )}
                  </div>
                )}
              </>
            )}
          </div>

          {/* Project section header */}
          <SidebarSectionHeader
            label={t("sidebar.projects")}
            collapsed={isProjectsCollapsed}
            onToggle={onToggleProjectsCollapsed}
            createLabel={t("sidebar.newProject")}
            onCreate={projectActions.onOpenNewProjectModal}
          >
            {selectModeButton}
          </SidebarSectionHeader>

          {/* Favorites project */}
          {!isProjectsCollapsed &&
            favoritesProject &&
            (() => {
              const fp = favoritesProject;
              return (
                <ProjectItem
                  ref={(el) => projectActions.onSetProjectRef(fp.id, el)}
                  project={fp}
                  currentSessionId={currentSessionId}
                  allProjects={projects}
                  onSelectSession={sessionActions.onSelectSession}
                  onDeleteSession={sessionActions.onDeleteSession}
                  onMoveSession={sessionActions.onMoveSession}
                  onToggleFavorite={sessionActions.onToggleFavorite}
                  onTogglePin={sessionActions.onTogglePin}
                  onShareSession={sessionActions.onShareSession}
                  onShareProject={projectActions.onShareProject}
                  onRenameProject={projectActions.onRenameProject}
                  onDeleteProject={projectActions.onDeleteProject}
                  onUpdateIcon={projectActions.onUpdateIcon}
                  scrollRoot={scrollEl}
                  draggingSessionId={
                    sessionActions.touchDropTarget === fp.id
                      ? sessionActions.draggingSessionId
                      : null
                  }
                  unreadBySession={unreadBySession}
                  favoritesOnly
                  onMarkAllRead={onMarkAllRead}
                  markingReadId={markingReadId}
                  selectionMode={isSelectionMode}
                  selectedSessionIds={selectedSessionIds}
                  onToggleSessionSelected={handleToggleSessionSelected}
                />
              );
            })()}

          {/* Custom projects */}
          {!isProjectsCollapsed &&
            customProjects.map((project) => (
              <ProjectItem
                key={project.id}
                ref={(el) => projectActions.onSetProjectRef(project.id, el)}
                project={project}
                currentSessionId={currentSessionId}
                allProjects={projects}
                onSelectSession={sessionActions.onSelectSession}
                onDeleteSession={sessionActions.onDeleteSession}
                onMoveSession={sessionActions.onMoveSession}
                onToggleFavorite={sessionActions.onToggleFavorite}
                onTogglePin={sessionActions.onTogglePin}
                onShareSession={sessionActions.onShareSession}
                onShareProject={projectActions.onShareProject}
                onRenameProject={projectActions.onRenameProject}
                onDeleteProject={projectActions.onDeleteProject}
                onUpdateIcon={projectActions.onUpdateIcon}
                onUpdateWorkspace={projectActions.onUpdateWorkspace}
                scrollRoot={scrollEl}
                draggingSessionId={
                  sessionActions.touchDropTarget === project.id
                    ? sessionActions.draggingSessionId
                    : null
                }
                onNewSessionInProject={projectActions.onNewSessionInProject}
                forceExpandProjectId={autoExpandProjectId}
                onConsumeAutoExpand={onConsumeAutoExpandProjectId}
                unreadBySession={unreadBySession}
                onMarkAllRead={onMarkAllRead}
                markingReadId={markingReadId}
                selectionMode={isSelectionMode}
                selectedSessionIds={selectedSessionIds}
                onToggleSessionSelected={handleToggleSessionSelected}
              />
            ))}

          {!isProjectsCollapsed &&
            !favoritesProject &&
            customProjects.length === 0 && (
              <p className="px-[9px] py-2 text-12 text-theme-text-tertiary">
                {t("sidebar.noProjects")}
              </p>
            )}

          {/* Recent uncategorized sessions */}
          {visibleUncategorizedSessions.length > 0 || isUncategorizedLoading ? (
            <>
              {isSelectionMode ? (
                <div className="flex h-9 max-sm:h-11 items-center justify-between gap-2 px-[9px]">
                  <span className="text-13 font-medium text-theme-text-secondary dark:text-stone-400">
                    {t("sidebar.selectedCount", { count: selectedCount })}
                  </span>
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={handleToggleAllVisible}
                      className="sidebar-nav-btn rounded-md px-2 py-1 text-12"
                    >
                      {allVisibleSelected
                        ? t("sidebar.clearVisibleSelection")
                        : t("sidebar.selectVisible")}
                    </button>
                    <button
                      type="button"
                      onClick={handleToggleSelectionMode}
                      aria-label={t("common.cancel")}
                      className="sidebar-nav-btn flex h-8 w-6 items-center justify-center rounded-md"
                    >
                      <X size={14} />
                    </button>
                  </div>
                </div>
              ) : (
                <SidebarSectionHeader
                  label={t("sidebar.recentChats")}
                  collapsed={isChatsCollapsed}
                  onToggle={onToggleChatsCollapsed}
                  createLabel={t("sidebar.newChat")}
                  onCreate={onNewSession}
                  createIcon="compose"
                >
                  {selectModeButton}
                  {chatsUnreadCount > 0 && (
                    <div className="flex h-8 w-6 shrink-0 items-center justify-center max-sm:h-11 max-sm:w-11">
                      <MarkAllReadBadge
                        count={chatsUnreadCount}
                        badgeId="all"
                        markingReadId={markingReadId}
                        onMarkAllRead={() => onMarkAllRead()}
                        tooltip={t("sidebar.markAllRead")}
                      />
                    </div>
                  )}
                </SidebarSectionHeader>
              )}

              {(!isChatsCollapsed || isSelectionMode) && (
                <>
                  {isUncategorizedLoading ? (
                    <SkeletonList count={5} compact />
                  ) : (
                    <div className="flex flex-col gap-px">
                      {visibleUncategorizedSessions
                        .filter((session) => session.id)
                        .map((session) => (
                          <SessionItem
                            key={session.id}
                            session={session}
                            isActive={currentSessionId === session.id}
                            projects={projects}
                            onSelect={() =>
                              sessionActions.onSelectSession(session.id)
                            }
                            onDelete={() =>
                              sessionActions.onDeleteSession(session.id)
                            }
                            onMoveToProject={(projectId) =>
                              sessionActions.onMoveSession(
                                session.id,
                                projectId,
                              )
                            }
                            currentProjectId={null}
                            onShare={() =>
                              sessionActions.onShareSession(session.id)
                            }
                            onToggleFavorite={() =>
                              sessionActions.onToggleFavorite(session.id)
                            }
                            onSessionUpdate={onUpdateUncategorizedSession}
                            isFavorite={isSessionFavorite(session)}
                            onTogglePin={() =>
                              sessionActions.onTogglePin(session.id)
                            }
                            isPinned={isSessionPinned(session)}
                            onDragStartTouch={sessionActions.onDragStartTouch}
                            isDraggingTouch={
                              sessionActions.draggingSessionId === session.id
                            }
                            selectionMode={isSelectionMode}
                            isSelected={selectedSessionIds.has(session.id)}
                            onToggleSelected={() =>
                              handleToggleSessionSelected(session.id)
                            }
                          />
                        ))}
                    </div>
                  )}
                  {hasMoreUncategorized && (
                    <div ref={loadMoreRef} className="flex justify-center py-2">
                      {isLoadingMoreUncategorized && (
                        <div className="flex items-center gap-2 text-theme-text-tertiary dark:text-stone-500">
                          <LoadingSpinner size="xs" />
                          <span className="text-12">{t("common.loading")}</span>
                        </div>
                      )}
                    </div>
                  )}
                </>
              )}
            </>
          ) : null}
        </div>
      </div>

      {isSelectionMode && (
        <div className="shrink-0 border-t border-theme-border/80 bg-[var(--theme-bg-sidebar)] px-2 py-2 dark:border-stone-800/70">
          <div className="relative">
            {isProjectPickerOpen && (
              <div className="absolute bottom-12 left-0 right-0 z-30 overflow-hidden rounded-xl border border-theme-border bg-theme-bg-subtle shadow-xl shadow-stone-900/10 dark:border-stone-700 dark:bg-stone-900 dark:shadow-black/30">
                <div className="px-3 py-2 text-11 font-medium uppercase tracking-wide text-theme-text-tertiary dark:text-stone-500">
                  {t("sidebar.moveSelectedToProject")}
                </div>
                <div className="max-h-56 overflow-y-auto p-1">
                  {customProjects.map((project) => (
                    <button
                      key={project.id}
                      type="button"
                      onClick={() => handleMoveSelected(project.id)}
                      className="flex h-9 w-full items-center gap-2 rounded-lg px-2.5 text-left text-13 font-medium text-theme-text-secondary transition hover:text-theme-text dark:text-stone-300 dark:hover:text-stone-50"
                    >
                      <FolderInput
                        size={15}
                        className="shrink-0 text-theme-text-tertiary"
                      />
                      <span className="truncate font-serif">
                        {project.name}
                      </span>
                    </button>
                  ))}
                  <button
                    type="button"
                    onClick={() => handleMoveSelected(null)}
                    className="flex h-9 w-full items-center gap-2 rounded-lg px-2.5 text-left text-13 font-medium text-theme-text-secondary transition hover:text-theme-text dark:text-stone-300 dark:hover:text-stone-50"
                  >
                    <Tag
                      size={15}
                      className="shrink-0 text-theme-text-tertiary"
                    />
                    <span className="truncate">
                      {t("sidebar.uncategorized")}
                    </span>
                  </button>
                </div>
              </div>
            )}

            <div className="flex items-center justify-between gap-2 rounded-[10px] bg-theme-bg-subtle/85 p-1 ring-1 ring-inset ring-theme-border/80 dark:bg-stone-800/55 dark:ring-stone-700/70">
              <div className="flex h-8 min-w-[72px] shrink-0 items-center justify-center rounded-lg bg-theme-bg-card/70 px-2 text-12 font-semibold text-theme-text-secondary ring-1 ring-inset ring-theme-border/70 dark:bg-stone-900/45 dark:text-stone-300 dark:ring-stone-700/60">
                {t("sidebar.selectedCount", {
                  count: selectedCount,
                  defaultValue: "已选 {{count}} 个",
                })}
              </div>
              <div className="flex shrink-0 items-center gap-1">
                <Tooltip content={t("sidebar.moveSelectedToProject")}>
                  <button
                    type="button"
                    disabled={selectedCount === 0}
                    onClick={() => setIsProjectPickerOpen((value) => !value)}
                    aria-label={t("sidebar.moveSelectedToProject")}
                    className="inline-flex h-8 w-6 shrink-0 items-center justify-center rounded-lg text-theme-text-secondary transition hover:text-theme-text disabled:cursor-not-allowed disabled:opacity-45 dark:text-stone-300 dark:hover:text-stone-50"
                  >
                    <FolderInput size={14} />
                  </button>
                </Tooltip>
                <Tooltip content={t("sidebar.deleteSelected")}>
                  <button
                    type="button"
                    disabled={selectedCount === 0}
                    onClick={handleRequestDeleteSelected}
                    aria-label={t("sidebar.deleteSelected")}
                    className="inline-flex h-8 w-6 shrink-0 items-center justify-center rounded-lg text-theme-error transition hover:text-theme-error disabled:cursor-not-allowed disabled:opacity-45 dark:text-red-400 dark:hover:text-red-300"
                  >
                    <Trash2 size={14} />
                  </button>
                </Tooltip>
                <Tooltip content={t("common.cancel")}>
                  <button
                    type="button"
                    onClick={onClearSelection}
                    aria-label={t("common.cancel")}
                    className="inline-flex h-8 w-6 shrink-0 items-center justify-center rounded-lg text-theme-text-secondary transition hover:text-theme-text dark:text-stone-400 dark:hover:text-stone-100"
                  >
                    <X size={15} />
                  </button>
                </Tooltip>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Footer */}
      {!compactChrome && (
        <div className="shrink-0 px-2 py-1 border-t border-theme-border-hover/70 dark:border-stone-800/60">
          <SidebarUserRow
            user={user}
            imgError={imgError}
            onShowProfile={onShowProfile}
          />
        </div>
      )}
    </>
  );
}
