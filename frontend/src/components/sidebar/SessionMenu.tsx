/**
 * Session context menu component for session actions
 */

import { useRef, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Edit2, Trash2, FolderPlus, Star, ChevronRight, X } from "lucide-react";
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
  const submenuRef = useRef<HTMLDivElement>(null);
  const [showFolderSubmenu, setShowFolderSubmenu] = useState(false);

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

  // Auto-scroll to submenu when expanded on mobile
  useEffect(() => {
    if (
      isMobile &&
      showFolderSubmenu &&
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
  }, [isMobile, showFolderSubmenu]);

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
      setShowFolderSubmenu(false);
    }
  }, [isOpen]);

  if (!isOpen || !anchorEl) return null;

  // Get favorites folder if it exists
  const favoritesFolder = folders.find((f) => f.type === "favorites");
  const customFolders = folders.filter((f) => f.type === "custom");

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
          ref={menuRef}
          className="fixed bottom-0 left-0 right-0 z-50 sm:hidden bg-white dark:bg-stone-800 rounded-t-2xl shadow-xl max-h-[70vh] overflow-y-auto"
        >
          {/* Handle bar */}
          <div className="flex justify-center py-2">
            <div className="w-10 h-1 rounded-full bg-gray-300 dark:bg-stone-600" />
          </div>

          {/* Header */}
          <div className="flex items-center justify-between px-4 pb-2">
            <span className="text-sm font-medium text-stone-700 dark:text-stone-200">
              {t("sidebar.sessionOptions")}
            </span>
            <button
              onClick={onClose}
              className="p-1 rounded-full hover:bg-gray-100 dark:hover:bg-stone-700"
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
              className="w-full flex items-center gap-3 px-3 py-3 text-base text-gray-700 dark:text-stone-200 hover:bg-gray-100 dark:hover:bg-stone-700 rounded-lg transition-colors"
            >
              <Edit2 size={18} />
              <span>{t("sidebar.rename")}</span>
            </button>

            {/* Move to folder */}
            <div className="mt-1">
              <button
                onClick={() => setShowFolderSubmenu(!showFolderSubmenu)}
                className="w-full flex items-center justify-between gap-3 px-3 py-3 text-base text-gray-700 dark:text-stone-200 hover:bg-gray-100 dark:hover:bg-stone-700 rounded-lg transition-colors"
              >
                <div className="flex items-center gap-3">
                  <FolderPlus size={18} />
                  <span>{t("sidebar.moveToFolder")}</span>
                </div>
                <ChevronRight
                  size={18}
                  className={`transition-transform ${
                    showFolderSubmenu ? "rotate-90" : ""
                  }`}
                />
              </button>

              {showFolderSubmenu && (
                <div
                  ref={submenuRef}
                  className="mt-1 ml-4 pl-3 border-l-2 border-gray-200 dark:border-stone-700"
                >
                  <p className="px-3 py-2 text-xs text-stone-400 dark:text-stone-500">
                    {t("sidebar.moveToFolderHint")}
                  </p>

                  {favoritesFolder && (
                    <button
                      onClick={() => {
                        if (isFavorite) {
                          onMoveToFolder(null);
                        } else {
                          onMoveToFolder(favoritesFolder.id);
                        }
                        onClose();
                      }}
                      className="w-full flex items-center gap-3 px-3 py-3 text-base text-gray-700 dark:text-stone-200 hover:bg-gray-100 dark:hover:bg-stone-700 rounded-lg transition-colors"
                    >
                      <Star
                        size={18}
                        className={
                          isFavorite ? "text-yellow-500 fill-yellow-500" : ""
                        }
                      />
                      <span>
                        {isFavorite
                          ? t("sidebar.removeFromFavorites")
                          : t("sidebar.addToFavorites")}
                      </span>
                    </button>
                  )}

                  {customFolders.length > 0 && (
                    <>
                      {favoritesFolder && (
                        <div className="h-px bg-gray-200 dark:bg-stone-700 mx-3 my-1" />
                      )}
                      {customFolders.map((folder) => (
                        <button
                          key={folder.id}
                          onClick={() => {
                            onMoveToFolder(folder.id);
                            onClose();
                          }}
                          className="w-full flex items-center gap-3 px-3 py-3 text-base text-gray-700 dark:text-stone-200 hover:bg-gray-100 dark:hover:bg-stone-700 rounded-lg transition-colors"
                        >
                          <span className="truncate">{folder.name}</span>
                        </button>
                      ))}
                    </>
                  )}

                  <div className="h-px bg-gray-200 dark:bg-stone-700 mx-3 my-1" />
                  <button
                    onClick={() => {
                      onMoveToFolder(null);
                      onClose();
                    }}
                    className="w-full flex items-center gap-3 px-3 py-3 text-base text-gray-500 dark:text-stone-400 hover:bg-gray-100 dark:hover:bg-stone-700 rounded-lg transition-colors"
                  >
                    <span>{t("sidebar.uncategorized")}</span>
                  </button>
                </div>
              )}
            </div>

            {/* Divider */}
            <div className="h-px bg-gray-200 dark:bg-stone-700 my-2" />

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
        <span>{t("sidebar.rename")}</span>
      </button>

      {/* Move to folder section */}
      <div>
        <button
          onClick={() => setShowFolderSubmenu(!showFolderSubmenu)}
          className="w-full flex items-center justify-between gap-2 px-3 py-2 text-sm text-gray-700 dark:text-stone-200 hover:bg-gray-100 dark:hover:bg-stone-700 transition-colors"
        >
          <div className="flex items-center gap-2">
            <FolderPlus size={14} />
            <span>{t("sidebar.moveToFolder")}</span>
          </div>
          <ChevronRight
            size={14}
            className={`transition-transform ${
              showFolderSubmenu ? "rotate-90" : ""
            }`}
          />
        </button>

        {/* Folder submenu - inline expansion */}
        {showFolderSubmenu && (
          <div className="bg-gray-50 dark:bg-stone-900/50">
            <p className="px-3 py-1.5 text-xs text-stone-400 dark:text-stone-500">
              {t("sidebar.moveToFolderHint")}
            </p>

            {/* Favorites option - only show if favorites folder exists */}
            {favoritesFolder && (
              <button
                onClick={() => {
                  if (isFavorite) {
                    onMoveToFolder(null);
                  } else {
                    onMoveToFolder(favoritesFolder.id);
                  }
                  onClose();
                }}
                className="w-full flex items-center gap-2 px-3 py-2 pl-8 text-sm text-gray-700 dark:text-stone-200 hover:bg-gray-100 dark:hover:bg-stone-700 transition-colors"
              >
                <Star
                  size={14}
                  className={
                    isFavorite ? "text-yellow-500 fill-yellow-500" : ""
                  }
                />
                <span>
                  {isFavorite
                    ? t("sidebar.removeFromFavorites")
                    : t("sidebar.addToFavorites")}
                </span>
              </button>
            )}

            {/* Custom folders */}
            {customFolders.length > 0 && (
              <>
                {favoritesFolder && (
                  <div className="h-px bg-gray-200 dark:bg-stone-700 mx-3" />
                )}
                {customFolders.map((folder) => (
                  <button
                    key={folder.id}
                    onClick={() => {
                      onMoveToFolder(folder.id);
                      onClose();
                    }}
                    className="w-full flex items-center gap-2 px-3 py-2 pl-8 text-sm text-gray-700 dark:text-stone-200 hover:bg-gray-100 dark:hover:bg-stone-700 transition-colors"
                  >
                    <span className="truncate">{folder.name}</span>
                  </button>
                ))}
              </>
            )}

            {/* Uncategorized option */}
            <div className="h-px bg-gray-200 dark:bg-stone-700 mx-3" />
            <button
              onClick={() => {
                onMoveToFolder(null);
                onClose();
              }}
              className="w-full flex items-center gap-2 px-3 py-2 pl-8 text-sm text-gray-500 dark:text-stone-400 hover:bg-gray-100 dark:hover:bg-stone-700 transition-colors"
            >
              <span>{t("sidebar.uncategorized")}</span>
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
        <span>{t("common.delete")}</span>
      </button>
    </div>
  );
}
