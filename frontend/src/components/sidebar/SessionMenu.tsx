/**
 * Session context menu component for session actions
 */

import { useRef, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Edit2, Trash2, FolderPlus, Star, ChevronRight } from "lucide-react";
import type { BackendSession } from "../../services/api/session";
import type { Folder } from "../../types";

interface SessionMenuProps {
  session: BackendSession;
  folders: Folder[];
  isOpen: boolean;
  onClose: () => void;
  onRename: () => void;
  onDelete: () => void;
  onMoveToFolder: (folderId: string | null) => void;
  anchorEl: HTMLElement | null;
  isFavorite?: boolean;
}

export function SessionMenu({
  session: _session,
  folders,
  isOpen,
  onClose,
  onRename,
  onDelete,
  onMoveToFolder,
  anchorEl,
  isFavorite = false,
}: SessionMenuProps) {
  // _session is available for future use (e.g., showing session info in menu)
  const { t } = useTranslation();
  const menuRef = useRef<HTMLDivElement>(null);
  const [showFolderSubmenu, setShowFolderSubmenu] = useState(false);

  // Close menu when clicking outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        menuRef.current &&
        !menuRef.current.contains(event.target as Node) &&
        !anchorEl?.contains(event.target as Node)
      ) {
        onClose();
      }
    };

    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
    }

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isOpen, onClose, anchorEl]);

  // Close on escape key
  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };

    if (isOpen) {
      document.addEventListener("keydown", handleEscape);
    }

    return () => {
      document.removeEventListener("keydown", handleEscape);
    };
  }, [isOpen, onClose]);

  if (!isOpen || !anchorEl) return null;

  // Calculate menu position
  const rect = anchorEl.getBoundingClientRect();
  const menuStyle: React.CSSProperties = {
    position: "fixed",
    top: rect.bottom + 4,
    right: window.innerWidth - rect.right,
    zIndex: 50,
  };

  // Get favorites folder if it exists
  const favoritesFolder = folders.find((f) => f.type === "favorites");
  const customFolders = folders.filter((f) => f.type === "custom");

  return (
    <div
      ref={menuRef}
      style={menuStyle}
      className="w-48 rounded-lg border border-gray-200 dark:border-stone-700 bg-white dark:bg-stone-800 shadow-lg py-1"
    >
      {/* Rename option */}
      <button
        onClick={() => {
          onRename();
          onClose();
        }}
        className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-700 dark:text-stone-200 hover:bg-gray-100 dark:hover:bg-stone-700 transition-colors"
      >
        <Edit2 size={14} />
        <span>{t("sidebar.rename", "Rename")}</span>
      </button>

      {/* Move to folder section */}
      <div
        className="relative"
        onMouseEnter={() => setShowFolderSubmenu(true)}
        onMouseLeave={() => setShowFolderSubmenu(false)}
      >
        <button className="w-full flex items-center justify-between gap-2 px-3 py-2 text-sm text-gray-700 dark:text-stone-200 hover:bg-gray-100 dark:hover:bg-stone-700 transition-colors">
          <div className="flex items-center gap-2">
            <FolderPlus size={14} />
            <span>{t("sidebar.moveToFolder", "Move to folder")}</span>
          </div>
          <ChevronRight size={14} />
        </button>

        {/* Folder submenu */}
        {showFolderSubmenu && (
          <div className="absolute left-0 top-0 -translate-x-full -ml-1 w-48 rounded-lg border border-gray-200 dark:border-stone-700 bg-white dark:bg-stone-800 shadow-lg py-1">
            {/* Favorites option - only show if favorites folder exists */}
            {favoritesFolder && (
              <button
                onClick={() => {
                  if (isFavorite) {
                    // Remove from favorites
                    onMoveToFolder(null);
                  } else {
                    // Add to favorites
                    onMoveToFolder(favoritesFolder.id);
                  }
                  onClose();
                }}
                className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-700 dark:text-stone-200 hover:bg-gray-100 dark:hover:bg-stone-700 transition-colors"
              >
                <Star
                  size={14}
                  className={
                    isFavorite ? "text-yellow-500 fill-yellow-500" : ""
                  }
                />
                <span>
                  {isFavorite
                    ? t("sidebar.removeFromFavorites", "Remove from Favorites")
                    : t("sidebar.addToFavorites", "Add to Favorites")}
                </span>
              </button>
            )}

            {/* Custom folders */}
            {customFolders.length > 0 && (
              <>
                {favoritesFolder && (
                  <div className="h-px bg-gray-200 dark:bg-stone-700 my-1" />
                )}
                {customFolders.map((folder) => (
                  <button
                    key={folder.id}
                    onClick={() => {
                      onMoveToFolder(folder.id);
                      onClose();
                    }}
                    className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-700 dark:text-stone-200 hover:bg-gray-100 dark:hover:bg-stone-700 transition-colors"
                  >
                    <span className="truncate">{folder.name}</span>
                  </button>
                ))}
              </>
            )}

            {/* Uncategorized option */}
            <div className="h-px bg-gray-200 dark:bg-stone-700 my-1" />
            <button
              onClick={() => {
                onMoveToFolder(null);
                onClose();
              }}
              className="w-full flex items-center gap-2 px-3 py-2 text-sm text-gray-500 dark:text-stone-400 hover:bg-gray-100 dark:hover:bg-stone-700 transition-colors"
            >
              <span>{t("sidebar.uncategorized", "Uncategorized")}</span>
            </button>
          </div>
        )}
      </div>

      {/* Divider */}
      <div className="h-px bg-gray-200 dark:bg-stone-700 my-1" />

      {/* Delete option */}
      <button
        onClick={() => {
          onDelete();
          onClose();
        }}
        className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
      >
        <Trash2 size={14} />
        <span>{t("common.delete", "Delete")}</span>
      </button>
    </div>
  );
}
