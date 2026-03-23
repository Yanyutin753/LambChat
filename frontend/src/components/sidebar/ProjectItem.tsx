/**
 * Project item component with expand/collapse and inline rename
 */

import { useState, useRef, useEffect } from "react";
import { useTranslation } from "react-i18next";
import {
  ChevronRight,
  Star,
  Folder as FolderIcon,
  MoreHorizontal,
} from "lucide-react";
import toast from "react-hot-toast";
import type { BackendSession } from "../../services/api/session";
import type { Project } from "../../types";
import { projectApi } from "../../services/api";
import { SessionItem } from "./SessionItem";
import { ProjectMenu } from "./ProjectMenu";

interface ProjectItemProps {
  project: Project;
  sessions: BackendSession[];
  currentSessionId: string | null;
  allProjects: Project[];
  onSelectSession: (sessionId: string) => void;
  onDeleteSession: (sessionId: string) => void;
  onMoveSession: (sessionId: string, projectId: string | null) => void;
  onSessionUpdate: (session: BackendSession) => void;
  onRenameProject: (projectId: string, name: string) => void;
  onDeleteProject: (projectId: string) => void;
  draggingSessionId?: string | null;
  onNewSessionInProject?: (projectId: string) => void;
}

export function ProjectItem({
  project,
  sessions,
  currentSessionId,
  allProjects,
  onSelectSession,
  onDeleteSession,
  onMoveSession,
  onSessionUpdate,
  onRenameProject,
  onDeleteProject,
  draggingSessionId,
  onNewSessionInProject,
}: ProjectItemProps) {
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
    <div className="mb-0.5">
      {/* Project header - ChatGPT style drop target */}
      <div
        onClick={handleToggle}
        onTouchStart={handleHeaderTouchStart}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        data-project-drop
        data-project-id={project.id}
        className={`group relative flex cursor-pointer items-center gap-2 rounded-lg px-2.5 py-2 transition-all duration-150 ${
          isDragOver || draggingSessionId
            ? "bg-stone-200/60 dark:bg-stone-700/40 ring-1 ring-inset ring-stone-300 dark:ring-stone-600"
            : isExpanded
              ? "bg-stone-100/60 dark:bg-stone-800/40"
              : "hover:bg-stone-100 dark:hover:bg-stone-800/30"
        }`}
      >
        {/* Chevron icon */}
        <ChevronRight
          size={14}
          className={`flex-shrink-0 text-stone-400 dark:text-stone-500 transition-transform duration-200 ${
            isExpanded ? "rotate-90" : ""
          }`}
        />

        {/* Project icon */}
        {isFavorites ? (
          <Star
            size={15}
            className="flex-shrink-0 text-amber-500 fill-amber-500"
          />
        ) : (
          <FolderIcon
            size={15}
            className="flex-shrink-0 text-stone-400 dark:text-stone-500 group-hover:text-stone-500 dark:group-hover:text-stone-400 transition-colors"
          />
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

      {/* Expandable content - sessions list */}
      {isExpanded && sessions.length > 0 && (
        <div className="ml-3 mt-0.5 space-y-0.5">
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
              onSessionUpdate={onSessionUpdate}
              isFavorite={isFavorites}
              onDragStartTouch={undefined}
              isDraggingTouch={draggingSessionId === session.id}
            />
          ))}
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
          anchorEl={menuAnchor}
        />
      )}
    </div>
  );
}
