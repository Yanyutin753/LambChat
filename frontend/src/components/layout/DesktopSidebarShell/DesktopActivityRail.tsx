import {
  CalendarClock,
  FolderOpen,
  MessageCircle,
  MoreHorizontal,
} from "lucide-react";
import { useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../../hooks/useAuth";
import { useMoreMenu } from "../../../hooks/useMoreMenu";
import { SidebarUserRow } from "../../panels/SidebarParts/SidebarUserRow";
import { DesktopMoreMenu } from "../../panels/SidebarParts/DesktopMoreMenu";
import { Permission } from "../../../types/auth";

export function DesktopActivityRail({
  collapsed,
  onOpenChats,
  onShowProfile,
}: {
  collapsed: boolean;
  onOpenChats: () => void;
  onShowProfile?: () => void;
}) {
  const { t } = useTranslation();
  const { user, hasPermission } = useAuth();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const menu = useMoreMenu({ isCollapsed: true, isMobile: false });
  const primaryPaths = ["/persona", "/team", "/skills", "/mcp"];
  const primaryItems = [
    {
      path: "/files",
      label: t("fileLibrary.title"),
      icon: FolderOpen,
      show: true,
    },
    {
      path: "/scheduled-tasks",
      label: t("nav.scheduled-tasks"),
      icon: CalendarClock,
      show: hasPermission(Permission.SCHEDULED_TASK_READ),
    },
    ...menu.moreMenuFeatureItems.filter((item) =>
      primaryPaths.includes(item.path),
    ),
  ].filter((item) => item.show);
  const moreItems = menu.moreMenuFeatureItems.filter(
    (item) => item.show && !primaryPaths.includes(item.path),
  );
  const buttonClass =
    "desktop-activity-button flex size-9 shrink-0 items-center justify-center rounded-[var(--radius-lg)] text-theme-text-secondary hover:bg-theme-bg-subtle focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--theme-ring)]";

  return (
    <nav
      aria-label={t("sidebarView")}
      data-desktop-activity-rail=""
      className="flex h-full w-[var(--sidebar-rail-width)] shrink-0 flex-col items-center border-r border-theme-border bg-[var(--theme-bg-sidebar)] py-1.5"
    >
      <div className="flex min-h-0 flex-1 flex-col items-center gap-2 overflow-y-auto">
        <button
          type="button"
          className={buttonClass}
          title={t("workspacePanel.viewChats")}
          aria-label={t("workspacePanel.viewChats")}
          aria-pressed={
            !collapsed && (pathname === "/" || pathname.startsWith("/chat"))
          }
          onClick={() => {
            onOpenChats();
            if (!pathname.startsWith("/chat")) navigate("/chat");
          }}
        >
          <MessageCircle size={19} />
        </button>
        {primaryItems.map((item) => (
          <button
            key={item.path}
            type="button"
            className={buttonClass}
            title={item.label}
            aria-label={item.label}
            aria-pressed={pathname === item.path}
            onClick={() => navigate(item.path)}
          >
            <item.icon size={19} />
          </button>
        ))}
        {moreItems.length > 0 && (
          <button
            type="button"
            ref={menu.moreMenuBtnRef}
            className={buttonClass}
            title={t("nav.more")}
            aria-label={t("nav.more")}
            aria-expanded={menu.isMoreMenuOpen}
            onClick={() => menu.setIsMoreMenuOpen((open) => !open)}
          >
            <MoreHorizontal size={19} />
          </button>
        )}
      </div>
      <SidebarUserRow
        compact
        user={user}
        imgError={false}
        onShowProfile={onShowProfile ?? (() => navigate("/settings"))}
      />
      <DesktopMoreMenu
        featureItems={moreItems}
        isOpen={menu.isMoreMenuOpen}
        onClose={() => menu.setIsMoreMenuOpen(false)}
        menuRef={menu.moreMenuRef}
        position={
          "top" in menu.moreMenuPosition
            ? (menu.moreMenuPosition as { top: number; left: number })
            : null
        }
      />
    </nav>
  );
}
