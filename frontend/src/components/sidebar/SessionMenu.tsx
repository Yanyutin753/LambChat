/**
 * Session context menu component for session actions
 */

import { useRef, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Edit2, Trash2, FolderPlus, ChevronRight, X } from "lucide-react";
import type { BackendSession } from "../../services/api/session";
import type { Project } from "../../types";
import { DynamicIcon } from "../common/DynamicIcon";
import { useSwipeToClose } from "../../hooks/useSwipeToClose";

interface SessionMenuProps {
  session: BackendSession;
  projects: Project[];
  isOpen: boolean;
  onClose: () => void;
  onRename: () => void;
  onDelete: () => void;
  onMoveToProject: (projectId: string | null) => void;
  anchorEl: HTMLElement | null;
  isFavorite?: boolean;
}

export function SessionMenu({
  session: _session,
  projects,
  isOpen,
  onClose,
  onRename,
  onDelete,
  onMoveToProject,
  anchorEl,
  isFavorite = false,
}: SessionMenuProps) {
  // _session is available for future use (e.g., showing session info in menu)
  const { t } = useTranslation();
  const menuRef = useRef<HTMLDivElement>(null);
  const submenuRef = useRef<HTMLDivElement>(null);
  const [showProjectSubmenu, setShowProjectSubmenu] = useState(false);

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

  // Auto-scroll to submenu when expanded on mobile
  useEffect(() => {
    if (
      isMobile &&
      showProjectSubmenu &&
      submenuRef.current &&
      menuRef.current
    ) {
      // Use setTimeout to ensure DOM is updated before scrolling
      setTimeout(() => {
        submenuRef.current?.scrollIntoView({
          behavior: "smooth",
          block: "nearest",
        });
      }, 100);
    }
  }, [isMobile, showProjectSubmenu]);

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

  // Reset submenu when menu opens/closes
  useEffect(() => {
    if (!isOpen) {
      setShowProjectSubmenu(false);
    }
  }, [isOpen]);

  if (!isOpen || !anchorEl) return null;

  // Get favorites project if it exists
  const favoritesProject = projects.find((f) => f.type === "favorites");
  const customProjects = projects.filter((f) => f.type === "custom");

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
              {t("sidebar.sessionOptions")}
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

            {/* Move to project */}
            <div className="mt-1">
              <button
                onClick={() => setShowProjectSubmenu(!showProjectSubmenu)}
                className="w-full flex items-center justify-between gap-3 px-3 py-3 text-base text-stone-700 dark:text-stone-200 hover:bg-stone-100 dark:hover:bg-stone-700 rounded-lg transition-colors"
              >
                <div className="flex items-center gap-3">
                  <FolderPlus size={18} />
                  <span>{t("sidebar.moveToProject")}</span>
                </div>
                <ChevronRight
                  size={18}
                  className={`transition-transform ${
                    showProjectSubmenu ? "rotate-90" : ""
                  }`}
                />
              </button>

              {showProjectSubmenu && (
                <div
                  ref={submenuRef}
                  className="mt-1 ml-4 pl-3 border-l-2 border-stone-200 dark:border-stone-700"
                >
                  <p className="px-3 py-2 text-[11px] font-medium uppercase tracking-wider text-stone-400 dark:text-stone-500">
                    {t("sidebar.moveToProjectHint")}
                  </p>

                  {favoritesProject && (
                    <button
                      onClick={() => {
                        if (isFavorite) {
                          onMoveToProject(null);
                        } else {
                          onMoveToProject(favoritesProject.id);
                        }
                        onClose();
                      }}
                      className="w-full flex items-center gap-3 px-3 py-2.5 text-base text-stone-600 dark:text-stone-300 hover:bg-amber-50 dark:hover:bg-amber-900/20 hover:text-amber-700 dark:hover:text-amber-300 rounded-lg transition-colors"
                    >
                      <DynamicIcon
                        name={favoritesProject.icon}
                        size={18}
                        className={
                          isFavorite
                            ? "text-amber-500"
                            : "text-stone-400 dark:text-stone-500"
                        }
                      />
                      <span>
                        {isFavorite
                          ? t("sidebar.removeFromFavorites")
                          : t("sidebar.addToFavorites")}
                      </span>
                    </button>
                  )}

                  {customProjects.length > 0 && (
                    <>
                      {favoritesProject && (
                        <div className="h-px bg-stone-200/70 dark:bg-stone-700/50 mx-3 my-1" />
                      )}
                      {customProjects.map((project) => (
                        <button
                          key={project.id}
                          onClick={() => {
                            onMoveToProject(project.id);
                            onClose();
                          }}
                          className="w-full flex items-center gap-3 px-3 py-2.5 text-base text-stone-600 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-700/70 rounded-lg transition-colors"
                        >
                          <DynamicIcon
                            name={project.icon}
                            size={18}
                            className="text-stone-400 dark:text-stone-500 shrink-0"
                          />
                          <span className="truncate">{project.name}</span>
                        </button>
                      ))}
                    </>
                  )}

                  <div className="h-px bg-stone-200/70 dark:bg-stone-700/50 mx-3 my-1" />
                  <button
                    onClick={() => {
                      onMoveToProject(null);
                      onClose();
                    }}
                    className="w-full flex items-center gap-3 px-3 py-2.5 text-base text-stone-500 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-stone-700/70 rounded-lg transition-colors"
                  >
                    <DynamicIcon name="🏷️" size={18} className="shrink-0" />
                    <span>{t("sidebar.uncategorized")}</span>
                  </button>
                </div>
              )}
            </div>

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

  // Desktop: dropdown menu - open in direction with more space
  const rect = anchorEl.getBoundingClientRect();
  const spaceBelow = window.innerHeight - rect.bottom;
  const spaceAbove = rect.top;
  const openBelow = spaceBelow >= spaceAbove;

  const menuStyle: React.CSSProperties = {
    position: "fixed",
    ...(openBelow
      ? { top: rect.bottom + 4 }
      : { bottom: window.innerHeight - rect.top + 4 }),
    right: window.innerWidth - rect.right,
    maxHeight: (openBelow ? spaceBelow : spaceAbove) - 16,
    overflowY: "auto",
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

      {/* Move to project section */}
      <div>
        <button
          onClick={() => setShowProjectSubmenu(!showProjectSubmenu)}
          className="w-full flex items-center justify-between gap-2 px-3 py-2 text-sm text-stone-700 dark:text-stone-200 hover:bg-stone-100 dark:hover:bg-stone-700 transition-colors"
        >
          <div className="flex items-center gap-2">
            <FolderPlus size={14} />
            <span>{t("sidebar.moveToProject")}</span>
          </div>
          <ChevronRight
            size={14}
            className={`transition-transform ${
              showProjectSubmenu ? "rotate-90" : ""
            }`}
          />
        </button>

        {/* Project submenu - inline expansion */}
        {showProjectSubmenu && (
          <div className="bg-stone-50 dark:bg-stone-900/50 max-h-60 overflow-y-auto py-1">
            <p className="px-4 py-1.5 text-[11px] font-medium uppercase tracking-wider text-stone-400 dark:text-stone-500">
              {t("sidebar.moveToProjectHint")}
            </p>

            {/* Favorites option - only show if favorites project exists */}
            {favoritesProject && (
              <button
                onClick={() => {
                  if (isFavorite) {
                    onMoveToProject(null);
                  } else {
                    onMoveToProject(favoritesProject.id);
                  }
                  onClose();
                }}
                className="w-full flex items-center gap-2.5 px-4 py-1.5 text-sm text-stone-600 dark:text-stone-300 hover:bg-amber-50 dark:hover:bg-amber-900/20 hover:text-amber-700 dark:hover:text-amber-300 transition-colors"
              >
                <DynamicIcon
                  name={favoritesProject.icon}
                  size={14}
                  className={
                    isFavorite
                      ? "text-amber-500"
                      : "text-stone-400 dark:text-stone-500"
                  }
                />
                <span>
                  {isFavorite
                    ? t("sidebar.removeFromFavorites")
                    : t("sidebar.addToFavorites")}
                </span>
              </button>
            )}

            {/* Custom projects */}
            {customProjects.length > 0 && (
              <>
                {favoritesProject && (
                  <div className="h-px bg-stone-200/70 dark:bg-stone-700/50 mx-3" />
                )}
                {customProjects.map((project) => (
                  <button
                    key={project.id}
                    onClick={() => {
                      onMoveToProject(project.id);
                      onClose();
                    }}
                    className="w-full flex items-center gap-2.5 px-4 py-1.5 text-sm text-stone-600 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-700/70 transition-colors"
                  >
                    <DynamicIcon
                      name={project.icon}
                      size={14}
                      className="text-stone-400 dark:text-stone-500 shrink-0"
                    />
                    <span className="truncate">{project.name}</span>
                  </button>
                ))}
              </>
            )}

            {/* Uncategorized option */}
            <div className="h-px bg-stone-200/70 dark:bg-stone-700/50 mx-3" />
            <button
              onClick={() => {
                onMoveToProject(null);
                onClose();
              }}
              className="w-full flex items-center gap-2.5 px-4 py-1.5 text-sm text-stone-500 dark:text-stone-400 hover:bg-stone-100 dark:hover:bg-stone-700/70 transition-colors"
            >
              <DynamicIcon name="🏷️" size={14} className="shrink-0" />
              <span>{t("sidebar.uncategorized")}</span>
            </button>
          </div>
        )}
      </div>

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
