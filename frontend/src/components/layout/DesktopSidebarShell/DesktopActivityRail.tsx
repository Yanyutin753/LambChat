import { MessageCircleIcon } from "@animateicons/react/lucide/message-circle-icon";
import { FolderOpenIcon } from "@animateicons/react/lucide/folder-open-icon";
import { CalendarClockIcon } from "@animateicons/react/lucide/calendar-clock-icon";
import { UserRoundIcon } from "@animateicons/react/lucide/user-round-icon";
import { UsersIcon } from "@animateicons/react/lucide/users-icon";
import { SparklesIcon } from "@animateicons/react/lucide/sparkles-icon";
import { ServerIcon } from "@animateicons/react/lucide/server-icon";
import { NetworkIcon } from "@animateicons/react/lucide/network-icon";
import { BrainIcon } from "@animateicons/react/lucide/brain-icon";
import { EllipsisIcon } from "@animateicons/react/lucide/ellipsis-icon";
import { ActivityRailButton } from "./ActivityRailButton";
import { useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useAuth } from "../../../hooks/useAuth";
import { useMoreMenu } from "../../../hooks/useMoreMenu";
import { SidebarUserRow } from "../../panels/SidebarParts/SidebarUserRow";
import { DesktopMoreMenu } from "../../panels/SidebarParts/DesktopMoreMenu";
import { Permission } from "../../../types/auth";

const navigationIcons: Record<string, typeof MessageCircleIcon> = {
  "/files": FolderOpenIcon,
  "/scheduled-tasks": CalendarClockIcon,
  "/persona": UserRoundIcon,
  "/team": UsersIcon,
  "/skills": SparklesIcon,
  "/mcp": ServerIcon,
  "/channels": NetworkIcon,
  "/memory": BrainIcon,
};

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
      show: true,
    },
    {
      path: "/scheduled-tasks",
      label: t("nav.scheduled-tasks"),
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
        <ActivityRailButton
          icon={MessageCircleIcon}
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
        />
        {primaryItems.map((item) => (
          <ActivityRailButton
            key={item.path}
            icon={navigationIcons[item.path] ?? EllipsisIcon}
            className={buttonClass}
            title={item.label}
            aria-label={item.label}
            aria-pressed={pathname === item.path}
            onClick={() => navigate(item.path)}
          />
        ))}
        {moreItems.length === 1 ? (
          <ActivityRailButton
            icon={navigationIcons[moreItems[0].path] ?? EllipsisIcon}
            className={buttonClass}
            title={moreItems[0].label}
            aria-label={moreItems[0].label}
            aria-pressed={pathname === moreItems[0].path}
            onClick={() => navigate(moreItems[0].path)}
          />
        ) : (
          moreItems.length > 1 && (
            <ActivityRailButton
              icon={EllipsisIcon}
              ref={menu.moreMenuBtnRef}
              className={buttonClass}
              title={t("nav.more")}
              aria-label={t("nav.more")}
              aria-expanded={menu.isMoreMenuOpen}
              onClick={() => menu.setIsMoreMenuOpen((open) => !open)}
            />
          )
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
