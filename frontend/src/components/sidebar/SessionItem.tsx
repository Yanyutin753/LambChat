/**
 * Session item component with inline title editing and drag support
 */

import { memo, useState, useRef, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { AlertCircle, Check, MoreHorizontal } from "lucide-react";
import toast from "react-hot-toast";
import type { BackendSession } from "../../services/api/session";
import type { Project } from "../../types";
import { sessionApi } from "../../services/api";
import { SessionMenu } from "./SessionMenu";
import { Tooltip } from "../common/Tooltip";
import { shouldBlockSessionSelection } from "../../utils/sessionSelectionGuard";

interface SessionItemProps {
  session: BackendSession;
  isActive: boolean;
  projects: Project[];
  onSelect: () => void;
  onDelete: () => void;
  onMoveToProject: (projectId: string | null) => void;
  onShare?: () => void;
  onToggleFavorite?: () => void;
  onTogglePin?: () => void;
  onSessionUpdate: (session: BackendSession) => void;
  isFavorite?: boolean;
  isPinned?: boolean;
  currentProjectId?: string | null;
  onDragStart?: (session: BackendSession) => void;
  onDragEnd?: () => void;
  onDragStartTouch?: (
    sessionId: string,
    clientX: number,
    clientY: number,
  ) => void;
  isDraggingTouch?: boolean;
  selectionMode?: boolean;
  isSelected?: boolean;
  onToggleSelected?: () => void;
}

function SessionItemComponent({
  session,
  isActive,
  projects,
  onSelect,
  onDelete,
  onMoveToProject,
  onShare,
  onToggleFavorite,
  onTogglePin,
  onSessionUpdate,
  isFavorite = false,
  isPinned = false,
  currentProjectId,
  onDragStart,
  onDragEnd,
  onDragStartTouch,
  isDraggingTouch = false,
  selectionMode = false,
  isSelected = false,
  onToggleSelected,
}: SessionItemProps) {
  const { t } = useTranslation();
  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [menuAnchor, setMenuAnchor] = useState<HTMLElement | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [isTouched, setIsTouched] = useState(false);
  const [cursorPosition, setCursorPosition] = useState<{
    x: number;
    y: number;
  } | null>(null);
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
    // Button-opened menus anchor to the button, not the cursor
    setCursorPosition(null);
    setIsMenuOpen(true);
  };

  // Touch: show menu button, auto-hide after 3s
  const handleItemTouchStart = (e: React.TouchEvent) => {
    if (selectionMode) return;
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

  // Right-click opens the menu anchored at the cursor; suppress during drag
  const handleContextMenu = (e: React.MouseEvent) => {
    if (isEditing) return; // Allow native context menu during rename
    if (isDragging) {
      e.preventDefault();
      return;
    }
    e.preventDefault();
    setCursorPosition({ x: e.clientX, y: e.clientY });
    // SessionMenu renders nothing without an anchor element, so provide one
    setMenuAnchor(menuButtonRef.current);
    setIsMenuOpen(true);
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
    if (selectionMode) {
      e.preventDefault();
      return;
    }
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
  const taskStatus = session.metadata?.task_status;
  const isWaitingForHuman = taskStatus === "waiting_human";
  const isGenerating = taskStatus === "running" || taskStatus === "pending";
  const taskStatusLabel = isGenerating
    ? t(
        taskStatus === "pending"
          ? "sidebar.pendingStatus"
          : "sidebar.runningStatus",
        taskStatus === "pending" ? "等待中" : "运行中",
      )
    : null;

  return (
    <>
      <div
        draggable={!selectionMode}
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
          if (selectionMode) {
            onToggleSelected?.();
            return;
          }
          if (!isEditing) {
            onSelect();
          }
        }}
        // Keep taps on mobile as normal activation gestures; the long-press
        // handlers below still own drag initiation once movement is detected.
        style={
          isDragging ? { touchAction: "none" } : { touchAction: "manipulation" }
        }
        className={`group relative flex cursor-pointer items-center gap-3 h-10 rounded-[10px] px-[9px] transition-colors ${
          isSelected
            ? "hover:bg-stone-100 dark:hover:bg-stone-800/40"
            : isActive
              ? "bg-stone-100 dark:bg-stone-800/60"
              : "hover:bg-stone-100 dark:hover:bg-stone-800/40"
        } ${isDragging || isDraggingTouch ? "opacity-50 scale-95" : ""} ${
          selectionMode ? "pr-2" : ""
        }`}
      >
        {selectionMode && (
          <button
            type="button"
            onClick={(e) => {
              e.stopPropagation();
              onToggleSelected?.();
            }}
            aria-pressed={isSelected}
            aria-label={
              isSelected
                ? t("sidebar.unselectSession")
                : t("sidebar.selectSession")
            }
            className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full border transition-colors ${
              isSelected
                ? "border-stone-700 bg-stone-700 text-white shadow-sm dark:border-stone-500 dark:bg-stone-600 dark:text-stone-100"
                : "border-stone-300 bg-transparent text-transparent group-hover:border-stone-400 dark:border-stone-600 dark:group-hover:border-stone-500"
            }`}
          >
            <Check size={11} strokeWidth={3} />
          </button>
        )}

        {/* Title - editable or display */}
        <div className="min-w-0 flex-1 flex items-center gap-2">
          {isEditing ? (
            <input
              ref={inputRef}
              type="text"
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              onKeyDown={handleKeyDown}
              onBlur={handleSaveTitle}
              disabled={isSaving}
              className="w-full text-13 bg-transparent text-stone-700 dark:text-stone-200 border border-stone-300 dark:border-stone-500 rounded px-1.5 py-0.5 focus:outline-none focus:ring-1 focus:ring-stone-400"
              onClick={(e) => e.stopPropagation()}
            />
          ) : (
            <div
              className={`truncate text-13 transition-colors ${
                isSelected
                  ? "text-stone-700 dark:text-stone-200"
                  : isActive
                    ? "text-stone-800 dark:text-stone-100 font-medium"
                    : "text-stone-600 dark:text-stone-300 group-hover:text-stone-700 dark:group-hover:text-stone-200"
              }`}
            >
              {displayTitle}
            </div>
          )}
        </div>

        {/* Task running indicator - same position/size as unread badge */}
        {isGenerating && taskStatusLabel && (
          <Tooltip content={taskStatusLabel} open={isTouched}>
            <span
              aria-label={taskStatusLabel}
              className="shrink-0 inline-flex items-center justify-center"
            >
              <span className="inline-flex items-center justify-center w-4 h-4 rounded-full border-2 border-amber-500/25 border-t-amber-500 dark:border-t-amber-400 animate-spin" />
            </span>
          </Tooltip>
        )}

        {isWaitingForHuman && (
          <Tooltip
            content={t("sidebar.waitingHuman", "等待回复")}
            open={isTouched}
          >
            <span
              data-session-status="ask-human"
              aria-label="Ask human · 等待你的回复"
              className="shrink-0 inline-flex items-center justify-center w-4 h-4 text-amber-500 dark:text-amber-400"
            >
              <AlertCircle size={16} strokeWidth={2.3} />
            </span>
          </Tooltip>
        )}

        {/* Unread dot - hidden when session is active (user is viewing it) */}
        {!selectionMode &&
          !isEditing &&
          !isActive &&
          (session.unread_count ?? 0) > 0 && (
            <span
              className={`shrink-0 inline-flex items-center justify-center rounded-full bg-red-500 text-10 font-medium leading-none text-white ${
                session.unread_count! <= 9
                  ? "w-4 h-4"
                  : "h-4 min-w-[20px] px-1.5"
              }`}
            >
              {session.unread_count}
            </span>
          )}
        {!selectionMode && !isEditing && (
          <Tooltip
            content={t("sidebar.moreOptions")}
            open={isTouched && !isMenuOpen}
          >
            <button
              ref={menuButtonRef}
              onClick={handleMenuClick}
              aria-label={t("sidebar.moreOptions")}
              className="flex-shrink-0 rounded p-1 hover:bg-stone-200/60 dark:hover:bg-stone-700/60 transition-all opacity-0 group-hover:opacity-100"
              style={isTouched ? { opacity: 1 } : undefined}
            >
              <MoreHorizontal
                size={14}
                className="text-stone-400 hover:text-stone-600 dark:text-stone-500 dark:hover:text-stone-300"
              />
            </button>
          </Tooltip>
        )}
      </div>
      {/* Context Menu */}
      {!selectionMode && (
        <SessionMenu
          session={session}
          projects={projects}
          isOpen={isMenuOpen}
          onClose={() => {
            setIsMenuOpen(false);
            setCursorPosition(null);
          }}
          onRename={handleStartEdit}
          onDelete={onDelete}
          onMoveToProject={onMoveToProject}
          onShare={onShare}
          onToggleFavorite={onToggleFavorite}
          onTogglePin={onTogglePin}
          anchorEl={menuAnchor}
          isFavorite={isFavorite}
          isPinned={isPinned}
          cursorPosition={cursorPosition ?? undefined}
          currentProjectId={currentProjectId}
        />
      )}
    </>
  );
}

function areSessionItemPropsEqual(
  prev: SessionItemProps,
  next: SessionItemProps,
): boolean {
  return (
    prev.session === next.session &&
    prev.isActive === next.isActive &&
    prev.projects === next.projects &&
    prev.isFavorite === next.isFavorite &&
    prev.isPinned === next.isPinned &&
    prev.currentProjectId === next.currentProjectId &&
    prev.isDraggingTouch === next.isDraggingTouch &&
    prev.selectionMode === next.selectionMode &&
    prev.isSelected === next.isSelected &&
    prev.onSessionUpdate === next.onSessionUpdate
  );
}

export const SessionItem = memo(SessionItemComponent, areSessionItemPropsEqual);
