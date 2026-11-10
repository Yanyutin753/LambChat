import { useLayoutEffect, useRef, useState, type ComponentProps } from "react";
import { FolderOpen, CalendarClock, Users } from "lucide-react";
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
import { AgentAvatar } from "../../common/AgentAvatar";
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
  const listRef = useRef<HTMLDivElement>(null);
  const draggedPath = useRef<string | null>(null);
  const [dropPath, setDropPath] = useState<string | null>(null);
  const [capacity, setCapacity] = useState(Infinity);
  const [order, setOrder] = useState<string[]>(() => {
    try {
      const saved = JSON.parse(
        localStorage.getItem("lambchat_activity_rail_order") ?? "[]",
      );
      return Array.isArray(saved)
        ? saved.filter((path): path is string => typeof path === "string")
        : [];
    } catch {
      return [];
    }
  });
  useLayoutEffect(() => {
    const list = listRef.current;
    const button = list?.querySelector("button");
    if (!list || !button) return;
    const measure = () => {
      const height = list.getBoundingClientRect().height;
      const buttonHeight = button.getBoundingClientRect().height;
      const gap = parseFloat(getComputedStyle(list).rowGap) || 0;
      if (height > 0 && buttonHeight > 0) {
        setCapacity(
          Math.max(1, Math.floor((height + gap) / (buttonHeight + gap)) - 1),
        );
      }
    };
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(list);
    observer.observe(button);
    return () => observer.disconnect();
  }, []);
  const allItems = [
    {
      path: "/assistants",
      icon: Users,
      label: t("assistants.title"),
      show: collapsed && hasPermission(Permission.SESSION_READ),
    },
    {
      path: "/files",
      icon: FolderOpen,
      label: t("fileLibrary.title"),
      show: hasPermission(Permission.FILE_READ),
    },
    {
      path: "/scheduled-tasks",
      icon: CalendarClock,
      label: t("nav.scheduled-tasks"),
      show: hasPermission(Permission.SCHEDULED_TASK_READ),
    },
    ...menu.moreMenuFeatureItems,
  ].filter((item) => item.show);
  const rank = (path: string) =>
    order.indexOf(path) < 0 ? order.length : order.indexOf(path);
  allItems.sort((a, b) => rank(a.path) - rank(b.path));
  const visibleCount =
    allItems.length <= capacity ? allItems.length : Math.max(0, capacity - 1);
  const primaryItems = allItems.slice(0, visibleCount);
  const moreItems = allItems.slice(visibleCount);
  const move = (source: string, target: string) => {
    const paths = [
      ...new Set([...order, ...allItems.map((item) => item.path)]),
    ];
    const from = paths.indexOf(source);
    const to = paths.indexOf(target);
    if (from < 0 || to < 0 || from === to) return;
    paths.splice(from, 1);
    paths.splice(to, 0, source);
    setOrder(paths);
    try {
      localStorage.setItem(
        "lambchat_activity_rail_order",
        JSON.stringify(paths),
      );
    } catch {
      // Keep sorting available when storage is disabled.
    }
  };
  const reorderProps = (
    path: string,
  ): ComponentProps<"button"> & { "data-rail-path": string } => ({
    draggable: true,
    "data-rail-path": path,
    "aria-description": t("nav.reorderHint"),
    "aria-keyshortcuts": "Alt+ArrowUp Alt+ArrowDown",
    onDragStart: (event) => {
      draggedPath.current = path;
      event.dataTransfer.effectAllowed = "move";
      event.dataTransfer.setData("text/plain", path);
    },
    onDragOver: (event) => {
      if (!draggedPath.current) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
      setDropPath(path);
    },
    onDrop: (event) => {
      event.preventDefault();
      if (draggedPath.current) move(draggedPath.current, path);
      draggedPath.current = null;
      setDropPath(null);
    },
    onDragEnd: () => {
      draggedPath.current = null;
      setDropPath(null);
    },
    onKeyDown: (event) => {
      if (!event.altKey || !["ArrowUp", "ArrowDown"].includes(event.key))
        return;
      event.preventDefault();
      const target =
        allItems[
          allItems.findIndex((item) => item.path === path) +
            (event.key === "ArrowUp" ? -1 : 1)
        ];
      if (!target) return;
      move(path, target.path);
      requestAnimationFrame(() => {
        const button =
          listRef.current?.querySelector<HTMLButtonElement>(
            `[data-rail-path="${path}"]`,
          ) ??
          menu.moreMenuRef.current?.querySelector<HTMLButtonElement>(
            `[data-rail-path="${path}"]`,
          );
        (button ?? menu.moreMenuBtnRef.current)?.focus();
      });
    },
  });
  const buttonClass =
    "desktop-activity-button flex size-9 shrink-0 items-center justify-center rounded-[var(--radius-lg)] text-theme-text-secondary hover:bg-theme-bg-hover focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--theme-ring)]";

  return (
    <nav
      aria-label={t("sidebarView")}
      data-desktop-activity-rail=""
      className="flex h-full w-[var(--sidebar-rail-width)] shrink-0 flex-col items-center border-r border-theme-border bg-[var(--theme-bg-sidebar)] py-1.5"
    >
      <div
        ref={listRef}
        className="flex min-h-0 flex-1 flex-col items-center gap-2 overflow-y-auto"
      >
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
            {...reorderProps(item.path)}
            icon={
              item.path === "/assistants"
                ? undefined
                : navigationIcons[item.path] ?? EllipsisIcon
            }
            className={buttonClass}
            style={
              dropPath === item.path
                ? { outline: "2px solid var(--theme-ring)" }
                : undefined
            }
            title={`${item.label} · ${t("nav.reorderHint")}`}
            aria-label={item.label}
            aria-pressed={pathname === item.path}
            onClick={() => navigate(item.path)}
          >
            {item.path === "/assistants" ? (
              <AgentAvatar seed="LambChat" size={20} />
            ) : undefined}
          </ActivityRailButton>
        ))}
        {moreItems.length > 0 && (
          <ActivityRailButton
            icon={EllipsisIcon}
            ref={menu.moreMenuBtnRef}
            className={buttonClass}
            title={t("nav.more")}
            aria-label={t("nav.more")}
            aria-expanded={menu.isMoreMenuOpen}
            onDragOver={(event) => {
              if (!draggedPath.current) return;
              event.preventDefault();
              menu.setIsMoreMenuOpen(true);
            }}
            onClick={() => menu.setIsMoreMenuOpen((open) => !open)}
          />
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
        itemButtonProps={reorderProps}
        isOpen={menu.isMoreMenuOpen && moreItems.length > 0}
        onClose={() => {
          menu.setIsMoreMenuOpen(false);
          menu.moreMenuBtnRef.current?.focus();
        }}
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
