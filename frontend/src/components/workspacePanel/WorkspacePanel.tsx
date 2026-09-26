/**
 * 工作区文件面板（桌面双栏的「文件」二级面板）。
 *
 * 数据源是本地沙箱 daemon（经 /api/sandbox/fs 中继）：实时列目录、懒加载、
 * run 结束后可手动刷新。文件点击走 fs/read 文本预览（复用 documents 预览
 * 层的代码高亮）；二进制文件给出占位提示。右键菜单提供复制路径与
 * 「在 Finder/资源管理器中显示」（Tauri 壳内）。
 */

import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  ChevronRight,
  Copy,
  FolderClosed,
  FolderOpen,
  HardDrive,
  Loader2,
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
import { sandboxFsApi } from "../../services/api/sandboxFs";
import {
  isShellAvailable,
  revealWorkspacePath,
} from "../../services/tauri/sandboxShell";
import { copyToClipboard } from "../../utils/clipboard";

interface WorkspacePanelProps {
  sessionId: string | null;
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

export function WorkspacePanel({ sessionId, workspaceSelection }: WorkspacePanelProps) {
  const { t } = useTranslation();
  const { online } = useSandboxStatus();
  // daemon 离线时置 null：树整体回到 idle，不发起注定失败的中继请求
  const effectiveSessionId = online ? sessionId : null;
  const { root, state, error, toggleDir, refresh, expandedPaths } =
    useWorkspaceTree(effectiveSessionId);
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
        const result = await sandboxFsApi.read(sessionId, path, 0, 2000);
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
    [sessionId, t],
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
      if (!sessionId) return;
      await revealWorkspacePath(sessionId, relPath, workspaceSelection);
    },
    [sessionId, workspaceSelection],
  );

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

  return (
    <div className="flex h-full flex-col bg-[var(--theme-bg-sidebar)]">
      {/* 面板头 */}
      <div className="flex items-center justify-between px-3 pt-3 pb-2">
        <div className="flex items-center gap-1.5">
          <HardDrive size={15} className="text-stone-500" />
          <span className="text-13 font-medium text-[var(--theme-text-secondary)]">
            {t("workspacePanel.title", { defaultValue: "工作区" })}
          </span>
        </div>
        <Tooltip content={t("workspacePanel.refresh", { defaultValue: "刷新" })}>
          <button
            onClick={refresh}
            disabled={!online || state === "loading"}
            className="flex size-7 items-center justify-center rounded-lg text-stone-500 hover:bg-stone-200/60 dark:text-stone-400 dark:hover:bg-stone-700/40 transition-colors disabled:opacity-40"
            aria-label={t("workspacePanel.refresh", { defaultValue: "刷新" })}
          >
            <RefreshCw size={14} className={state === "loading" ? "animate-spin" : ""} />
          </button>
        </Tooltip>
      </div>

      {/* 状态区 */}
      {!online ? (
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
      ) : state === "error" ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-2 px-6 text-center">
          <p className="text-12 text-stone-500 dark:text-stone-400">{error}</p>
          <button
            onClick={refresh}
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
            <p className="pt-4 text-center text-12 text-stone-500 dark:text-stone-400">
              {t("workspacePanel.emptyDir", { defaultValue: "空工作区" })}
            </p>
          ) : (
            <div className="flex flex-col gap-px">{renderNodes(root, 0)}</div>
          )}
        </div>
      )}

      {/* 文本预览（右侧 dock 面板，复用 documents 预览层） */}
      {preview && (
        <LazyDocumentPreview
          path={preview.path}
          content={preview.content}
          onClose={() => setPreview(null)}
          registryKey={`workspace-preview-${preview.path}`}
        />
      )}

      {/* 右键菜单（复制路径 / 在系统文件管理器中显示） */}
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
          {isShellAvailable() && (
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
