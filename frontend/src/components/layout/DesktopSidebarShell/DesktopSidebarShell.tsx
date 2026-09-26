/**
 * 桌面双栏导航壳（仅 Tauri 桌面壳渲染；web/移动端原样透传 children）。
 *
 * 结构 = ActivityRail（图标导航栏）+ 二级面板：
 *   - 「聊天」面板 = 原 SessionSidebar（variant="desktopShell"，隐藏自带
 *     头部/操作行/折叠 rail，职责移到这里）
 *   - 「文件」面板 = WorkspacePanel（本地工作区文件树）
 *   - 其余图标是直达入口（新聊天/搜索/文件库/定时任务/设置/头像）
 *
 * 折叠状态复用 AppContent 的 sidebarCollapsed（与 web 端同一持久化语义）；
 * 当前视图（chat/files）独立持久化到 localStorage。搜索按钮经自定义事件
 * 交给 SessionSidebar（SearchDialog 状态归它管，⌘K 同一通路）。
 */

import {
  useCallback,
  useEffect,
  useState,
  type ReactNode,
} from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  CalendarClock,
  FolderOpen,
  FolderTree,
  MessageSquarePlus,
  MessagesSquare,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Settings,
} from "lucide-react";
import clsx from "clsx";
import { Tooltip } from "../../common/Tooltip";
import { WorkspacePanel } from "../../workspacePanel/WorkspacePanel";
import { useAuth } from "../../../hooks/useAuth";
import { Permission } from "../../../types/auth";
import {
  DESKTOP_SIDEBAR_OPEN_SEARCH_EVENT,
  shouldUseDesktopShellGate,
  type DesktopSidebarView,
} from "./desktopShellPlatform";

const VIEW_STORAGE_KEY = "lambchat_desktop_sidebar_view";

function readStoredView(): DesktopSidebarView {
  try {
    const saved = localStorage.getItem(VIEW_STORAGE_KEY);
    return saved === "files" ? "files" : "chat";
  } catch {
    return "chat";
  }
}

interface DesktopSidebarShellProps {
  collapsed: boolean;
  onToggleCollapsed: (collapsed: boolean) => void;
  sessionId?: string | null;
  /** 会话 sandbox_workspace 的原样 JSON（reveal 用）。 */
  workspaceSelection?: string | null;
  onNewSession: () => void;
  onShowProfile: () => void;
  children: ReactNode;
}

interface RailButtonProps {
  label: string;
  icon: ReactNode;
  active?: boolean;
  disabled?: boolean;
  onClick: () => void;
}

function RailButton({ label, icon, active, disabled, onClick }: RailButtonProps) {
  return (
    <Tooltip content={label} placement="right">
      <button
        onClick={onClick}
        disabled={disabled}
        aria-label={label}
        className={clsx(
          "flex size-9 items-center justify-center rounded-[10px] transition-colors",
          active
            ? "bg-stone-200/80 text-stone-900 dark:bg-stone-700/60 dark:text-stone-100"
            : "text-stone-500 hover:bg-stone-200/60 hover:text-stone-800 dark:text-stone-400 dark:hover:bg-stone-700/40 dark:hover:text-stone-100",
          disabled && "opacity-40",
        )}
      >
        {icon}
      </button>
    </Tooltip>
  );
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
  workspaceSelection,
  onNewSession,
  onShowProfile,
  children,
}: DesktopSidebarShellProps) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { user, hasPermission } = useAuth();
  const [view, setView] = useState<DesktopSidebarView>(readStoredView);
  const canReadScheduledTasks = hasPermission(Permission.SCHEDULED_TASK_READ);

  useDesktopShellShortcuts(collapsed, onToggleCollapsed, navigate);

  const switchView = useCallback((next: DesktopSidebarView) => {
    setView(next);
    try {
      localStorage.setItem(VIEW_STORAGE_KEY, next);
    } catch {
      /* 私密模式等场景静默 */
    }
    // 从折叠态点视图图标 = 同时展开二级面板
    onToggleCollapsed(false);
  }, [onToggleCollapsed]);

  const openSearch = useCallback(() => {
    window.dispatchEvent(new CustomEvent(DESKTOP_SIDEBAR_OPEN_SEARCH_EVENT));
  }, []);

  const title =
    view === "chat"
      ? t("workspacePanel.viewChats", { defaultValue: "会话" })
      : t("workspacePanel.title", { defaultValue: "工作区" });

  return (
    <div className="hidden sm:flex h-full shrink-0">
      {/* ActivityRail */}
      <div className="flex h-full w-[3.25rem] flex-col items-center gap-1 border-r border-stone-300/70 py-2 dark:border-stone-800/60">
        <RailButton
          label={t("workspacePanel.viewChats", { defaultValue: "会话" })}
          icon={<MessagesSquare size={19} />}
          active={!collapsed && view === "chat"}
          onClick={() => (collapsed || view !== "chat" ? switchView("chat") : onToggleCollapsed(true))}
        />
        <RailButton
          label={t("workspacePanel.title", { defaultValue: "工作区" })}
          icon={<FolderTree size={19} />}
          active={!collapsed && view === "files"}
          onClick={() => (collapsed || view !== "files" ? switchView("files") : onToggleCollapsed(true))}
        />

        <div className="my-1.5 h-px w-5 bg-stone-300/70 dark:bg-stone-700/70" />

        <RailButton
          label={t("sidebar.newChat")}
          icon={<MessageSquarePlus size={19} />}
          onClick={onNewSession}
        />
        <RailButton
          label={t("sidebar.searchSessions")}
          icon={<Search size={19} />}
          onClick={openSearch}
        />
        <RailButton
          label={t("fileLibrary.title")}
          icon={<FolderOpen size={19} />}
          active={false}
          onClick={() => navigate("/files")}
        />
        {canReadScheduledTasks && (
          <RailButton
            label={t("nav.scheduled-tasks")}
            icon={<CalendarClock size={19} />}
            onClick={() => navigate("/scheduled-tasks")}
          />
        )}

        <div className="flex-1" />

        <RailButton
          label={t("workspacePanel.settings", { defaultValue: "设置" })}
          icon={<Settings size={19} />}
          onClick={() => navigate("/settings")}
        />
        <Tooltip content={user?.username || t("workspacePanel.account", { defaultValue: "账号" })} placement="right">
          <button
            onClick={onShowProfile}
            aria-label={t("workspacePanel.account", { defaultValue: "账号" })}
            className="mt-0.5 flex size-9 items-center justify-center overflow-hidden rounded-full transition-colors hover:bg-stone-200/60 dark:hover:bg-stone-700/40"
          >
            {user?.avatar_url ? (
              <img
                src={user.avatar_url}
                alt={user.username || "avatar"}
                className="size-7 rounded-full object-cover"
              />
            ) : (
              <span className="flex size-7 items-center justify-center rounded-full bg-stone-300 text-12 font-medium text-stone-700 dark:bg-stone-600 dark:text-stone-200">
                {(user?.username || "?").slice(0, 1).toUpperCase()}
              </span>
            )}
          </button>
        </Tooltip>
      </div>

      {/* 二级面板（折叠时收零；chat/files 内容都常驻挂载保状态，仅切显隐） */}
      <div
        className="relative h-full shrink-0 overflow-hidden transition-[width] duration-150 ease-in-out"
        style={{ width: collapsed ? 0 : "var(--sidebar-width)" }}
      >
        {/* 面板头：当前视图名 + 折叠开关 */}
        <div className="absolute inset-0 flex flex-col">
          <div className="flex h-9 shrink-0 items-center justify-between border-b border-stone-300/60 px-2 dark:border-stone-800/50">
            <span className="truncate px-1 text-12 font-medium text-stone-500 dark:text-stone-400">
              {title}
            </span>
            <Tooltip content={t("sidebar.collapseSidebar")}>
              <button
                onClick={() => onToggleCollapsed(true)}
                className="flex size-7 items-center justify-center rounded-lg text-stone-500 hover:bg-stone-200/60 dark:text-stone-400 dark:hover:bg-stone-700/40 transition-colors"
                aria-label={t("sidebar.collapseSidebar")}
              >
                <PanelLeftClose size={15} />
              </button>
            </Tooltip>
          </div>
          <div className="flex min-h-0 flex-1 flex-col">
            <div className={clsx("min-h-0 flex-1", view === "chat" ? (collapsed ? "hidden" : "flex") : "hidden")}>
              <div className="min-h-0 w-full flex-1">{children}</div>
            </div>
            <div className={clsx("min-h-0 flex-1", view === "files" && !collapsed ? "flex" : "hidden")}>
              <div className="min-h-0 w-full flex-1">
                <WorkspacePanel
                  sessionId={sessionId ?? null}
                  workspaceSelection={workspaceSelection}
                />
              </div>
            </div>
          </div>
        </div>

        {/* 折叠态：面板头剩一个展开按钮贴 rail 右侧 */}
        {collapsed && (
          <div className="absolute inset-0 flex items-start justify-start pt-1.5 pl-1">
            <Tooltip content={t("sidebar.expandSidebar")} placement="right">
              <button
                onClick={() => onToggleCollapsed(false)}
                className="flex size-7 items-center justify-center rounded-lg text-stone-500 hover:bg-stone-200/60 dark:text-stone-400 dark:hover:bg-stone-700/40 transition-colors"
                aria-label={t("sidebar.expandSidebar")}
              >
                <PanelLeftOpen size={15} />
              </button>
            </Tooltip>
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
