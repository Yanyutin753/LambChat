/**
 * Project context menu component for project actions
 */

import { useRef, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Edit2, Trash2, MessageSquarePlus, X } from "lucide-react";
import type { Project } from "../../types";
import { useSwipeToClose } from "../../hooks/useSwipeToClose";

interface ProjectMenuProps {
  project: Project;
  isOpen: boolean;
  onClose: () => void;
  onRename: () => void;
  onDelete: () => void;
  onNewSessionInProject?: (projectId: string) => void;
  anchorEl: HTMLElement | null;
}

export function ProjectMenu({
  project: _project,
  isOpen,
  onClose,
  onRename,
  onDelete,
  onNewSessionInProject,
  anchorEl,
}: ProjectMenuProps) {
  // _project is available for future use (e.g., showing project info in menu)
  const { t } = useTranslation();
  const menuRef = useRef<HTMLDivElement>(null);

  // Reactive mobile detection
  const [isMobile, setIsMobile] = useState(() => {
    if (typeof window === "undefined") return false;
    return window.innerWidth < 640;
  });

  const swipeRef = useSwipeToClose({
    onClose,
    enabled: isOpen && isMobile,
  });

  // Update isMobile on resize
  useEffect(() => {
    const handleResize = () => {
      setIsMobile(window.innerWidth < 640);
    };

    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, []);

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

  // Mobile: bottom sheet style
  if (isMobile) {
    return (
      <>
        {/* Backdrop */}
        <div
          className="fixed inset-0 z-40 bg-black/50 sm:hidden"
          onClick={onClose}
        />
        {/* Bottom sheet */}
        <div
          ref={(el) => {
            menuRef.current = el;
            swipeRef.current = el;
          }}
          className="fixed bottom-0 left-0 right-0 z-50 sm:hidden bg-white dark:bg-stone-800 rounded-t-2xl shadow-xl max-h-[70vh] overflow-y-auto"
        >
          {/* Handle bar */}
          <div className="flex justify-center py-2">
            <div className="w-10 h-1 rounded-full bg-stone-300 dark:bg-stone-600" />
          </div>

          {/* Header */}
          <div className="flex items-center justify-between px-4 pb-2">
            <span className="text-sm font-medium text-stone-700 dark:text-stone-200">
              {t("sidebar.projectOptions")}
            </span>
            <button
              onClick={onClose}
              className="p-1 rounded-full hover:bg-stone-100 dark:hover:bg-stone-700"
            >
              <X size={18} className="text-stone-400" />
            </button>
          </div>

          {/* Menu items */}
          <div className="px-2 pb-4">
            {/* New Session */}
            {onNewSessionInProject && (
              <button
                onClick={() => {
                  onNewSessionInProject(_project.id);
                  onClose();
                }}
                className="w-full flex items-center gap-3 px-3 py-3 text-base text-stone-700 dark:text-stone-200 hover:bg-stone-100 dark:hover:bg-stone-700 rounded-lg transition-colors"
              >
                <MessageSquarePlus size={18} />
                <span>{t("sidebar.newChat")}</span>
              </button>
            )}

            {/* Rename */}
            <button
              onClick={() => {
                onRename();
                onClose();
              }}
              className="w-full flex items-center gap-3 px-3 py-3 text-base text-stone-700 dark:text-stone-200 hover:bg-stone-100 dark:hover:bg-stone-700 rounded-lg transition-colors"
            >
              <Edit2 size={18} />
              <span>{t("sidebar.rename")}</span>
            </button>

            {/* Divider */}
            <div className="h-px bg-stone-200 dark:bg-stone-700 my-2" />

            {/* Delete */}
            <button
              onClick={() => {
                onDelete();
                onClose();
              }}
              className="w-full flex items-center gap-3 px-3 py-3 text-base text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
            >
              <Trash2 size={18} />
              <span>{t("common.delete")}</span>
            </button>
          </div>
        </div>
      </>
    );
  }

  // Desktop: dropdown menu
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
      className="w-48 rounded-lg border border-stone-200 dark:border-stone-700 bg-white dark:bg-stone-800 shadow-lg py-1"
    >
      {/* Rename option */}
      <button
        onClick={() => {
          onRename();
          onClose();
        }}
        className="w-full flex items-center gap-2 px-3 py-2 text-sm text-stone-700 dark:text-stone-200 hover:bg-stone-100 dark:hover:bg-stone-700 transition-colors"
      >
        <Edit2 size={14} />
        <span>{t("sidebar.rename")}</span>
      </button>

      {/* New Session option */}
      {onNewSessionInProject && (
        <button
          onClick={() => {
            onNewSessionInProject(_project.id);
            onClose();
          }}
          className="w-full flex items-center gap-2 px-3 py-2 text-sm text-stone-700 dark:text-stone-200 hover:bg-stone-100 dark:hover:bg-stone-700 transition-colors"
        >
          <MessageSquarePlus size={14} />
          <span>{t("sidebar.newChat")}</span>
        </button>
      )}

      {/* Divider */}
      <div className="h-px bg-stone-200 dark:bg-stone-700 my-1" />

      {/* Delete option */}
      <button
        onClick={() => {
          onDelete();
          onClose();
        }}
        className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
      >
        <Trash2 size={14} />
        <span>{t("common.delete")}</span>
      </button>
    </div>
  );
}
