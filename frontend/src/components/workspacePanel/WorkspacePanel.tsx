/** 会话右侧工作区：按需浏览本地/云端文件，复用文档预览。 */

import {
  useContext,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import { createPortal } from "react-dom";
import { useTranslation } from "react-i18next";
import {
  ChevronRight,
  Cloud,
  Copy,
  FolderClosed,
  FolderOpen,
  HardDrive,
  Loader2,
  RefreshCw,
} from "lucide-react";
import clsx from "clsx";
import { ToolbarIconButton } from "../common/ui/ToolbarIconButton";
import { Tooltip } from "../common/Tooltip";
import { activateRightPanelByKey } from "../common/rightPanelCoordinator";
import { RightPanelActiveContext } from "../common/useRightPanelEntry";
import {
  closeRevealPreviewTab,
  getRevealPreviewTabs,
  setActiveRevealPreviewState,
} from "../chat/ChatMessage/items/activeRevealPreviewStore";
import { createActiveRevealPreviewState } from "../chat/ChatMessage/items/revealPreviewState";
import { getFileTypeInfo } from "../documents/utils";
import { useSandboxStatus } from "../../hooks/useSandboxStatus";
import {
  useWorkspaceTree,
  type WorkspaceTreeNode,
} from "../../hooks/useWorkspaceTree";
import {
  sandboxCloudFsApi,
  sandboxFsApi,
  sandboxFsCloudStatusApi,
  type SandboxCloudStatus,
} from "../../services/api/sandboxFs";
import {
  isShellAvailable,
  revealWorkspacePath,
} from "../../services/tauri/sandboxShell";
import { parseWorkspaceSelection } from "../chat/workspaceSelection";
import { copyToClipboard } from "../../utils/clipboard";

interface WorkspacePanelProps {
  sessionId: string | null;
  /** 会话沙箱模式（agent_options.sandbox，"local" | "cloud"）。 */
  sandboxMode?: string | null;
  /** 会话 sandbox_machine_id（未显式选机器时空）。 */
  machineId?: string | null;
  /** 会话 sandbox_workspace 的原样 JSON（reveal 用，Rust 侧与绑定文件比对）。 */
  workspaceSelection?: string | null;
  /** Render controls beside the shell title; undefined retains the standalone toolbar. */
  headerActionsTarget?: HTMLElement | null;
}

interface ContextMenuState {
  x: number;
  y: number;
  path: string;
}

export function WorkspacePanel({
  sessionId,
  sandboxMode,
  machineId,
  workspaceSelection,
  headerActionsTarget,
}: WorkspacePanelProps) {
  const { t } = useTranslation();
  const active = useContext(RightPanelActiveContext);
  const { machines, currentMachineId, defaultMachineId, online } =
    useSandboxStatus();

  // Match the conversation default; a stale panel preference must not choose its backend.
  const view = sandboxMode === "local" ? "local" : "cloud";
  const isCloudView = view === "cloud";

  // ── 本地视图的目标机与 reveal 资格（对齐 SessionWorkspaceBar）──
  const onlineMachines = machines.filter((item) => item.online);
  const selection = parseWorkspaceSelection(workspaceSelection);
  const selectedMachineId =
    machineId ||
    defaultMachineId ||
    (onlineMachines.length === 1 ? onlineMachines[0].machine_id : "");
  const isLocalMachineWorkspace =
    !isCloudView &&
    online &&
    !!currentMachineId &&
    selectedMachineId === currentMachineId;

  // ── 云端视图状态徽标（零副作用速览，不唤醒沙箱）──
  const [cloudStatus, setCloudStatus] = useState<SandboxCloudStatus | null>(
    null,
  );
  const [cloudStatusLoading, setCloudStatusLoading] = useState(false);
  const cloudRequest = useRef(0);
  const refreshCloudStatus = useCallback(async () => {
    if (!sessionId) return;
    const request = ++cloudRequest.current;
    setCloudStatusLoading(true);
    try {
      const status = await sandboxFsCloudStatusApi.status(sessionId);
      if (request === cloudRequest.current) setCloudStatus(status);
    } catch {
      if (request === cloudRequest.current) setCloudStatus(null);
    } finally {
      if (request === cloudRequest.current) setCloudStatusLoading(false);
    }
  }, [sessionId]);
  useEffect(() => {
    if (!isCloudView || !sessionId) {
      setCloudStatus(null);
      return undefined;
    }
    if (!active) return;
    void refreshCloudStatus();
    // 30s 对账：暂停/回收后徽标及时转黄（status 零副作用，不唤醒沙箱）
    const timer = window.setInterval(() => void refreshCloudStatus(), 30_000);
    return () => {
      cloudRequest.current += 1;
      window.clearInterval(timer);
    };
  }, [active, isCloudView, sessionId, refreshCloudStatus]);

  // 云端可浏览：已创建（running/paused——浏览即唤醒）；未创建/未启用显示空态
  const cloudBrowsable =
    cloudStatus?.state === "running" ||
    cloudStatus?.state === "paused" ||
    // status 尚未返回时也放行（错误态兜底；404/410 由错误文案引导）
    cloudStatus === null;

  // ── 文件树：数据源随视图切换，重置键覆盖全部上下文 ──
  const source = isCloudView ? sandboxCloudFsApi : sandboxFsApi;
  const effectiveSessionId = isCloudView
    ? sessionId && cloudBrowsable
      ? sessionId
      : null
    : online && sandboxMode !== "cloud"
      ? sessionId
      : null;
  const resetKey = `${sessionId ?? ""}|${view}|${
    isCloudView
      ? "cloud"
      : `${sandboxMode ?? ""}|${selectedMachineId}|${selection?.id ?? ""}`
  }`;
  const { root, state, error, toggleDir, refresh, expandedPaths } =
    useWorkspaceTree(effectiveSessionId, resetKey, source);

  const previewPrefix = `workspace:${JSON.stringify([
    resetKey,
    workspaceSelection,
  ])}:`;
  const [openingPath, setOpeningPath] = useState<string | null>(null);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const previewRequest = useRef(0);
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    previewRequest.current += 1;
    for (const tab of getRevealPreviewTabs()) {
      const key = tab.request.previewKey;
      if (key.startsWith("workspace:") && !key.startsWith(previewPrefix))
        closeRevealPreviewTab(key);
    }
    setPreviewError(null);
    setOpeningPath(null);
    setContextMenu(null);
    return () => {
      previewRequest.current += 1;
    };
  }, [previewPrefix]);

  useEffect(() => {
    if (!contextMenu) return undefined;
    const close = () => setContextMenu(null);
    const keydown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        close();
      }
    };
    document.addEventListener("keydown", keydown, true);
    // click 在菜单项 onClick 冒泡后到达，下一拍再挂避免立即自关闭
    const timer = window.setTimeout(() => {
      document.addEventListener("click", close);
      document.addEventListener("contextmenu", close);
    }, 0);
    return () => {
      document.removeEventListener("keydown", keydown, true);
      window.clearTimeout(timer);
      document.removeEventListener("click", close);
      document.removeEventListener("contextmenu", close);
    };
  }, [contextMenu]);

  const openFile = useCallback(
    async (path: string) => {
      if (!sessionId) return;
      const previewKey = `${previewPrefix}${path}`;
      if (
        getRevealPreviewTabs().some(
          (tab) => tab.request.previewKey === previewKey,
        )
      ) {
        activateRightPanelByKey(`reveal-preview:${previewKey}`);
        return;
      }
      const request = ++previewRequest.current;
      setOpeningPath(path);
      setPreviewError(null);
      try {
        const result = await source.read(sessionId, path, 0, 2000);
        if (request !== previewRequest.current) return;
        if (result.error) throw new Error(result.error);
        if (result.encoding === "utf-8" || result.encoding === "base64") {
          // Binary reads keep the existing placeholder until a URL channel is available.
          const content =
            result.encoding === "utf-8"
              ? result.content ?? ""
              : t("workspacePanel.binaryFileHint", {
                  defaultValue: "（二进制文件，暂不支持内联预览）",
                });
          setActiveRevealPreviewState(
            createActiveRevealPreviewState(
              {
                kind: "file",
                previewKey,
                filePath: path,
                content,
              },
              "manual",
            ),
          );
        }
      } catch {
        if (request === previewRequest.current)
          setPreviewError(t("documents.error"));
      } finally {
        if (request === previewRequest.current) setOpeningPath(null);
      }
    },
    [sessionId, source, t, previewPrefix],
  );

  const handleContextMenu = useCallback(
    (event: React.MouseEvent, path: string) => {
      event.preventDefault();
      event.stopPropagation();
      setContextMenu({
        x: Math.max(8, Math.min(event.clientX, window.innerWidth - 240)),
        y: Math.max(8, Math.min(event.clientY, window.innerHeight - 100)),
        path,
      });
    },
    [],
  );

  const handleReveal = useCallback(
    async (relPath: string) => {
      if (!sessionId || isCloudView) return;
      try {
        await revealWorkspacePath(
          sessionId,
          relPath,
          workspaceSelection,
          selectedMachineId,
        );
      } catch {
        setPreviewError(t("sessionWorkspace.failed"));
      }
    },
    [sessionId, isCloudView, workspaceSelection, selectedMachineId, t],
  );

  const handleRefresh = useCallback(() => {
    if (isCloudView) {
      void refreshCloudStatus();
    }
    refresh();
  }, [isCloudView, refreshCloudStatus, refresh]);

  const renderNodes = (nodes: WorkspaceTreeNode[], depth: number) =>
    nodes.map((node) => {
      const padding = 6 + depth * 12;
      if (node.isDir) {
        const expanded = expandedPaths.has(node.path);
        return (
          <div key={node.path}>
            <button
              onClick={() => toggleDir(node.path)}
              aria-expanded={expanded}
              title={node.path}
              className="sidebar-nav-btn w-full min-h-11 sm:min-h-8 rounded-md flex items-center gap-1.5 pr-2 transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--theme-ring)]"
              style={{ paddingLeft: padding }}
            >
              <ChevronRight
                size={13}
                className={clsx(
                  "shrink-0 text-theme-text-muted transition-transform duration-150 motion-reduce:transition-none",
                  expanded && "rotate-90",
                )}
              />
              {node.loading ? (
                <Loader2
                  size={15}
                  className="shrink-0 animate-spin text-theme-text-tertiary"
                />
              ) : expanded ? (
                <FolderOpen size={15} className="shrink-0 text-theme-text-secondary" />
              ) : (
                <FolderClosed size={15} className="shrink-0 text-theme-text-secondary" />
              )}
              <span className="truncate text-13 text-left">{node.name}</span>
            </button>
            {expanded && node.children && renderNodes(node.children, depth + 1)}
          </div>
        );
      }
      const info = getFileTypeInfo(node.name);
      const Icon = info.icon;
      const isLoading = openingPath === node.path;
      return (
        <button
          key={node.path}
          onClick={() => void openFile(node.path)}
          title={node.path}
          aria-busy={isLoading}
          onContextMenu={(e) => handleContextMenu(e, node.path)}
          className="sidebar-nav-btn w-full min-h-11 sm:min-h-8 rounded-md flex items-center gap-1.5 pr-2 transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--theme-ring)]"
          style={{ paddingLeft: padding + 13 + 6 }}
        >
          {isLoading ? (
            <Loader2
              size={15}
              className="shrink-0 animate-spin text-theme-text-tertiary"
            />
          ) : (
            <Icon
              size={15}
              className="shrink-0"
              style={{ color: info.color }}
            />
          )}
          <span className="truncate text-13 text-left">{node.name}</span>
        </button>
      );
    });

  // 云端状态徽标（云端视图头部）：running 绿 / paused 黄（打开时自动唤醒）
  const cloudStateBadge = useMemo(() => {
    if (!isCloudView || cloudStatusLoading) return null;
    const stateValue = cloudStatus?.state;
    if (stateValue === "running") {
      return (
        <Tooltip
          content={t("workspacePanel.cloudRunning", {
            defaultValue: "云端电脑 · 运行中",
          })}
        >
          <span className="size-1.5 rounded-full bg-theme-success" />
        </Tooltip>
      );
    }
    if (stateValue === "paused") {
      return (
        <Tooltip
          content={t("workspacePanel.cloudPaused", {
            defaultValue: "云端电脑 · 已暂停，打开时自动唤醒",
          })}
        >
          <span className="size-1.5 rounded-full bg-amber-500" />
        </Tooltip>
      );
    }
    return null;
  }, [isCloudView, cloudStatusLoading, cloudStatus, t]);

  // 云端视图空态文案
  const cloudEmptyHint = useMemo(() => {
    if (cloudStatus?.state === "not_created") {
      return t("workspacePanel.cloudNotCreated", {
        defaultValue: "云端电脑尚未创建；在云端会话中发送消息后会自动创建",
      });
    }
    if (cloudStatus?.state === "disabled") {
      return t("workspacePanel.cloudDisabled", {
        defaultValue: "云端沙箱未启用",
      });
    }
    return null;
  }, [cloudStatus, t]);

  const localViewBlocked = !isCloudView && (!online || !sessionId);
  const toolbar = (
    <div className="flex items-center gap-1.5">
      {cloudStateBadge}
      <ToolbarIconButton
        variant="muted"
        onClick={handleRefresh}
        disabled={state === "loading" || cloudStatusLoading}
        className="disabled:opacity-40"
        aria-label={t("workspacePanel.refresh", { defaultValue: "刷新" })}
        title={t("workspacePanel.refresh", { defaultValue: "刷新" })}
        icon={
          <RefreshCw
            size={16}
            className={
              state === "loading" || cloudStatusLoading
                ? "animate-spin motion-reduce:animate-none"
                : ""
            }
          />
        }
      />
    </div>
  );

  return (
    <div className="flex h-full min-h-0 flex-col bg-theme-bg text-theme-text">
      {headerActionsTarget
        ? createPortal(toolbar, headerActionsTarget)
        : headerActionsTarget === undefined && (
            <div className="flex shrink-0 justify-end border-b border-theme-border px-2 py-1">
              {toolbar}
            </div>
          )}

      {!isCloudView && selection && (
        <div
          className="shrink-0 truncate border-b border-theme-border px-3 py-2 text-12 text-theme-text-secondary"
          title={selection.path}
        >
          {selection.path}
        </div>
      )}
      {previewError && (
        <p
          role="alert"
          className="shrink-0 px-3 py-2 text-12 text-theme-text-secondary"
        >
          {previewError}
        </p>
      )}

      {/* 本地视图状态区 */}
      {!isCloudView ? (
        !online ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center">
            <HardDrive size={22} className="text-theme-text-tertiary" />
            <p className="text-12 text-theme-text-secondary dark:text-stone-400">
              {t("workspacePanel.daemonOffline", {
                defaultValue: "本地沙箱未连接，无法浏览工作区文件",
              })}
            </p>
          </div>
        ) : !sessionId ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center">
            <p className="text-12 text-theme-text-secondary dark:text-stone-400">
              {t("workspacePanel.noSession", {
                defaultValue: "打开一个会话后即可浏览其工作区文件",
              })}
            </p>
          </div>
        ) : null
      ) : null}

      {/* 云端视图空态（未创建/未启用）；会话缺省提示两视图共用 */}
      {isCloudView && cloudEmptyHint ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center">
          <Cloud size={22} className="text-theme-text-tertiary" />
          <p className="text-12 text-theme-text-secondary dark:text-stone-400">
            {cloudEmptyHint}
          </p>
        </div>
      ) : isCloudView && !sessionId ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center">
          <p className="text-12 text-theme-text-secondary dark:text-stone-400">
            {t("workspacePanel.noSession", {
              defaultValue: "打开一个会话后即可浏览其工作区文件",
            })}
          </p>
        </div>
      ) : null}

      {/* 文件树（本地/云端共用） */}
      {!localViewBlocked &&
      !(isCloudView && cloudEmptyHint) &&
      !(isCloudView && !sessionId) ? (
        state === "error" ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center">
            <p className="text-12 text-theme-text-secondary dark:text-stone-400">
              {error}
            </p>
            <button
              onClick={handleRefresh}
              className="text-12 text-theme-text-secondary hover:underline dark:text-stone-300"
            >
              {t("workspacePanel.retry", { defaultValue: "重试" })}
            </button>
          </div>
        ) : (
          <div className="min-h-0 flex-1 overflow-y-auto p-2">
            {state === "loading" && root.length === 0 ? (
              <div className="flex items-center justify-center pt-6">
                <Loader2 size={16} className="animate-spin text-theme-text-tertiary" />
              </div>
            ) : root.length === 0 ? (
              state === "idle" ? null : (
                <p className="pt-4 text-center text-12 text-theme-text-secondary dark:text-stone-400">
                  {t("workspacePanel.emptyDir", { defaultValue: "空工作区" })}
                </p>
              )
            ) : (
              <div className="flex flex-col gap-px">{renderNodes(root, 0)}</div>
            )}
          </div>
        )
      ) : null}

      {/* 右键菜单（复制路径 / 在系统文件管理器中显示——仅本地视图本机工作区） */}
      {contextMenu && (
        <div
          ref={menuRef}
          className="fixed z-[350] w-56 overflow-hidden rounded-lg border border-theme-border bg-theme-bg-card py-1 shadow-lg dark:border-stone-700 dark:bg-stone-800"
          style={{ left: contextMenu.x, top: contextMenu.y }}
        >
          <button
            onClick={() => {
              void copyToClipboard(contextMenu.path);
              setContextMenu(null);
            }}
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-13 text-theme-text hover:bg-theme-bg-subtle dark:text-stone-200 dark:hover:bg-stone-700/60"
          >
            <Copy size={14} />
            {t("workspacePanel.copyPath", { defaultValue: "复制路径" })}
          </button>
          {isShellAvailable() && isLocalMachineWorkspace && (
            <button
              onClick={() => {
                void handleReveal(contextMenu.path);
                setContextMenu(null);
              }}
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-13 text-theme-text hover:bg-theme-bg-subtle dark:text-stone-200 dark:hover:bg-stone-700/60"
            >
              <FolderOpen size={14} />
              {t("workspacePanel.revealInFileManager", {
                defaultValue: "在文件管理器中显示",
              })}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
