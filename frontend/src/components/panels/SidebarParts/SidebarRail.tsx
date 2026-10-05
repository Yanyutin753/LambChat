import { SidebarToggleIcon } from "../../common/SidebarToggleIcon";
import {
  SquarePen,
  Search,
  CalendarClock,
  History,
  MoreHorizontal,
  FolderOpen,
  Bookmark,
} from "lucide-react";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../../hooks/useAuth";
import { Permission } from "../../../types/auth";
import { getFullUrl } from "../../../services/api";
import { APP_NAME } from "../../../constants";
import { BrandLogo } from "../../common/BrandLogo";
import { Tooltip } from "../../common/Tooltip";
import { ImageWithSkeleton } from "../../chat/ChatMessage/ImageWithSkeleton";

const railBtn =
  "sidebar-rail-btn flex size-8 items-center justify-center rounded-full transition-colors mx-2 touch-manipulation";

interface SidebarRailProps {
  user: { username?: string; avatar_url?: string } | null;
  imgError: boolean;
  onImgError: () => void;
  onExpand: () => void;
  onNewSession: () => void;
  onOpenSearch: () => void;
  onOpenRecentChats: () => void;
  onOpenFileLibrary: () => void;
  onOpenBookmarks: () => void;
  onOpenScheduledTasks: () => void;
  hasMoreMenuItems: boolean;
  singleMoreMenuItem?: { label: string; icon: typeof MoreHorizontal };
  onToggleMoreMenu: () => void;
  moreMenuBtnRef: React.RefObject<HTMLButtonElement | null>;
  recentChatsBtnRef: React.RefObject<HTMLButtonElement | null>;
  onShowProfile: () => void;
  unreadCount?: number;
}

export function SidebarRail({
  user,
  imgError,
  onImgError: _onImgError,
  onExpand,
  onNewSession,
  onOpenSearch,
  onOpenRecentChats,
  onOpenFileLibrary,
  onOpenBookmarks,
  onOpenScheduledTasks,
  hasMoreMenuItems,
  singleMoreMenuItem,
  onToggleMoreMenu,
  moreMenuBtnRef,
  recentChatsBtnRef,
  onShowProfile,
  unreadCount = 0,
}: SidebarRailProps) {
  const { t } = useTranslation();
  const MoreIcon = singleMoreMenuItem?.icon ?? MoreHorizontal;
  const moreLabel = singleMoreMenuItem?.label ?? t("nav.more", "更多");
  const { hasPermission } = useAuth();
  const canReadScheduledTasks = hasPermission(Permission.SCHEDULED_TASK_READ);

  return (
    <nav
      className="absolute inset-0 flex h-full w-[--sidebar-rail-width] flex-col items-start border-r select-none transition-opacity duration-150 ease-[steps(1,end)] opacity-100 pointer-events-auto"
      style={{
        backgroundColor: "var(--theme-bg-sidebar)",
        borderColor: "var(--theme-border)",
      }}
      aria-label={t("sidebarView")}
    >
      {/* Expand button — default: app icon, hover: expand icon */}
      <div className="flex items-center justify-center w-full pt-3">
        <Tooltip content={t("sidebar.expandSidebar")}>
          <button
            onClick={onExpand}
            className={`${railBtn} group cursor-e-resize rtl:cursor-w-resize`}
            aria-label={t("sidebar.expandSidebar")}
          >
            <BrandLogo alt={APP_NAME} className="size-7 group-hover:hidden" />
            <SidebarToggleIcon className="size-5 hidden group-hover:block" />
          </button>
        </Tooltip>
      </div>

      {/* Action icons — scrollable when overflowing, no scrollbar */}
      <div
        className="mt-3 flex-1 min-h-0 overflow-y-auto overflow-x-hidden flex flex-col items-center w-full space-y-1"
        style={{ scrollbarWidth: "none", msOverflowStyle: "none" }}
      >
        <Tooltip content={t("sidebar.newChat")}>
          <button
            type="button"
            onClick={onNewSession}
            className={railBtn}
            aria-label={t("sidebar.newChat")}
          >
            <SquarePen size={20} />
          </button>
        </Tooltip>
        <Tooltip content={t("sidebar.searchSessions")}>
          <button
            type="button"
            onClick={onOpenSearch}
            className={railBtn}
            aria-label={t("sidebar.searchSessions")}
          >
            <Search size={20} />
          </button>
        </Tooltip>
        {canReadScheduledTasks && (
          <Tooltip content={t("nav.scheduled-tasks")}>
            <button
              type="button"
              onClick={onOpenScheduledTasks}
              className={railBtn}
              aria-label={t("nav.scheduled-tasks")}
            >
              <CalendarClock size={20} />
            </button>
          </Tooltip>
        )}
        <Tooltip content={t("fileLibrary.title")}>
          <button
            type="button"
            onClick={onOpenFileLibrary}
            className={railBtn}
            aria-label={t("fileLibrary.title")}
          >
            <FolderOpen size={20} />
          </button>
        </Tooltip>
        <Tooltip content={t("bookmarks.title")}>
          <button
            type="button"
            onClick={onOpenBookmarks}
            className={railBtn}
            aria-label={t("bookmarks.title")}
          >
            <Bookmark size={20} />
          </button>
        </Tooltip>
        <Tooltip content={t("sidebar.recentChats")}>
          <button
            type="button"
            ref={recentChatsBtnRef}
            onClick={onOpenRecentChats}
            className={`${railBtn} relative`}
            aria-label={t("sidebar.recentChats")}
          >
            <History size={20} />
            {unreadCount > 0 && (
              <span
                className={`absolute -top-0 right-0 flex items-center justify-center rounded-full bg-gradient-to-br from-red-400 to-rose-500 text-9 font-bold leading-none text-white shadow-[0_1px_3px_rgba(239,68,68,0.4)] ring-1 ring-white/20 ${
                  unreadCount <= 9 ? "w-3.5 h-3.5" : "h-3.5 min-w-[18px] px-1"
                }`}
              >
                {unreadCount > 99 ? "99+" : unreadCount}
              </span>
            )}
          </button>
        </Tooltip>
        {hasMoreMenuItems && (
          <Tooltip content={moreLabel}>
            <button
              type="button"
              ref={moreMenuBtnRef}
              onClick={onToggleMoreMenu}
              className={railBtn}
              aria-label={moreLabel}
            >
              <MoreIcon size={20} />
            </button>
          </Tooltip>
        )}
      </div>

      {/* Profile avatar */}
      <div
        className="shrink-0 py-4 border-t flex flex-col items-center w-full"
        style={{ borderColor: "var(--theme-border)" }}
      >
        <Tooltip content={t("sidebar.expandSidebar")}>
          <button
            onClick={onShowProfile}
            className={`${railBtn} rounded-full transition cursor-pointer`}
            aria-label={t("sidebar.expandSidebar")}
          >
            <div
              className="shrink-0 w-8 h-8 rounded-full overflow-hidden transition"
              style={{ boxShadow: "0 0 0 1px var(--theme-border)" }}
            >
              {user?.avatar_url && !imgError ? (
                <ImageWithSkeleton
                  src={getFullUrl(user.avatar_url) ?? user.avatar_url}
                  alt={user?.username || t("common.user")}
                  skipUrlResolve
                  inline
                  className="w-full h-full object-cover rounded-full"
                  style={{ borderRadius: "50%" }}
                  errorFallback={
                    <div className="flex w-full h-full items-center justify-center bg-gradient-to-br from-amber-400 to-orange-500 rounded-full">
                      <span className="text-12 font-semibold text-white font-serif">
                        {user?.username?.charAt(0).toUpperCase() || "U"}
                      </span>
                    </div>
                  }
                />
              ) : (
                <div className="flex w-full h-full items-center justify-center bg-gradient-to-br from-amber-400 to-orange-500 rounded-full">
                  <span className="text-12 font-semibold text-white font-serif">
                    {user?.username?.charAt(0).toUpperCase() || "U"}
                  </span>
                </div>
              )}
            </div>
          </button>
        </Tooltip>
      </div>
    </nav>
  );
}
