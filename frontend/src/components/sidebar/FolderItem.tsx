/**
 * Folder item component with expand/collapse and inline rename
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
import type { Folder } from "../../types";
import { folderApi } from "../../services/api";
import { SessionItem } from "./SessionItem";
import { FolderMenu } from "./FolderMenu";

interface FolderItemProps {
  folder: Folder;
  sessions: BackendSession[];
  currentSessionId: string | null;
  allFolders: Folder[];
  onSelectSession: (sessionId: string) => void;
  onDeleteSession: (sessionId: string) => void;
  onMoveSession: (sessionId: string, folderId: string | null) => void;
  onSessionUpdate: (session: BackendSession) => void;
  onRenameFolder: (folderId: string, name: string) => void;
  onDeleteFolder: (folderId: string) => void;
}

export function FolderItem({
  folder,
  sessions,
  currentSessionId,
  allFolders,
  onSelectSession,
  onDeleteSession,
  onMoveSession,
  onSessionUpdate,
  onRenameFolder,
  onDeleteFolder,
}: FolderItemProps) {
  const { t } = useTranslation();
  const [isExpanded, setIsExpanded] = useState(true);
  const [isEditing, setIsEditing] = useState(false);
  const [editName, setEditName] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [isMenuOpen, setIsMenuOpen] = useState(false);
  const [menuAnchor, setMenuAnchor] = useState<HTMLElement | null>(null);

  const inputRef = useRef<HTMLInputElement>(null);
  const menuButtonRef = useRef<HTMLButtonElement>(null);

  const isFavorites = folder.type === "favorites";

  // Start editing
  const handleStartEdit = () => {
    setEditName(folder.name);
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

  // Save folder name
  const handleSaveName = async () => {
    const trimmedName = editName.trim();

    // Don't save if name hasn't changed or is empty
    if (!trimmedName || trimmedName === folder.name) {
      setIsEditing(false);
      return;
    }

    setIsSaving(true);
    try {
      const updatedFolder = await folderApi.update(folder.id, {
        name: trimmedName,
      });
      onRenameFolder(folder.id, updatedFolder.name);
      toast.success(t("sidebar.folderRenamed", "Folder renamed"));
    } catch (error) {
      console.error("Failed to update folder name:", error);
      toast.error(t("sidebar.folderRenameFailed", "Failed to rename folder"));
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

  // Toggle expand/collapse
  const handleToggle = () => {
    if (!isEditing) {
      setIsExpanded(!isExpanded);
    }
  };

  return (
    <div className="mb-1">
      {/* Folder header */}
      <div
        onClick={handleToggle}
        className={`group relative flex cursor-pointer items-center gap-2 rounded-lg px-2 py-2 transition-colors ${
          isExpanded
            ? "bg-gray-100 dark:bg-stone-800"
            : "hover:bg-gray-50 dark:hover:bg-stone-800/50"
        }`}
      >
        {/* Chevron icon */}
        <ChevronRight
          size={16}
          className={`flex-shrink-0 text-gray-500 dark:text-stone-400 transition-transform ${
            isExpanded ? "rotate-90" : ""
          }`}
        />

        {/* Folder icon */}
        {isFavorites ? (
          <Star
            size={16}
            className="flex-shrink-0 text-yellow-500 fill-yellow-500"
          />
        ) : (
          <FolderIcon
            size={16}
            className="flex-shrink-0 text-gray-500 dark:text-stone-400"
          />
        )}

        {/* Folder name - editable or display */}
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
              className="w-full text-sm font-medium bg-transparent text-gray-700 dark:text-stone-200 border border-blue-500 dark:border-blue-400 rounded px-1 py-0.5 focus:outline-none focus:ring-1 focus:ring-blue-500 dark:focus:ring-blue-400"
              onClick={(e) => e.stopPropagation()}
            />
          ) : (
            <div className="truncate text-sm font-medium text-gray-700 dark:text-stone-200">
              {isFavorites ? t("sidebar.favorites", "Favorites") : folder.name}
            </div>
          )}
        </div>

        {/* Session count badge */}
        {sessions.length > 0 && (
          <span className="flex-shrink-0 text-xs text-gray-400 dark:text-stone-500 bg-gray-200 dark:bg-stone-700 rounded-full px-2 py-0.5">
            {sessions.length}
          </span>
        )}

        {/* Menu button - only for custom folders */}
        {!isFavorites && !isEditing && (
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

      {/* Expandable content - sessions list */}
      {isExpanded && sessions.length > 0 && (
        <div className="ml-4 mt-1 space-y-0.5 border-l border-gray-200 dark:border-stone-700 pl-2">
          {sessions.map((session) => (
            <SessionItem
              key={session.id}
              session={session}
              isActive={session.id === currentSessionId}
              folders={allFolders}
              onSelect={() => onSelectSession(session.id)}
              onDelete={() => onDeleteSession(session.id)}
              onMoveToFolder={(folderId) => onMoveSession(session.id, folderId)}
              onSessionUpdate={onSessionUpdate}
              isFavorite={isFavorites}
            />
          ))}
        </div>
      )}

      {/* Context Menu */}
      {!isFavorites && (
        <FolderMenu
          folder={folder}
          isOpen={isMenuOpen}
          onClose={() => setIsMenuOpen(false)}
          onRename={handleStartEdit}
          onDelete={() => onDeleteFolder(folder.id)}
          anchorEl={menuAnchor}
        />
      )}
    </div>
  );
}
