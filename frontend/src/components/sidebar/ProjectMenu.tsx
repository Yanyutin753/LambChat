import { DialogCloseButton } from "../common/DialogCloseButton";
import { ModalSurface } from "../common/ModalSurface";
/**
 * Project context menu component for project actions
 */

import { useRef, useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import { Edit2, Trash2, SquarePen, Share2 } from "lucide-react";
import type { Project } from "../../types";

import { useStickyDropdownPosition } from "../../hooks/useStickyDropdownPosition";
import { ProjectWorkspaceField } from "./ProjectWorkspaceField";

interface ProjectMenuProps {
  project: Project;
  isOpen: boolean;
  onClose: () => void;
  onRename: () => void;
  onDelete: () => void;
  onShare?: () => void;
  onNewSessionInProject?: (projectId: string) => void;
  anchorEl: HTMLElement | null;
  onWorkspaceChange?: (workspace: Project["workspace"]) => Promise<void>;
}

export function ProjectMenu({
  project: _project,
  isOpen,
  onClose,
  onRename,
  onDelete,
  onShare,
  onNewSessionInProject,
  anchorEl,
  onWorkspaceChange,
}: ProjectMenuProps) {
  // _project is available for future use (e.g., showing project info in menu)
  const { t } = useTranslation();
  const menuRef = useRef<HTMLDivElement>(null);
  const anchorRef = useRef(anchorEl);
  anchorRef.current = anchorEl;

  const menuStyle = useStickyDropdownPosition(anchorRef, isOpen, (rect) => ({
    position: "fixed",
    top: rect.bottom + 4,
    right: window.innerWidth - rect.right,
    zIndex: 50,
  }));

  // Reactive mobile detection
  const [isMobile, setIsMobile] = useState(() => {
    if (typeof window === "undefined") return false;
    return window.innerWidth < 640;
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
      if (isMobile) return;
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
  }, [isOpen, onClose, anchorEl, isMobile]);

  // Close on escape key
  useEffect(() => {
    const handleEscape = (event: KeyboardEvent) => {
      if (isMobile) return;
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
  }, [isOpen, onClose, isMobile]);

  if (!isOpen || !anchorEl) return null;

  // Mobile: bottom sheet style
  if (isMobile) {
    return (
      <ModalSurface open onClose={onClose} label={t("sidebar.projectOptions")}>
        <div
          ref={menuRef}
          className="safe-area-bottom bg-theme-bg-card rounded-t-2xl shadow-xl max-h-[70dvh] overflow-y-auto"
        >
          {/* Header */}
          <div className="flex items-center justify-between px-4 pb-1.5">
            <span className="text-13 font-medium text-[var(--theme-text)]">
              {t("sidebar.projectOptions")}
            </span>
            <DialogCloseButton onClick={onClose} />
          </div>

          {/* Menu items */}
          <div className="px-2 pb-4">
            {onWorkspaceChange && (
              <ProjectWorkspaceField
                value={_project.workspace}
                onChange={onWorkspaceChange}
              />
            )}
            {/* New Session */}
            {onNewSessionInProject && (
              <button
                onClick={() => {
                  onNewSessionInProject(_project.id);
                  onClose();
                }}
                className="w-full flex items-center gap-2.5 px-3 py-2.5 text-13 text-[var(--theme-text-secondary)] hover:bg-stone-100 dark:hover:bg-stone-700 rounded-lg transition-colors"
              >
                <SquarePen size={16} />
                <span>{t("sidebar.newChat")}</span>
              </button>
            )}

            {/* Rename */}
            <button
              onClick={() => {
                onRename();
                onClose();
              }}
              className="w-full flex items-center gap-2.5 px-3 py-2.5 text-13 text-[var(--theme-text-secondary)] hover:bg-stone-100 dark:hover:bg-stone-700 rounded-lg transition-colors"
            >
              <Edit2 size={16} />
              <span>{t("sidebar.rename")}</span>
            </button>

            {/* Share project */}
            {onShare && (
              <button
                onClick={() => {
                  onShare();
                  onClose();
                }}
                className="w-full flex items-center gap-2.5 px-3 py-2.5 text-13 text-[var(--theme-text-secondary)] hover:bg-stone-100 dark:hover:bg-stone-700 rounded-lg transition-colors"
              >
                <Share2 size={16} />
                <span>{t("sidebar.shareProject", "分享项目")}</span>
              </button>
            )}

            {/* Divider */}
            <div className="h-px bg-stone-200 dark:bg-stone-700 my-1.5" />

            {/* Delete */}
            <button
              onClick={() => {
                onDelete();
                onClose();
              }}
              className="w-full flex items-center gap-2.5 px-3 py-2.5 text-13 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 rounded-lg transition-colors"
            >
              <Trash2 size={16} />
              <span>{t("common.delete")}</span>
            </button>
          </div>
        </div>
      </ModalSurface>
    );
  }

  // Desktop: dropdown menu
  return createPortal(
    <div
      ref={menuRef}
      style={menuStyle}
      className="w-48 rounded-lg border border-stone-200 dark:border-stone-700 bg-white dark:bg-stone-800 shadow-lg py-1"
    >
      {onWorkspaceChange && (
        <ProjectWorkspaceField
          value={_project.workspace}
          onChange={onWorkspaceChange}
        />
      )}
      {/* Rename option */}
      <button
        onClick={() => {
          onRename();
          onClose();
        }}
        className="w-full flex items-center gap-2 px-3 py-2 text-14 text-[var(--theme-text-secondary)] hover:bg-stone-100 dark:hover:bg-stone-700 transition-colors"
      >
        <Edit2 size={14} />
        <span>{t("sidebar.rename")}</span>
      </button>

      {/* Share project option */}
      {onShare && (
        <button
          onClick={() => {
            onShare();
            onClose();
          }}
          className="w-full flex items-center gap-2 px-3 py-2 text-14 text-[var(--theme-text-secondary)] hover:bg-stone-100 dark:hover:bg-stone-700 transition-colors"
        >
          <Share2 size={14} />
          <span>{t("sidebar.shareProject", "分享项目")}</span>
        </button>
      )}

      {/* New Session option */}
      {onNewSessionInProject && (
        <button
          onClick={() => {
            onNewSessionInProject(_project.id);
            onClose();
          }}
          className="w-full flex items-center gap-2 px-3 py-2 text-14 text-[var(--theme-text-secondary)] hover:bg-stone-100 dark:hover:bg-stone-700 transition-colors"
        >
          <SquarePen size={14} />
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
        className="w-full flex items-center gap-2 px-3 py-2 text-14 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 transition-colors"
      >
        <Trash2 size={14} />
        <span>{t("common.delete")}</span>
      </button>
    </div>,
    document.body,
  );
}
