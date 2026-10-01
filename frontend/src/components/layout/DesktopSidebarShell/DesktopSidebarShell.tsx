import { hasVisibleModalDialog } from "../../../utils/modalDialog";
/** 左侧导航壳：会话列表、全局导航和可调整宽度。会话文件由右侧面板承载。 */

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Bell, Search } from "lucide-react";
import clsx from "clsx";
import { BrandLogo } from "../../common/BrandLogo";
import { BrandWordmark } from "../../common/BrandWordmark";
import { APP_NAME } from "../../../constants";
import { DesktopActivityRail } from "./DesktopActivityRail";
import { isEditableEventTarget } from "../../../utils/editableTarget";
import {
  DESKTOP_SIDEBAR_TOGGLE_EVENT,
  DESKTOP_SIDEBAR_OPEN_SEARCH_EVENT,
  OPEN_NOTIFICATIONS_EVENT,
  NOTIFICATION_COUNT_EVENT,
  isDesktopShell,
} from "./desktopShellPlatform";

const WIDTH_STORAGE_KEY = "lambchat_desktop_sidebar_width";
const DEFAULT_WIDTH = 264;
const MIN_WIDTH = 232;
const MAX_WIDTH_CAP = 480;
const MAX_WIDTH_RATIO = 0.5;

function clampWidth(value: number): number {
  const cap = Math.min(
    typeof window === "undefined"
      ? MAX_WIDTH_CAP
      : window.innerWidth * MAX_WIDTH_RATIO,
    MAX_WIDTH_CAP,
  );
  return Math.round(Math.min(cap, Math.max(MIN_WIDTH, value)));
}

function readStoredWidth(): number {
  try {
    const saved = Number(localStorage.getItem(WIDTH_STORAGE_KEY));
    return Number.isFinite(saved) && saved > 0
      ? clampWidth(saved)
      : DEFAULT_WIDTH;
  } catch {
    return DEFAULT_WIDTH;
  }
}

interface DesktopSidebarShellProps {
  collapsed: boolean;
  onToggleCollapsed: (collapsed: boolean) => void;
  onShowProfile?: () => void;
  mobileOpen?: boolean;
  onToggleMobile?: (open: boolean) => void;
  children: ReactNode;
}

/**
 * 桌面壳专属快捷键：⌘/Ctrl+B 切侧栏、⌘/Ctrl+, 打开设置（macOS 惯例）。
 * 挂在 shell 内部即只在桌面渲染时生效，web 路径零绑定。
 */
function useDesktopShellShortcuts(
  collapsed: boolean,
  onToggleCollapsed: (collapsed: boolean) => void,
  navigate: (to: string) => void,
) {
  useEffect(() => {
    if (!isDesktopShell()) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (
        e.defaultPrevented ||
        e.isComposing ||
        e.altKey ||
        e.shiftKey ||
        isEditableEventTarget(e.target) ||
        hasVisibleModalDialog()
      )
        return;
      const isMac = navigator.platform.toUpperCase().includes("MAC");
      const modifier = isMac ? e.metaKey : e.ctrlKey;
      if (modifier && (e.key === "b" || e.key === "B")) {
        e.preventDefault();
        onToggleCollapsed(!collapsed);
      }
      if (modifier && e.key === ",") {
        e.preventDefault();
        navigate("/settings");
      }
    };
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [collapsed, onToggleCollapsed, navigate]);
}

export function DesktopSidebarShell({
  collapsed: chatCollapsed,
  onToggleCollapsed: onToggleChatCollapsed,
  children,
  onShowProfile,
  mobileOpen = false,
  onToggleMobile,
}: DesktopSidebarShellProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const isChatPage =
    pathname === "/" || pathname === "/chat" || pathname.startsWith("/chat/");
  const [expandedPanel, setExpandedPanel] = useState<string | null>(null);
  const collapsed = isChatPage ? chatCollapsed : expandedPanel !== pathname;
  const onToggleCollapsed = useCallback(
    (next: boolean) => {
      if (isChatPage) onToggleChatCollapsed(next);
      else setExpandedPanel(next ? null : pathname);
    },
    [isChatPage, onToggleChatCollapsed, pathname],
  );
  const [wide, setWide] = useState(() => window.innerWidth >= 640);
  const [notificationCount, setNotificationCount] = useState(0);
  const [width, setWidth] = useState(readStoredWidth);
  const [resizing, setResizing] = useState(false);
  const dragRef = useRef<{ startX: number; startW: number } | null>(null);
  // pointerup 闭包可能拿到过期渲染的 width（同批连发事件），以 ref 为准持久化
  const widthRef = useRef(width);

  useEffect(() => {
    const update = (event: Event) =>
      setNotificationCount((event as CustomEvent<number>).detail);
    window.addEventListener(NOTIFICATION_COUNT_EVENT, update);
    return () => window.removeEventListener(NOTIFICATION_COUNT_EVENT, update);
  }, []);

  useEffect(() => {
    const resize = () => {
      setWide(window.innerWidth >= 640);
      const next = readStoredWidth();
      widthRef.current = next;
      setWidth(next);
    };
    window.addEventListener("resize", resize);
    return () => window.removeEventListener("resize", resize);
  }, []);

  useEffect(() => {
    if (!resizing) return;
    const { cursor, userSelect } = document.body.style;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
    return () => {
      document.body.style.cursor = cursor;
      document.body.style.userSelect = userSelect;
    };
  }, [resizing]);

  const setNavigationCollapsed = useCallback(
    (next: boolean) => {
      if (wide) onToggleCollapsed(next);
      else onToggleMobile?.(!next);
    },
    [wide, onToggleCollapsed, onToggleMobile],
  );
  const navigationCollapsed = wide ? collapsed : !mobileOpen;
  useDesktopShellShortcuts(
    navigationCollapsed,
    setNavigationCollapsed,
    navigate,
  );

  // 标题栏折叠按钮的事件桥（TitleBar 不持有折叠状态）
  useEffect(() => {
    const handleToggle = () => setNavigationCollapsed(!navigationCollapsed);
    window.addEventListener(DESKTOP_SIDEBAR_TOGGLE_EVENT, handleToggle);
    return () => {
      window.removeEventListener(DESKTOP_SIDEBAR_TOGGLE_EVENT, handleToggle);
    };
  }, [navigationCollapsed, setNavigationCollapsed]);

  const handleResizeDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (collapsed || e.button !== 0) return;
    e.preventDefault();
    dragRef.current = { startX: e.clientX, startW: width };
    setResizing(true);
    try {
      // 无活动指针（合成事件）时捕获失败不致命：move/up 走冒泡仍可达
      e.currentTarget.setPointerCapture(e.pointerId);
    } catch {
      /* pointer capture 不可用，依赖事件冒泡 */
    }
  };

  const handleResizeMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    if (!drag) return;
    const next = clampWidth(drag.startW + (e.clientX - drag.startX));
    widthRef.current = next;
    setWidth(next);
  };

  const handleResizeUp = () => {
    if (!dragRef.current) return;
    dragRef.current = null;
    setResizing(false);
    try {
      localStorage.setItem(WIDTH_STORAGE_KEY, String(widthRef.current));
    } catch {
      /* 私密模式等场景静默 */
    }
  };

  return (
    <div
      data-desktop-sidebar-shell={wide ? "" : undefined}
      className={wide ? "relative flex h-full shrink-0" : "contents"}
    >
      {wide && (
        <DesktopActivityRail
          collapsed={collapsed}
          onOpenChats={() => onToggleChatCollapsed(false)}
          onShowProfile={onShowProfile}
        />
      )}
      <div
        data-desktop-sidebar={wide ? "" : undefined}
        inert={navigationCollapsed}
        className={
          wide
            ? clsx(
                "relative h-full shrink-0 overflow-hidden bg-[var(--theme-bg-sidebar)]",
                !collapsed && "border-r border-[var(--theme-border)]",
                resizing
                  ? "transition-none"
                  : "transition-[width] duration-200 ease-out",
              )
            : "contents"
        }
        style={wide ? { width: collapsed ? 0 : width } : undefined}
      >
        <div className={wide ? "absolute inset-0 flex flex-col" : "contents"}>
          {wide && (
            <>
              <div
                data-sidebar-brand=""
                className="flex h-12 shrink-0 items-center gap-2 ps-[13px] pe-[7px]"
              >
                <Link
                  to="/chat"
                  aria-label={APP_NAME}
                  className="flex min-w-0 flex-1 items-center gap-3 rounded-md focus-visible:outline focus-visible:outline-2"
                >
                  {/* The image ink sits 2px below its box center at this size. */}
                  <BrandLogo
                    alt={APP_NAME}
                    className="-mx-1 relative -top-0.5 size-7 shrink-0"
                  />
                  <BrandWordmark decorative className="h-7 w-auto min-w-0" />
                </Link>
                <div className="ml-auto flex shrink-0 items-center">
                  <button
                    type="button"
                    title={t("nav.notifications")}
                    aria-label={t("nav.notifications")}
                    onClick={() =>
                      window.dispatchEvent(new Event(OPEN_NOTIFICATIONS_EVENT))
                    }
                    className="relative flex size-8 items-center justify-center rounded-lg text-theme-text-secondary hover:bg-theme-bg-subtle focus-visible:outline focus-visible:outline-2"
                  >
                    <Bell size={16} />
                    {notificationCount > 0 && (
                      <span
                        className="absolute right-1.5 top-1.5 size-1.5 rounded-full bg-[var(--theme-primary)]"
                        aria-label={String(notificationCount)}
                      />
                    )}
                  </button>
                  <button
                    type="button"
                    title={t("sidebar.searchSessions")}
                    aria-label={t("sidebar.searchSessions")}
                    onClick={() =>
                      window.dispatchEvent(
                        new Event(DESKTOP_SIDEBAR_OPEN_SEARCH_EVENT),
                      )
                    }
                    className="flex size-8 items-center justify-center rounded-lg text-theme-text-secondary hover:bg-theme-bg-subtle focus-visible:outline focus-visible:outline-2"
                  >
                    <Search size={16} />
                  </button>
                </div>
              </div>
            </>
          )}
          <div className={wide ? "flex min-h-0 flex-1 flex-col" : "contents"}>
            <div className={wide ? "min-h-0 w-full flex-1" : "contents"}>
              {children}
            </div>
          </div>
        </div>
      </div>
      {/* Keep the hit area centered on the divider, outside the clipped content. */}
      {wide && !collapsed && (
        <div
          onPointerDown={handleResizeDown}
          onPointerMove={handleResizeMove}
          onPointerUp={handleResizeUp}
          onPointerCancel={handleResizeUp}
          onLostPointerCapture={handleResizeUp}
          onKeyDown={(e) => {
            if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
            e.preventDefault();
            const next = clampWidth(
              widthRef.current + (e.key === "ArrowLeft" ? -10 : 10),
            );
            widthRef.current = next;
            setWidth(next);
            try {
              localStorage.setItem(WIDTH_STORAGE_KEY, String(next));
            } catch {
              /* storage unavailable */
            }
          }}
          role="separator"
          tabIndex={0}
          aria-label={t("common.resizePanel")}
          aria-orientation="vertical"
          aria-valuemin={MIN_WIDTH}
          aria-valuemax={clampWidth(MAX_WIDTH_CAP)}
          aria-valuenow={width}
          data-resizing={resizing || undefined}
          className="workspace-resize-handle group/sidebar-resize absolute inset-y-0 -right-2 z-10 flex touch-none cursor-col-resize items-stretch"
        >
          <div />
        </div>
      )}
    </div>
  );
}

/**
 * 窄屏透传，保留 SessionSidebar 的移动抽屉；宽屏网页共用电脑入口。
 * children 即原 sidebar。
 */
export function DesktopSidebarShellGate(props: DesktopSidebarShellProps) {
  return <DesktopSidebarShell {...props} />;
}
