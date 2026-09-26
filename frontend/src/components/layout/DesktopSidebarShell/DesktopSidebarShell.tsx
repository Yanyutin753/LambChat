/**
 * 桌面侧栏壳（仅 Tauri 桌面壳渲染；web/移动端原样透传 children）。
 * 排版对齐 ZCode 桌面端：单栏侧边栏（无图标导航栏）——
 *
 *   [会话|电脑 tabs]      [搜索]     ← 顶部标签行
 *   ─────────────────────────────
 *   会话列表 / 电脑面板（工作区文件树） ← 滚动区
 *   ─────────────────────────────
 *   [用户胶囊]  [文件库][定时][设置]   ← 底部（ZCode 式 footer）
 *
 *   折叠/新建入口上移到自绘标题栏（事件桥，见 desktopShellPlatform）；
 *   宽度可拖拽调整（右缘手柄），localStorage 持久化。
 *
 * 折叠状态复用 AppContent 的 sidebarCollapsed（与 web 端同一持久化语义）；
 * 当前视图（chat/files）独立持久化。搜索按钮经自定义事件交给
 * SessionSidebar（SearchDialog 状态归它管，⌘K 同一通路）。
 */

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type PointerEvent as ReactPointerEvent,
  type ReactNode,
} from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  CalendarClock,
  FolderOpen,
  MessagesSquare,
  Monitor,
  Search,
  Settings,
} from "lucide-react";
import clsx from "clsx";
import { Tooltip } from "../../common/Tooltip";
import { WorkspacePanel } from "../../workspacePanel/WorkspacePanel";
import { useAuth } from "../../../hooks/useAuth";
import { Permission } from "../../../types/auth";
import {
  DESKTOP_SIDEBAR_NEW_SESSION_EVENT,
  DESKTOP_SIDEBAR_OPEN_SEARCH_EVENT,
  DESKTOP_SIDEBAR_TOGGLE_EVENT,
  shouldUseDesktopShellGate,
  type DesktopSidebarView,
} from "./desktopShellPlatform";

const VIEW_STORAGE_KEY = "lambchat_desktop_sidebar_view";
const WIDTH_STORAGE_KEY = "lambchat_desktop_sidebar_width";
const DEFAULT_WIDTH = 264;
const MIN_WIDTH = 232;
const MAX_WIDTH_CAP = 480;
const MAX_WIDTH_RATIO = 0.5;

function readStoredView(): DesktopSidebarView {
  try {
    const saved = localStorage.getItem(VIEW_STORAGE_KEY);
    return saved === "files" ? "files" : "chat";
  } catch {
    return "chat";
  }
}

function clampWidth(value: number): number {
  const cap = Math.min(
    typeof window === "undefined" ? MAX_WIDTH_CAP : window.innerWidth * MAX_WIDTH_RATIO,
    MAX_WIDTH_CAP,
  );
  return Math.round(Math.min(cap, Math.max(MIN_WIDTH, value)));
}

function readStoredWidth(): number {
  try {
    const saved = Number(localStorage.getItem(WIDTH_STORAGE_KEY));
    return Number.isFinite(saved) && saved > 0 ? clampWidth(saved) : DEFAULT_WIDTH;
  } catch {
    return DEFAULT_WIDTH;
  }
}

interface DesktopSidebarShellProps {
  collapsed: boolean;
  onToggleCollapsed: (collapsed: boolean) => void;
  sessionId?: string | null;
  /** 会话沙箱模式（agent_options.sandbox，"local" | "cloud"）。 */
  sandboxMode?: string | null;
  /** 会话 sandbox_machine_id（未显式选机器时空）。 */
  machineId?: string | null;
  /** 会话 sandbox_workspace 的原样 JSON（reveal 用）。 */
  workspaceSelection?: string | null;
  onNewSession: () => void;
  onShowProfile: () => void;
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
    const handleKeyDown = (e: KeyboardEvent) => {
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
  collapsed,
  onToggleCollapsed,
  sessionId,
  sandboxMode,
  machineId,
  workspaceSelection,
  onNewSession,
  onShowProfile,
  children,
}: DesktopSidebarShellProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { user, hasPermission } = useAuth();
  const [view, setView] = useState<DesktopSidebarView>(readStoredView);
  const [width, setWidth] = useState(readStoredWidth);
  const [resizing, setResizing] = useState(false);
  const dragRef = useRef<{ startX: number; startW: number } | null>(null);
  // pointerup 闭包可能拿到过期渲染的 width（同批连发事件），以 ref 为准持久化
  const widthRef = useRef(width);
  const canReadScheduledTasks = hasPermission(Permission.SCHEDULED_TASK_READ);

  useDesktopShellShortcuts(collapsed, onToggleCollapsed, navigate);

  // 标题栏折叠按钮/新建对话按钮的事件桥（TitleBar 不持有这两份状态）
  useEffect(() => {
    const handleToggle = () => onToggleCollapsed(!collapsed);
    const handleNewSession = () => onNewSession();
    window.addEventListener(DESKTOP_SIDEBAR_TOGGLE_EVENT, handleToggle);
    window.addEventListener(DESKTOP_SIDEBAR_NEW_SESSION_EVENT, handleNewSession);
    return () => {
      window.removeEventListener(DESKTOP_SIDEBAR_TOGGLE_EVENT, handleToggle);
      window.removeEventListener(DESKTOP_SIDEBAR_NEW_SESSION_EVENT, handleNewSession);
    };
  }, [collapsed, onToggleCollapsed, onNewSession]);

  const switchView = useCallback(
    (next: DesktopSidebarView) => {
      setView(next);
      try {
        localStorage.setItem(VIEW_STORAGE_KEY, next);
      } catch {
        /* 私密模式等场景静默 */
      }
      // 从折叠态点视图 = 同时展开侧栏
      onToggleCollapsed(false);
    },
    [onToggleCollapsed],
  );

  const openSearch = useCallback(() => {
    window.dispatchEvent(new CustomEvent(DESKTOP_SIDEBAR_OPEN_SEARCH_EVENT));
  }, []);

  const handleResizeDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (collapsed) return;
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

  const tabButtonClass = (active: boolean) =>
    clsx(
      "flex h-7 items-center gap-1.5 rounded-lg px-2.5 text-13 font-medium transition-colors",
      active
        ? "bg-[var(--theme-bg-card)] text-[var(--color-text-primary)] shadow-[var(--shadow-card)]"
        : "text-[var(--color-text-secondary)] hover:text-[var(--color-text-primary)]",
    );

  return (
    <div className="hidden sm:flex h-full shrink-0">
      <div
        data-desktop-sidebar=""
        className={clsx(
          "relative h-full shrink-0 overflow-hidden bg-[var(--theme-bg-sidebar)]",
          !collapsed && "border-r border-[var(--theme-border)]",
          resizing ? "transition-none" : "transition-[width] duration-200 ease-out",
        )}
        style={{ width: collapsed ? 0 : width }}
      >
        <div className="absolute inset-0 flex flex-col">
          {/* 顶部标签行：会话|电脑 + 搜索（新建对话入口在标题栏） */}
          <div className="flex h-11 shrink-0 items-center gap-1.5 px-2">
            <div className="flex items-center gap-0.5 rounded-[10px] bg-[var(--theme-bg-subtle)] p-0.5">
              <button
                type="button"
                onClick={() => switchView("chat")}
                aria-pressed={view === "chat"}
                className={tabButtonClass(view === "chat")}
              >
                <MessagesSquare size={14} className="shrink-0" />
                <span>{t("workspacePanel.viewChats", { defaultValue: "会话" })}</span>
              </button>
              <button
                type="button"
                onClick={() => switchView("files")}
                aria-pressed={view === "files"}
                className={tabButtonClass(view === "files")}
              >
                <Monitor size={14} className="shrink-0" />
                <span>{t("workspacePanel.title", { defaultValue: "电脑" })}</span>
              </button>
            </div>
            <div className="min-w-0 flex-1" />
            <Tooltip content={t("sidebar.searchSessions")}>
              <button
                type="button"
                onClick={openSearch}
                aria-label={t("sidebar.searchSessions")}
                className="flex size-7 items-center justify-center rounded-lg text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-background-muted)] hover:text-[var(--color-text-primary)]"
              >
                <Search size={15} />
              </button>
            </Tooltip>
          </div>

          {/* 内容区（chat/files 常驻挂载保状态，仅切显隐） */}
          <div className="flex min-h-0 flex-1 flex-col">
            <div
              className={clsx(
                "min-h-0 flex-1",
                view === "chat" && !collapsed ? "flex" : "hidden",
              )}
            >
              <div className="min-h-0 w-full flex-1">{children}</div>
            </div>
            <div
              className={clsx(
                "min-h-0 flex-1",
                view === "files" && !collapsed ? "flex" : "hidden",
              )}
            >
              <div className="min-h-0 w-full flex-1">
                <WorkspacePanel
                  sessionId={sessionId ?? null}
                  sandboxMode={sandboxMode}
                  machineId={machineId}
                  workspaceSelection={workspaceSelection}
                />
              </div>
            </div>
          </div>

          {/* 底部 footer（ZCode 式：用户胶囊 + 直达图标） */}
          <footer className="flex shrink-0 items-center gap-1 border-t border-[var(--theme-border-faint)] px-2 py-2">
            <button
              type="button"
              onClick={onShowProfile}
              aria-label={user?.username || t("workspacePanel.account", { defaultValue: "账号" })}
              className="flex h-8 min-w-0 flex-1 items-center gap-2 rounded-[10px] px-1.5 transition-colors hover:bg-[var(--color-background-muted)]"
            >
              {user?.avatar_url ? (
                <img
                  src={user.avatar_url}
                  alt={user.username || "avatar"}
                  className="size-6 shrink-0 rounded-full object-cover"
                />
              ) : (
                <span className="flex size-6 shrink-0 items-center justify-center rounded-full bg-stone-300 text-12 font-medium text-stone-700 dark:bg-stone-600 dark:text-stone-200">
                  {(user?.username || "?").slice(0, 1).toUpperCase()}
                </span>
              )}
              <span className="truncate text-left text-13 font-medium text-[var(--color-text-primary)]">
                {user?.username || t("workspacePanel.account", { defaultValue: "账号" })}
              </span>
            </button>
            <Tooltip content={t("fileLibrary.title")} placement="top">
              <button
                type="button"
                onClick={() => navigate("/files")}
                aria-label={t("fileLibrary.title")}
                className="flex size-7 items-center justify-center rounded-lg text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-background-muted)] hover:text-[var(--color-text-primary)]"
              >
                <FolderOpen size={15} />
              </button>
            </Tooltip>
            {canReadScheduledTasks && (
              <Tooltip content={t("nav.scheduled-tasks")} placement="top">
                <button
                  type="button"
                  onClick={() => navigate("/scheduled-tasks")}
                  aria-label={t("nav.scheduled-tasks")}
                  className="flex size-7 items-center justify-center rounded-lg text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-background-muted)] hover:text-[var(--color-text-primary)]"
                >
                  <CalendarClock size={15} />
                </button>
              </Tooltip>
            )}
            <Tooltip content={t("workspacePanel.settings", { defaultValue: "设置" })} placement="top">
              <button
                type="button"
                onClick={() => navigate("/settings")}
                aria-label={t("workspacePanel.settings", { defaultValue: "设置" })}
                className="flex size-7 items-center justify-center rounded-lg text-[var(--color-text-secondary)] transition-colors hover:bg-[var(--color-background-muted)] hover:text-[var(--color-text-primary)]"
              >
                <Settings size={15} />
              </button>
            </Tooltip>
          </footer>
        </div>

        {/* 宽度拖拽手柄（右缘；折叠时不交互） */}
        {!collapsed && (
          <div
            onPointerDown={handleResizeDown}
            onPointerMove={handleResizeMove}
            onPointerUp={handleResizeUp}
            onPointerCancel={handleResizeUp}
            className="group absolute inset-y-0 right-0 z-10 flex w-[7px] cursor-col-resize items-stretch"
            aria-hidden="true"
          >
            <div
              className={clsx(
                "mx-auto h-full w-px transition-colors",
                resizing
                  ? "bg-[var(--theme-primary)]"
                  : "bg-transparent group-hover:bg-[var(--theme-border-hover)]",
              )}
            />
          </div>
        )}
      </div>
    </div>
  );
}

/**
 * web/移动端透传：非桌面壳时不引入双栏 DOM（零回归边界），
 * children 即原 sidebar。
 */
export function DesktopSidebarShellGate(props: DesktopSidebarShellProps) {
  if (!shouldUseDesktopShellGate()) {
    return <>{props.children}</>;
  }
  return <DesktopSidebarShell {...props} />;
}
