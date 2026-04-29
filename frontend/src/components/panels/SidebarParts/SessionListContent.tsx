import {
  ChevronDown,
  ChevronsUpDown,
  Search,
  FolderPlus,
  FolderOpen,
  MessageSquarePlus,
  MoreHorizontal,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { LoadingSpinner } from "../../common/LoadingSpinner";
import type { BackendSession } from "../../../services/api";
import type { ProjectItemHandle } from "../../sidebar/ProjectItem";
import {
  formatUnreadCount,
  getUnreadCountForUncategorized,
  type UnreadBySession,
} from "../../sidebar/unreadCounts";
import { groupSessionsByTime } from "../sessionHelpers";
import { ProjectItem } from "../../sidebar/ProjectItem";
import { SessionItem } from "../../sidebar/SessionItem";
import { APP_NAME, GITHUB_URL } from "../../../constants";
import { isSessionFavorite } from "../../sidebar/sessionFavorites";
import type { Project } from "../../../types";

export interface SessionActions {
  onDeleteSession: (id: string) => void;
  onMoveSession: (id: string, projectId: string | null) => void;
  onToggleFavorite: (id: string) => void;
  onShareSession: (id: string) => void;
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
  onUpdateIcon: (id: string, icon: string) => void;
  onOpenNewProjectModal: () => void;
  onNewSessionInProject: (projectId: string) => void;
  onSetProjectRef: (id: string, handle: ProjectItemHandle | null) => void;
}

interface SessionListContentProps {
  user: { username?: string; avatar_url?: string; roles?: string[] } | null;
  imgError: boolean;
  onImgError: () => void;
  onCollapse: () => void;
  onNewSession: () => void;
  onOpenSearch: () => void;
  onShowProfile: () => void;
  hasMoreMenuItems: boolean;
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
  projects: Project[];
  favoritesProject: Project | undefined;
  currentSessionId: string | null;
  unreadBySession: UnreadBySession;
  sessionActions: SessionActions;
  projectActions: ProjectActions;
  isProjectsCollapsed: boolean;
  onToggleProjectsCollapsed: () => void;
  isChatsCollapsed: boolean;
  onToggleChatsCollapsed: () => void;
  autoExpandProjectId: string | null | undefined;
  onConsumeAutoExpandProjectId: (id: string) => void;
}

export function SessionListContent({
  user,
  imgError,
  onImgError,
  onCollapse,
  onNewSession,
  onOpenSearch,
  onShowProfile,
  hasMoreMenuItems,
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
}: SessionListContentProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();

  const chatsUnreadCount = getUnreadCountForUncategorized({
    loadedSessions: uncategorizedSessions,
    unreadBySession,
  });
  const groupedUncategorized = groupSessionsByTime(uncategorizedSessions, t);

  return (
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
          onClick={onCollapse}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-stone-600 hover:bg-stone-100 dark:text-stone-400 dark:hover:bg-stone-800/60 transition-colors cursor-w-resize rtl:cursor-e-resize"
          title={t("sidebar.collapseSidebar")}
        >
          <svg
            xmlns="http://www.w3.org/2000/svg"
            fill="none"
            viewBox="0 0 24 24"
            className="w-5 h-5 text-stone-600 dark:text-stone-300"
          >
            <path
              fillRule="evenodd"
              clipRule="evenodd"
              d="M8.85719 3H15.1428C16.2266 2.99999 17.1007 2.99998 17.8086 3.05782C18.5375 3.11737 19.1777 3.24318 19.77 3.54497C20.7108 4.02433 21.4757 4.78924 21.955 5.73005C22.2568 6.32234 22.3826 6.96253 22.4422 7.69138C22.5 8.39925 22.5 9.27339 22.5 10.3572V13.6428C22.5 14.7266 22.5 15.6008 22.4422 16.3086C22.3826 17.0375 22.2568 17.6777 21.955 18.27C21.4757 19.2108 20.7108 19.9757 19.77 20.455C19.1777 20.7568 18.5375 20.8826 17.8086 20.9422C17.1008 21 16.2266 21 15.1428 21H8.85717C7.77339 21 6.89925 21 6.19138 20.9422C5.46253 20.8826 4.82234 20.7568 4.23005 20.455C3.28924 19.9757 2.52433 19.2108 2.04497 18.27C1.74318 17.6777 1.61737 17.0375 1.55782 16.3086C1.49998 15.6007 1.49999 14.7266 1.5 13.6428V10.3572C1.49999 9.27341 1.49998 8.39926 1.55782 7.69138C1.61737 6.96253 1.74318 6.32234 2.04497 5.73005C2.52433 4.78924 3.28924 4.02433 4.23005 3.54497C4.82234 3.24318 5.46253 3.11737 6.19138 3.05782C6.89926 2.99998 7.77341 2.99999 8.85719 3ZM6.35424 5.05118C5.74907 5.10062 5.40138 5.19279 5.13803 5.32698C4.57354 5.6146 4.1146 6.07354 3.82698 6.63803C3.69279 6.90138 3.60062 7.24907 3.55118 7.85424C3.50078 8.47108 3.5 9.26339 3.5 10.4V13.6C3.5 14.7366 3.50078 15.5289 3.55118 16.1458C3.60062 16.7509 3.69279 17.0986 3.82698 17.362C4.1146 17.9265 4.57354 18.3854 5.13803 18.673C5.40138 18.8072 5.74907 18.8994 6.35424 18.9488C6.97108 18.9992 7.76339 19 8.9 19H9.5V5H8.9C7.76339 5 6.97108 5.00078 6.35424 5.05118ZM11.5 5V19H15.1C16.2366 19 17.0289 18.9992 17.6458 18.9488C18.2509 18.8994 18.5986 18.8072 18.862 18.673C19.4265 18.3854 19.8854 17.9265 20.173 17.362C20.3072 17.0986 20.3994 16.7509 20.4488 16.1458C20.4992 15.5289 20.5 14.7366 20.5 13.6V10.4C20.5 9.26339 20.4992 8.47108 20.4488 7.85424C20.3994 7.24907 20.3072 6.90138 20.173 6.63803C19.8854 6.57354 19.4265 6.1146 18.862 5.32698C18.5986 5.19279 18.2509 5.10062 17.6458 5.05118C17.0289 5.00078 16.2366 5 15.1 5H11.5ZM5 8.5C5 7.94772 5.44772 7.5 6 7.5H7C7.55229 7.5 8 7.94772 8 8.5C8 9.05229 7.55229 9.5 7 9.5H6C5.44772 9.5 5 9.05229 5 8.5ZM5 12C5 11.4477 5.44772 11 6 11H7C7.55229 11 8 11.4477 8 12C8 12.5523 7.55229 13 7 13H6C5.44772 13 5 12.4477 5 12Z"
              fill="currentColor"
            />
          </svg>
        </button>
      </div>

      {/* Action buttons */}
      <div className="flex flex-col gap-px px-2 py-2 space-y-1">
        <button
          onClick={onNewSession}
          className="w-full h-9 rounded-[10px] flex items-center gap-3 px-[9px] text-sm font-medium text-stone-600 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-stone-800/60 focus:outline-none transition-colors group"
        >
          <MessageSquarePlus size={20} />
          <span className="flex-1 text-left">{t("sidebar.newChat")}</span>
          <kbd className="hidden sm:inline-flex items-center gap-0.5 px-1.5 py-0.5 text-[10px] font-medium text-stone-400 dark:text-stone-500 rounded opacity-0 group-hover:opacity-100 transition-opacity">
            {t("sidebar.newChatShortcut")}
          </kbd>
        </button>

        <button
          onClick={onOpenSearch}
          className="w-full h-9 rounded-[10px] flex items-center gap-3 px-[9px] text-sm text-stone-600 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-stone-800/60 focus:outline-none transition-colors group"
        >
          <Search size={20} />
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
          <FolderOpen size={20} />
          <span>{t("fileLibrary.title")}</span>
        </button>

        {hasMoreMenuItems && (
          <div className="relative">
            <button
              ref={expandedMoreMenuBtnRef}
              onClick={onToggleMoreMenu}
              className="w-full h-9 rounded-[10px] flex items-center gap-3 px-[9px] text-sm text-stone-600 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-stone-800/60 focus:outline-none transition-colors"
            >
              <MoreHorizontal size={20} />
              <span className="flex-1 text-left">{t("nav.more", "更多")}</span>
            </button>
          </div>
        )}
      </div>

      {/* Session list */}
      <div
        ref={onSetScrollEl}
        data-sidebar-scroll
        className="flex-1 overflow-y-auto px-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        <div className="flex flex-col gap-px">
          {/* Project section header */}
          <div
            onClick={onToggleProjectsCollapsed}
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
              onClick={projectActions.onOpenNewProjectModal}
              className="w-full h-9 rounded-[10px] flex items-center gap-3 px-[9px] text-sm text-stone-500 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-stone-800/60 transition-colors cursor-pointer"
            >
              <FolderPlus size={20} />
              <span>{t("sidebar.newProject")}</span>
            </button>
          )}

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
                  onShareSession={sessionActions.onShareSession}
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
                  ref={(el) => projectActions.onSetProjectRef(project.id, el)}
                  project={project}
                  currentSessionId={currentSessionId}
                  allProjects={projects}
                  onSelectSession={sessionActions.onSelectSession}
                  onDeleteSession={sessionActions.onDeleteSession}
                  onMoveSession={sessionActions.onMoveSession}
                  onToggleFavorite={sessionActions.onToggleFavorite}
                  onShareSession={sessionActions.onShareSession}
                  onRenameProject={projectActions.onRenameProject}
                  onDeleteProject={projectActions.onDeleteProject}
                  onUpdateIcon={projectActions.onUpdateIcon}
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
                />
              ))}

          {!isProjectsCollapsed && (
            <div className="h-px bg-stone-200/60 dark:bg-stone-700/40 mx-2 my-1" />
          )}

          {/* Uncategorized sessions (by time) */}
          {groupedUncategorized.length > 0 || isUncategorizedLoading ? (
            <>
              <div
                onClick={onToggleChatsCollapsed}
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
                  {isUncategorizedLoading ? (
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
                                onDragStartTouch={
                                  sessionActions.onDragStartTouch
                                }
                                isDraggingTouch={
                                  sessionActions.draggingSessionId ===
                                  session.id
                                }
                              />
                            ))}
                        </div>
                      </div>
                    ))
                  )}
                  {hasMoreUncategorized && (
                    <div ref={loadMoreRef} className="flex justify-center py-2">
                      {isLoadingMoreUncategorized && (
                        <div className="flex items-center gap-2 text-stone-400 dark:text-stone-500">
                          <LoadingSpinner size="xs" />
                          <span className="text-xs">{t("common.loading")}</span>
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

      {/* Footer */}
      <div className="shrink-0 px-2 pt-2 pb-1 border-t border-stone-200/60 dark:border-stone-800/60">
        <div
          onClick={onShowProfile}
          className="group flex items-center rounded-xl py-2 px-2 w-full hover:bg-stone-100 dark:hover:bg-stone-800/60 transition cursor-pointer"
        >
          <div className="shrink-0 w-8 h-8 rounded-full overflow-hidden ring-1 ring-stone-200 dark:ring-stone-700 group-hover:ring-[var(--theme-primary)] transition mr-3">
            {user?.avatar_url && !imgError ? (
              <img
                src={user.avatar_url}
                alt={user?.username || "User"}
                className="w-full h-full object-cover rounded-full"
                onError={onImgError}
                draggable={false}
              />
            ) : (
              <div className="flex w-full h-full items-center justify-center bg-gradient-to-br from-amber-400 to-orange-500 rounded-full">
                <span className="text-xs font-semibold text-white">
                  {user?.username?.charAt(0).toUpperCase() || "U"}
                </span>
              </div>
            )}
          </div>
          <div className="flex-1 text-left min-w-0 space-y-0.5">
            <div className="text-sm font-medium text-stone-800 dark:text-stone-100 truncate">
              {user?.username || "User"}
            </div>
            <div className="text-xs text-stone-400 dark:text-stone-500 whitespace-nowrap">
              {(user?.roles?.[0] || "User").replace(/^./, (c) =>
                c.toUpperCase(),
              )}
            </div>
          </div>
          <ChevronsUpDown className="size-4 text-stone-400 shrink-0" />
        </div>
      </div>
    </>
  );
}
