/**
 * Session item component with inline title editing
 */

import { useState, useRef, useEffect, useCallback } from "react";
import { useTranslation } from "react-i18next";
import { Star, MoreHorizontal } from "lucide-react";
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
}: SessionItemProps) {
  const { t } = useTranslation();
  const [isEditing, setIsEditing] = useState(false);
  const [editTitle, setEditTitle] = useState("");
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [menuAnchor, setMenuAnchor] = useState<HTMLElement | null>(null);

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

  // Get display title
  const displayTitle = getSessionTitle(session);

  return (
    <>
      <div
        onClick={() => {
          if (!isEditing) {
            onSelect();
          }
        }}
        className={`group relative flex cursor-pointer items-center gap-2 rounded-lg px-2 py-2.5 transition-colors ${
          isActive
            ? "bg-gray-100 dark:bg-stone-800"
            : "hover:bg-gray-50 dark:hover:bg-stone-800/50"
        }`}
      >
        {/* Favorite star icon */}
        {isFavorite && (
          <Star
            size={14}
            className="flex-shrink-0 text-yellow-500 fill-yellow-500"
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
              className="w-full text-sm bg-transparent text-gray-700 dark:text-stone-200 border border-blue-500 dark:border-blue-400 rounded px-1 py-0.5 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:focus:ring-blue-400"
              onClick={(e) => e.stopPropagation()}
            />
          ) : (
            <div className="truncate text-sm text-gray-700 dark:text-stone-200">
              {displayTitle}
            </div>
          )}
        </div>

        {/* Menu button */}
        {!isEditing && (
          <button
            ref={menuButtonRef}
            onClick={handleMenuClick}
            className="flex-shrink-0 rounded p-1 opacity-0 group-hover:opacity-100 hover:bg-gray-200 dark:hover:bg-stone-700 transition-all"
            title={t("sidebar.moreOptions", "More options")}
          >
            <MoreHorizontal
              size={14}
              className="text-gray-400 hover:text-gray-600 dark:text-stone-500 dark:hover:text-stone-300"
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
