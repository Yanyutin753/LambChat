/**
 * Folder context menu component for folder actions
 */

import { useRef, useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Edit2, Trash2 } from "lucide-react";
import type { Folder } from "../../types";

interface FolderMenuProps {
  folder: Folder;
  isOpen: boolean;
  onClose: () => void;
  onRename: () => void;
  onDelete: () => void;
  anchorEl: HTMLElement | null;
}

export function FolderMenu({
  folder: _folder,
  isOpen,
  onClose,
  onRename,
  onDelete,
  anchorEl,
}: FolderMenuProps) {
  // _folder is available for future use (e.g., showing folder info in menu)
  const { t } = useTranslation();
  const menuRef = useRef<HTMLDivElement>(null);

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
