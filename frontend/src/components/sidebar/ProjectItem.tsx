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
import { MoreHorizontal } from "lucide-react";
import toast from "react-hot-toast";
import type { BackendSession } from "../../services/api/session";
import type { Project } from "../../types";
import { projectApi } from "../../services/api";
import { useProjectSessionList } from "../../hooks/useSession";
import { SessionItem } from "./SessionItem";
import { ProjectMenu } from "./ProjectMenu";
import { LoadingSpinner } from "../common/LoadingSpinner";
import { DynamicIcon } from "../common/DynamicIcon";
import { shouldAutoExpandProject } from "./autoExpandProject";
import {
  formatUnreadCount,
  getUnreadCountForProject,
  type UnreadBySession,
} from "./unreadCounts";

export interface ProjectItemHandle {
  refresh: () => Promise<void>;
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
  onRenameProject: (projectId: string, name: string) => void;
  onDeleteProject: (projectId: string) => void;
  onUpdateIcon?: (projectId: string, icon: string) => void;
  scrollRoot?: Element | null;
  draggingSessionId?: string | null;
  onNewSessionInProject?: (projectId: string) => void;
  forceExpandProjectId?: string | null;
  onConsumeAutoExpand?: (projectId: string) => void;
  unreadBySession?: UnreadBySession;
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
      onRenameProject,
      onDeleteProject,
      draggingSessionId,
      onNewSessionInProject,
      forceExpandProjectId,
      onConsumeAutoExpand,
      unreadBySession = new Map(),
      onUpdateIcon,
      scrollRoot,
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
    const {
      sessions,
      isLoading,
      isLoadingMore,
      hasMore,
      loadMoreRef,
      refresh,
      prependSession,
      removeSession,
      updateSession,
    } = useProjectSessionList(project.id, scrollRoot);
    const unreadCount = getUnreadCountForProject({
      projectId: project.id,
      loadedSessions: sessions,
      unreadBySession,
    });

    // Only fetch when expanded (lazy loading)
    const hasLoadedRef = useRef(false);
    useEffect(() => {
      if (isExpanded && !hasLoadedRef.current) {
        hasLoadedRef.current = true;
        refresh();
      }
    }, [isExpanded, refresh]);

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
        prependSession,
        removeSession,
        updateSession,
        sessions,
      }),
      [refresh, prependSession, removeSession, updateSession, sessions],
    );

    // Start editing
    const handleStartEdit = () => {
      setEditName(project.name);
      setIsEditing(true);
      setIsMenuOpen(false);
    };

    const [isEditingIcon, setIsEditingIcon] = useState(false);
    const [editIcon, setEditIcon] = useState("");

    const handleStartIconEdit = () => {
      setEditIcon(project.icon || "📁");
      setIsEditingIcon(true);
    };

    const handleSaveIcon = () => {
      const trimmedIcon = editIcon.trim() || "📁";
      setIsEditingIcon(false);
      if (trimmedIcon !== project.icon) {
        onUpdateIcon?.(project.id, trimmedIcon);
      }
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
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      setIsDragOver(true);
    };

    const handleDragLeave = (e: React.DragEvent) => {
      // Only set dragOver to false if we're leaving the project entirely
      const relatedTarget = e.relatedTarget as Node;
      if (!e.currentTarget.contains(relatedTarget)) {
        setIsDragOver(false);
      }
    };

    const handleDrop = (e: React.DragEvent) => {
      e.preventDefault();
      setIsDragOver(false);

      const sessionId = e.dataTransfer.getData("text/plain");
      if (sessionId) {
        onMoveSession(sessionId, project.id);
      }
    };

    return (
      <div>
        {/* Project header - ChatGPT style drop target */}
        <div
          onClick={handleToggle}
          onTouchStart={handleHeaderTouchStart}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          data-project-drop
          data-project-id={project.id}
          className={`group relative flex cursor-pointer items-center gap-3 h-10 rounded-[10px] px-[9px] transition-colors ${
            isDragOver || draggingSessionId
              ? "bg-stone-200/60 dark:bg-stone-700/40 ring-1 ring-inset ring-stone-300 dark:ring-stone-600"
              : isExpanded
                ? "bg-stone-100/60 dark:bg-stone-800/40"
                : "hover:bg-stone-100 dark:hover:bg-stone-800/30"
          }`}
        >
          {/* Project icon - editable */}
          {isEditingIcon ? (
            <input
              type="text"
              value={editIcon}
              onChange={(e) => setEditIcon(e.target.value)}
              onBlur={handleSaveIcon}
              onKeyDown={(e) => {
                if (e.key === "Enter") handleSaveIcon();
                if (e.key === "Escape") setIsEditingIcon(false);
              }}
              className="w-16 text-xs bg-white dark:bg-stone-700 border border-stone-300 dark:border-stone-500 rounded px-1 py-0.5 focus:outline-none focus:ring-1 focus:ring-stone-400"
              autoFocus
            />
          ) : (
            <button
              onClick={handleStartIconEdit}
              className="flex-shrink-0 hover:opacity-70 transition-opacity"
              title={t("sidebar.clickToEditIcon")}
            >
              <DynamicIcon
                name={project.icon}
                size={18}
                className="text-stone-500 dark:text-stone-400 fill-current text-[18px]"
              />
            </button>
          )}

          {/* Project name - editable or display */}
          <div className="min-w-0 flex-1">
            {isEditing ? (
              <input
                ref={inputRef}
                type="text"
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                onKeyDown={handleKeyDown}
                onBlur={handleSaveName}
                disabled={isSaving}
                className="w-full text-sm bg-transparent text-stone-700 dark:text-stone-200 border border-stone-300 dark:border-stone-500 rounded px-1.5 py-0.5 focus:outline-none focus:ring-1 focus:ring-stone-400"
                onClick={(e) => e.stopPropagation()}
              />
            ) : (
              <div className="truncate text-[13px] text-stone-600 dark:text-stone-400 group-hover:text-stone-700 dark:group-hover:text-stone-300 transition-colors">
                {isFavorites ? t("sidebar.favorites") : project.name}
              </div>
            )}
          </div>

          {!isEditing && unreadCount > 0 && (
            <span className="inline-flex h-4 min-w-[16px] flex-shrink-0 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-medium leading-none text-white">
              {formatUnreadCount(unreadCount)}
            </span>
          )}

          {/* Menu button - only for custom projects */}
          {!isFavorites && !isEditing && (
            <button
              ref={menuButtonRef}
              onClick={handleMenuClick}
              className="flex-shrink-0 rounded p-0.5 hover:bg-stone-200/60 dark:hover:bg-stone-700/60 transition-all opacity-0 group-hover:opacity-100 [&:not(:placeholder-shown)]:opacity-100"
              style={isTouched ? { opacity: 1 } : undefined}
              title={t("sidebar.moreOptions")}
            >
              <MoreHorizontal
                size={14}
                className="text-stone-400 hover:text-stone-600 dark:text-stone-500 dark:hover:text-stone-300"
              />
            </button>
          )}
        </div>

        {/* Expandable content - sessions list with independent pagination */}
        {isExpanded && (
          <div className="ml-3 mt-0.5 flex flex-col gap-px">
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
                    onSessionUpdate={updateSession}
                    isFavorite={isFavorites}
                    onDragStartTouch={undefined}
                    isDraggingTouch={draggingSessionId === session.id}
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
            onNewSessionInProject={
              onNewSessionInProject
                ? () => onNewSessionInProject(project.id)
                : undefined
            }
            anchorEl={menuAnchor}
          />
        )}
      </div>
    );
  },
);
