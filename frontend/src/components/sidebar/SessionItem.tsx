/**
 * Session item component with inline title editing and drag support
 */

import { useState, useRef, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { MoreHorizontal } from "lucide-react";
import toast from "react-hot-toast";
import type { BackendSession } from "../../services/api/session";
import type { Project } from "../../types";
import { sessionApi } from "../../services/api";
import { SessionMenu } from "./SessionMenu";
import { shouldBlockSessionSelection } from "../../utils/sessionSelectionGuard";

interface SessionItemProps {
  session: BackendSession;
  isActive: boolean;
  projects: Project[];
  onSelect: () => void;
  onDelete: () => void;
  onMoveToProject: (projectId: string | null) => void;
  onSessionUpdate: (session: BackendSession) => void;
  isFavorite?: boolean;
  onDragStart?: (session: BackendSession) => void;
  onDragEnd?: () => void;
  onDragStartTouch?: (
    sessionId: string,
    clientX: number,
    clientY: number,
  ) => void;
  isDraggingTouch?: boolean;
}

export function SessionItem({
  session,
  isActive,
  projects,
  onSelect,
  onDelete,
  onMoveToProject,
  onSessionUpdate,
  isFavorite = false,
  onDragStart,
  onDragEnd,
  onDragStartTouch,
  isDraggingTouch = false,
}: SessionItemProps) {
  const { t } = useTranslation();
  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [menuAnchor, setMenuAnchor] = useState<HTMLElement | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isTouched, setIsTouched] = useState(false);
  const touchShowTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const longPressTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const touchStartRef = useRef<{ x: number; y: number } | null>(null);

  const inputRef = useRef<HTMLInputElement>(null);
  const menuButtonRef = useRef<HTMLButtonElement>(null);
  const wasDraggingRef = useRef(false);

  // Get session title from various sources
  const getSessionTitle = useCallback(
    (s: BackendSession) => {
      if (s.name) return s.name;
      const meta = s.metadata as Record<string, unknown>;
      if (meta?.title) return meta.title as string;
      return t("sidebar.newChat");
    },
    [t],
  );

  // Start editing
  const handleStartEdit = () => {
    setEditTitle(getSessionTitle(session));
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

  // Save title
  const handleSaveTitle = async () => {
    const trimmedTitle = editTitle.trim();

    // Don't save if title hasn't changed or is empty
    if (!trimmedTitle || trimmedTitle === getSessionTitle(session)) {
      setIsEditing(false);
      return;
    }

    setIsSaving(true);
    try {
      const response = await sessionApi.update(session.id, {
        name: trimmedTitle,
      });
      if (response.session) {
        onSessionUpdate(response.session);
        toast.success(t("sidebar.renamed"));
      }
    } catch (error) {
      console.error("Failed to update session title:", error);
      toast.error(t("sidebar.renameFailed"));
    } finally {
      setIsSaving(false);
      setIsEditing(false);
    }
  };

  // Cancel editing
  const handleCancelEdit = () => {
    setIsEditing(false);
    setEditTitle("");
  };

  // Handle key events
  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") {
      e.preventDefault();
      handleSaveTitle();
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
  const handleItemTouchStart = (e: React.TouchEvent) => {
    if (isEditing) return;
    const touch = e.touches[0];
    touchStartRef.current = { x: touch.clientX, y: touch.clientY };

    if (touchShowTimerRef.current) clearTimeout(touchShowTimerRef.current);
    setIsTouched(true);
    touchShowTimerRef.current = setTimeout(() => setIsTouched(false), 3000);

    // Long press (400ms) to start drag
    longPressTimerRef.current = setTimeout(() => {
      setIsDragging(true);
      wasDraggingRef.current = true;
      onDragStartTouch?.(session.id, touch.clientX, touch.clientY);
    }, 400);
  };

  const handleItemTouchMove = (e: React.TouchEvent) => {
    // Cancel long press if moved too much before drag starts
    if (longPressTimerRef.current && touchStartRef.current) {
      const touch = e.touches[0];
      const dx = touch.clientX - touchStartRef.current.x;
      const dy = touch.clientY - touchStartRef.current.y;
      if (Math.sqrt(dx * dx + dy * dy) > 10) {
        clearTimeout(longPressTimerRef.current);
        longPressTimerRef.current = null;
      }
    }
  };

  const handleItemTouchEnd = () => {
    if (longPressTimerRef.current) {
      clearTimeout(longPressTimerRef.current);
      longPressTimerRef.current = null;
    }
    if (isDragging) {
      setIsDragging(false);
      setTimeout(() => {
        wasDraggingRef.current = false;
      }, 100);
    }
  };

  // Prevent context menu during drag
  const handleContextMenu = (e: React.MouseEvent | React.TouchEvent) => {
    if (isDragging) {
      e.preventDefault();
    }
  };

  // Cleanup timers
  useEffect(() => {
    return () => {
      if (touchShowTimerRef.current) clearTimeout(touchShowTimerRef.current);
      if (longPressTimerRef.current) clearTimeout(longPressTimerRef.current);
    };
  }, []);

  // Drag handlers (desktop)
  const handleDragStart = (e: React.DragEvent) => {
    e.dataTransfer.setData("text/plain", session.id);
    e.dataTransfer.effectAllowed = "move";
    setIsDragging(true);
    onDragStart?.(session);
  };

  const handleDragEnd = () => {
    setIsDragging(false);
    onDragEnd?.();
  };

  // Get display title
  const displayTitle = getSessionTitle(session);

  return (
    <>
      <div
        draggable
        onDragStart={handleDragStart}
        onDragEnd={handleDragEnd}
        onTouchStart={handleItemTouchStart}
        onTouchMove={handleItemTouchMove}
        onTouchEnd={handleItemTouchEnd}
        onContextMenu={handleContextMenu}
        onClick={() => {
          if (wasDraggingRef.current) {
            wasDraggingRef.current = false;
            return;
          }
          if (shouldBlockSessionSelection(window.location.pathname)) {
            return;
          }
          if (!isEditing) {
            onSelect();
          }
        }}
        style={isDragging ? { touchAction: "none" } : undefined}
        className={`group relative flex cursor-pointer items-center gap-3 h-10 rounded-[10px] px-[9px] transition-colors ${
          isActive
            ? "bg-stone-100 dark:bg-stone-800/60"
            : "hover:bg-stone-100 dark:hover:bg-stone-800/40"
        } ${isDragging || isDraggingTouch ? "opacity-50 scale-95" : ""}`}
      >
        {/* Title - editable or display */}
        <div className="min-w-0 flex-1">
          {isEditing ? (
            <input
              ref={inputRef}
              type="text"
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              onKeyDown={handleKeyDown}
              onBlur={handleSaveTitle}
              disabled={isSaving}
              className="w-full text-[13px] bg-transparent text-stone-700 dark:text-stone-200 border border-stone-300 dark:border-stone-500 rounded px-1.5 py-0.5 focus:outline-none focus:ring-1 focus:ring-stone-400"
              onClick={(e) => e.stopPropagation()}
            />
          ) : (
            <div
              className={`truncate text-[13px] transition-colors ${
                isActive
                  ? "text-stone-800 dark:text-stone-100 font-medium"
                  : "text-stone-600 dark:text-stone-300 group-hover:text-stone-700 dark:group-hover:text-stone-200"
              }`}
            >
              {displayTitle}
            </div>
          )}
        </div>

        {/* Unread badge - hidden when session is active (user is viewing it) */}
        {!isEditing && !isActive && (session.unread_count ?? 0) > 0 && (
          <span className="flex-shrink-0 inline-flex items-center justify-center min-w-[16px] h-[16px] px-1 rounded-full bg-red-500 text-white text-[10px] font-medium leading-none animate-[scale-in_0.2s_ease-out]">
            {(session.unread_count ?? 0) > 99 ? "99+" : session.unread_count}
          </span>
        )}

        {/* Menu button */}
        {!isEditing && (
          <button
            ref={menuButtonRef}
            onClick={handleMenuClick}
            className="flex-shrink-0 rounded p-1 hover:bg-stone-200/60 dark:hover:bg-stone-700/60 transition-all opacity-0 group-hover:opacity-100"
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

      {/* Context Menu */}
      <SessionMenu
        session={session}
        projects={projects}
        isOpen={isMenuOpen}
        onClose={() => setIsMenuOpen(false)}
        onRename={handleStartEdit}
        onDelete={onDelete}
        onMoveToProject={onMoveToProject}
        anchorEl={menuAnchor}
        isFavorite={isFavorite}
      />
    </>
  );
}
