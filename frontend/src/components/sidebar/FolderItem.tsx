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
  const [isDragOver, setIsDragOver] = useState(false);

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

  // Drag and drop handlers
  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = "move";
    setIsDragOver(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    // Only set dragOver to false if we're leaving the folder entirely
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
      onMoveSession(sessionId, folder.id);
    }
  };

  return (
    <div className="mb-1">
      {/* Folder header - drop target */}
      <div
        onClick={handleToggle}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={`group relative flex cursor-pointer items-center gap-2 rounded-lg px-2 py-2 transition-all duration-200 ${
          isDragOver
            ? "bg-blue-50 dark:bg-blue-900/20 ring-1 ring-blue-400 dark:ring-blue-500"
            : isExpanded
              ? "bg-stone-100/70 dark:bg-stone-800/70"
              : "hover:bg-stone-50 dark:hover:bg-stone-800/50"
        }`}
      >
        {/* Chevron icon */}
        <ChevronRight
          size={16}
          className={`flex-shrink-0 text-stone-400 dark:text-stone-500 transition-transform duration-200 ${
            isExpanded ? "rotate-90" : ""
          }`}
        />

        {/* Folder icon */}
        {isFavorites ? (
          <Star
            size={16}
            className="flex-shrink-0 text-amber-500 fill-amber-500"
          />
        ) : (
          <FolderIcon
            size={16}
            className="flex-shrink-0 text-stone-400 dark:text-stone-500"
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
              className="w-full text-sm font-medium bg-transparent text-stone-700 dark:text-stone-200 border border-stone-400 dark:border-stone-500 rounded px-1.5 py-0.5 focus:outline-none"
              onClick={(e) => e.stopPropagation()}
            />
          ) : (
            <div className="truncate text-sm font-medium text-stone-700 dark:text-stone-200">
              {isFavorites ? t("sidebar.favorites", "Favorites") : folder.name}
            </div>
          )}
        </div>

        {/* Session count badge */}
        {sessions.length > 0 && (
          <span className="flex-shrink-0 text-xs text-stone-400 dark:text-stone-500 bg-stone-100 dark:bg-stone-700 rounded-full px-2 py-0.5 font-medium">
            {sessions.length}
          </span>
        )}

        {/* Menu button - only for custom folders */}
        {!isFavorites && !isEditing && (
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

      {/* Expandable content - sessions list */}
      {isExpanded && sessions.length > 0 && (
        <div className="ml-3 mt-1 space-y-0.5 border-l-2 border-stone-200 dark:border-stone-700 pl-3">
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
