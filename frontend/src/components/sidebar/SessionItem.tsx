/**
 * Session item component with inline title editing and drag support
 */

import { useState, useRef, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { Star, MoreHorizontal, GripVertical } from "lucide-react";
import toast from "react-hot-toast";
import type { BackendSession } from "../../services/api/session";
import type { Folder } from "../../types";
import { sessionApi } from "../../services/api";
import { SessionMenu } from "./SessionMenu";

interface SessionItemProps {
  session: BackendSession;
  isActive: boolean;
  folders: Folder[];
  onSelect: () => void;
  onDelete: () => void;
  onMoveToFolder: (folderId: string | null) => void;
  onSessionUpdate: (session: BackendSession) => void;
  isFavorite?: boolean;
  onDragStart?: (session: BackendSession) => void;
  onDragEnd?: () => void;
}

export function SessionItem({
  session,
  isActive,
  folders,
  onSelect,
  onDelete,
  onMoveToFolder,
  onSessionUpdate,
  isFavorite = false,
  onDragStart,
  onDragEnd,
}: SessionItemProps) {
  const { t } = useTranslation();
  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [menuAnchor, setMenuAnchor] = useState<HTMLElement | null>(null);
  const [isDragging, setIsDragging] = useState(false);

  const inputRef = useRef<HTMLInputElement>(null);
  const menuButtonRef = useRef<HTMLButtonElement>(null);

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
        toast.success(t("sidebar.renamed", "Session renamed"));
      }
    } catch (error) {
      console.error("Failed to update session title:", error);
      toast.error(t("sidebar.renameFailed", "Failed to rename session"));
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

  // Drag handlers
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
        onClick={() => {
          if (!isEditing) {
            onSelect();
          }
        }}
        className={`group relative flex cursor-pointer items-center gap-2 rounded-lg px-2 py-2 transition-all duration-150 ${
          isActive
            ? "bg-stone-100 dark:bg-stone-800 border-l-2 border-stone-900 dark:border-stone-100"
            : "hover:bg-stone-50 dark:hover:bg-stone-800/50 border-l-2 border-transparent"
        } ${isDragging ? "opacity-50" : ""}`}
      >
        {/* Drag handle */}
        <div
          className="flex-shrink-0 cursor-grab opacity-0 group-hover:opacity-60 transition-opacity"
          onMouseDown={(e) => e.stopPropagation()}
        >
          <GripVertical
            size={14}
            className="text-stone-300 dark:text-stone-600"
          />
        </div>
        {/* Favorite star icon */}
        {isFavorite && (
          <Star
            size={14}
            className="flex-shrink-0 text-amber-500 fill-amber-500"
          />
        )}

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
              className="w-full text-sm bg-transparent text-stone-700 dark:text-stone-200 border border-stone-400 dark:border-stone-500 rounded px-1.5 py-0.5 focus:outline-none"
              onClick={(e) => e.stopPropagation()}
            />
          ) : (
            <div
              className={`truncate text-sm ${
                isActive
                  ? "font-medium text-stone-900 dark:text-stone-100"
                  : "text-stone-600 dark:text-stone-300"
              }`}
            >
              {displayTitle}
            </div>
          )}
        </div>

        {/* Menu button */}
        {!isEditing && (
          <button
            ref={menuButtonRef}
            onClick={handleMenuClick}
            className="flex-shrink-0 rounded-lg p-1 opacity-0 group-hover:opacity-100 hover:bg-stone-200 dark:hover:bg-stone-700 transition-all"
            title={t("sidebar.moreOptions", "More options")}
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
        folders={folders}
        isOpen={isMenuOpen}
        onClose={() => setIsMenuOpen(false)}
        onRename={handleStartEdit}
        onDelete={onDelete}
        onMoveToFolder={onMoveToFolder}
        anchorEl={menuAnchor}
        isFavorite={isFavorite}
      />
    </>
  );
}
