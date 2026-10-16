import { InteractiveIcon } from "../common/InteractiveIcon";
import { LoadingSpinner } from "../common/LoadingSpinner";
/**
 * Session item component with inline title editing and drag support
 */

import { memo, useState, useRef, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertCircle,
  Check,
  MessageCircle,
  MoreHorizontal,
} from "lucide-react";
import toast from "react-hot-toast";
import type { BackendSession } from "../../services/api/session";
import type { Project } from "../../types";
import { sessionApi } from "../../services/api";
import { SessionMenu } from "./SessionMenu";
import { getSessionTaskIndicator } from "./sessionTaskIndicator";
import { formatDateTime, formatTimeAgo, parseDate } from "../../utils/datetime";
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

  const rowRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const titleRef = useRef<HTMLButtonElement>(null);
  const returnTitleFocusRef = useRef(false);
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
    returnTitleFocusRef.current = false;
    setEditTitle(getSessionTitle(session));
    setIsEditing(true);
    setIsMenuOpen(false);
  };

  // Focus input when editing starts
  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    } else {
      if (
        returnTitleFocusRef.current &&
        document.activeElement === document.body
      ) {
        titleRef.current?.focus();
      }
      returnTitleFocusRef.current = false;
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
      returnTitleFocusRef.current = true;
      handleSaveTitle();
    } else if (e.key === "Escape") {
      e.preventDefault();
      returnTitleFocusRef.current = true;
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
    if (selectionMode) {
      e.preventDefault();
      return;
    }
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
    e.dataTransfer.setData("application/x-lambchat-session", session.id);
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
  const taskIndicator = getSessionTaskIndicator(session.metadata?.task_status);
  const isWaitingForHuman = taskIndicator.kind === "attention";
  const isGenerating = taskIndicator.kind === "busy";
  const taskStatusLabel =
    isGenerating && taskIndicator.labelKey
      ? t(
          taskIndicator.labelKey,
          taskIndicator.labelKey === "sidebar.pendingStatus"
            ? "等待中"
            : "运行中",
        )
      : null;
  const hasUnread = !isActive && (session.unread_count ?? 0) > 0;
  const unreadLabel = t("sidebar.unreadMessages", {
    count: session.unread_count ?? 0,
  });
  const validUpdatedAt = Number.isFinite(
    parseDate(session.updated_at).getTime(),
  );
  const attentionLabel = t("sidebar.waitingHuman", "等待回复");

  const activate = () => {
    if (wasDraggingRef.current) {
      wasDraggingRef.current = false;
      return;
    }
    if (shouldBlockSessionSelection(window.location.pathname)) return;
    if (selectionMode) onToggleSelected?.();
    else if (!isEditing) onSelect();
  };

  return (
    <>
      <div
        ref={rowRef}
        role="group"
        aria-label={displayTitle}
        data-selected={isSelected || (!selectionMode && isActive) || undefined}
        draggable={!selectionMode}
        onDragStart={handleDragStart}
        onDragEnd={handleDragEnd}
        onTouchStart={handleItemTouchStart}
        onTouchMove={handleItemTouchMove}
        onTouchEnd={handleItemTouchEnd}
        onContextMenu={handleContextMenu}
        onClick={activate}
        // Keep taps on mobile as normal activation gestures; the long-press
        // handlers below still own drag initiation once movement is detected.
        style={
          isDragging ? { touchAction: "none" } : { touchAction: "manipulation" }
        }
        className={`sidebar-session-row sidebar-action-row group relative flex cursor-pointer items-center gap-1 h-8 max-sm:h-10 rounded-[10px] px-[9px] transition-colors ${
          isDragging || isDraggingTouch ? "opacity-50 scale-95" : ""
        } ${selectionMode ? "pr-2" : ""}`}
      >
        {/* Title - editable or display */}
        <div className="min-w-0 flex-1 flex items-center gap-2">
          {isEditing && !selectionMode ? (
            <input
              ref={inputRef}
              type="text"
              aria-label={`${t("sidebar.rename")} ${displayTitle}`}
              value={editTitle}
              onChange={(e) => setEditTitle(e.target.value)}
              onKeyDown={handleKeyDown}
              onBlur={handleSaveTitle}
              disabled={isSaving}
              className="w-full text-13 bg-transparent text-theme-text dark:text-stone-200 border border-theme-border-hover dark:border-stone-500 rounded px-1.5 py-0.5 focus:outline-hidden focus:ring-1 focus:ring-theme-ring"
              onClick={(e) => e.stopPropagation()}
            />
          ) : (
            <Tooltip
              placement="right"
              align="start"
              anchorRef={rowRef}
              hoverDelay={450}
              variant="card"
              disabled={
                selectionMode || isMenuOpen || isDragging || isDraggingTouch
              }
              content={
                <span className="flex w-72 max-w-full flex-col gap-1.5">
                  <span className="flex items-start gap-3">
                    <span className="min-w-0 flex-1 break-words text-13 leading-5 font-medium">
                      {displayTitle}
                    </span>
                    {validUpdatedAt && (
                      <time
                        dateTime={session.updated_at}
                        title={formatDateTime(session.updated_at)}
                        className="shrink-0 text-11 text-theme-text-tertiary"
                      >
                        {formatTimeAgo(t, session.updated_at)}
                      </time>
                    )}
                    {hasUnread && (
                      <span
                        role="img"
                        aria-label={unreadLabel}
                        className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-theme-primary"
                      />
                    )}
                  </span>
                  <span className="flex items-center gap-1.5 text-theme-text-secondary">
                    <MessageCircle size={14} aria-hidden="true" />
                    <span>{t("nav.chat")}</span>
                    {(taskStatusLabel || isWaitingForHuman) && (
                      <span className="ml-auto text-11">
                        {taskStatusLabel || attentionLabel}
                      </span>
                    )}
                  </span>
                </span>
              }
            >
              <button
                ref={titleRef}
                type="button"
                role={selectionMode ? "checkbox" : undefined}
                aria-current={!selectionMode && isActive ? "page" : undefined}
                aria-checked={selectionMode ? isSelected : undefined}
                onClick={(e) => {
                  e.stopPropagation();
                  activate();
                }}
                className={`truncate text-13 font-serif transition-colors ${
                  isSelected
                    ? "text-theme-text dark:text-stone-200"
                    : isActive
                      ? "text-theme-text dark:text-stone-100 font-medium"
                      : "text-theme-text-secondary dark:text-stone-300 group-hover:text-theme-text dark:group-hover:text-stone-200"
                } min-w-0 w-full h-8 max-sm:h-9 rounded text-left flex items-center gap-1 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--theme-primary)]`}
              >
                {selectionMode && (
                  <span
                    aria-hidden="true"
                    className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-[4px] border transition-colors ${
                      isSelected
                        ? "border-theme-primary bg-theme-primary text-white"
                        : "border-theme-border-hover bg-transparent text-transparent group-hover:border-theme-ring"
                    }`}
                  >
                    <InteractiveIcon>
                      <Check size={11} strokeWidth={3} />
                    </InteractiveIcon>
                  </span>
                )}

                <span className="truncate leading-5">{displayTitle}</span>
              </button>
            </Tooltip>
          )}
        </div>

        {/* Task running indicator - same position/size as unread badge */}
        {isGenerating && taskStatusLabel && (
          <Tooltip content={taskStatusLabel}>
            <span
              aria-label={taskStatusLabel}
              className="shrink-0 inline-flex h-8 w-6 max-sm:h-9 max-sm:w-9 items-center justify-center"
            >
              <LoadingSpinner size="sm" color="text-[var(--theme-primary)]" />
            </span>
          </Tooltip>
        )}

        {isWaitingForHuman && (
          <Tooltip content={attentionLabel}>
            <span
              data-session-status="ask-human"
              aria-label={attentionLabel}
              className="shrink-0 inline-flex items-center justify-center h-8 w-6 max-sm:h-9 max-sm:w-9 text-amber-500 dark:text-amber-400"
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
            <span className="inline-flex h-8 w-6 shrink-0 items-center justify-center max-sm:h-9 max-sm:w-9">
              <span
                role="img"
                aria-label={unreadLabel}
                className="h-1.5 w-1.5 rounded-full bg-theme-primary"
              />
            </span>
          )}
        {!selectionMode && !isEditing && (
          <Tooltip content={t("sidebar.moreOptions")}>
            <button
              type="button"
              ref={menuButtonRef}
              onClick={handleMenuClick}
              aria-label={t("sidebar.moreOptions")}
              className="sidebar-action-reveal flex h-8 w-6 shrink-0 items-center justify-center rounded-md max-sm:h-9 max-sm:w-9 focus-visible:outline focus-visible:outline-2"
              style={isTouched || isMenuOpen ? { opacity: 1 } : undefined}
            >
              <InteractiveIcon>
                <MoreHorizontal
                  size={14}
                  className="text-theme-text-tertiary hover:text-theme-text-secondary dark:text-stone-500 dark:hover:text-stone-300"
                />
              </InteractiveIcon>
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
