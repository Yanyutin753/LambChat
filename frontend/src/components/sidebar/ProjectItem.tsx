/**
 * Project item component with expand/collapse and inline rename.
 * Manages its own session list via useProjectSessionList.
 */

import {
  useState,
  useRef,
  useEffect,
  forwardRef,
  useImperativeHandle,
} from "react";
import { useTranslation } from "react-i18next";
import {
  FolderClosed,
  FolderOpen,
  MoreHorizontal,
  SquarePen,
  Star,
} from "lucide-react";
import toast from "react-hot-toast";
import type { BackendSession } from "../../services/api/session";
import type { Project } from "../../types";
import { projectApi } from "../../services/api";
import { useFilteredSessionList } from "../../hooks/useSession";
import { SessionItem } from "./SessionItem";
import { ProjectMenu } from "./ProjectMenu";
import { ProjectWorkspaceDetails } from "./ProjectWorkspaceField";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { Tooltip } from "../common/Tooltip";
import { isSessionFavorite } from "./sessionFavorites";
import { isSessionPinned } from "./sessionPin";
import { shouldAutoExpandProject } from "./autoExpandProject";
import {
  getUnreadCountForFavorites,
  getUnreadCountForProject,
  type UnreadBySession,
} from "./unreadCounts";
import { MarkAllReadBadge } from "./MarkAllReadBadge";

export interface ProjectItemHandle {
  refresh: () => Promise<void>;
  softRefresh: () => Promise<void>;
  prependSession: (session: BackendSession) => void;
  removeSession: (sessionId: string) => void;
  updateSession: (session: BackendSession) => void;
  sessions: BackendSession[];
}

interface ProjectItemProps {
  project: Project;
  currentSessionId: string | null;
  allProjects: Project[];
  onSelectSession: (sessionId: string) => void;
  onDeleteSession: (sessionId: string) => void;
  onMoveSession: (sessionId: string, projectId: string | null) => void;
  onToggleFavorite?: (sessionId: string) => void;
  onTogglePin?: (sessionId: string) => void;
  onShareSession?: (sessionId: string) => void;
  onShareProject?: (projectId: string) => void;
  onRenameProject: (projectId: string, name: string) => void;
  onDeleteProject: (projectId: string) => void;
  onUpdateIcon?: (projectId: string, icon: string) => void;
  onUpdateWorkspace?: (
    projectId: string,
    workspace: Project["workspace"],
  ) => Promise<void>;
  scrollRoot?: Element | null;
  draggingSessionId?: string | null;
  onNewSessionInProject?: (projectId: string) => void;
  forceExpandProjectId?: string | null;
  onConsumeAutoExpand?: (projectId: string) => void;
  unreadBySession?: UnreadBySession;
  favoritesOnly?: boolean;
  onMarkAllRead?: (opts?: { projectId?: string }) => void;
  markingReadId?: string | null;
  selectionMode?: boolean;
  selectedSessionIds?: Set<string>;
  onToggleSessionSelected?: (sessionId: string) => void;
}

export const ProjectItem = forwardRef<ProjectItemHandle, ProjectItemProps>(
  function ProjectItem(
    {
      project,
      currentSessionId,
      allProjects,
      onSelectSession,
      onDeleteSession,
      onMoveSession,
      onToggleFavorite,
      onTogglePin,
      onShareSession,
      onShareProject,
      onRenameProject,
      onDeleteProject,
      draggingSessionId,
      onNewSessionInProject,
      forceExpandProjectId,
      onConsumeAutoExpand,
      unreadBySession = new Map(),
      onUpdateWorkspace,
      scrollRoot,
      favoritesOnly = false,
      onMarkAllRead,
      markingReadId,
      selectionMode = false,
      selectedSessionIds = new Set(),
      onToggleSessionSelected,
    },
    ref,
  ) {
    const { t } = useTranslation();
    const [isExpanded, setIsExpanded] = useState(false);
    const [isEditing, setIsEditing] = useState(false);
    const [editName, setEditName] = useState("");
    const [isSaving, setIsSaving] = useState(false);
    const [isMenuOpen, setIsMenuOpen] = useState(false);
    const [menuAnchor, setMenuAnchor] = useState<HTMLElement | null>(null);
    const [isDragOver, setIsDragOver] = useState(false);

    const inputRef = useRef<HTMLInputElement>(null);
    const menuButtonRef = useRef<HTMLButtonElement>(null);
    const [isTouched, setIsTouched] = useState(false);
    const touchTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

    const isFavorites = project.type === "favorites";

    // ─── Per-project session list ──────────────────────────────────
    const listState = useFilteredSessionList(
      favoritesOnly ? { favoritesOnly: true } : { projectId: project.id },
      scrollRoot,
      isExpanded,
    );
    const {
      sessions,
      isLoading,
      isLoadingMore,
      error,
      hasMore,
      loadMoreRef,
      refresh,
      softRefresh,
      prependSession,
      removeSession,
      updateSession,
    } = listState;
    const unreadCount = favoritesOnly
      ? getUnreadCountForFavorites(sessions, unreadBySession)
      : getUnreadCountForProject({
          projectId: project.id,
          loadedSessions: sessions,
          unreadBySession,
        });

    // Auto-expand when a new session is created in this project
    useEffect(() => {
      if (!shouldAutoExpandProject(forceExpandProjectId, project.id)) {
        return;
      }

      setIsExpanded(true);
      onConsumeAutoExpand?.(project.id);
    }, [forceExpandProjectId, onConsumeAutoExpand, project.id]);

    // Expose handle to parent
    useImperativeHandle(
      ref,
      () => ({
        refresh,
        softRefresh,
        prependSession,
        removeSession,
        updateSession,
        sessions,
      }),
      [
        refresh,
        softRefresh,
        prependSession,
        removeSession,
        updateSession,
        sessions,
      ],
    );

    // Start editing
    const handleStartEdit = () => {
      setEditName(project.name);
      setIsEditing(true);
      setIsMenuOpen(false);
    };

    // Focus input when editing starts
    useEffect(() => {
      if (isEditing && inputRef.current) {
        inputRef.current.focus();
        inputRef.current.select();
      }
    }, [isEditing]);

    // Save project name
    const handleSaveName = async () => {
      const trimmedName = editName.trim();

      // Don't save if name hasn't changed or is empty
      if (!trimmedName || trimmedName === project.name) {
        setIsEditing(false);
        return;
      }

      setIsSaving(true);
      try {
        const updatedProject = await projectApi.update(project.id, {
          name: trimmedName,
        });
        onRenameProject(project.id, updatedProject.name);
        toast.success(t("sidebar.projectRenamed"));
      } catch (error) {
        console.error("Failed to update project name:", error);
        toast.error(t("sidebar.projectRenameFailed"));
      } finally {
        setIsSaving(false);
        setIsEditing(false);
      }
    };

    // Cancel editing
    const handleCancelEdit = () => {
      setIsEditing(false);
      setEditName("");
    };

    // Handle key events
    const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
      if (e.key === "Enter") {
        e.preventDefault();
        handleSaveName();
      } else if (e.key === "Escape") {
        e.preventDefault();
        handleCancelEdit();
      }
    };

    // Handle menu button click
    const handleMenuClick = (e: React.MouseEvent) => {
      e.stopPropagation();
      setMenuAnchor(menuButtonRef.current);
      setIsMenuOpen(true);
    };

    // Touch: show menu button, auto-hide after 3s
    const handleHeaderTouchStart = () => {
      if (isEditing) return;
      if (touchTimerRef.current) clearTimeout(touchTimerRef.current);
      setIsTouched(true);
      touchTimerRef.current = setTimeout(() => setIsTouched(false), 3000);
    };

    // Cleanup touch timer
    useEffect(() => {
      return () => {
        if (touchTimerRef.current) clearTimeout(touchTimerRef.current);
      };
    }, []);

    // Toggle expand/collapse
    const handleToggle = () => {
      if (!isEditing) {
        setIsExpanded(!isExpanded);
      }
    };

    // Drag and drop handlers
    const handleDragOver = (e: React.DragEvent) => {
      if (
        favoritesOnly ||
        !e.dataTransfer.types.includes("application/x-lambchat-session")
      )
        return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      setIsDragOver(true);
    };

    const handleDragLeave = (e: React.DragEvent) => {
      if (favoritesOnly) return;
      // Only set dragOver to false if we're leaving the project entirely
      const relatedTarget = e.relatedTarget as Node;
      if (!e.currentTarget.contains(relatedTarget)) {
        setIsDragOver(false);
      }
    };

    const handleDrop = (e: React.DragEvent) => {
      if (
        favoritesOnly ||
        !e.dataTransfer.types.includes("application/x-lambchat-session")
      )
        return;
      e.preventDefault();
      setIsDragOver(false);

      const sessionId = e.dataTransfer.getData(
        "application/x-lambchat-session",
      );
      if (sessionId) {
        onMoveSession(sessionId, project.id);
      }
    };

    return (
      <div>
        {/* Project header - ChatGPT style drop target */}
        <div
          onTouchStart={handleHeaderTouchStart}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          data-project-drop={favoritesOnly ? undefined : true}
          data-project-id={favoritesOnly ? undefined : project.id}
          className={`sidebar-action-row group relative flex cursor-pointer items-center gap-2 h-8 max-sm:h-10 rounded-[10px] px-[9px] transition-colors ${
            (!favoritesOnly && isDragOver) ||
            (!favoritesOnly && draggingSessionId)
              ? "bg-stone-200/60 dark:bg-stone-700/40 ring-1 ring-inset ring-stone-300 dark:ring-stone-600"
              : isExpanded
                ? "bg-stone-100 dark:bg-stone-700/50"
                : ""
          }`}
        >
          {/* Project icon */}
          <span
            className="shrink-0 text-theme-text-secondary"
            aria-hidden="true"
          >
            {isFavorites ? (
              <Star size={16} />
            ) : isExpanded ? (
              <FolderOpen size={16} />
            ) : (
              <FolderClosed size={16} />
            )}
          </span>

          {/* Project name - editable or display */}
          <div className="min-w-0 flex-1">
            {isEditing ? (
              <input
                ref={inputRef}
                type="text"
                aria-label={`${t("sidebar.rename")} ${project.name}`}
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                onKeyDown={handleKeyDown}
                onBlur={handleSaveName}
                disabled={isSaving}
                className="w-full text-14 bg-transparent text-stone-700 dark:text-stone-200 border border-stone-300 dark:border-stone-500 rounded px-1.5 py-0.5 focus:outline-none focus:ring-1 focus:ring-stone-400"
                onClick={(e) => e.stopPropagation()}
              />
            ) : (
              <button
                type="button"
                onClick={handleToggle}
                aria-expanded={isExpanded}
                className="block h-8 max-sm:h-10 w-full rounded text-left truncate text-13 font-serif text-stone-700 dark:text-stone-300 group-hover:text-stone-700 dark:group-hover:text-stone-300 transition-colors motion-reduce:transition-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--theme-primary)]"
              >
                {isFavorites ? t("sidebar.favorites") : project.name}
              </button>
            )}
          </div>
          {/* Project actions */}
          <div
            className="flex shrink-0 items-center gap-1 sidebar-action-reveal sidebar-action-controls"
            style={isTouched || isMenuOpen ? { opacity: 1 } : undefined}
          >
            {!isEditing && project.workspace && (
              <ProjectWorkspaceDetails value={project.workspace} />
            )}
            {!isEditing && unreadCount > 0 && (
              <div className="flex h-8 w-8 shrink-0 items-center justify-center max-sm:h-9 max-sm:w-9">
                <MarkAllReadBadge
                  count={unreadCount}
                  badgeId={`project-${project.id}`}
                  markingReadId={markingReadId ?? null}
                  onMarkAllRead={() =>
                    onMarkAllRead?.({ projectId: project.id })
                  }
                  tooltip={t("sidebar.markAllRead")}
                />
              </div>
            )}

            {!isFavorites && !isEditing && onNewSessionInProject && (
              <Tooltip
                content={t("sidebar.newChatInProject", {
                  project: project.name,
                })}
              >
                <button
                  type="button"
                  onClick={() => onNewSessionInProject(project.id)}
                  aria-label={t("sidebar.newChatInProject", {
                    project: project.name,
                  })}
                  className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-stone-500 hover:text-stone-700 dark:text-stone-400 dark:hover:text-stone-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--theme-primary)] max-sm:h-9 max-sm:w-9"
                >
                  <SquarePen size={16} aria-hidden="true" />
                </button>
              </Tooltip>
            )}

            {/* Menu button - only for custom projects */}
            {!isFavorites && !isEditing && (
              <Tooltip content={t("sidebar.moreOptions")}>
                <button
                  ref={menuButtonRef}
                  onClick={handleMenuClick}
                  aria-label={t("sidebar.moreOptions")}
                  className="flex h-8 w-8 shrink-0 items-center justify-center max-sm:h-9 max-sm:w-9 rounded p-0.5 transition-colors"
                >
                  <MoreHorizontal
                    size={14}
                    className="text-stone-400 hover:text-stone-600 dark:text-stone-500 dark:hover:text-stone-300"
                  />
                </button>
              </Tooltip>
            )}
          </div>
        </div>

        {/* Expandable content - sessions list with independent pagination */}
        {isExpanded && (
          <div className="ms-6 mt-0.5 mb-2 flex flex-col gap-px">
            {isLoading ? (
              <div className="flex justify-center py-4">
                <LoadingSpinner size="sm" color="text-[var(--theme-primary)]" />
              </div>
            ) : sessions.length > 0 ? (
              <>
                {sessions.map((session) => (
                  <SessionItem
                    key={session.id}
                    session={session}
                    isActive={session.id === currentSessionId}
                    projects={allProjects}
                    onSelect={() => onSelectSession(session.id)}
                    onDelete={() => onDeleteSession(session.id)}
                    onMoveToProject={(projectId) =>
                      onMoveSession(session.id, projectId)
                    }
                    currentProjectId={project.id}
                    onShare={
                      onShareSession
                        ? () => onShareSession(session.id)
                        : undefined
                    }
                    onToggleFavorite={
                      onToggleFavorite
                        ? () => onToggleFavorite(session.id)
                        : undefined
                    }
                    onSessionUpdate={updateSession}
                    isFavorite={isSessionFavorite(session)}
                    onTogglePin={
                      onTogglePin ? () => onTogglePin(session.id) : undefined
                    }
                    isPinned={isSessionPinned(session)}
                    onDragStartTouch={undefined}
                    isDraggingTouch={draggingSessionId === session.id}
                    selectionMode={selectionMode}
                    isSelected={selectedSessionIds.has(session.id)}
                    onToggleSelected={() =>
                      onToggleSessionSelected?.(session.id)
                    }
                  />
                ))}
                {hasMore && (
                  <div ref={loadMoreRef} className="flex justify-center py-2">
                    {isLoadingMore && (
                      <LoadingSpinner
                        size="xs"
                        color="text-[var(--theme-primary)]"
                      />
                    )}
                  </div>
                )}
              </>
            ) : !error && !isFavorites && onNewSessionInProject ? (
              <button
                type="button"
                onClick={() => onNewSessionInProject(project.id)}
                className="flex min-h-10 items-center gap-2 rounded-md px-3 text-left text-13 text-stone-500 hover:text-stone-700 dark:text-stone-400 dark:hover:text-stone-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--theme-primary)]"
              >
                <SquarePen size={14} className="shrink-0" aria-hidden="true" />
                {t("sidebar.startFirstChat")}
              </button>
            ) : null}
          </div>
        )}

        {/* Context Menu */}
        {!isFavorites && (
          <ProjectMenu
            project={project}
            isOpen={isMenuOpen}
            onClose={() => setIsMenuOpen(false)}
            onRename={handleStartEdit}
            onDelete={() => onDeleteProject(project.id)}
            onShare={
              onShareProject ? () => onShareProject(project.id) : undefined
            }
            onNewSessionInProject={
              onNewSessionInProject
                ? () => onNewSessionInProject(project.id)
                : undefined
            }
            anchorEl={menuAnchor}
            onWorkspaceChange={
              onUpdateWorkspace
                ? (workspace) => onUpdateWorkspace(project.id, workspace)
                : undefined
            }
          />
        )}
      </div>
    );
  },
);
