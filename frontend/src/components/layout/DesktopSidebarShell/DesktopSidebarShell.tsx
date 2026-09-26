/**
 * 桌面侧栏壳（仅 Tauri 桌面壳渲染；web/移动端原样透传 children）。
 * 结构对齐 ZCode 桌面端：单栏侧边栏（无图标导航栏）——
 *
 *   [会话|电脑 tabs]              ← 壳唯一的自有 chrome（视图切换）
 *   原版 SessionSidebar 内容      ← 操作行/列表/底部用户区全部复用原版
 *   ───────── 或 电脑面板（工作区文件树）
 *
 *   折叠入口在自绘标题栏（事件桥）；宽度可拖拽调整（右缘手柄），
 *   localStorage 持久化。
 *
 * 折叠状态复用 AppContent 的 sidebarCollapsed（与 web 端同一持久化语义）；
 * 当前视图（chat/files）独立持久化。
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
import { MessagesSquare, Monitor } from "lucide-react";
import clsx from "clsx";
import { WorkspacePanel } from "../../workspacePanel/WorkspacePanel";
import {
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
  children,
}: DesktopSidebarShellProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [view, setView] = useState<DesktopSidebarView>(readStoredView);
  const [width, setWidth] = useState(readStoredWidth);
  const [resizing, setResizing] = useState(false);
  const dragRef = useRef<{ startX: number; startW: number } | null>(null);
  // pointerup 闭包可能拿到过期渲染的 width（同批连发事件），以 ref 为准持久化
  const widthRef = useRef(width);

  useDesktopShellShortcuts(collapsed, onToggleCollapsed, navigate);

  // 标题栏折叠按钮的事件桥（TitleBar 不持有折叠状态）
  useEffect(() => {
    const handleToggle = () => onToggleCollapsed(!collapsed);
    window.addEventListener(DESKTOP_SIDEBAR_TOGGLE_EVENT, handleToggle);
    return () => {
      window.removeEventListener(DESKTOP_SIDEBAR_TOGGLE_EVENT, handleToggle);
    };
  }, [collapsed, onToggleCollapsed]);

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
      "flex h-7 items-center gap-1.5 rounded-[10px] px-[9px] text-13 font-medium transition-colors",
      active
        ? "bg-[var(--theme-bg-card)] text-[var(--color-text-primary)] shadow-[var(--shadow-card)]"
        : "text-[var(--color-text-secondary)] hover:bg-[var(--theme-bg-subtle)] hover:text-[var(--color-text-primary)]",
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
          {/* 顶部标签行：会话|电脑（操作行/用户区沿用原版 SessionSidebar 内容；
              px-[9px] 与下方操作行按钮左缘/图标对齐同一节奏） */}
          <div className="flex h-9 shrink-0 items-center gap-0.5 px-2">
            <button
              type="button"
              onClick={() => switchView("chat")}
              aria-pressed={view === "chat"}
              className={tabButtonClass(view === "chat")}
            >
              <MessagesSquare size={15} className="shrink-0" />
              <span>{t("workspacePanel.viewChats", { defaultValue: "会话" })}</span>
            </button>
            <button
              type="button"
              onClick={() => switchView("files")}
              aria-pressed={view === "files"}
              className={tabButtonClass(view === "files")}
            >
              <Monitor size={15} className="shrink-0" />
              <span>{t("workspacePanel.title", { defaultValue: "电脑" })}</span>
            </button>
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
