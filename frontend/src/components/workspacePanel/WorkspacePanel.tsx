/**
 * 电脑面板（桌面双栏的「电脑」二级面板）——豆包式双视图：
 *
 *   [本地电脑] 本地沙箱 daemon（经 /api/sandbox/fs 中继），实时列目录、
 *              懒加载、文本预览、右键复制路径 / 在文件管理器中显示；
 *   [云端电脑] 云端沙箱（E2B/Daytona SDK 直连，/api/sandbox/fs/cloud/*），
 *              状态徽标（运行中/已暂停/未创建/未启用）+ 同款文件树；
 *              浏览即意图——paused 沙箱在首次列目录时自动唤醒，未创建/
 *              被回收不新建，给引导文案。
 *
 * 视图默认跟随会话当前平台，用户可手动切换（本地会话也能看它的云端子
 * 目录）；会话切换时回到跟随。任一上下文变化（会话/平台/机器/绑定/视图）
 * 整树重置，杜绝 stale 文件。
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  ChevronRight,
  Cloud,
  Copy,
  FolderClosed,
  FolderOpen,
  HardDrive,
  Loader2,
  Monitor,
  RefreshCw,
} from "lucide-react";
import clsx from "clsx";
import { Tooltip } from "../common/Tooltip";
import { LazyDocumentPreview } from "../documents/LazyDocumentPreview";
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

type WorkspaceView = "local" | "cloud";

const VIEW_STORAGE_KEY = "lambchat_workspace_view";

interface WorkspacePanelProps {
  sessionId: string | null;
  /** 会话沙箱模式（agent_options.sandbox，"local" | "cloud"）。 */
  sandboxMode?: string | null;
  /** 会话 sandbox_machine_id（未显式选机器时空）。 */
  machineId?: string | null;
  /** 会话 sandbox_workspace 的原样 JSON（reveal 用，Rust 侧与绑定文件比对）。 */
  workspaceSelection?: string | null;
}

interface PendingPreview {
  path: string;
  content: string;
}

interface ContextMenuState {
  x: number;
  y: number;
  path: string;
}

function readStoredView(): WorkspaceView {
  try {
    return localStorage.getItem(VIEW_STORAGE_KEY) === "cloud" ? "cloud" : "local";
  } catch {
    return "local";
  }
}

export function WorkspacePanel({
  sessionId,
  sandboxMode,
  machineId,
  workspaceSelection,
}: WorkspacePanelProps) {
  const { t } = useTranslation();
  const { machines, currentMachineId, defaultMachineId, online } = useSandboxStatus();

  // ── 视图：默认跟随会话平台，会话切换时回归跟随；用户手选持久化 ──
  const [view, setView] = useState<WorkspaceView>(() =>
    sandboxMode === "cloud" ? "cloud" : readStoredView(),
  );
  const sessionRef = useRef(sessionId);
  useEffect(() => {
    if (sessionRef.current !== sessionId) {
      sessionRef.current = sessionId;
      setView(sandboxMode === "cloud" ? "cloud" : "local");
    }
  }, [sessionId, sandboxMode]);
  const switchView = useCallback((next: WorkspaceView) => {
    setView(next);
    try {
      localStorage.setItem(VIEW_STORAGE_KEY, String(next));
    } catch {
      /* 私密模式等场景静默 */
    }
  }, []);

  const isCloudView = view === "cloud";

  // ── 本地视图的目标机与 reveal 资格（对齐 SessionWorkspaceBar）──
  const onlineMachines = machines.filter((item) => item.online);
  const selection = parseWorkspaceSelection(workspaceSelection);
  const selectedMachineId =
    machineId || defaultMachineId || (onlineMachines.length === 1 ? onlineMachines[0].machine_id : "");
  const isLocalMachineWorkspace =
    !isCloudView && online && !!currentMachineId && selectedMachineId === currentMachineId;

  // ── 云端视图状态徽标（零副作用速览，不唤醒沙箱）──
  const [cloudStatus, setCloudStatus] = useState<SandboxCloudStatus | null>(null);
  const [cloudStatusLoading, setCloudStatusLoading] = useState(false);
  const refreshCloudStatus = useCallback(async () => {
    if (!sessionId) return;
    setCloudStatusLoading(true);
    try {
      setCloudStatus(await sandboxFsCloudStatusApi.status(sessionId));
    } catch {
      setCloudStatus(null);
    } finally {
      setCloudStatusLoading(false);
    }
  }, [sessionId]);
  useEffect(() => {
    if (!isCloudView || !sessionId) {
      setCloudStatus(null);
      return undefined;
    }
    void refreshCloudStatus();
  }, [isCloudView, sessionId, refreshCloudStatus]);

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
  const resetKey = `${sessionId ?? ""}|${view}|${isCloudView ? (cloudStatus?.state ?? "") : `${sandboxMode ?? ""}|${selectedMachineId}|${selection?.id ?? ""}`}`;
  const { root, state, error, toggleDir, refresh, expandedPaths } = useWorkspaceTree(
    effectiveSessionId,
    resetKey,
    source,
  );

  const [preview, setPreview] = useState<PendingPreview | null>(null);
  const [openingPath, setOpeningPath] = useState<string | null>(null);
  const [contextMenu, setContextMenu] = useState<ContextMenuState | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!contextMenu) return undefined;
    const close = () => setContextMenu(null);
    // click 在菜单项 onClick 冒泡后到达，下一拍再挂避免立即自关闭
    const timer = window.setTimeout(() => {
      document.addEventListener("click", close);
      document.addEventListener("contextmenu", close);
    }, 0);
    return () => {
      window.clearTimeout(timer);
      document.removeEventListener("click", close);
      document.removeEventListener("contextmenu", close);
    };
  }, [contextMenu]);

  const openFile = useCallback(
    async (path: string) => {
      if (!sessionId) return;
      setOpeningPath(path);
      try {
        const result = await source.read(sessionId, path, 0, 2000);
        if (result.encoding === "utf-8") {
          setPreview({ path, content: result.content ?? "" });
        } else if (result.encoding === "base64") {
          // 二进制：documents 预览层需要 URL 通道，本轮给占位（路径操作仍可用）
          setPreview({
            path,
            content: t("workspacePanel.binaryFileHint", {
              defaultValue: "（二进制文件，暂不支持内联预览）",
            }),
          });
        }
        // 文件级错误（file_not_found 等）：静默失败——树刷新后节点自然消失
      } catch {
        // 中继失败：预览不弹，交由整体错误态/用户重试
      } finally {
        setOpeningPath(null);
      }
    },
    [sessionId, source, t],
  );

  const handleContextMenu = useCallback(
    (event: React.MouseEvent, path: string) => {
      event.preventDefault();
      event.stopPropagation();
      setContextMenu({ x: event.clientX, y: event.clientY, path });
    },
    [],
  );

  const handleReveal = useCallback(
    async (relPath: string) => {
      if (!sessionId || isCloudView) return;
      await revealWorkspacePath(sessionId, relPath, workspaceSelection, selectedMachineId);
    },
    [sessionId, isCloudView, workspaceSelection, selectedMachineId],
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
              className="sidebar-nav-btn w-full h-7 rounded-[8px] flex items-center gap-1.5 pr-2 transition-colors"
              style={{ paddingLeft: padding }}
            >
              <ChevronRight
                size={13}
                className={clsx(
                  "shrink-0 text-stone-400 transition-transform duration-150",
                  expanded && "rotate-90",
                )}
              />
              {node.loading ? (
                <Loader2 size={15} className="shrink-0 animate-spin text-stone-400" />
              ) : expanded ? (
                <FolderOpen size={15} className="shrink-0 text-stone-500" />
              ) : (
                <FolderClosed size={15} className="shrink-0 text-stone-500" />
              )}
              <span className="truncate text-13 text-left">{node.name}</span>
            </button>
            {expanded &&
              node.children &&
              renderNodes(node.children, depth + 1)}
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
          onContextMenu={(e) => handleContextMenu(e, node.path)}
          className="sidebar-nav-btn w-full h-7 rounded-[8px] flex items-center gap-1.5 pr-2 transition-colors"
          style={{ paddingLeft: padding + 13 + 6 }}
        >
          {isLoading ? (
            <Loader2 size={15} className="shrink-0 animate-spin text-stone-400" />
          ) : (
            <Icon size={15} className="shrink-0" style={{ color: info.color }} />
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
        <Tooltip content={t("workspacePanel.cloudRunning", { defaultValue: "云端电脑 · 运行中" })}>
          <span className="size-1.5 rounded-full bg-emerald-500" />
        </Tooltip>
      );
    }
    if (stateValue === "paused") {
      return (
        <Tooltip content={t("workspacePanel.cloudPaused", { defaultValue: "云端电脑 · 已暂停，打开时自动唤醒" })}>
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
      return t("workspacePanel.cloudDisabled", { defaultValue: "云端沙箱未启用" });
    }
    return null;
  }, [cloudStatus, t]);

  const showLocalCloudHint = !isCloudView && sandboxMode === "cloud";
  const localViewBlocked = !online || !sessionId || showLocalCloudHint;

  return (
    <div className="flex h-full flex-col bg-[var(--theme-bg-sidebar)]">
      {/* 视图切换（本地电脑 / 云端电脑）+ 刷新 */}
      <div className="flex items-center justify-between gap-1 px-2 pt-3 pb-2">
        <div className="flex items-center gap-0.5 rounded-lg bg-stone-200/60 p-0.5 dark:bg-stone-800/60">
          <button
            onClick={() => switchView("local")}
            aria-pressed={!isCloudView}
            className={clsx(
              "flex h-6 items-center gap-1 rounded-md px-2 text-12 transition-colors",
              !isCloudView
                ? "bg-white text-stone-800 shadow-sm dark:bg-stone-700 dark:text-stone-100"
                : "text-stone-500 hover:text-stone-700 dark:text-stone-400 dark:hover:text-stone-200",
            )}
          >
            <Monitor size={13} />
            {t("workspacePanel.viewLocal", { defaultValue: "本地电脑" })}
          </button>
          <button
            onClick={() => switchView("cloud")}
            aria-pressed={isCloudView}
            className={clsx(
              "flex h-6 items-center gap-1 rounded-md px-2 text-12 transition-colors",
              isCloudView
                ? "bg-white text-stone-800 shadow-sm dark:bg-stone-700 dark:text-stone-100"
                : "text-stone-500 hover:text-stone-700 dark:text-stone-400 dark:hover:text-stone-200",
            )}
          >
            <Cloud size={13} />
            {t("workspacePanel.viewCloud", { defaultValue: "云端电脑" })}
          </button>
        </div>
        <div className="flex items-center gap-1.5">
          {cloudStateBadge}
          <Tooltip content={t("workspacePanel.refresh", { defaultValue: "刷新" })}>
            <button
              onClick={handleRefresh}
              disabled={state === "loading" || cloudStatusLoading}
              className="flex size-7 items-center justify-center rounded-lg text-stone-500 hover:bg-stone-200/60 dark:text-stone-400 dark:hover:bg-stone-700/40 transition-colors disabled:opacity-40"
              aria-label={t("workspacePanel.refresh", { defaultValue: "刷新" })}
            >
              <RefreshCw
                size={14}
                className={state === "loading" || cloudStatusLoading ? "animate-spin" : ""}
              />
            </button>
          </Tooltip>
        </div>
      </div>

      {/* 本地视图状态区 */}
      {!isCloudView ? (
        showLocalCloudHint ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center">
            <Cloud size={22} className="text-stone-400" />
            <p className="text-12 text-stone-500 dark:text-stone-400">
              {t("workspacePanel.cloudSession", {
                defaultValue: "此会话使用云端沙箱，工作区文件在云端",
              })}
            </p>
            <button
              onClick={() => switchView("cloud")}
              className="text-12 text-stone-600 underline-offset-2 hover:underline dark:text-stone-300"
            >
              {t("workspacePanel.switchToCloud", { defaultValue: "查看云端电脑 →" })}
            </button>
          </div>
        ) : !online ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center">
            <HardDrive size={22} className="text-stone-400" />
            <p className="text-12 text-stone-500 dark:text-stone-400">
              {t("workspacePanel.daemonOffline", {
                defaultValue: "本地沙箱未连接，无法浏览工作区文件",
              })}
            </p>
          </div>
        ) : !sessionId ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center">
            <p className="text-12 text-stone-500 dark:text-stone-400">
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
          <Cloud size={22} className="text-stone-400" />
          <p className="text-12 text-stone-500 dark:text-stone-400">{cloudEmptyHint}</p>
        </div>
      ) : isCloudView && !sessionId ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center">
          <p className="text-12 text-stone-500 dark:text-stone-400">
            {t("workspacePanel.noSession", {
              defaultValue: "打开一个会话后即可浏览其工作区文件",
            })}
          </p>
        </div>
      ) : null}

      {/* 文件树（本地/云端共用） */}
      {!localViewBlocked && !(isCloudView && cloudEmptyHint) && !(isCloudView && !sessionId) ? (
        state === "error" ? (
          <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center">
            <p className="text-12 text-stone-500 dark:text-stone-400">{error}</p>
            <button
              onClick={handleRefresh}
              className="text-12 text-stone-600 hover:underline dark:text-stone-300"
            >
              {t("workspacePanel.retry", { defaultValue: "重试" })}
            </button>
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto px-2 pb-3 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden">
            {state === "loading" && root.length === 0 ? (
              <div className="flex items-center justify-center pt-6">
                <Loader2 size={16} className="animate-spin text-stone-400" />
              </div>
            ) : root.length === 0 ? (
              state === "idle" ? null : (
                <p className="pt-4 text-center text-12 text-stone-500 dark:text-stone-400">
                  {t("workspacePanel.emptyDir", { defaultValue: "空工作区" })}
                </p>
              )
            ) : (
              <div className="flex flex-col gap-px">{renderNodes(root, 0)}</div>
            )}
          </div>
        )
      ) : null}

      {/* 文本预览（右侧 dock 面板，复用 documents 预览层） */}
      {preview && (
        <LazyDocumentPreview
          path={preview.path}
          content={preview.content}
          onClose={() => setPreview(null)}
          registryKey={`workspace-preview-${view}-${preview.path}`}
        />
      )}

      {/* 右键菜单（复制路径 / 在系统文件管理器中显示——仅本地视图本机工作区） */}
      {contextMenu && (
        <div
          ref={menuRef}
          className="fixed z-[200] min-w-44 overflow-hidden rounded-lg border border-stone-200 bg-white py-1 shadow-lg dark:border-stone-700 dark:bg-stone-800"
          style={{ left: contextMenu.x, top: contextMenu.y }}
        >
          <button
            onClick={() => {
              void copyToClipboard(contextMenu.path);
              setContextMenu(null);
            }}
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-13 text-stone-700 hover:bg-stone-100 dark:text-stone-200 dark:hover:bg-stone-700/60"
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
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-13 text-stone-700 hover:bg-stone-100 dark:text-stone-200 dark:hover:bg-stone-700/60"
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
